"""Checkpointed visual-per-shot + audio + deterministic report pipeline."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import requests

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = Path('C:/Program Files (x86)/FormatFactory/ffmpeg.exe')
MODEL = 'qwen3.8-omni-flash'
BASE = 'https://maas.qianwenaiapi.com/compatible-mode/v1'

def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def stamp(t):
    ms = round(float(t) * 1000)
    return f'{ms // 60000:02d}:{ms // 1000 % 60:02d}.{ms % 1000:03d}'

def ffmpeg(*args):
    proc = subprocess.run([str(FFMPEG), '-hide_banner', '-nostdin', *map(str, args)], capture_output=True)
    return proc.returncode, proc.stderr.decode('utf-8', errors='replace')

def prepare(source, out):
    media = out / 'media'
    media.mkdir(exist_ok=True)
    manifest = media / 'manifest.json'
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if manifest.exists():
        result = json.loads(manifest.read_text(encoding='utf-8'))
        assert result['source_sha256'] == source_hash
        return result
    _, info = ffmpeg('-i', source)
    duration_match = re.search(r'Duration: (\d+):(\d+):(\d+\.\d+)', info)
    assert duration_match
    h, m, s = map(float, duration_match.groups())
    duration = h * 3600 + m * 60 + s
    source_fps = float(re.search(r'(\d+(?:\.\d+)?) fps', info).group(1))
    rc, cuts_log = ffmpeg('-i', source, '-vf', 'select=gt(scene\\,0.12),showinfo'.replace('\\\\', '\\'), '-an', '-f', 'null', '-')
    assert rc == 0, cuts_log[-1000:]
    cut_frames = sorted(set(round(float(v) * source_fps) for v in re.findall(r'pts_time:([0-9.]+)', cuts_log)))
    total = round(duration * source_fps)
    boundaries = [0] + [n for n in cut_frames if 0 < n < total] + [total]
    images = media / 'frames'
    images.mkdir(exist_ok=True)
    rc, log = ffmpeg('-loglevel', 'error', '-i', source, '-vf', 'scale=960:-1', '-vsync', '0', '-start_number', '0', '-q:v', '3', '-y', images / 'frame_%06d.jpg')
    assert rc == 0, log
    extracted = sorted(images.glob('frame_*.jpg'))
    assert len(extracted) == total, (len(extracted), total)
    rc, log = ffmpeg('-loglevel', 'error', '-i', source, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', '-y', media / 'audio.wav')
    assert rc == 0, log
    stride = max(1, round(source_fps / 10))
    shots = []
    for i, (start, end) in enumerate(zip(boundaries, boundaries[1:]), 1):
        indices = sorted(set([start, end - 1] + list(range(start, end, stride))))
        shots.append({'shot': f'S{i:02d}', 'start': start / source_fps, 'end': end / source_fps,
                      'frames': [{'index': n, 'time': n / source_fps, 'file': f'frame_{n:06d}.jpg'} for n in indices]})
    result = {'source': str(source), 'source_sha256': source_hash, 'duration': duration, 'source_fps': source_fps,
              'scene_threshold': 0.12, 'detected_cut_seconds': [n / source_fps for n in cut_frames],
              'local_sampling_fps': source_fps / stride, 'shots': shots}
    dump(manifest, result)
    return result

def parse_json(text):
    clean = text.strip()
    if clean.startswith('```'):
        clean = re.sub(r'^```(?:json)?\s*|\s*```$', '', clean)
    return json.loads(clean)

def call_stage(name, prompt, parts, key, out, thinking, state):
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    result_path = out / (name + '.json')
    meta_path = out / (name + '_metadata.json')
    if result_path.exists() and meta_path.exists():
        metadata = json.loads(meta_path.read_text(encoding='utf-8'))
        if metadata.get('prompt_sha256') == prompt_hash and metadata.get('status') == 'complete':
            state[name] = 'cached'
            return json.loads(result_path.read_text(encoding='utf-8'))
        raise RuntimeError('Checkpoint does not match prompt: ' + name)
    (out / (name + '_prompt.txt')).write_text(prompt, encoding='utf-8')
    start = time.monotonic()
    metadata = {'stage': name, 'model': MODEL, 'base_url': BASE, 'prompt_sha256': prompt_hash,
                'enable_thinking': thinking, 'max_tokens': 12288 if thinking else 4096}
    state[name] = 'requesting'
    payload = {'model': MODEL, 'messages': [{'role': 'user', 'content': parts + [{'type': 'text', 'text': prompt}]}],
               'modalities': ['text'], 'enable_thinking': thinking, 'max_tokens': metadata['max_tokens'],
               'stream': True, 'stream_options': {'include_usage': True}}
    text = ''
    try:
        with requests.post(BASE + '/chat/completions', headers={'Authorization': 'Bearer ' + key}, json=payload,
                           stream=True, timeout=(20, 180)) as response:
            metadata['http_status'] = response.status_code
            if response.status_code != 200:
                raise RuntimeError(response.text.replace(key, '[REDACTED]')[:1200])
            with (out / (name + '.partial.txt')).open('w', encoding='utf-8') as handle:
                for line in response.iter_lines():
                    if not line.startswith(b'data: '):
                        continue
                    raw = line[6:]
                    if raw == b'[DONE]':
                        break
                    chunk = json.loads(raw)
                    if chunk.get('error'):
                        raise RuntimeError(json.dumps(chunk['error']))
                    metadata['response_id'] = chunk.get('id', metadata.get('response_id'))
                    if chunk.get('usage'):
                        metadata['usage'] = chunk['usage']
                    for choice in chunk.get('choices', []):
                        if choice.get('finish_reason'):
                            metadata['finish_reason'] = choice['finish_reason']
                        delta = choice.get('delta', {})
                        if delta.get('reasoning_content'):
                            state[name] = 'thinking'
                        if delta.get('content'):
                            text += delta['content']
                            handle.write(delta['content'])
                            handle.flush()
                            state[name] = f'{len(text)} characters'
        if metadata.get('finish_reason') != 'stop':
            raise RuntimeError('Incomplete response: ' + str(metadata.get('finish_reason')))
        result = parse_json(text)
        dump(result_path, result)
        metadata['status'] = 'complete'
        state[name] = 'complete'
        return result
    except Exception as exc:
        metadata['status'] = 'failed'
        metadata['error'] = str(exc).replace(key, '[REDACTED]')
        state[name] = 'failed'
        raise
    finally:
        metadata['elapsed_seconds'] = round(time.monotonic() - start, 2)
        dump(meta_path, metadata)
        print(name, metadata['status'], flush=True)

def render(out, manifest, visual, audio):
    labels = {}
    vocab_path = out / 'shared_prompt.txt'
    vocab = (vocab_path if vocab_path.exists() else ROOT / 'badminton_prompt.txt').read_text(encoding='utf-8')
    for eng, chinese in re.findall(r'^- ([a-z ]+) \| ([^:]+):', vocab, re.M):
        labels[eng] = chinese
    warnings = []
    events = []
    for shot, data in zip(manifest['shots'], visual):
        sid = shot['shot']
        assert data['shot'] == sid
        actors = {a['id'] for a in data['actors']}
        for e in data['actions']:
            e = dict(e)
            assert e['actor'] in actors, (sid, e)
            assert e['technique'] in labels, e
            if e['start'] < shot['start'] and shot['start'] - e['start'] <= 0.101:
                raw_start = e['start']
                e['start'] = shot['start']
                e['detail'] += '; onset cropped at shot boundary (model estimate ' + stamp(raw_start) + ' fell outside this shot)'
                warnings.append('Rounded action onset bounded to observed shot: ' + sid + ' ' + e['actor'])
            if e['end'] > shot['end'] and e['end'] - shot['end'] <= 0.101:
                e['end'] = shot['end']
                e['detail'] += '; offset cropped at shot boundary'
                warnings.append('Rounded action offset bounded to observed shot: ' + sid + ' ' + e['actor'])
            assert shot['start'] - 0.001 <= e['start'] < e['end'] <= shot['end'] + 0.001, e
            if re.search(r'\(\s*\d{2,4}\s*,\s*\d{2,4}\s*\)', e['evidence']):
                warnings.append('Unverified model pixel coordinates in evidence: ' + sid + ' ' + e['actor'])
                e['evidence'] += ' Pixel-coordinate claims above are model-generated and unverified, not measured tracking data.'
            events.append({**e, 'shot': sid})
    events.sort(key=lambda e: (e['start'], e['actor'], e['end']))
    for i, e in enumerate(events, 1):
        e['id'] = f'A{i:02d}'
    alignment_path = out / 'alignment.json'
    alignment = json.loads(alignment_path.read_text(encoding='utf-8')) if alignment_path.exists() else None
    segments = []
    sound_assessments = {}
    if alignment:
        signature = [{k: a[k] for k in ('id', 'shot', 'actor', 'start', 'end', 'technique')} for a in events]
        if alignment['source_sha256'] != manifest['source_sha256'] or alignment['action_signature'] != signature:
            raise ValueError('AV alignment is stale: source or action IDs/timing changed; rerun alignment.')
        segments = [u for s in alignment['shots'] for u in s['speech_segments']]
        segments.sort(key=lambda u: (u['start'], u['end']))
        sound_assessments = {item['action_id']: item for s in alignment['shots'] for item in s['action_sounds']}
        warnings += [w for s in alignment['shots'] for w in s.get('validation_warnings', [])]
        warnings += alignment.get('boundary_warnings', [])
    lines = ['## Storyline', '']
    for shot, data in zip(manifest['shots'], visual):
        lines += [stamp(shot['start']) + ' - ' + stamp(shot['end']), 'Shot: ' + shot['shot']]
        actors = '; '.join(a['id'] + ': ' + a['description'] for a in data['actors'])
        story = data['storyline']
        if alignment:
            story = story.replace('No speech or sounds are available to this stage.', '').replace('No speech or sounds are available to this stage', '')
        lines += [story + ' People: ' + actors]
        sounds = [s for s in audio['sounds'] if s['start'] < shot['end'] and s['end'] > shot['start']]
        utterances = [u for u in (segments if alignment else audio['utterances']) if u['start'] < shot['end'] and u['end'] > shot['start']]
        if sounds:
            lines += ['Audio: ' + '; '.join(stamp(max(s['start'], shot['start'])) + ' - ' + stamp(min(s['end'], shot['end'])) + ': ' + s['description'] for s in sounds)]
        if utterances:
            title = 'Speech (AV reviewed; associations below): ' if alignment else 'Speech (speaker association unverified): '
            lines += [title + '; '.join(stamp(u['start']) + ' - ' + stamp(u['end']) + ' ' + u['speaker'] + ': ' + u['text'] for u in utterances)]
        lines += ['']
    lines += ['## Visible Text', '']
    count = 0
    for shot, data in zip(manifest['shots'], visual):
        for item in data['visible_text']:
            item = dict(item)
            if item['start'] == item['end']:
                # A readable single frame has a known source-frame exposure,
                # but does not establish the full subtitle's display duration.
                support = min(shot['frames'], key=lambda f: abs(f['time'] - item['start']))
                if abs(support['time'] - item['start']) <= 0.001:
                    observed = item['start']
                    item['start'] = support['time']
                    item['end'] = min(shot['end'], support['time'] + 1 / manifest['source_fps'])
                    item['appearance'] += '; single-frame observation: interval covers only that source frame display, not the full text duration'
                    warnings.append('Single-frame visible text normalized to source frame exposure: ' + shot['shot'] + ' at ' + stamp(observed))
            assert shot['start'] - 0.001 <= item['start'] < item['end'] <= shot['end'] + 0.001
            count += 1
            lines += [stamp(item['start']) + ' - ' + stamp(item['end']), 'Shot: ' + shot['shot'],
                      json.dumps(item['text'], ensure_ascii=False) + ': ' + item['appearance'], '']
    if not count:
        lines += ['No visible text', '']
    lines += ['## Speakers and Transcript', '', 'Speaker profiles:']
    for speaker in audio['speakers']:
        suffix = '; visual identity assessed per utterance by model AV review.' if alignment else '; visual identity unverified.'
        lines += [speaker['id'] + ' - ' + speaker['description'] + suffix]
    lines += ['']
    for u in (segments if alignment else audio['utterances']):
        assert 0 <= u['start'] < u['end'] <= manifest['duration']
        if alignment:
            identity = u['speaker_status'] + (': ' + u['actor'] if u.get('actor') else '')
            relations = '; '.join(link['action_id'] + ': ' + link['relationship'] + ' (' + link['evidence'] + ')' for link in u['related_actions']) or 'none after AV review'
        else:
            identity = 'visual identity unverified'
            relations = 'none (semantic/audio-visual association not verified)'
        lines += [stamp(u['start']) + ' - ' + stamp(u['end']), 'Speaker: ' + u['speaker'] + ' (' + identity + ')',
                  'State: ' + u['state'], 'Content: ' + json.dumps(u['text'], ensure_ascii=False),
                  'Related actions: ' + relations]
        if alignment:
            lines += ['AV evidence: ' + u['evidence'] + '; model confidence=' + u['confidence']]
        lines += ['']
    if not (segments if alignment else audio['utterances']):
        lines += ['No intelligible speech', '']
    lines += ['## Atomic Sports Actions', '']
    for e in events:
        anchors = []
        for anchor in e['key_moments']:
            when = anchor.get('time')
            if when is not None and not (e['start'] <= when <= e['end']):
                warnings.append('Out-of-event anchor left uncertain: ' + e['id'])
                when = None
            anchors.append(anchor['name'] + ': ' + (stamp(when) + ' (estimated)' if when is not None else 'uncertain'))
        assessment = sound_assessments.get(e['id'])
        sound_line = 'uncertain (sound-to-action association not verified)'
        if assessment:
            sound_line = assessment['status'] + ' after model AV review: ' + assessment['description']
            if assessment['sound_time'] is not None:
                sound_line += '; audio=' + stamp(assessment['sound_time']) + ' (estimated)'
            if assessment['visual_time'] is not None:
                sound_line += '; visual=' + stamp(assessment['visual_time']) + ' (estimated)'
            if assessment['audio_minus_visual_seconds'] is not None:
                sound_line += '; audio-minus-visual=' + format(assessment['audio_minus_visual_seconds'], '+.3f') + ' s'
            sound_line += '; confidence=' + assessment['confidence'] + '; evidence: ' + assessment['evidence']
        lines += [stamp(e['start']) + ' - ' + stamp(e['end']), 'Action ID: ' + e['id'], 'Shot: ' + e['shot'],
                  'Actor: ' + e['actor'], 'Technique: ' + e['technique'], 'Chinese term: ' + labels[e['technique']],
                  'Visual evidence: ' + e['evidence'], 'Detail: ' + e['detail'],
                  'Key moments: ' + ('; '.join(anchors) if anchors else 'none'),
                  'Aligned sounds: ' + sound_line, '']
    if not events:
        lines += ['No discernible sports actions', '']
    report = out / 'badminton_response.txt'
    report.write_text('\n'.join(lines), encoding='utf-8')
    dump(out / 'combined_annotations.json', {'shots': visual, 'audio': audio, 'actions': events, 'warnings': warnings, 'alignment': alignment})
    dump(out / 'pipeline_validation.json', {'status': 'complete', 'shot_count': len(visual), 'action_count': len(events),
         'sorted_action_ids': True, 'timestamps_and_labels_validated': True, 'warnings': warnings, 'av_alignment': 'model_reviewed' if alignment else 'not_run',
         'limits': ['Visual event content and audio transcription are model estimates, not verified ground truth.',
                    'AV links are model-reviewed estimates, not human-verified synchronization.' if alignment else 'No automatic assignment of voices or sounds to visible people or actions.',
                    'Scene-cut detection uses a configurable pixel-change threshold and requires review on other videos.']})
    print('REPORT:', report, flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', default='transfer2paas_2/badminton_lift_31679122798_first8s.mp4')
    parser.add_argument('--resume')
    parser.add_argument('--assemble-only', action='store_true', help='Render cached stages without another API call')
    parser.add_argument('--skip-alignment', action='store_true', help='Stop after visual/audio observations and deterministic merging')
    args = parser.parse_args()
    if args.assemble_only and not args.resume:
        raise SystemExit('--assemble-only requires --resume')
    if args.resume:
        out = (ROOT / args.resume).resolve()
    else:
        run = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        version = re.search(r'prompt v(\d+)\.(\d+)', (ROOT / 'badminton_prompt.txt').read_text(encoding='utf-8'))
        tag = 'v' + ''.join(version.groups()) if version else 'current'
        out = ROOT / 'qwen3.8_omni_results' / (run + '_pipeline_' + tag)
        out.mkdir(parents=True)
        (out / 'shared_prompt.txt').write_bytes((ROOT / 'badminton_prompt.txt').read_bytes())
    provenance = out / 'provenance.json'
    if args.assemble_only and provenance.exists():
        manifest = json.loads(provenance.read_text(encoding='utf-8'))['source_manifest']
    else:
        manifest = prepare((ROOT / args.source).resolve(), out)
    print('Output directory:', out, flush=True)
    print('Shot boundaries:', manifest['detected_cut_seconds'], 'local fps:', manifest['local_sampling_fps'], flush=True)
    if args.assemble_only:
        visual = [json.loads((out / ('visual_' + shot['shot'] + '.json')).read_text(encoding='utf-8')) for shot in manifest['shots']]
        audio = json.loads((out / 'audio.json').read_text(encoding='utf-8'))
        render(out, manifest, visual, audio)
        metas = [json.loads(p.read_text(encoding='utf-8')) for p in out.rglob('*_metadata.json')]
        dump(out / 'summary.json', {'model': MODEL, 'stages': metas, 'total_tokens': sum(m.get('usage', {}).get('total_tokens', 0) for m in metas)})
        return
    key = getpass.getpass('API key (hidden): ').strip()
    state = {}
    visual_prompt = (ROOT / 'badminton_prompt.txt').read_text(encoding='utf-8') + '\n' + (ROOT / 'badminton_pipeline/visual_prompt.txt').read_text(encoding='utf-8')
    audio_prompt = (ROOT / 'badminton_pipeline/audio_prompt.txt').read_text(encoding='utf-8')
    def visual_job(shot):
        parts = []
        for frame in shot['frames']:
            data = (out / 'media/frames' / frame['file']).read_bytes()
            parts += [{'type': 'text', 'text': 'Source-clip time ' + stamp(frame['time'])},
                      {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}]
        context = {'shot': shot['shot'], 'start': shot['start'], 'end': shot['end'], 'duration': manifest['duration'],
                   'frame_times': [f['time'] for f in shot['frames']]}
        prompt = visual_prompt + '\nCaller metadata: ' + json.dumps(context)
        return call_stage('visual_' + shot['shot'], prompt, parts, key, out, True, state)
    def audio_job():
        data = (out / 'media/audio.wav').read_bytes()
        parts = [{'type': 'input_audio', 'input_audio': {'data': 'data:audio/wav;base64,' + base64.b64encode(data).decode(), 'format': 'wav'}}]
        return call_stage('audio', audio_prompt + '\nDuration seconds: ' + str(manifest['duration']), parts, key, out, False, state)
    with ThreadPoolExecutor(max_workers=4) as pool:
        vf = [pool.submit(visual_job, shot) for shot in manifest['shots']]
        af = pool.submit(audio_job)
        pending = set(vf + [af])
        while pending:
            _, pending = wait(pending, timeout=20)
            if pending:
                print('Progress:', json.dumps(state), flush=True)
        visual = [f.result() for f in vf]
        audio = af.result()
    render(out, manifest, visual, audio)
    if not args.skip_alignment:
        from badminton_alignment import run_alignment
        run_alignment(out, manifest, key)
        render(out, manifest, visual, audio)
    metas = [json.loads(p.read_text(encoding='utf-8')) for p in out.rglob('*_metadata.json')]
    dump(out / 'summary.json', {'model': MODEL, 'stages': metas,
          'total_tokens': sum(m.get('usage', {}).get('total_tokens', 0) for m in metas)})

if __name__ == '__main__':
    main()
