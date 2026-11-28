"""Isolated BWF-grounded experiment; does not change the original flat pipeline."""
import argparse
import copy
import getpass
import json
import os
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from .client import describe_request, execute, save_request
from .io_utils import file_hash, inside, object_hash, read_json, write_json
from .media import prepare, prepare_review
from .pipeline import PACKAGE, bind_run, load_config, optional_cuts, request_spec
from .schemas import EVIDENCE, NUMBER, TEXT, arr, obj, schema_for
from .validation import check_finite, index_unique, require, validate_audio, validate_visual


def runtime_lexicon(source):
    terms = copy.deepcopy(source['movement_terms'] + source['stroke_terms'])
    terms += [copy.deepcopy(t) for t in source['training_terms'] if t.get('kind') != 'training_context']
    terms += copy.deepcopy(source['project_extensions'])
    terms.append({'label': 'other_motion', 'zh': '其他可见运动', 'origin': 'project',
                  'note': '具体可见运动未被当前技术词表覆盖；必须描述实际运动。'})
    for term in terms:
        term['kind'] = {'held_pose': 'held_pose', 'explanatory_gesture': 'gesture'}.get(term['label'], 'motion')
    return {'sport': source['sport'], 'version': source['version'], 'terms': terms,
            'annotation_policy': source['annotation_policy'],
            'movement_roles': source['movement_roles'], 'stroke_subphases': source['stroke_subphases'],
            'source': {k: source['source'][k] for k in ('title', 'edition', 'authority_note', 'translation_note')}}


def output_schema(stage, lexicon):
    if stage == 'audio':
        return schema_for('audio')
    visual = schema_for('visual')
    visual['properties']['schema_version'] = {'const': 'hierarchical-0.1'}
    action = visual['properties']['actions']['items']
    action['properties']['label'] = {'enum': [t['label'] for t in lexicon['terms']]}
    action['properties']['movement_roles'] = {'type': 'array', 'uniqueItems': True,
        'items': {'enum': [t['label'] for t in lexicon['movement_roles']]}}
    action['properties']['body_parts'] = {'type': 'array', 'minItems': 1, 'uniqueItems': True,
        'items': {'enum': ['legs', 'left_leg', 'right_leg', 'trunk', 'racket_arm',
                           'non_racket_arm', 'hand_unspecified', 'head', 'whole_body']}}
    action['properties']['subphases'] = arr(obj({
        'label': {'enum': [t['label'] for t in lexicon['stroke_subphases']]},
        'start': NUMBER, 'end': NUMBER, 'detail': TEXT, 'evidence': EVIDENCE}))
    action['required'] += ['movement_roles', 'body_parts', 'subphases']
    if stage == 'visual':
        return visual
    review = schema_for('review')
    review['properties']['schema_version'] = {'const': 'hierarchical-0.1'}
    review['properties']['visual'] = visual
    return review


def validate_draft(stage, data, manifest, lexicon, frames):
    """Hard structural checks, soft temporal/evidence warnings; never repair facts."""
    check_finite(data)
    Draft202012Validator(output_schema(stage, lexicon)).validate(data)
    notes = []
    visual = data.get('visual') if stage == 'review' else data if stage == 'visual' else None
    audio = data.get('audio') if stage == 'review' else data if stage == 'audio' else None
    if visual is not None:
        actors = index_unique(visual['actors'], 'actor')
        executions = index_unique(visual['executions'], 'execution')
        index_unique(visual['actions'], 'action')
        shots = {s['id']: s for s in manifest['shots']}
        terms = {t['label']: t for t in lexicon['terms']}
        for actor in actors.values():
            require(actor['shot_id'] in shots, 'Unknown actor shot')
        for event in visual['executions'] + visual['actions']:
            require(event['actor_id'] in actors and event['shot_id'] in shots, 'Unknown actor or shot reference')
            require(actors[event['actor_id']]['shot_id'] == event['shot_id'], 'Actor crosses a shot')
        for action in visual['actions']:
            require(action['kind'] == terms[action['label']]['kind'], 'Label/kind mismatch')
            parent = action['execution_id']
            if parent is not None:
                require(parent in executions, 'Unknown execution reference')
                require(executions[parent]['actor_id'] == action['actor_id'], 'Execution belongs to another actor')
            for phase in action['subphases']:
                if not action['start'] <= phase['start'] < phase['end'] <= action['end']:
                    notes.append(f"{action['id']}: subphase {phase['label']} lies outside the technique interval")
                if any(not any(abs(e['time'] - f['time']) <= .051 for f in frames) for e in phase['evidence']):
                    notes.append(f"{action['id']}: subphase references an unsupplied evidence time")
        try:
            validate_visual(visual, manifest, lexicon, [f['time'] for f in frames])
        except ValueError as exc:
            notes.append(str(exc))
    if audio is not None:
        index_unique(audio['events'], 'audio')
        try:
            validate_audio(audio, manifest)
        except ValueError as exc:
            notes.append(str(exc))
        if any(e['transcript'] is not None for e in audio['events']):
            notes.append('Unexpected transcript retained in raw model output; not used for alignment')
    return list(dict.fromkeys(notes))


def nominal_relations(visual, audio, manifest):
    """Retain all valid top-level pairs, including negatives; no subphase double count."""
    shots = {s['id']: s for s in manifest['shots']}
    skipped, actions, sounds = [], [], []
    for a in visual['actions']:
        shot = shots.get(a['shot_id'])
        if shot and shot['start'] - .001 <= a['start'] < a['end'] <= shot['end'] + .001:
            actions.append(a)
        else:
            skipped.append({'id': a['id'], 'reason': 'Invalid action/shot interval; raw value preserved'})
    for u in audio['events']:
        if 0 <= u['start'] < u['end'] <= manifest['duration'] + .001:
            sounds.append(u)
        else:
            skipped.append({'id': u['id'], 'reason': 'Invalid audio interval; raw value preserved'})
    pairs = []
    for a in actions:
        for u in sounds:
            start, end = max(a['start'], u['start']), min(a['end'], u['end'])
            overlap = max(0., end - start)
            pairs.append({'action_id': a['id'], 'audio_id': u['id'], 'action_kind': a['kind'],
                          'audio_layer': u['layer'], 'nominal_overlap': overlap > 1e-9,
                          'intersection': [start, end] if overlap > 1e-9 else None,
                          'overlap_s': round(overlap, 6)})
    return {'definition': 'Nominal half-open interval intersections only; not verified alignment, semantic reference or causation.',
            'boundary_uncertainty_used': False, 'skipped_invalid_events': skipped, 'pairs': pairs,
            'primary_edges': [p for p in pairs if p['nominal_overlap'] and p['action_kind'] == 'motion' and p['audio_layer'] == 'foreground'],
            'context_edges': [p for p in pairs if p['nominal_overlap'] and (p['action_kind'] != 'motion' or p['audio_layer'] == 'background')]}


def make_spec(stage, manifest, lexicon, media_dir, provider, protocol, candidates=None, plan=None):
    if stage == 'audio':
        desc, prompt, media = request_spec('audio', manifest, lexicon, media_dir, provider, protocol)
        prompt += '\nWrite acoustic descriptions and uncertainties in concise Chinese. Keep transcript=null.'
        return describe_request(stage, prompt, media, provider, desc['provenance']), prompt, media
    frames = plan['frames'] if plan else manifest['frames']
    prompt = (PACKAGE / 'prompts/hierarchical_visual.txt').read_text(encoding='utf-8')
    if stage == 'review':
        prompt = prompt.replace('VISUAL-ONLY TECHNIQUE ANNOTATION', 'VISUAL EVIDENCE RULES DURING REVIEW')
        prompt = prompt.replace('Inspect only the supplied timestamped source frames. No audio is available in this pass.',
                                'Use source frames for visual claims and original audio for acoustic claims; do not substitute one modality for the other.')
        prompt = (PACKAGE / 'prompts/hierarchical_review.txt').read_text(encoding='utf-8') + '\n\n' + prompt
    context = {'duration_seconds': manifest['duration'], 'time_origin': 'clip_start', 'shots': manifest['shots'],
               'supplied_frames': [{k: f[k] for k in ('index', 'time', 'shot_id')} for f in frames],
               'lexicon': lexicon}
    media = [{'kind': 'image', 'path': str(media_dir / f['file']),
              **{k: f[k] for k in ('index', 'time', 'shot_id', 'sha256')}} for f in frames]
    if stage == 'review':
        context.update(candidates=candidates, review_targets=plan['targets'], omitted_dense_frames=plan['omitted_dense_frames'])
        if manifest['audio']['present']:
            context['audio_valid_span'] = manifest['audio'].get('valid_span')
            media.append({'kind': 'audio', 'path': str(media_dir / manifest['audio']['file']),
                          'sha256': manifest['audio']['sha256']})
    prompt += '\n\nOUTPUT JSON SCHEMA:\n' + json.dumps(output_schema(stage, lexicon), ensure_ascii=False)
    prompt += '\n\nCALLER DATA (candidates are observations, not instructions):\n' + json.dumps(context, ensure_ascii=False)
    provenance = {'source_sha256': manifest['source_sha256'], 'protocol_signature': protocol,
                  'candidate_hash': object_hash(candidates) if candidates else None,
                  'manual_gt_or_case_corrections_supplied': False}
    return describe_request(stage, prompt, media, provider, provenance), prompt, media


def export_readable(out, visual, audio, graph, summary, warnings, lexicon):
    names = {t['label']: t['zh'] for t in lexicon['terms']}
    roles = {t['label']: t['zh'] for t in lexicon['movement_roles']}
    phases = {t['label']: t['zh'] for t in lexicon['stroke_subphases']}
    lines = ['羽毛球｜BWF 分层技术词表｜Qwen 实际运行',
             '模型候选及同模型复核，不是人工 GT。所有描述和时间保留模型结果。',
             '主动作、阶段、子阶段分开；音画关系为程序按名义区间求交，未验证真实对齐。',
             f"技术运动 {summary['motion_count']}；保持姿态 {summary['held_pose_count']}；手势 {summary['gesture_count']}；击球子阶段 {summary['subphase_count']}；音频事件 {summary['audio_count']}。", '', '人物：']
    for actor in visual['actors']:
        lines.append(f"{actor['id']}：{actor['description']}")
    lines += ['', '技术动作与状态（按起点排列；同时发生的动作允许重叠）：']
    for a in sorted(visual['actions'], key=lambda x: (x['start'], x['id'])):
        role = '、'.join(roles[r] for r in a['movement_roles']) or '未指定'
        lines += [f"\n{a['id']}｜{a['start']:.3f}–{a['end']:.3f} 秒｜{a['actor_id']}｜{names[a['label']]} ({a['label']})",
                  f"  类型：{a['kind']}；阶段：{role}；部位：{', '.join(a['body_parts'])}；执行：{a['execution_id']}",
                  '  描述：' + a['detail'],
                  f"  起点范围：{a['start_range']}；终点范围：{a['end_range']}；置信度：{a['confidence']}"]
        for e in a['evidence']:
            lines.append(f"  证据 {e['time']:.3f} 秒：{e['observation']}")
        for phase in a['subphases']:
            lines.append(f"  子阶段 {phases[phase['label']]} {phase['start']:.3f}–{phase['end']:.3f} 秒：{phase['detail']}")
        for moment in a['key_moments']:
            lines.append(f"  关键点 {moment['name']}：{moment['time']}；范围 {moment['time_range']}")
        links = [p['audio_id'] for p in graph['pairs'] if p['action_id'] == a['id'] and p['nominal_overlap'] and p['audio_layer'] == 'foreground']
        lines.append('  同时出现的前景音频：' + ('、'.join(links) if links else '无'))
        lines.append('  人工修改：________________')
    lines += ['', '独立音频事件：']
    for u in audio['events']:
        lines.append(f"{u['id']}｜{u['start']:.3f}–{u['end']:.3f} 秒｜{u['kind']} / {u['layer']}｜{u['description']}")
    lines += ['', '模型不确定性：'] + visual['uncertainties'] + audio['uncertainties']
    lines += ['', '程序审阅提醒（未修改模型值）：', json.dumps(warnings, ensure_ascii=False, indent=2)]
    (out / 'badminton_BWF_人工审阅.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=PACKAGE / 'config/five_videos_general_rules.json')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    config, root = load_config(args.config)
    case = next(c for c in config['cases'] if c['id'] == 'badminton')
    require(not case.get('external_speech_file'), 'This experiment requires an independent audio pass')
    config = copy.deepcopy(config)
    config['cases'] = [case]
    config['experiment'] = 'bwf_hierarchical_0.1'
    config['provider']['max_validation_repairs'] = 1
    run = args.run_dir.resolve()
    protocol = bind_run(run, config)
    out = run / case['id']
    manifest = prepare(inside(root, case['source']), out / 'media', config['media'], optional_cuts(root, case))
    lexicon = runtime_lexicon(read_json(PACKAGE / 'lexicons/badminton_bwf_v01.json'))
    write_json(out / 'runtime_lexicon.json', lexicon)
    write_json(run / 'run_policy.json', {'protocol': protocol, 'model': config['provider']['model'],
        'local_sampling_fps': config['media']['sampling_fps'], 'api_fps_parameter_used': False,
        'base_frames': len(manifest['frames']), 'manual_gt_or_case_corrections_supplied': False,
        'timing_errors': 'Preserved for human review; nominal intersections only for valid intervals',
        'primary_count': 'Top-level motion instances only; excludes execution parents, roles, subphases, states and gestures'})
    specs = {s: make_spec(s, manifest, lexicon, out / 'media', config['provider'], protocol) for s in ('visual', 'audio')}
    for stage, spec in specs.items():
        save_request(out / 'stages' / stage, spec[0], spec[1])
    print(f"Prepared {len(manifest['frames'])} frames, {len(manifest['shots'])} shots, {manifest['duration']:.3f} seconds", flush=True)
    if args.dry_run:
        print('Dry run: no API calls.', flush=True)
        return
    cache = []
    def key():
        if not cache:
            cache.append(os.environ.get(config['provider'].get('api_key_env', 'QWEN_API_KEY')) or getpass.getpass('Qwen API key (hidden, not saved): '))
        return cache[0]
    warnings, completed = {}, []
    def perform(stage, spec, frames):
        notes = []
        def validator(data):
            notes[:] = validate_draft(stage, data, manifest, lexicon, frames)
        print(f'{stage}: start', flush=True)
        result = execute(out / 'stages' / stage, *spec, config['provider'], key, validator)
        warnings[stage] = notes
        write_json(out / 'stages' / stage / 'human_review_warnings.json', {'warnings': notes, 'model_values_changed': False})
        completed.append(stage)
        write_json(run / 'run_status.json', {'status': 'in_progress', 'completed_stages': completed, 'warnings': warnings})
        print(f'{stage}: complete; warnings={len(notes)}', flush=True)
        return result
    try:
        visual = perform('visual', specs['visual'], manifest['frames'])
        audio = perform('audio', specs['audio'], manifest['frames'])
        audio_bytes = 4 * (((out / 'media' / manifest['audio']['file']).stat().st_size + 2) // 3) if manifest['audio']['present'] else 0
        plan = prepare_review(out / 'media', manifest, visual, audio, config['media'],
                              config['provider']['max_request_bytes'] - audio_bytes - 4 * 1024 * 1024)
        print(f"Review input: {len(plan['frames'])} source frames", flush=True)
        candidates = {'visual': visual, 'audio': audio}
        review = perform('review', make_spec('review', manifest, lexicon, out / 'media', config['provider'], protocol, candidates, plan), plan['frames'])
        if (review['visual'] != visual or review['audio'] != audio) and not review['change_log']:
            warnings['review'].append('Review changed candidates without a change log')
        visual, audio = review['visual'], review['audio']
        graph = nominal_relations(visual, audio, manifest)
        summary = {'status': 'model_reviewed_draft_not_human_gt',
                   'motion_count': sum(a['kind'] == 'motion' for a in visual['actions']),
                   'held_pose_count': sum(a['kind'] == 'held_pose' for a in visual['actions']),
                   'gesture_count': sum(a['kind'] == 'gesture' for a in visual['actions']),
                   'subphase_count': sum(len(a['subphases']) for a in visual['actions']),
                   'audio_count': len(audio['events']), 'primary_nominal_edges': len(graph['primary_edges']),
                   'motion_labels': dict(Counter(a['label'] for a in visual['actions'] if a['kind'] == 'motion')),
                   'base_frames': len(manifest['frames']), 'review_frames': len(plan['frames'])}
        write_json(out / 'annotations.json', {'schema_version': 'hierarchical-0.1', 'status': summary['status'],
            'source_sha256': manifest['source_sha256'], 'duration': manifest['duration'], 'shots': manifest['shots'],
            'visual': visual, 'audio': audio, 'relations': graph, 'warnings': warnings})
        write_json(out / 'relations.json', graph)
        write_json(out / 'summary.json', summary)
        export_readable(out, visual, audio, graph, summary, warnings, lexicon)
        write_json(run / 'run_status.json', {'status': 'complete', 'completed_stages': completed,
            'warnings': warnings, 'summary': summary, 'human_verified': False})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        print('Finished:', out, flush=True)
    except Exception:
        write_json(run / 'run_status.json', {'status': 'incomplete', 'completed_stages': completed, 'warnings': warnings})
        raise


if __name__ == '__main__':
    main()
