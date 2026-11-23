"""Run/check audiovisual association stages and reuse earlier observations."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
import math
import re
from pathlib import Path
import shutil

from run_badminton_pipeline import ROOT, call_stage, dump, render, stamp

def validate_alignment(result, manifest, combined):
    data = deepcopy(result)
    shots = {s['shot']: s for s in manifest['shots']}
    sid = data['shot']
    if sid not in shots:
        raise ValueError('Unknown shot: ' + str(sid))
    shot = shots[sid]
    actors = {a['id'] for s in combined['shots'] if s['shot'] == sid for a in s['actors']}
    actions = {a['id']: a for a in combined['actions'] if a['shot'] == sid}
    voices = {s['id'] for s in combined['audio']['speakers']}
    utterances = {'U' + str(i + 1).zfill(2) for i in range(len(combined['audio']['utterances']))}
    warnings = []
    def point(t, start, end):
        return isinstance(t, (int, float)) and math.isfinite(t) and start - 0.001 <= t <= end + 0.001
    def interval(item):
        if not (point(item['start'], shot['start'], shot['end']) and point(item['end'], shot['start'], shot['end']) and item['start'] < item['end']):
            raise ValueError('Interval outside shot: ' + str(item))
    for segment in data['speech_segments']:
        interval(segment)
        if segment['speaker'] not in voices or segment['source_utterance_id'] not in utterances | {None}:
            raise ValueError('Invalid voice/utterance reference')
        if segment['speaker_status'] not in {'supported', 'off_screen', 'uncertain'} or segment['confidence'] not in {'high', 'medium', 'low'}:
            raise ValueError('Invalid speech status/confidence')
        if segment['actor'] is not None and segment['actor'] not in actors:
            raise ValueError('Invalid visible actor')
        if segment['speaker_status'] == 'supported' and (not segment['actor'] or not segment['evidence'].strip() or segment['confidence'] == 'low'):
            segment['speaker_status'] = 'uncertain'
            warnings.append('Low-evidence speaker link downgraded')
        if segment['speaker_status'] != 'supported':
            segment['actor'] = None
        for link in segment['related_actions']:
            if link['action_id'] not in actions or link['relationship'] not in {'instruction', 'description', 'retrospective comment', 'temporal overlap only'}:
                raise ValueError('Invalid speech/action link')
            a = actions[link['action_id']]
            if link['relationship'] == 'temporal overlap only' and not (segment['start'] < a['end'] and segment['end'] > a['start']):
                raise ValueError('Temporal-overlap link has no overlap')
    seen = []
    for item in data['action_sounds']:
        aid = item['action_id']
        if aid not in actions or aid in seen:
            raise ValueError('Invalid or duplicate sound/action reference: ' + aid)
        seen.append(aid)
        if item['status'] not in {'supported', 'uncertain', 'none_detected'} or item['confidence'] not in {'high', 'medium', 'low'}:
            raise ValueError('Invalid sound status/confidence')
        a = actions[aid]
        at, vt = item['sound_time'], item['visual_time']
        if at is not None and not point(at, shot['start'], shot['end']):
            raise ValueError('Audio time outside shot')
        if vt is not None and not point(vt, a['start'], a['end']):
            raise ValueError('Visual anchor outside action: ' + aid)
        item['audio_minus_visual_seconds'] = round(at - vt, 3) if at is not None and vt is not None else None
        if item['status'] == 'supported' and (at is None or vt is None or abs(at - vt) > 0.200001 or item['confidence'] == 'low' or not item['evidence'].strip()):
            item['status'] = 'uncertain'
            item['evidence'] += '; validator: insufficient localization/confidence or offset exceeds 0.200 s'
            warnings.append('Unsupported sound match downgraded: ' + aid)
    if set(seen) != set(actions):
        raise ValueError('Not all candidate actions were assessed: ' + str(set(actions) - set(seen)))
    for item in data['unmatched_sounds']:
        interval(item)
    data['speech_segments'].sort(key=lambda u: (u['start'], u['end']))
    data['validation_warnings'] = warnings
    return data

def find_media_run(out):
    current = out.resolve()
    for _ in range(10):
        if (current / 'media/manifest.json').exists():
            return current
        info = current / 'provenance.json'
        if not info.exists():
            break
        current = Path(json.loads(info.read_text(encoding='utf-8'))['baseline_run'])
    raise ValueError('Cannot locate source frames for ' + str(out))

def run_alignment(out, manifest, key):
    media_run = find_media_run(out)
    source = Path(manifest['source'])
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest['source_sha256']:
        raise ValueError('Source video changed since visual analysis')
    combined = json.loads((out / 'combined_annotations.json').read_text(encoding='utf-8'))
    prompt = (ROOT / 'badminton_pipeline/alignment_prompt.txt').read_text(encoding='utf-8')
    stage_dir = out / 'av_alignment'
    stage_dir.mkdir(exist_ok=True)
    state = {}
    video_part = {'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,' + base64.b64encode(raw).decode()}}
    candidate_utterances = [{'id': f'U{i+1:02d}', **u} for i, u in enumerate(combined['audio']['utterances'])]
    def job(shot):
        sid = shot['shot']
        parts = [video_part]
        frame_hashes = []
        for f in shot['frames']:
            image = (media_run / 'media/frames' / f['file']).read_bytes()
            frame_hashes.append(hashlib.sha256(image).hexdigest())
            parts += [{'type': 'text', 'text': 'Additional SAME-video frame at global time ' + stamp(f['time'])},
                      {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}}]
        context = {'shot': sid, 'start': shot['start'], 'end': shot['end'], 'duration': manifest['duration'],
                   'source_sha256': manifest['source_sha256'], 'frame_times': [f['time'] for f in shot['frames']],
                   'frame_sha256': frame_hashes, 'actors': next(s['actors'] for s in combined['shots'] if s['shot'] == sid),
                   'voices': combined['audio']['speakers'], 'candidate_utterances': candidate_utterances,
                   'candidate_sounds': combined['audio']['sounds'], 'candidate_actions': [a for a in combined['actions'] if a['shot'] == sid]}
        answer = call_stage('alignment_' + sid, prompt + '\nINPUT CONTEXT:\n' + json.dumps(context, ensure_ascii=False), parts, key, stage_dir, True, state)
        checked = validate_alignment(answer, manifest, combined)
        dump(stage_dir / ('alignment_' + sid + '_validated.json'), checked)
        return checked
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(job, shot) for shot in manifest['shots']]
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=20)
            if pending:
                print('AV progress:', json.dumps(state), flush=True)
        results = [f.result() for f in futures]
    signature = [{k: a[k] for k in ('id', 'shot', 'actor', 'start', 'end', 'technique')} for a in combined['actions']]
    boundary_warnings = []
    ordered = sorted(((s['shot'], u) for s in results for u in s['speech_segments']), key=lambda pair: pair[1]['start'])
    for (left_shot, left), (right_shot, right) in zip(ordered, ordered[1:]):
        if left_shot == right_shot or not left['source_utterance_id'] or left['source_utterance_id'] != right['source_utterance_id']:
            continue
        lt = re.sub(r'[^\w]', '', left['text'])
        rt = re.sub(r'[^\w]', '', right['text'])
        if lt and rt and lt.endswith(rt) and abs(left['end'] - right['start']) <= 0.001:
            note = 'Cross-cut transcript fragments may repeat a syllable; exact split remains uncertain (original fragments preserved).'
            left['state'] += '; ' + note
            right['state'] += '; ' + note
            boundary_warnings.append(left['source_utterance_id'] + ': ' + note)
    alignment = {'version': '0.8', 'status': 'model_reviewed', 'source_sha256': manifest['source_sha256'],
                 'action_signature': signature, 'shots': results,
                 'boundary_warnings': boundary_warnings,
                 'limits': 'Model-backed associations, not human-verified synchronization or measured impact times.'}
    dump(out / 'alignment.json', alignment)
    counts = {}
    for shot in results:
        for item in shot['action_sounds']:
            counts[item['status']] = counts.get(item['status'], 0) + 1
    metas = [json.loads(p.read_text(encoding='utf-8')) for p in stage_dir.glob('*_metadata.json')]
    dump(out / 'alignment_summary.json', {'new_requests': len(metas), 'new_tokens': sum(m.get('usage', {}).get('total_tokens', 0) for m in metas),
         'sound_status_counts': counts, 'speech_segments': sum(len(s['speech_segments']) for s in results),
         'supported_speaker_links': sum(u['speaker_status'] == 'supported' for s in results for u in s['speech_segments']),
         'warnings': [w for s in results for w in s['validation_warnings']] + boundary_warnings})
    return alignment

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-run', required=True)
    parser.add_argument('--resume')
    parser.add_argument('--cached-only', action='store_true', help='Validate and merge existing complete alignment responses without API calls')
    args = parser.parse_args()
    if args.cached_only and not args.resume:
        parser.error('--cached-only requires --resume')
    baseline = (ROOT / args.source_run).resolve()
    if args.resume:
        out = (ROOT / args.resume).resolve()
    else:
        date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        out = ROOT / 'qwen3.8_omni_results' / (date + '_pipeline_v08_alignment')
        out.mkdir(parents=True)
        for name in ['audio.json', 'combined_annotations.json'] + [p.name for p in baseline.glob('visual_S[0-9][0-9].json')]:
            shutil.copyfile(baseline / name, out / name)
        (out / 'shared_prompt.txt').write_bytes((ROOT / 'badminton_prompt.txt').read_bytes())
    media = find_media_run(baseline)
    manifest = json.loads((media / 'media/manifest.json').read_text(encoding='utf-8'))
    dump(out / 'provenance.json', {'baseline_run': str(baseline), 'source_manifest': manifest, 'reused_stages': 'all visual and audio observations; new requests only for AV alignment'})
    print('Output directory:', out, flush=True)
    if args.cached_only:
        for shot in manifest['shots']:
            name = 'alignment_' + shot['shot']
            metadata = json.loads((out / 'av_alignment' / (name + '_metadata.json')).read_text(encoding='utf-8'))
            if metadata.get('status') != 'complete' or not (out / 'av_alignment' / (name + '.json')).exists():
                raise ValueError('Incomplete checkpoint; cached-only cannot call the API')
        key = ''
    else:
        key = getpass.getpass('API key (hidden): ').strip()
    run_alignment(out, manifest, key)
    visual = [json.loads((out / ('visual_' + s['shot'] + '.json')).read_text(encoding='utf-8')) for s in manifest['shots']]
    audio = json.loads((out / 'audio.json').read_text(encoding='utf-8'))
    render(out, manifest, visual, audio)

if __name__ == '__main__':
    main()
