"""Run independent visual and verbatim audio passes and export a review caption."""

import argparse
import getpass
import os
from pathlib import Path

from .bwf_model_comparison import make_audio_spec, validate_transcript
from .client import describe_request, execute, save_request
from .io_utils import read_json, write_json
from .media import prepare
from .pipeline import PACKAGE, bind_run, load_config, optional_cuts, request_spec
from .relations import build_relations
from .validation import validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    config, root = load_config(PACKAGE / 'config/five_videos_live_compact.json')
    case = next(case for case in config['cases'] if case['id'] == 'standing_jump')
    config['cases'] = [case]
    config['experiment'] = 'standing_jump_independent_transcript'
    provider = config['provider']
    protocol = bind_run(args.run_dir, config)
    output = args.run_dir / case['id']
    media = output / 'media'
    manifest = prepare(root / case['source'], media, config['media'], optional_cuts(root, case))
    lexicon = read_json(PACKAGE / 'lexicons/standing_jump.json')
    descriptor, prompt, attachments = request_spec('visual', manifest, lexicon, media, provider, protocol)
    prompt = prompt.replace('Write descriptions in English.', 'Write descriptions in concise Chinese.', 1)
    visual_spec = describe_request('visual', prompt, attachments, provider, descriptor['provenance']), prompt, attachments
    audio_spec = make_audio_spec(manifest, media, provider, protocol)
    visual_stage = output / 'stages/visual'
    audio_stage = output / 'stages/audio_transcript'
    save_request(visual_stage, *visual_spec[:2])
    save_request(audio_stage, *audio_spec[:2])
    print(f"Prepared {manifest['duration']:.3f}s, {len(manifest['shots'])} shots, "
          f"{len(manifest['frames'])} timestamped images.", flush=True)
    if args.dry_run:
        return

    key = os.environ.get(provider['api_key_env']) or getpass.getpass('Qwen API key (hidden, not saved): ')
    print('Audio transcription: start', flush=True)
    audio = execute(audio_stage, *audio_spec, provider, lambda: key,
                    lambda data: validate_transcript(data, manifest))
    print('Visual annotation: start', flush=True)
    visual = execute(visual_stage, *visual_spec, provider, lambda: key,
                     lambda data: validate('visual', data, manifest, lexicon,
                                           [frame['time'] for frame in manifest['frames']]))
    sound_warnings = validate_transcript(audio, manifest)
    valid_sounds = []
    for event in audio['events']:
        try:
            validate('audio', {**audio, 'events': [event]}, manifest, lexicon)
        except ValueError:
            continue
        valid_sounds.append(event)
    graph = build_relations(visual['actions'], valid_sounds)
    write_json(output / 'annotations.json', {'model': provider['model'], 'human_verified': False,
        'source_sha256': manifest['source_sha256'], 'duration': manifest['duration'], 'shots': manifest['shots'],
        'visual': visual, 'audio': audio, 'relations': graph, 'audio_warnings': sound_warnings})
    write_json(output / 'relations.json', graph)

    names = {term['label']: term['zh'] for term in lexicon['terms']}
    names.update(explanatory_gesture='讲解手势', held_pose='保持姿态', other_motion='其他可见动作')
    lines = ['立定跳远 0–7 秒｜Qwen 3.8 Omni Flash 管道生成的候选 Caption',
             '视觉和原声分别输入，时间以片头为零。区间为模型估计，关系由程序求交。', '', '镜头']
    for shot in manifest['shots']:
        lines.append(f"{shot['id']}  {shot['start']:.3f}–{shot['end']:.3f} s")
    lines += ['', '动作与状态']
    for event in sorted(visual['actions'], key=lambda item: (item['start'], item['id'])):
        lines.append(f"{event['id']}  {event['start']:.3f}–{event['end']:.3f} s  {event['actor_id']}  "
                     f"{names[event['label']]}。{event['detail']}")
    lines += ['', '原声转写与声音事件']
    for event in sorted(audio['events'], key=lambda item: (item['start'], item['id'])):
        content = f"「{event['transcript']}」" if event['transcript'] else event['description']
        lines.append(f"{event['id']}  {event['start']:.3f}–{event['end']:.3f} s  {content}")
    lines += ['', '动作与前景音频的名义交集（秒）']
    for edge in graph['pairs']:
        if edge['nominal_overlap'] and edge['audio_layer'] == 'foreground' and edge['action_kind'] != 'held_pose':
            start, end = edge['intersection']
            status = '给定边界范围内有重叠' if edge['status'] == 'overlap' else '边界有待复核'
            lines.append(f"{edge['action_id']} × {edge['audio_id']}  {start:.3f}–{end:.3f} s  {status}")
    lines += ['', '待复核'] + visual['uncertainties'] + audio['uncertainties'] + sound_warnings
    (output / 'caption.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Caption written:', output / 'caption.txt', flush=True)


if __name__ == '__main__':
    main()
