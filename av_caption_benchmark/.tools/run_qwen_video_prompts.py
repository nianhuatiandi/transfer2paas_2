import base64
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
from pathlib import Path
import re
import time

import requests

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = 'https://maas.qianwenaiapi.com/compatible-mode/v1'
MODEL = 'qwen3.8-omni-flash'
FPS = 10
JOBS = [
    ('badminton', 'badminton_prompt.txt', 'transfer2paas_2/badminton_lift_31679122798_first8s.mp4', 8),
    ('jump', 'jump_prompt.txt', 'transfer2paas_2/standing_long_jump_1039046118_0-7s.mp4', 7),
]
SECTIONS = ['## Storyline', '## Visible Text', '## Speakers and Transcript', '## Atomic Sports Actions']

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', choices=['badminton', 'jump'])
    parser.add_argument('--badminton-prompt', default='badminton_prompt.txt')
    parser.add_argument('--tag', default='')
    parser.add_argument('--supplementary-frames', help='JSON manifest of source-video frames with timestamps, for badminton only')
    args = parser.parse_args()
    jobs = [job for job in JOBS if args.only is None or job[0] == args.only]
    jobs = [(name, args.badminton_prompt if name == 'badminton' else prompt, video, duration) for name, prompt, video, duration in jobs]
    for name, prompt_path, _, _ in jobs:
        if name == 'badminton' and 'Pipeline contract:' in (ROOT / prompt_path).read_text(encoding='utf-8-sig'):
            raise SystemExit('This is a staged prompt. Use python .tools/run_badminton_pipeline.py, or select an explicit older prompt with --badminton-prompt.')
    if args.tag and not re.fullmatch(r'[A-Za-z0-9_-]+', args.tag):
        raise SystemExit('Tag must contain only letters, digits, underscores, or hyphens.')
    key = getpass.getpass('API key (hidden): ').strip()
    if not key:
        raise SystemExit('Missing API key.')
    run_time = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    output = ROOT / 'qwen3.8_omni_results' / (run_time + ('_' + args.tag if args.tag else ''))
    output.mkdir(parents=True, exist_ok=False)
    print('Output directory:', output, flush=True)
    progress = {}

    def run(job):
        name, prompt_path, video_path, duration = job
        started = time.monotonic()
        prompt_bytes = (ROOT / prompt_path).read_bytes()
        prompt = prompt_bytes.decode('utf-8-sig')
        video = (ROOT / video_path).read_bytes()
        (output / (name + '_prompt.txt')).write_bytes(prompt_bytes)
        metadata = {
            'name': name, 'model': MODEL, 'base_url': BASE_URL,
            'prompt': prompt_path, 'prompt_sha256': hashlib.sha256(prompt_bytes).hexdigest(),
            'video': video_path, 'video_sha256': hashlib.sha256(video).hexdigest(),
            'clip_duration_seconds': duration, 'requested_fps': FPS,
            'fps_field_location': 'content_part.fps (sibling of video_url)',
            'enable_thinking': True, 'max_tokens': 16384,
        }
        progress[name] = 'uploading'
        try:
            content_parts = [
                {'type': 'video_url', 'video_url': {'url': 'data:video/mp4;base64,' + base64.b64encode(video).decode()}, 'fps': FPS},
            ]
            if args.supplementary_frames and name == 'badminton':
                manifest_path = (ROOT / args.supplementary_frames).resolve()
                frame_list = json.loads(manifest_path.read_text(encoding='utf-8'))
                metadata['supplementary_frames'] = []
                content_parts.append({'type': 'text', 'text': 'The following are timestamped frames extracted from the SAME supplied video, not a new video or separate scenes. Times are elapsed source-clip times. Use them as additional visual evidence and use the video for audio. Do not count repeated views of the same action twice.'})
                for frame in frame_list:
                    image_path = manifest_path.parent / frame['file']
                    image_bytes = image_path.read_bytes()
                    metadata['supplementary_frames'].append({**frame, 'sha256': hashlib.sha256(image_bytes).hexdigest()})
                    timestamp = frame['timestamp_seconds']
                    content_parts.append({'type': 'text', 'text': 'Source video frame at elapsed 00:' + format(timestamp, '06.3f') + '.'})
                    content_parts.append({'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image_bytes).decode()}})
            content_parts.append({'type': 'text', 'text': prompt})
            payload = {
                'model': MODEL,
                'messages': [{'role': 'user', 'content': content_parts}],
                'modalities': ['text'], 'stream': True,
                'stream_options': {'include_usage': True},
                'enable_thinking': True, 'max_tokens': 16384,
            }
            with requests.post(BASE_URL + '/chat/completions', headers={'Authorization': 'Bearer ' + key}, json=payload, stream=True, timeout=(20, 180)) as response:
                metadata['http_status'] = response.status_code
                metadata['request_id'] = response.headers.get('x-request-id')
                if response.status_code != 200:
                    raise RuntimeError(response.text.replace(key, '[REDACTED]')[:1500])
                content = ''
                progress[name] = 'processing'
                partial = output / (name + '_response.partial.txt')
                with partial.open('w', encoding='utf-8', newline='\n') as handle:
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
                                progress[name] = 'thinking'
                            text = delta.get('content') or ''
                            if text:
                                content += text
                                handle.write(text)
                                handle.flush()
                                progress[name] = str(len(content)) + ' output characters'
                if not content:
                    raise RuntimeError('No text response received.')
                if metadata.get('finish_reason') != 'stop':
                    raise RuntimeError('Response incomplete: ' + str(metadata.get('finish_reason')))
                partial.rename(output / (name + '_response.txt'))
                positions = [content.find(section) for section in SECTIONS]
                metadata['four_sections_in_order'] = all(i >= 0 for i in positions) and positions == sorted(positions)
                stamps = [int(m) * 60 + int(s) + int(ms) / 1000 for m, s, ms in re.findall(r'(?<!\d)(\d{2}):(\d{2})\.(\d{3})(?!\d)', content)]
                metadata['timestamps_beyond_clip'] = sorted(set(t for t in stamps if t > duration))
                metadata['output_characters'] = len(content)
                metadata['status'] = 'complete'
                progress[name] = 'complete'
        except Exception as exc:
            metadata['status'] = 'failed'
            metadata['error'] = str(exc).replace(key, '[REDACTED]')
            progress[name] = 'failed'
        metadata['elapsed_seconds'] = round(time.monotonic() - started, 2)
        (output / (name + '_metadata.json')).write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(metadata, ensure_ascii=False), flush=True)
        return metadata

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=20)
            if pending:
                print('Progress:', json.dumps(progress), flush=True)
        results = [future.result() for future in futures]
    (output / 'summary.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if any(result['status'] != 'complete' for result in results):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
