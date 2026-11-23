from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
import base64
import getpass
import json
from pathlib import Path
import shutil
import sys

from run_badminton_pipeline import ROOT, MODEL, call_stage, dump, render, stamp

source = ROOT / sys.argv[1]
manifest = json.loads((source / 'media/manifest.json').read_text(encoding='utf-8'))
out = ROOT / 'qwen3.8_omni_results' / (datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S') + '_pipeline_v07')
out.mkdir(parents=True)
shared = (ROOT / 'badminton_prompt.txt').read_text(encoding='utf-8')
(out / 'shared_prompt.txt').write_text(shared, encoding='utf-8')
task = (ROOT / 'badminton_pipeline/review_prompt.txt').read_text(encoding='utf-8')
dump(out / 'provenance.json', {'baseline_run': str(source), 'reused_stages': ['audio', 'visual_S03'], 'reviewed_shots': ['S01', 'S02'], 'source_manifest': manifest})
for name in ['audio', 'visual_S03']:
    for suffix in ['.json', '_metadata.json', '_prompt.txt']:
        original = source / (name + suffix)
        if original.exists():
            shutil.copyfile(original, out / original.name)
key = getpass.getpass('API key (hidden): ').strip()
state = {}

def review(shot):
    sid = shot['shot']
    candidate = json.loads((source / ('visual_' + sid + '.json')).read_text(encoding='utf-8'))
    dump(out / ('baseline_' + sid + '.json'), candidate)
    parts = []
    for f in shot['frames']:
        data = (source / 'media/frames' / f['file']).read_bytes()
        parts += [{'type': 'text', 'text': 'Source clip time ' + stamp(f['time'])},
                  {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(data).decode()}}]
    context = {'shot': sid, 'start': shot['start'], 'end': shot['end'], 'source_fps': manifest['source_fps'],
               'frame_times': [f['time'] for f in shot['frames']]}
    prompt = shared + '\n' + task + '\nCaller metadata: ' + json.dumps(context) + '\nCandidate annotations to verify, not ground truth:\n' + json.dumps(candidate, ensure_ascii=False)
    return call_stage('review_' + sid, prompt, parts, key, out, True, state)

print('Output directory:', out, flush=True)
with ThreadPoolExecutor(max_workers=2) as pool:
    futures = [pool.submit(review, s) for s in manifest['shots'][:2]]
    pending = set(futures)
    while pending:
        _, pending = wait(pending, timeout=20)
        if pending:
            print('Progress:', json.dumps(state), flush=True)
    results = [f.result() for f in futures]
visual = results + [json.loads((out / 'visual_S03.json').read_text(encoding='utf-8'))]
audio = json.loads((out / 'audio.json').read_text(encoding='utf-8'))
for sid, result in zip(['S01', 'S02'], results):
    dump(out / ('visual_' + sid + '.json'), result)
render(out, manifest, visual, audio)
metas = [json.loads(p.read_text(encoding='utf-8')) for p in out.glob('review_*_metadata.json')]
dump(out / 'summary.json', {'model': MODEL, 'new_request_count': len(metas), 'reused_request_count': 2,
                          'new_request_tokens': sum(m.get('usage', {}).get('total_tokens', 0) for m in metas), 'stages': metas})
