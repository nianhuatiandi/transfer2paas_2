"""Run independent first passes, BWF-style audiovisual review and audio-only transcription."""
import argparse
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from sports_annotation.bwf_model_comparison import images, make_audio_spec, validate_transcript
from sports_annotation.client import describe_request, execute, save_request
from sports_annotation.hierarchical_experiment import make_spec, nominal_relations, output_schema, runtime_lexicon
from sports_annotation.io_utils import file_hash, object_hash, read_json, write_json
from sports_annotation.media import prepare, prepare_review
from sports_annotation.pipeline import PACKAGE
from sports_annotation.schemas import EVIDENCE, NUMBER, TEXT, arr, obj, schema_for
from sports_annotation.validation import evidence, interval, validate_audio
from unified_review import export_case, export_index

PROMPTS = HERE / 'unified_prompts'
VERSION = 'bwf-unified-1'
SPORT_FILES = {'badminton': 'badminton_bwf_v01.json', 'standing_jump': 'standing_jump.json'}


def sport_vocabulary(sport):
    if not sport:
        return None
    source = read_json(PACKAGE / 'lexicons' / SPORT_FILES[sport])
    if sport == 'badminton':
        return runtime_lexicon(source)
    extra = [('other_motion', '其他可见动作'), ('held_pose', '保持姿态'), ('explanatory_gesture', '讲解手势')]
    return {**source, 'terms': source['terms'] + [dict(label=k, zh=v) for k, v in extra]}


def visual_schema(sport, vocab):
    if sport == 'badminton':
        schema = output_schema('visual', vocab)
    else:
        schema = schema_for('visual')
        action = schema['properties']['actions']['items']
        additions = {'body_parts': arr(TEXT), 'movement_roles': arr(TEXT), 'subphases': arr(obj({
            'label': TEXT, 'start': NUMBER, 'end': NUMBER, 'detail': TEXT, 'evidence': EVIDENCE}))}
        action['properties'].update(additions)
        action['required'].extend(additions)
        if vocab:
            action['properties']['label'] = {'enum': [t['label'] for t in vocab['terms']]}
    schema['properties']['schema_version'] = {'const': VERSION}
    action = schema['properties']['actions']['items']
    action['properties']['brief'] = {'type': 'string', 'minLength': 1}
    action['required'].append('brief')
    return schema


def audio_checks(data, manifest):
    notes = []
    for event in data['events']:
        try:
            validate_audio({**data, 'events': [event]}, manifest)
        except ValueError as exc:
            notes.append(f"{event['id']}: {exc}")
    return notes


def visual_timing_notes(visual, manifest, frames):
    notes = []
    shots = {s['id']: s for s in manifest['shots']}
    times = [f['time'] for f in frames]
    for a in visual['actions']:
        shot = shots[a['shot_id']]
        try:
            interval(a, shot['start'], shot['end'])
            evidence(a['evidence'], shot['start'], shot['end'], times)
            if not a['evidence']:
                raise ValueError('缺少可回看的动作证据')
            for phase in a['subphases']:
                interval(phase, a['start'], a['end'], uncertain=False)
            for point in a['key_moments']:
                if point['time'] is not None and not a['start'] <= point['time'] <= a['end']:
                    raise ValueError('关键点超出所属动作区间')
        except ValueError as exc:
            notes.append(f"{a['id']}　{exc}")
    return notes


def validate_visual(data, manifest):
    shots = {s['id']: s for s in manifest['shots']}
    actors = {a['id']: a['shot_id'] for a in data['actors']}
    executions = {e['id']: e['actor_id'] for e in data['executions']}
    for group in ('actors', 'executions', 'actions'):
        rows = data[group]
        if len({r['id'] for r in rows}) != len(rows):
            raise ValueError('Duplicate IDs in ' + group)
        for row in rows:
            if row['shot_id'] not in shots:
                raise ValueError(f"{row['id']} must name exactly one supplied shot, received {row['shot_id']}")
            if 'actor_id' in row and actors.get(row['actor_id']) != row['shot_id']:
                raise ValueError(f"{row['id']} references {row['actor_id']} in {row['shot_id']}, "
                                 "but actors[] has no matching pair. Check all such references.")
    for action in data['actions']:
        if action['execution_id'] is not None and executions.get(action['execution_id']) != action['actor_id']:
            raise ValueError('Invalid execution reference in ' + action['id'])
        if not action['brief'].strip() or not action['detail'].strip() or action['brief'].strip() == action['detail'].strip():
            raise ValueError('Provide both a short action statement and a distinct visible description: ' + action['id'])


def visual_request(stage, sport, vocab, manifest, media, frames, provider, candidates=None, plan=None, people_limit=2):
    visual = visual_schema(sport, vocab)
    schema = visual
    prompt = (PROMPTS / 'visual.txt').read_text('utf8')
    context = dict(duration_seconds=manifest['duration'], time_origin='clip_start', shots=manifest['shots'])
    context['supplied_frames'] = [{k: f[k] for k in ('index', 'time', 'shot_id')} for f in frames]
    if vocab:
        context['lexicon'] = vocab
        prompt += '\n使用所给运动术语与可见依据。不确定技术名称时使用允许的宽泛标签，写清实际运动。'
        if sport == 'badminton':
            policy = (PACKAGE / 'prompts/hierarchical_visual.txt').read_text('utf8')
            prompt += '\n' + policy.split('ANNOTATION UNIT AND HIERARCHY', 1)[1]
    else:
        prompt += '\n生活场景采用开放中文命名。根据画面用普通用语填写 label；可自由描述人物、物体与动作。'
    if people_limit == 3:
        prompt = prompt.replace('一至两位主要执行者', '一至三位主要动作执行者')
        prompt += ('\n按持续参与或完成核心动作来确定主要执行者。远处观众、路人和短暂入镜的旁观者可写入场景说明，'
                   '不要将他们逐一列为主要动作执行者。第一人称镜头可用画面中可辨的手或身体部位作为证据。'
                   '推拉、摇移、变焦属于镜头运动；仅在能观察到人物相对场景或身体部位之间的变化时记为人物动作。')
        prompt = prompt.replace('At most two main participants', 'At most three main participants')
        prompt = prompt.replace('Cover both participants when visible', 'Cover the main participants when visible')
    attachments = images(media, frames)
    if stage == 'review':
        schema = schema_for('review')
        schema['properties'].update(schema_version={'const': VERSION}, visual=visual)
        prompt = (PROMPTS / 'review.txt').read_text('utf8') + '\n' + prompt
        context.update(candidates=candidates, review_targets=plan['targets'])
        a = manifest['audio']
        attachments.append(dict(kind='audio', path=str(media / a['file']), sha256=a['sha256']))
    prompt += '\nOUTPUT JSON SCHEMA\n' + json.dumps(schema, ensure_ascii=False)
    prompt += '\nINPUT\n' + json.dumps(context, ensure_ascii=False)
    provenance = dict(version=VERSION, source_sha256=manifest['source_sha256'], sport=sport,
                      candidate_hash=object_hash(candidates) if candidates else None)
    spec = describe_request(stage, prompt, attachments, provider, provenance)

    def validate(result):
        Draft202012Validator(schema).validate(result)
        validate_visual(result if stage == 'visual' else result['visual'], manifest)
        if stage == 'review':
            check_acoustic(result['audio'])
    return (spec, prompt, attachments), validate


def check_acoustic(data):
    Draft202012Validator(schema_for('audio')).validate(data)
    if len({e['id'] for e in data['events']}) != len(data['events']):
        raise ValueError('Duplicate sound event IDs')
    if any(e['transcript'] is not None for e in data['events']):
        raise ValueError('Keep transcripts null in the acoustic pass')


def run_checkpoint(directory, spec, provider, validator):
    descriptor, prompt, files = spec
    get_key = lambda: os.environ[provider['api_key_env']]
    metadata = directory / 'metadata.json'
    if not metadata.exists() or read_json(metadata)['status'] == 'complete':
        return execute(directory, *spec, provider, get_key, validator)
    previous = read_json(metadata)
    if previous['signature'] != descriptor['signature']:
        raise ValueError(f'Stage inputs changed: {directory}. Use a new --run-dir.')
    if list(directory.rglob('RUNNING.lock')):
        raise RuntimeError(f'Stage already running: {directory}')
    # Continue a failed stage without overwriting its original reply or its first repair.
    retries = sorted((directory / 'continuations').glob('[0-9][0-9]'))
    attempt = retries[-1] if retries else directory
    latest = attempt / 'repairs/01/metadata.json'
    if not latest.exists():
        latest = attempt / 'metadata.json'
    feedback = read_json(latest) if latest.exists() else previous
    if 'degenerate response' in feedback.get('error', '').lower() or feedback.get('finish_reason') == 'length':
        prompt += ('\n请用单行压紧 JSON，省略缩进空格和换行。每个简述一句，详述只写一至两句可见过程。'
                   '每项选择一处关键画面证据，子阶段仅留实际可辨的独立过程。避免同义词串列。'
                   '所有字段保留，全部动作及音频候选都须输出。')
    if feedback.get('finish_reason') == 'stop' and feedback.get('status') == 'failed':
        reason = feedback.get('error', '').splitlines()[0][:500]
        prompt += '\n上一次输出未通过结构检查。请重新依据原始素材给出完整 JSON，保留要求的所有结构字段。'
        if descriptor['stage'] in ('visual', 'review'):
            prompt += '每个镜头内先声明人物。每个动作与执行段只能引用同一镜头的人物。'
            if 'actor' in feedback.get('error','').lower() or 'none is not of type' in reason.lower():
                prompt += ('只有物体或环境在变化且未看见操作者时，把该现象及时间写入 uncertainties，'
                           '这个镜头可以没有人物、执行段或人物动作。不要补出画外人物。')
        if 'delimiter' in reason or 'json' in reason.lower():
            prompt += '请用简洁的 JSON，逐层闭合嵌套的对象和数组。change_log 只写依据媒体作出的内容修订。'
        if 'actor' in reason.lower():
            prompt += '先核对所有 (shot_id, actor_id) 的组合都有对应 actors 记录；未能确认有人实施的动作请留作不确定。'
        prompt += '具体校验反馈：' + reason
    retry = directory / 'continuations' / f'{len(retries) + 1:02d}'
    wire_provider = provider
    if os.name == 'nt' and any(word in feedback.get('error', '').lower() for word in ('ssl', 'connection', 'proxy', 'ended prematurely')):
        wire_provider = {**provider, 'transport': 'curl'}
    desc = describe_request(descriptor['stage'], prompt, files, wire_provider,
                            {**descriptor['provenance'], 'continuation_of': descriptor['signature']})
    data = execute(retry, desc, prompt, files, wire_provider, get_key, validator)
    accepted = read_json(retry / 'metadata.json')
    first_failure = directory / 'pre_continuation_metadata.json'
    if not first_failure.exists():
        write_json(first_failure, previous)
    write_json(directory / 'result.json', data)
    response = retry / accepted.get('accepted_response_path', 'response.txt')
    write_json(metadata, {**accepted, 'signature': descriptor['signature'],
                         'result_sha256': file_hash(directory / 'result.json'),
                         'accepted_response_path': response.relative_to(directory).as_posix()})
    return data


def reuse_audio(source, target, spec, validator):
    """Adopt an already completed, identical audio-only task; preserve the accepted raw reply."""
    if not (source/'metadata.json').is_file() or (target/'metadata.json').exists():
        return False
    meta, request = read_json(source/'metadata.json'), read_json(source/'request.json')
    desc, prompt, _ = spec
    if (meta.get('status') != 'complete' or meta.get('finish_reason') != 'stop'
            or request['image_count'] != 0 or request['audio_count'] != 1
            or request['attachments'] != desc['attachments'] or request['prompt_sha256'] != desc['prompt_sha256']
            or any(request['inference'].get(k) != desc['inference'].get(k) for k in ('base_url', 'model', 'extra_body'))):
        return False
    raw = source / meta.get('accepted_response_path', 'response.txt')
    if not raw.exists() or file_hash(source/'result.json') != meta['result_sha256']:
        raise ValueError('Invalid source audio checkpoint: ' + str(source))
    data = read_json(source/'result.json')
    validator(data)
    save_request(target, desc, prompt)
    shutil.copyfile(raw, target/'imported_response.txt')
    shutil.copyfile(raw.parent/'prompt.txt', target/'imported_prompt.txt')
    write_json(target/'result.json', data)
    write_json(target/'metadata.json', {'signature': desc['signature'], 'status': 'complete',
               'api_call_made': False, 'imported_from': str(source), 'accepted_response_path':'imported_response.txt',
               'result_sha256':file_hash(target/'result.json'), 'source_metadata':meta, 'source_inference':request['inference']})
    return True


def process_case(case, out, config, task, source_folder=None):
    case_id = case['id']
    source_folder = source_folder or HERE / 'cases' / case_id
    directory = out / 'cases' / case_id
    media = directory / 'media'
    settings = config['media']
    manifest = prepare(source_folder / 'clip.mp4', media, settings)
    if task != 'visual' and not manifest['audio']['present']:
        raise ValueError(f'{case_id} has no original audio for joint review')
    if manifest['source_sha256'] != case['clip_sha256']:
        raise ValueError(f'{case_id} clip hash does not match sample manifest')
    sport = case.get('sport')
    vocab = sport_vocabulary(sport)
    provider = config['provider']

    def call(name, spec, validator):
        print(case_id, name, flush=True)
        stage_dir = directory / 'stages' / name
        if name in ('audio', 'audio_transcript'):
            old = HERE / 'bwf_unified_v1/cases' / case_id / 'stages' / name
            if old != stage_dir and reuse_audio(old, stage_dir, spec, validator):
                return read_json(stage_dir/'result.json')
        return run_checkpoint(stage_dir, spec, provider, validator)

    if task != 'audio':
        spec, validator = visual_request('visual', sport, vocab, manifest, media, manifest['frames'], provider,
                                         people_limit=case.get('people_limit', 2))
        visual = call('visual', spec, validator)
        if task == 'visual':
            return visual
    spec = make_spec('audio', manifest, {}, media, provider, VERSION)
    acoustic = call('audio', spec, check_acoustic)
    if task == 'audio':
        return
    candidates = {'visual': visual, 'audio': acoustic}
    plan = prepare_review(media, manifest, visual, acoustic, settings,
                          image_byte_budget=provider['max_request_bytes'] - 2_000_000)
    spec, validator = visual_request('review', sport, vocab, manifest, media, plan['frames'], provider, candidates, plan,
                                     people_limit=case.get('people_limit', 2))
    reviewed = call('review', spec, validator)
    spec = make_audio_spec(manifest, media, provider, VERSION)
    transcript = call('audio_transcript', spec, lambda d: validate_transcript(d, manifest))
    save_final(directory, source_folder, case, provider, manifest, plan, reviewed, transcript)


def save_final(directory, source_folder, case, provider, manifest, plan, reviewed, transcript):
    relations = nominal_relations(reviewed['visual'], transcript, manifest)
    notes = list(reviewed['unresolved']) + list(reviewed['visual']['uncertainties'])
    notes.extend(visual_timing_notes(reviewed['visual'], manifest, plan['frames']))
    notes.extend(audio_checks(reviewed['audio'], manifest))
    notes.extend(validate_transcript(transcript, manifest))
    notes.extend(relations['skipped_invalid_events'])
    final = {'model': provider['model'], 'human_verified': False, 'protocol': VERSION, 'source': case,
             'duration_seconds': manifest['duration'], 'shots': manifest['shots'],
             'input_frames': {'visual': len(manifest['frames']), 'review': len(plan['frames'])},
             'visual_origin': 'stages/review', 'audio_origin': 'stages/audio_transcript',
             'visual': reviewed['visual'], 'audio': transcript, 'relations': relations, 'warnings': notes}
    write_json(directory / 'annotations.json', final)
    export_case(directory, source_folder / 'clip.mp4', final)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--stage', choices=['both', 'visual', 'audio', 'export'], default='both')
    parser.add_argument('--run-dir', type=Path, default=HERE / 'bwf_unified')
    parser.add_argument('--workers', type=int, default=3)
    args = parser.parse_args()
    config = read_json(PACKAGE / 'runs/badminton_bwf_hierarchical_20261125_v01/protocol.json')['config']
    if config['provider']['base_url'] != 'https://maas.qianwenaiapi.com/compatible-mode/v1':
        parser.error('Unexpected Qwen endpoint')
    cases = read_json(HERE / 'sample_manifest.json')
    sports = read_json(PROMPTS / 'sports.json')
    for case in cases:
        if case['id'] in sports:
            case['sport'] = sports[case['id']]
    if set(args.ids) - {c['id'] for c in cases}:
        parser.error('Unknown case ID')
    by_id = {c['id']: c for c in cases}
    selected = [by_id[i] for i in dict.fromkeys(args.ids)] if args.ids else cases
    out = args.run_dir.resolve()
    if args.stage == 'export':
        for case in selected:
            directory = out / 'cases' / case['id']
            outputs = []
            for name in ('review', 'audio_transcript'):
                stage = directory / 'stages' / name
                meta = read_json(stage / 'metadata.json')
                if meta['status'] != 'complete' or meta['result_sha256'] != file_hash(stage / 'result.json'):
                    raise ValueError(f'Incomplete checkpoint: {stage}')
                outputs.append(read_json(stage / 'result.json'))
            save_final(directory, HERE/'cases'/case['id'], case, config['provider'],
                       read_json(directory/'media/manifest.json'), read_json(directory/'media/review_plan.json'), *outputs)
        export_index(out, cases)
        return 0
    failed = []
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(process_case, c, out, config, args.stage): c['id'] for c in selected}
        for job in as_completed(jobs):
            try:
                job.result()
            except Exception as exc:
                failed.append(jobs[job])
                print(jobs[job], 'FAILED:', str(exc)[:700], flush=True)
    export_index(out, cases)
    return int(bool(failed))


if __name__ == '__main__':
    sys.exit(main())
