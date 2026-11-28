"""Independent Qwen transcription and GPT visual annotation against a frozen BWF baseline."""
import argparse
import copy
import getpass
import json
import os
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from .client import describe_request, execute, save_request
from .hierarchical_experiment import nominal_relations, output_schema, validate_draft, export_readable
from .io_utils import file_hash, object_hash, parse_model_json, read_json, write_json
from .media import prepare, prepare_review
from .pipeline import PACKAGE, bind_run, load_config, optional_cuts
from .schemas import EVIDENCE, TEXT, arr, obj, schema_for
from .validation import check_finite, require, validate_audio


def validate_transcript(data, manifest):
    check_finite(data)
    Draft202012Validator(schema_for('audio')).validate(data)
    require(len({e['id'] for e in data['events']}) == len(data['events']), 'Duplicate audio IDs')
    warnings = []
    for event in data['events']:
        if event['kind'] == 'speech':
            require(isinstance(event['transcript'], str) and bool(event['transcript'].strip()),
                    'Every speech event needs verbatim words or an explicit unintelligible marker')
        else:
            require(event['transcript'] is None and event['speaker_id'] is None,
                    'Non-speech events must not contain a transcript or speaker')
        try:
            validate_audio({**data, 'events': [event]}, manifest)
        except ValueError as exc:
            warnings.append(str(exc))
    return warnings


def import_completed_audio(source, target, descriptor, prompt, manifest, provider):
    """Adopt a raw completed reply with explicit timing warnings; never edit its values."""
    source, target = Path(source).resolve(), Path(target)
    meta, request = read_json(source / 'metadata.json'), read_json(source / 'request.json')
    require(meta.get('http_status') == 200 and meta.get('finish_reason') == 'stop', 'Not a completed model reply')
    require(request['inference']['model'] == provider['model'], 'Imported audio model differs')
    require(request['image_count'] == 0 and request['audio_count'] == 1, 'Imported reply was not audio-only')
    require(request['attachments'][0]['sha256'] == manifest['audio']['sha256'], 'Imported audio differs')
    raw = (source / 'response.txt').read_text(encoding='utf-8')
    result = parse_model_json(raw)
    warnings = validate_transcript(result, manifest)
    save_request(target, descriptor, prompt)
    (target / 'imported_response.txt').write_text(raw, encoding='utf-8')
    (target / 'imported_prompt.txt').write_bytes((source / 'prompt.txt').read_bytes())
    write_json(target / 'imported_api_metadata.json', meta)
    write_json(target / 'result.json', result)
    write_json(target / 'metadata.json', {'status': 'complete', 'signature': descriptor['signature'],
        'api_call_made': False, 'imported_from': str(source), 'source_response_sha256': file_hash(source / 'response.txt'),
        'result_sha256': file_hash(target / 'result.json'), 'accepted_response_path': 'imported_response.txt',
        'note': 'Offline adoption under soft timing validation; raw model values unchanged; API usage belongs to source run.'})
    write_json(target / 'human_review_warnings.json', warnings)
    return result


def review_schema(lexicon):
    return obj({'visual': output_schema('visual', lexicon),
                'change_log': arr(obj({'target': TEXT, 'change': TEXT, 'evidence': EVIDENCE})),
                'unresolved': arr(TEXT)})


def images(media_dir, frames):
    return [{'kind': 'image', 'path': str(media_dir / f['file']),
             **{k: f[k] for k in ('index', 'time', 'shot_id', 'sha256')}} for f in frames]


def make_audio_spec(manifest, media_dir, provider, protocol):
    prompt = (PACKAGE / 'prompts/audio_transcript.txt').read_text(encoding='utf-8')
    prompt += '\nOUTPUT JSON SCHEMA:\n' + json.dumps(schema_for('audio'), ensure_ascii=False)
    prompt += '\nCALLER DATA:\n' + json.dumps({'duration_seconds': manifest['duration'],
        'time_origin': 'clip_start', 'audio_valid_span': manifest['audio']['valid_span']})
    media = [{'kind': 'audio', 'path': str(media_dir / manifest['audio']['file']), 'sha256': manifest['audio']['sha256']}]
    return describe_request('audio_transcript', prompt, media, provider,
                            {'protocol': protocol, 'source_sha256': manifest['source_sha256']}), prompt, media


def make_gpt_spec(stage, baseline, manifest, media_dir, lexicon, provider, protocol, frames, candidates=None):
    if stage == 'gpt_visual':
        # Exactly the baseline first-pass prompt; no baseline predictions are supplied.
        prompt = (baseline / 'badminton/stages/visual/prompt.txt').read_text(encoding='utf-8')
    else:
        rules = (baseline / 'protocol_files/prompts/hierarchical_visual.txt').read_text(encoding='utf-8')
        prompt = ('VISUAL-ONLY REVIEW. Review your own candidates against the supplied source frames. '
                  'No audio or transcript is available. Preserve the BWF hierarchy and vocabulary below. '
                  'Check visible foot sequences, movement directions, actor identities, chronology, '
                  'duplicate actions and completeness. Candidates are fallible, not ground truth. '
                  'Correct only what visible evidence supports; do not invent a repeat cycle. '
                  'Return a complete visual object, a change_log with evidence for each change, and unresolved issues. '
                  'Write concise Chinese. The output schema below supersedes any output-format instruction in the rules.\n' + rules)
        prompt += '\nOUTPUT JSON SCHEMA:\n' + json.dumps(review_schema(lexicon), ensure_ascii=False)
        prompt += '\nCALLER DATA:\n' + json.dumps({'duration_seconds': manifest['duration'],
            'time_origin': 'clip_start', 'shots': manifest['shots'], 'lexicon': lexicon,
            'supplied_frames': [{k: f[k] for k in ('index', 'time', 'shot_id')} for f in frames],
            'candidates': candidates}, ensure_ascii=False)
    media = images(media_dir, frames)
    return describe_request(stage, prompt, media, provider, {'protocol': protocol,
        'source_sha256': manifest['source_sha256'], 'baseline_predictions_supplied': False,
        'own_candidate_hash': object_hash(candidates) if candidates else None}), prompt, media


def export_variant(folder, visual, audio, manifest, lexicon, visual_origin, warnings):
    folder.mkdir(parents=True, exist_ok=True)
    graph = nominal_relations(visual, audio, manifest)
    summary = {'status': 'model_candidates_not_human_gt',
        'motion_count': sum(a['kind'] == 'motion' for a in visual['actions']),
        'held_pose_count': sum(a['kind'] == 'held_pose' for a in visual['actions']),
        'gesture_count': sum(a['kind'] == 'gesture' for a in visual['actions']),
        'subphase_count': sum(len(a['subphases']) for a in visual['actions']),
        'audio_count': len(audio['events']), 'speech_count': sum(e['kind'] == 'speech' for e in audio['events']),
        'motion_labels': dict(Counter(a['label'] for a in visual['actions'] if a['kind'] == 'motion'))}
    write_json(folder / 'annotations.json', {'source_sha256': manifest['source_sha256'], 'duration': manifest['duration'],
        'visual_origin': visual_origin, 'audio_origin': 'Qwen audio-only verbatim transcription',
        'visual': visual, 'audio': audio, 'relations': graph, 'human_verified': False})
    write_json(folder / 'summary.json', summary)
    write_json(folder / 'relations.json', graph)
    export_readable(folder, visual, audio, graph, summary, warnings, lexicon)
    path = folder / 'badminton_BWF_人工审阅.txt'
    text = path.read_text(encoding='utf-8')
    text = text.replace('羽毛球｜BWF 分层技术词表｜Qwen 实际运行', '羽毛球｜BWF 分层技术词表｜' + visual_origin, 1)
    text = text.replace('模型候选及同模型复核，不是人工 GT。所有描述和时间保留模型结果。',
                        '视觉来源见标题；音频由 Qwen 独立重新转写。原模型内容保留，尚未人工验证。', 1)
    for event in audio['events']:
        if event['kind'] == 'speech':
            original = f"{event['id']}｜{event['start']:.3f}–{event['end']:.3f} 秒｜{event['kind']} / {event['layer']}｜{event['description']}"
            replacement = original + f"\n  说话人：{event['speaker_id'] or '未确定'}\n  原话：“{event['transcript']}”"
            text = text.replace(original, replacement)
    path.write_text(text, encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['audio', 'gpt', 'export'], required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--reuse-audio-stage', type=Path)
    parser.add_argument('--image-max-width', type=int, default=1280)
    parser.add_argument('--max-review-frames', type=int, default=160)
    args = parser.parse_args(argv)
    baseline, run = args.baseline.resolve(), args.run_dir.resolve()
    require(baseline != run and baseline not in run.parents, 'Use a separate run directory')
    config, root = load_config(PACKAGE / 'config/five_videos_general_rules.json')
    config = copy.deepcopy(config)
    require(args.image_max_width in (640, 960, 1280), 'Unsupported image width')
    config['media']['max_frame_width'] = args.image_max_width
    config['media']['max_review_frames'] = args.max_review_frames
    if args.image_max_width < 1280:
        config['media']['jpeg_quality'] = 70
    case = next(c for c in config['cases'] if c['id'] == 'badminton')
    config['cases'] = [case]
    config['experiment'] = 'bwf_gpt_visual_qwen_verbatim_v1'
    config['baseline_annotations_sha256'] = file_hash(baseline / 'badminton/annotations.json')
    config['baseline_visual_prompt_sha256'] = file_hash(baseline / 'badminton/stages/visual/prompt.txt')
    config['gpt_provider'] = {'base_url': 'https://api.openai.com/v1', 'model': 'gpt-6.2-sol',
        'api_style': 'openai_chat', 'api_key_env': 'OPENAI_API_KEY', 'max_tokens': 24576,
        'image_detail': 'high', 'transport': 'requests', 'connect_timeout_seconds': 120,
        'request_timeout_seconds': 300, 'max_validation_repairs': 1,
        'extra_body': {'reasoning_effort': 'medium', 'store': False}}
    config['provider']['max_validation_repairs'] = 1
    protocol = bind_run(run, config)
    out = run / 'badminton'
    media_dir = out / 'media'
    manifest = prepare(root / case['source'], media_dir, config['media'], optional_cuts(root, case))
    original = read_json(baseline / 'badminton/annotations.json')
    old_manifest = read_json(baseline / 'badminton/media/manifest.json')
    require(original['source_sha256'] == manifest['source_sha256'], 'Baseline source differs')
    frame_identity = lambda m: [(f['index'], f['time'], f['shot_id']) for f in m['frames']]
    require(frame_identity(old_manifest) == frame_identity(manifest), 'First-pass source frame times differ from baseline')
    lexicon = read_json(baseline / 'badminton/runtime_lexicon.json')
    write_json(out / 'runtime_lexicon.json', lexicon)
    write_json(run / 'comparison_policy.json', {'visual_baseline': str(baseline),
        'baseline_role': 'preferred model output, not human ground truth',
        'gpt_first_pass_prompt_identical': True, 'gpt_first_pass_frame_times_identical': True,
        'gpt_first_pass_image_bytes_identical': old_manifest['frames'] == manifest['frames'],
        'image_max_width': args.image_max_width, 'jpeg_quality': config['media']['jpeg_quality'],
        'gpt_baseline_answers_supplied': False,
        'gpt_audio_supplied': False, 'qwen_transcript_visual_context_supplied': False,
        'same_new_audio_used_for_both_visual_outputs': True, 'gpt_review_is_visual_only': True,
        'comparison_limit': 'Prior Qwen final review used original audio; GPT review is visual-only. This is not a controlled model benchmark.',
        'local_fps': 10, 'api_fps_parameter_used': False})
    cache = {}
    def key(provider):
        name = provider['api_key_env']
        if name not in cache:
            cache[name] = os.environ.get(name) or getpass.getpass(name + ' (hidden, not saved): ')
        return cache[name]
    print(f"Prepared {len(manifest['frames'])} original frames, {manifest['duration']} seconds", flush=True)
    if args.mode == 'audio':
        provider = config['provider']
        spec = make_audio_spec(manifest, media_dir, provider, protocol)
        save_request(out / 'stages/audio_transcript', spec[0], spec[1])
        if not args.dry_run:
            if args.reuse_audio_stage:
                audio = import_completed_audio(args.reuse_audio_stage, out / 'stages/audio_transcript',
                                               spec[0], spec[1], manifest, provider)
            else:
                audio = execute(out / 'stages/audio_transcript', *spec, provider, lambda: key(provider),
                                lambda data: validate_transcript(data, manifest))
            audio_warnings = validate_transcript(audio, manifest)
            write_json(out / 'stages/audio_transcript/human_review_warnings.json', audio_warnings)
            write_json(out / 'audio_transcript.json', audio)
            summary = export_variant(out / 'qwen_bwf_with_transcript', original['visual'], audio, manifest, lexicon,
                                     '原 BWF Qwen 视觉结果 + 新 Qwen 转写',
                                     {'original_visual_run': original.get('warnings', {}), 'new_audio': audio_warnings})
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    elif args.mode == 'gpt':
        provider = config['gpt_provider']
        spec = make_gpt_spec('gpt_visual', baseline, manifest, media_dir, lexicon, provider, protocol, manifest['frames'])
        save_request(out / 'stages/gpt_visual', spec[0], spec[1])
        if not args.dry_run:
            notes = []
            def validator(data):
                notes[:] = validate_draft('visual', data, manifest, lexicon, manifest['frames'])
            visual = execute(out / 'stages/gpt_visual', *spec, provider, lambda: key(provider), validator)
            write_json(out / 'stages/gpt_visual/human_review_warnings.json', notes)
            print('GPT first visual pass complete', flush=True)
            plan = prepare_review(media_dir, manifest, visual, {'events': []}, config['media'], 76 * 1024 * 1024)
            review_spec = make_gpt_spec('gpt_review', baseline, manifest, media_dir, lexicon, provider, protocol, plan['frames'], visual)
            def review_validator(data):
                check_finite(data)
                Draft202012Validator(review_schema(lexicon)).validate(data)
                notes[:] = validate_draft('visual', data['visual'], manifest, lexicon, plan['frames'])
                if data['visual'] != visual and not data['change_log']:
                    notes.append('Visual review changed candidates without a change log')
            review = execute(out / 'stages/gpt_review', *review_spec, provider, lambda: key(provider), review_validator)
            write_json(out / 'stages/gpt_review/human_review_warnings.json', notes)
            print('GPT visual review complete', flush=True)
    else:
        audio = read_json(out / 'stages/audio_transcript/result.json')
        review = read_json(out / 'stages/gpt_review/result.json')
        notes = read_json(out / 'stages/gpt_review/human_review_warnings.json')
        summary = export_variant(out / 'gpt_sol_with_qwen_transcript', review['visual'], audio, manifest, lexicon,
                                 'GPT-6.2 Sol 视觉标注及复核 + Qwen 转写',
                                 {'gpt_review': notes, 'audio': validate_transcript(audio, manifest)})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    print('Finished mode:', args.mode, 'dry_run:', args.dry_run, flush=True)


if __name__ == '__main__':
    main()
