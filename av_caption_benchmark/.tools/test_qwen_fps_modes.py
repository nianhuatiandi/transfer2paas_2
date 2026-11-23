import base64
import argparse
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import getpass
import hashlib
import json
from pathlib import Path

from run_badminton_pipeline import ROOT, call_stage, dump, stamp

PROMPT = '''Inspect the supplied 8-second video using the actual available visual and audio evidence. If additional timestamped pictures are supplied, they are source frames of this SAME video, not extra scenes. Their labels are elapsed source-clip times. Do not infer unseen frames from duration or instructions. Do not assume an expected number of shots or actions.
Return JSON only:
{
"shots":[{"start":0.0,"end":1.0,"description":"camera viewpoint, visible people/clothing and chronological events; estimated boundaries and unobserved intervals explicitly stated"}],
"tail_observation":{"last_observed_time":null,"description":"what is actually visible near the end, or unobserved","readable_text":["only verbatim text readable near the end"]},
"racket_and_shuttle_events":[{"start":0.0,"end":0.2,"actor":"stable visible-person description and shot","description":"observed racket/hand/shuttle event; distinguish bare-hand delivery, racket delivery, stroke and conversational gesture; indicate uncertainty"}],
"footwork_observations":[{"start":0.0,"end":0.2,"actor":"person description","description":"visible foot-by-foot evidence, or unresolved foot pattern"}],
"audible_speech":[{"start":0.0,"end":0.2,"text":"audible original-language words; do not read subtitles as speech"}],
"uncertainties":["limitations of actual observed evidence"]
}
Use empty lists for absent observations; no example values or pixel coordinates. Times are estimated seconds between 0 and 8. Scan the entire available clip, including its final frames. Describe every distinguishable occurrence but do not guess frame availability or claimed sampling rate.'''

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tail-only', action='store_true')
    args = parser.parse_args()
    date = datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
    out = ROOT / 'qwen3.8_omni_results' / (date + ('_fps_tail_comparison' if args.tail_only else '_fps_comparison'))
    out.mkdir(parents=True)
    source = ROOT / 'transfer2paas_2/badminton_lift_31679122798_first8s.mp4'
    media = ROOT / 'qwen3.8_omni_results/20261123_001444_pipeline_v06/media'
    manifest = json.loads((media / 'manifest.json').read_text(encoding='utf-8'))
    raw = source.read_bytes()
    url = 'data:video/mp4;base64,' + base64.b64encode(raw).decode()
    video = lambda: {'type': 'video_url', 'video_url': {'url': url}}
    default = video()
    nested = video()
    nested['video_url']['fps'] = 10
    sibling = video()
    sibling['fps'] = 10
    pictures = [video()]
    for shot in manifest['shots']:
        for f in shot['frames']:
            image = (media / 'frames' / f['file']).read_bytes()
            pictures += [{'type': 'text', 'text': 'Additional SAME-video frame at ' + stamp(f['time'])},
                         {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(image).decode()}}]
    modes = {'default_video': [default], 'nested_fps10_legacy': [nested], 'api_fps10_sibling': [sibling], 'local_10fps_images_plus_video': pictures}
    prompt = PROMPT
    if args.tail_only:
        modes = {name: parts for name, parts in modes.items() if name in {'api_fps10_sibling', 'local_10fps_images_plus_video'}}
        prompt += '\nFOCUSED FOLLOW-UP: Focus ONLY on the final 0.5 seconds, from 7.500 to 8.000. In shots and event lists include only observations in this final window. Describe the last actual visible image and readable text. Do not assume the previous scene continues. If the final window is not actually visible, explicitly say so instead of guessing. Keep the same JSON schema.'
    dump(out / 'test_config.json', {
        'source': str(source), 'source_sha256': hashlib.sha256(raw).hexdigest(),
        'model': 'qwen3.8-omni-flash', 'base_url': 'https://maas.qianwenaiapi.com/compatible-mode/v1',
        'enable_thinking': False, 'max_tokens': 4096, 'repetitions_per_mode': 1,
        'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(), 'tail_only': args.tail_only,
        'additional_image_count': sum(len(s['frames']) for s in manifest['shots']),
        'image_size': '960x540 JPEG, as used by the current pipeline',
        'modes': {
            'default_video': {'video_part': {'type': 'video_url', 'video_url': {'url': '[same MP4 base64]'}}},
            'nested_fps10_legacy': {'video_part': {'type': 'video_url', 'video_url': {'url': '[same MP4 base64]', 'fps': 10}}},
            'api_fps10_sibling': {'video_part': {'type': 'video_url', 'video_url': {'url': '[same MP4 base64]'}, 'fps': 10}},
            'local_10fps_images_plus_video': {'video_part': {'type': 'video_url', 'video_url': {'url': '[same MP4 base64]'}}, 'additional_images': 84}},
        'limits': ['One invocation per mode; content quality differences are observations, not statistical accuracy estimates.',
                   'Local image mode also changes modality representation, timestamp text and image resizing; token totals are not directly comparable as frame counts.']})
    print('Output directory:', out, flush=True)
    key = getpass.getpass('API key (hidden): ').strip()
    state = {}
    def job(name, parts):
        return call_stage(name, prompt, parts, key, out, False, state)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(job, name, parts) for name, parts in modes.items()}
        pending = set(futures.values())
        while pending:
            _, pending = wait(pending, timeout=20)
            if pending:
                print('Progress:', json.dumps(state), flush=True)
        results = {name: future.result() for name, future in futures.items()}
    summary = {}
    for name, result in results.items():
        meta = json.loads((out / (name + '_metadata.json')).read_text(encoding='utf-8'))
        summary[name] = {'shot_count': len(result['shots']), 'shots': result['shots'], 'tail': result['tail_observation'],
                         'event_count': len(result['racket_and_shuttle_events']), 'usage': meta.get('usage'),
                         'elapsed_seconds': meta['elapsed_seconds']}
    dump(out / 'comparison_summary.json', summary)
    print('All comparison requests completed.', flush=True)

if __name__ == '__main__':
    main()
