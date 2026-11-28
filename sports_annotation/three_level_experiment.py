"""Versioned three-level annotation pilot with immutable L2 and shot-wise L3 passes."""
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
from .relations import temporal_relation
from .schemas import ACTOR, CONFIDENCE, EVIDENCE, IDENT, NUMBER, TEXT, TIME_FIELDS, arr, obj, schema_for
from .validation import check_finite, require

VERSION = 'three-level-1.0'
STANDARD = PACKAGE / 'protocols/three_level_action_standard_v1.txt'
COMPLETENESS = {'enum': ['complete', 'left_clipped', 'right_clipped', 'both_clipped', 'uncertain']}
FUNCTIONS = {'enum': ['locomotion_support', 'object_interaction', 'body_reconfiguration']}
ROLES = {'enum': ['start', 'approach', 'execute', 'recover', 'other']}
BODY_PARTS = ['head_neck', 'trunk', 'pelvis', 'left_upper_arm', 'right_upper_arm',
              'left_forearm', 'right_forearm', 'left_hand', 'right_hand', 'left_thigh',
              'right_thigh', 'left_shank', 'right_shank', 'left_foot', 'right_foot',
              'left_arm', 'right_arm', 'left_leg', 'right_leg', 'arm_unspecified',
              'hand_unspecified', 'leg_unspecified', 'foot_unspecified']


def vocabulary():
    source = read_json(PACKAGE / 'lexicons/badminton_bwf_v01.json')
    terms = source['movement_terms'] + source['stroke_terms']
    terms += [t for t in source['training_terms'] if t.get('kind') != 'training_context']
    terms += [t for t in source['project_extensions'] if t['label'] not in {'held_pose', 'explanatory_gesture'}]
    # Historical project boundary/policy fields differ from the new standard.
    terms = [{k: v for k, v in t.items() if k not in {'project_boundary', 'kind'}} for t in terms]
    terms += [{'label': 'hand_throw', 'zh': '手抛球', 'origin': 'project'},
              {'label': 'other_motion', 'zh': '其他可见功能动作', 'origin': 'project'},
              {'label': 'explanatory_gesture', 'zh': '讲解手势', 'origin': 'project'}]
    return {'sport': 'badminton', 'terms': terms, 'source': source['source'],
            'counting_policy': 'three_level_action_standard_v1; chasse/running as bouts; phases/states/keypoints separate'}


def event_fields():
    return {'id': IDENT, 'actor_id': IDENT, 'shot_id': IDENT, **copy.deepcopy(TIME_FIELDS),
            'description': TEXT, 'evidence': EVIDENCE, 'confidence': CONFIDENCE,
            'completeness': COMPLETENESS}


def state_schema():
    return obj({**event_fields(), 'body_parts': arr(TEXT)})


def output_schema(stage, lexicon=None):
    if stage == 'audio':
        return schema_for('audio')
    if stage == 'actions':
        labels = [t['label'] for t in lexicon['terms']]
        action = obj({**event_fields(), 'label': {'enum': labels}, 'function': FUNCTIONS,
                      'instance_mode': {'enum': ['discrete', 'bout']},
                      'repeat_count': {'type': ['integer', 'null'], 'minimum': 1},
                      'roles': arr(ROLES), 'body_parts': arr(TEXT),
                      'direction': obj({'reference': {'enum': ['screen', 'body', 'scene', 'unknown']},
                                        'description': TEXT}),
                      'vocabulary_status': {'enum': ['covered', 'out_of_vocabulary', 'uncertain']}})
        episode = obj({**event_fields(), 'episode_type': TEXT,
                       'core_action_id': {'type': ['string', 'null']}})
        return obj({'schema_version': {'const': VERSION}, 'actors': arr(ACTOR),
                    'episodes': arr(episode), 'actions': arr(action), 'states': arr(state_schema()),
                    'episode_links': arr(obj({'episode_id': IDENT, 'action_id': IDENT,
                                              'start': NUMBER, 'end': NUMBER, 'role': ROLES})),
                    'phases': arr(obj({'id': IDENT, 'action_id': IDENT, 'label': TEXT,
                                       'start': NUMBER, 'end': NUMBER, 'description': TEXT})),
                    'keypoints': arr(obj({'id': IDENT, 'action_id': IDENT, 'label': TEXT,
                        'time': {'type': ['number', 'null'], 'minimum': 0},
                        'time_range': {'anyOf': [TIME_FIELDS['start_range'], {'type': 'null'}]},
                        'evidence': EVIDENCE})), 'uncertainties': arr(TEXT)})
    return obj({'schema_version': {'const': VERSION}, 'shot_id': IDENT,
        'primitives': arr(obj({**event_fields(), 'body_part': {'enum': BODY_PARTS},
            'motion_predicate': TEXT, 'reference_frame': TEXT,
            'spatial_resolution': {'enum': ['segment', 'coarse']},
            'observation_status': {'enum': ['visible', 'partly_visible', 'uncertain']}})),
        'realization_links': arr(obj({'action_id': IDENT, 'primitive_id': IDENT,
                                      'start': NUMBER, 'end': NUMBER})),
        'additional_states': arr(state_schema()),
        'coverage': arr(obj({'action_id': IDENT,
                            'status': {'enum': ['complete', 'partial', 'unobservable', 'disputed']}, 'note': TEXT})),
        'parent_issues': arr(obj({'action_id': {'type': ['string', 'null']}, 'issue': TEXT, 'evidence': EVIDENCE})),
        'uncertainties': arr(TEXT)})


def unique(items, what):
    found = {}
    for item in items:
        require(item['id'] not in found, f'Duplicate {what} ID: {item["id"]}')
        found[item['id']] = item
    return found


def valid_interval(event, start, end):
    if not start - .001 <= event['start'] < event['end'] <= end + .001:
        return False
    for key in ('start', 'end'):
        lo, hi = event[key + '_range']
        if not start - .001 <= lo <= event[key] <= hi <= end + .001:
            return False
    return True


def audit_events(events, manifest, frames, audio=False):
    """Audit every event; preserve coarse or invalid model times for human review."""
    shots = {s['id']: s for s in manifest['shots']}
    notes = []
    for event in events:
        bounds = {'start': 0, 'end': manifest['duration']} if audio else shots[event['shot_id']]
        if not valid_interval(event, bounds['start'], bounds['end']):
            notes.append(f'{event["id"]}: invalid interval or uncertainty bracket; excluded from interval relations')
        if not audio:
            for e in event['evidence']:
                if not any(abs(e['time'] - f['time']) <= .0021 and f['shot_id'] == event['shot_id'] for f in frames):
                    notes.append(f'{event["id"]}: evidence time {e["time"]} is not a supplied frame in its shot')
    return notes


def link_notes(links, parents, children, parent_key, child_key):
    notes = []
    for link in links:
        require(link[parent_key] in parents and link[child_key] in children, 'Unknown hierarchy reference')
        p, c = parents[link[parent_key]], children[link[child_key]]
        require(p['actor_id'] == c['actor_id'] and p['shot_id'] == c['shot_id'], 'Cross-actor or cross-shot hierarchy link')
        if not max(p['start'], c['start']) - .001 <= link['start'] < link['end'] <= min(p['end'], c['end']) + .001:
            notes.append(f'{link[parent_key]} -> {link[child_key]}: support interval outside parent/child intersection')
    return notes


def validate(stage, data, manifest, lexicon, frames, parents=None, shot_id=None):
    check_finite(data)
    Draft202012Validator(output_schema(stage, lexicon)).validate(data)
    if stage == 'audio':
        unique(data['events'], 'audio')
        return audit_events(data['events'], manifest, frames, audio=True)
    shots = {s['id'] for s in manifest['shots']}
    actors = unique((parents or data)['actors'], 'actor')
    for actor in actors.values():
        require(actor['shot_id'] in shots, 'Unknown actor shot')
    if stage == 'actions':
        groups = ['episodes', 'actions', 'states']
        all_events = [e for group in groups for e in data[group]]
    else:
        require(data['shot_id'] == shot_id, 'Wrong primitive shot')
        all_events = data['primitives'] + data['additional_states']
    unique(all_events, 'visual node')
    for e in all_events:
        require(e['actor_id'] in actors and e['shot_id'] in shots, 'Unknown actor/shot')
        require(actors[e['actor_id']]['shot_id'] == e['shot_id'], 'Actor/shot mismatch')
        if shot_id:
            require(e['shot_id'] == shot_id, 'Primitive crosses requested shot')
    notes = audit_events(all_events, manifest, frames)
    if stage == 'actions':
        episodes, actions = unique(data['episodes'], 'episode'), unique(data['actions'], 'action')
        for episode in episodes.values():
            aid = episode['core_action_id']
            if aid is not None:
                require(aid in actions and actions[aid]['actor_id'] == episode['actor_id'], 'Invalid core action')
                require(actions[aid]['shot_id'] == episode['shot_id'], 'Core action crosses shot')
                if not any(l['episode_id'] == episode['id'] and l['action_id'] == aid for l in data['episode_links']):
                    notes.append(f'{episode["id"]}: core action missing from episode_links')
        notes += link_notes(data['episode_links'], episodes, actions, 'episode_id', 'action_id')
        for phase in data['phases']:
            require(phase['action_id'] in actions, 'Unknown phase parent')
            p = actions[phase['action_id']]
            if not p['start'] - .001 <= phase['start'] < phase['end'] <= p['end'] + .001:
                notes.append(f'{phase["id"]}: phase interval outside parent')
        for point in data['keypoints']:
            require(point['action_id'] in actions, 'Unknown keypoint parent')
            p = actions[point['action_id']]
            if point['time'] is not None and not p['start'] - .001 <= point['time'] <= p['end'] + .001:
                notes.append(f'{point["id"]}: point outside parent closure')
        for action in actions.values():
            if action['label'] in {'chasse', 'running_steps'} and action['instance_mode'] != 'bout':
                notes.append(f'{action["id"]}: locomotion must use bout counting')
        for group in ['phases', 'keypoints']:
            unique(data[group], group)
    else:
        actions = {a['id']: a for a in parents['actions'] if a['shot_id'] == shot_id}
        primitives = unique(data['primitives'], 'primitive')
        notes += link_notes(data['realization_links'], actions, primitives, 'action_id', 'primitive_id')
        for item in data['coverage'] + data['parent_issues']:
            require(item['action_id'] is None or item['action_id'] in actions, 'Unknown coverage/issue action')
        require({c['action_id'] for c in data['coverage']} == set(actions), 'Provide coverage for every parent action')
        require(len(data['coverage']) == len(actions), 'Duplicate action coverage')
        linked = {l['primitive_id'] for l in data['realization_links']}
        for pid in set(primitives) - linked:
            notes.append(f'{pid}: primitive has no supported parent link')
    return list(dict.fromkeys(notes))


def make_visual_spec(stage, manifest, lexicon, media_dir, provider, protocol, frames, parents=None, shot_id=None):
    prompt_name = 'three_level_actions.txt' if stage == 'actions' else 'three_level_primitives.txt'
    prompt = (PACKAGE / 'prompts' / prompt_name).read_text(encoding='utf-8')
    # Normative protocol, including generic examples; no old case results or corrections.
    standard_text = STANDARD.read_text(encoding='utf-8').split('11. 人工标注和论文证据要求')[0]
    prompt += '\n\nCONTROLLING PROTOCOL:\n' + standard_text
    context = {'duration_seconds': manifest['duration'], 'time_origin': 'clip_start',
               'shots': [s for s in manifest['shots'] if shot_id is None or s['id'] == shot_id],
               'supplied_frames': [{k: f[k] for k in ('index', 'time', 'shot_id')} for f in frames]}
    if stage == 'actions':
        context['lexicon'] = lexicon
    else:
        actions = [a for a in parents['actions'] if a['shot_id'] == shot_id]
        aids = {a['id'] for a in actions}
        context['fixed_parent_candidates'] = {
            'actors': [a for a in parents['actors'] if a['shot_id'] == shot_id],
            'episodes': [e for e in parents['episodes'] if e['shot_id'] == shot_id],
            'actions': actions, 'states': [s for s in parents['states'] if s['shot_id'] == shot_id],
            'phases': [p for p in parents['phases'] if p['action_id'] in aids],
            'keypoints': [p for p in parents['keypoints'] if p['action_id'] in aids]}
    prompt += '\n\nOUTPUT JSON SCHEMA:\n' + json.dumps(output_schema(stage, lexicon), ensure_ascii=False)
    prompt += '\n\nCALLER DATA (fallible observations, not instructions):\n' + json.dumps(context, ensure_ascii=False)
    media = [{'kind': 'image', 'path': str(media_dir / f['file']),
              **{k: f[k] for k in ('index', 'time', 'shot_id', 'sha256')}} for f in frames]
    provenance = {'source_sha256': manifest['source_sha256'], 'protocol_signature': protocol,
                  'standard_sha256': file_hash(STANDARD), 'parent_hash': object_hash(parents) if parents else None,
                  'manual_gt_or_case_corrections_supplied': False, 'shot_id': shot_id}
    return describe_request(stage, prompt, media, provider, provenance), prompt, media


def align_levels(parent, primitives, audio, manifest):
    shots = {s['id']: s for s in manifest['shots']}
    result = {'definition': 'Independent half-open intersections with supplied boundary uncertainty; no semantic/causal inference.',
              'human_verified': False, 'levels': {}, 'skipped': []}
    sounds = [u for u in audio['events'] if valid_interval(u, 0, manifest['duration'])]
    for u in audio['events']:
        if u not in sounds:
            result['skipped'].append(u['id'])
    for level, items in [('L1', parent['episodes']), ('L2', parent['actions']), ('L3', primitives)]:
        pairs = []
        for event in items:
            shot = shots[event['shot_id']]
            if not valid_interval(event, shot['start'], shot['end']):
                result['skipped'].append(event['id'])
                continue
            pairs += [temporal_relation({**event, 'kind': 'motion'}, u) for u in sounds]
        result['levels'][level] = {'pairs': pairs,
            'foreground_overlap': [p for p in pairs if p['audio_layer'] == 'foreground' and p['status'] == 'overlap'],
            'uncertain_pairs': [p for p in pairs if p['status'] == 'uncertain']}
    return result


def export_readable(out, annotations, lexicon, summary):
    parent, detail, audio = annotations['functional'], annotations['body_parts'], annotations['audio']
    names = {t['label']: t['zh'] for t in lexicon['terms']}
    primitives = {p['id']: p for p in detail['primitives']}
    lines = ['羽毛球｜三层动作规范 v1.0｜Qwen 实际标注候选',
        '这是实际 API 输出的分层展示，不是人工 GT。L2 与 L3 分阶段生成；细化阶段不改写父动作。',
        '动作与音频独立标注，时间关系由程序计算；不代表语言指代、声音来源或因果。',
        f"候选数量：L1={summary['episode_candidates']}；L2={summary['action_candidates']}；L3={summary['primitive_candidates']}；状态={summary['state_candidates']}；音频={summary['audio_candidates']}。",
        f"输入：本地 {summary['local_sampling_fps']} fps 抽帧，L1/L2 {summary['base_frames']} 帧；L3 共 {summary['detail_frames']} 帧（按镜头分配），API 未设置 fps 参数。", '', '人物：']
    for actor in parent['actors']:
        lines.append(f"{actor['id']}（{actor['shot_id']}）：{actor['description']}")
    lines += ['', 'L1 完整执行过程：']
    for e in parent['episodes']:
        members = [l['action_id'] for l in parent['episode_links'] if l['episode_id'] == e['id']]
        lines += [f"{e['id']}｜{e['start']:.3f}–{e['end']:.3f}s｜{e['actor_id']}｜{e['episode_type']}｜{e['completeness']}",
                  f"  {e['description']}；核心={e['core_action_id']}；成员={', '.join(members)}"]
    lines += ['', 'L2 功能动作及关联的 L3 身体运动：']
    for a in sorted(parent['actions'], key=lambda x: (x['start'], x['actor_id'], x['id'])):
        lines += [f"\n{a['id']}｜{a['start']:.3f}–{a['end']:.3f}s｜{a['actor_id']}｜{names.get(a['label'], a['label'])} ({a['label']})",
                  f"  {a['description']}",
                  f"  计数={a['instance_mode']}；周期数={a['repeat_count']}；角色={','.join(a['roles'])}；状态={a['completeness']}；置信度={a['confidence']}",
                  f"  方向参照={a['direction']['reference']}：{a['direction']['description']}",
                  f"  起点范围={a['start_range']}；终点范围={a['end_range']}"]
        for ev in a['evidence']:
            lines.append(f"  证据 {ev['time']:.3f}s：{ev['observation']}")
        for phase in parent['phases']:
            if phase['action_id'] == a['id']:
                lines.append(f"  阶段 {phase['start']:.3f}–{phase['end']:.3f}s {phase['label']}：{phase['description']}")
        for point in parent['keypoints']:
            if point['action_id'] == a['id']:
                lines.append(f"  关键点 {point['label']}：{point['time']}；范围={point['time_range']}")
        for link in detail['realization_links']:
            if link['action_id'] == a['id']:
                p = primitives[link['primitive_id']]
                lines += [f"    L3 {p['id']}｜{p['start']:.3f}–{p['end']:.3f}s｜{p['body_part']}｜{p['motion_predicate']}",
                          f"      {p['description']}；参照={p['reference_frame']}；可见性={p['observation_status']}"]
        for coverage in detail['coverage']:
            if coverage['action_id'] == a['id']:
                lines.append(f"  L3 覆盖={coverage['status']}：{coverage['note']}")
        overlap = [p['audio_id'] for p in annotations['relations']['levels']['L2']['pairs']
                   if p['action_id'] == a['id'] and p['nominal_overlap'] and p['audio_layer'] == 'foreground']
        lines += ['  名义同时出现的前景音频：' + (', '.join(overlap) or '无'), '  人工修改：________________']
    linked_primitives = {link['primitive_id'] for link in detail['realization_links']}
    unlinked = [p for p in detail['primitives'] if p['id'] not in linked_primitives]
    if unlinked:
        lines += ['', '未关联父动作的 L3 候选（保留待审，不自动新增 L2）：']
        for p in unlinked:
            lines += [f"{p['id']}｜{p['start']:.3f}–{p['end']:.3f}s｜{p['actor_id']}｜{p['body_part']}｜{p['motion_predicate']}",
                      f"  {p['description']}；参照={p['reference_frame']}；可见性={p['observation_status']}"]
    lines += ['', '保持状态（不计入动态动作数）：']
    for s in parent['states'] + detail['additional_states']:
        lines.append(f"{s['id']}｜{s['start']:.3f}–{s['end']:.3f}s｜{s['actor_id']}｜{s['description']}")
    lines += ['', '音频事件：']
    for u in audio['events']:
        lines.append(f"{u['id']}｜{u['start']:.3f}–{u['end']:.3f}s｜{u['kind']}/{u['layer']}｜{u['description']}")
    lines += ['', '细化阶段提出的父动作问题（原结果保留）：']
    for issue in detail['parent_issues']:
        lines.append(f"{issue['action_id']}：{issue['issue']}")
    lines += ['', '不确定性：'] + parent['uncertainties'] + detail['uncertainties'] + audio['uncertainties']
    lines += ['', '程序审阅提醒：', json.dumps(annotations['warnings'], ensure_ascii=False, indent=2)]
    (out / 'badminton_三层标注_人工审阅.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=PACKAGE / 'config/five_videos_general_rules.json')
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    cfg, root = load_config(args.config)
    cfg = copy.deepcopy(cfg)
    case = next(c for c in cfg['cases'] if c['id'] == 'badminton')
    require(not case.get('external_speech_file'), 'Pilot expects independent audio')
    cfg['cases'] = [case]
    cfg['experiment'] = VERSION
    cfg['standard_sha256'] = file_hash(STANDARD)
    cfg['provider']['max_validation_repairs'] = 1
    run = args.run_dir.resolve()
    protocol = bind_run(run, cfg)
    standard_snapshot = run / 'protocol_files/protocols' / STANDARD.name
    standard_snapshot.parent.mkdir(parents=True, exist_ok=True)
    standard_snapshot.write_bytes(STANDARD.read_bytes())
    out, media_dir = run / case['id'], run / case['id'] / 'media'
    manifest = prepare(inside(root, case['source']), media_dir, cfg['media'], optional_cuts(root, case))
    lexicon = vocabulary()
    write_json(out / 'runtime_lexicon.json', lexicon)
    provider = cfg['provider']
    action_spec = make_visual_spec('actions', manifest, lexicon, media_dir, provider, protocol, manifest['frames'])
    audio_spec = request_spec('audio', manifest, lexicon, media_dir, provider, protocol)
    for stage, spec in [('actions', action_spec), ('audio', audio_spec)]:
        save_request(out / 'stages' / stage, spec[0], spec[1])
    write_json(run / 'run_policy.json', {'standard_sha256': cfg['standard_sha256'],
        'model': provider['model'], 'local_sampling_fps': cfg['media']['sampling_fps'],
        'api_fps_parameter_used': False, 'manual_gt_or_case_corrections_supplied': False,
        'base_frames': len(manifest['frames']), 'l2_rewritten_by_detail_pass': False})
    print(f"Prepared {manifest['duration']:.3f}s; {len(manifest['frames'])} frames; {len(manifest['shots'])} shots", flush=True)
    if args.dry_run:
        print('Dry run; no API calls.', flush=True)
        return
    key_cache = []
    def key():
        if not key_cache:
            key_cache.append(os.environ.get(provider.get('api_key_env', 'QWEN_API_KEY')) or getpass.getpass('Qwen API key (hidden, not saved): '))
        return key_cache[0]
    warnings, completed = {}, []
    def perform(name, stage, spec, frames, parents=None, shot_id=None):
        notes = []
        def validator(data):
            notes[:] = validate(stage, data, manifest, lexicon, frames, parents, shot_id)
        print(name + ': start', flush=True)
        data = execute(out / 'stages' / name, *spec, provider, key, validator)
        warnings[name] = notes
        write_json(out / 'stages' / name / 'human_review_warnings.json', {'warnings': notes, 'model_values_changed': False})
        completed.append(name)
        write_json(run / 'run_status.json', {'status': 'in_progress', 'completed_stages': completed, 'warnings': warnings})
        print(f'{name}: complete; warnings={len(notes)}', flush=True)
        return data
    try:
        parent = perform('actions', 'actions', action_spec, manifest['frames'])
        audio = perform('audio', 'audio', audio_spec, [])
        adapt_actions = []
        for a in parent['actions']:
            moments = [{'time': p['time'], 'name': p['label']} for p in parent['keypoints'] if p['action_id'] == a['id']]
            adapt_actions.append({**a, 'key_moments': moments})
        # Extra frames selected from visual evidence only, independently of audio segmentation.
        plan = prepare_review(media_dir, manifest, {'actions': adapt_actions}, {'events': []},
                              cfg['media'], provider['max_request_bytes'] - 4 * 1024 * 1024)
        detail = {k: [] for k in ('primitives', 'realization_links', 'additional_states', 'coverage', 'parent_issues', 'uncertainties')}
        for shot in manifest['shots']:
            frames = [f for f in plan['frames'] if f['shot_id'] == shot['id']]
            spec = make_visual_spec('primitives', manifest, lexicon, media_dir, provider, protocol, frames, parent, shot['id'])
            data = perform('primitives_' + shot['id'], 'primitives', spec, frames, parent, shot['id'])
            for k in detail:
                detail[k].extend(data[k])
        unique(detail['primitives'], 'global primitive')
        unique(parent['states'] + detail['additional_states'], 'global state')
        graph = align_levels(parent, detail['primitives'], audio, manifest)
        summary = {'status': 'model_candidates_not_human_gt', 'episode_candidates': len(parent['episodes']),
            'action_candidates': len(parent['actions']), 'primitive_candidates': len(detail['primitives']),
            'state_candidates': len(parent['states']) + len(detail['additional_states']),
            'phase_candidates': len(parent['phases']), 'keypoint_candidates': len(parent['keypoints']),
            'audio_candidates': len(audio['events']), 'parent_issues': len(detail['parent_issues']),
            'l2_labels': dict(Counter(a['label'] for a in parent['actions'])),
            'l3_coverage': dict(Counter(c['status'] for c in detail['coverage'])),
            'base_frames': len(manifest['frames']), 'detail_frames': len(plan['frames']),
            'local_sampling_fps': cfg['media']['sampling_fps'], 'api_fps_parameter_used': False,
            'relation_counts': {k: len(v['foreground_overlap']) for k, v in graph['levels'].items()}}
        annotations = {'schema_version': VERSION, 'status': summary['status'],
            'source_sha256': manifest['source_sha256'], 'duration': manifest['duration'],
            'shots': manifest['shots'], 'functional': parent, 'body_parts': detail,
            'audio': audio, 'relations': graph, 'warnings': warnings}
        write_json(out / 'annotations.json', annotations)
        write_json(out / 'relations.json', graph)
        write_json(out / 'summary.json', summary)
        export_readable(out, annotations, lexicon, summary)
        usage = []
        for name in completed:
            stage_dir = out / 'stages' / name
            meta = read_json(stage_dir / 'metadata.json')
            usage.append({'stage': name, 'accepted_usage': meta.get('usage'),
                          'accepted_elapsed_seconds': meta.get('elapsed_seconds'), 'repair_count': meta.get('repair_count', 0)})
            if (stage_dir / 'initial_metadata.json').exists():
                first = read_json(stage_dir / 'initial_metadata.json')
                usage.append({'stage': name + '_initial_failed_validation', 'usage': first.get('usage'),
                              'elapsed_seconds': first.get('elapsed_seconds')})
        write_json(run / 'usage.json', usage)
        write_json(run / 'run_status.json', {'status': 'complete', 'completed_stages': completed,
                                           'summary': summary, 'human_verified': False})
        print(json.dumps(summary, ensure_ascii=False), flush=True)
        print('Finished:', out, flush=True)
    except Exception:
        write_json(run / 'run_status.json', {'status': 'incomplete', 'completed_stages': completed, 'warnings': warnings})
        raise


if __name__ == '__main__':
    main()
