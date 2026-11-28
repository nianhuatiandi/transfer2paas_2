"""Run the two independent annotation stages on the prepared pilot clips."""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from sports_annotation.client import describe_request, execute
from sports_annotation.media import prepare
from sports_annotation.io_utils import file_hash, read_json
PROMPTS = ROOT / 'av_caption_benchmark/research/question_types_domain_prompts_20261126/prompts'

def prompt_for(case, stage, duration):
    prefix = '06' if stage == 'audio' else case['card']
    content = next(PROMPTS.glob(prefix + '_*.txt')).read_text(encoding='utf8')
    if stage == 'visual':
        # Only the visual task, without the caption parsing mode or worked example.
        content = (content.split('MODE = CAPTION_TEXT\n')[0].split('什么是一条原子语句')[-1]
                   + '\n领域类别卡\n' + content.split('领域类别卡\n')[-1].split('拆分示例')[0]
                   + '\n输出 JSON。顶层字段：' + content.split('输出 JSON。顶层字段：')[-1])
        if case.get('domain_rule'):
            content += '\n领域细则：' + case['domain_rule']
        if case['id'] == 'sport01':
            terms = read_json(ROOT/'sports_annotation/lexicons/badminton_bwf_v01.json')
            content += '\n备查术语（只在可见依据足够时选用；同一技术的子阶段置于父项下）：' + json.dumps({
                k: [x['zh'] for x in terms[k]] for k in ['movement_terms','stroke_terms','stroke_subphases','training_terms','project_extensions']},ensure_ascii=False)
        content += '\n本次 MODE=VISUAL_GT，只看图像。可见 L2 区间写在 visible_spans 内，只有单个连续段也写。每个动作的中文 claim 含对象或方向及可观察变化。关系若可用区间计算，交给后处理。'
    if stage == 'audio':
        content += '\n每条语音记录对应一次发言中的一个独立句子或连续的未完片语。问句结束后开始另一句话时另起；不要把四个句子合并到一条。不要因为镜头或可猜测的动作拆句。若为多个可辨瞬态，各给一个 ID；不可辨次数时明确记录成簇。instance_range 只用一对数字或 null。boundary_ranges 仅表示起点与终点的误差范围，格式为 {"start":[lo,hi],"end":[lo,hi]} 或 null，绝不用于枚举句子或声响。evidence_time 给能回听的数值秒。type 使用 speech/sfx/music/ambience/vocalization；layer 使用 foreground/background/unknown。'
    content += (f'\nclip_id={case["id"]}；片头为零，片长 {duration:.6f} 秒。只返回 JSON 对象。'
                '所有 ID 是短字符串，时间字段用秒数，保留真实不确定性。中文事实保持简明。')
    return content

def describe_actions(directory, case, manifest, visual, files, cfg):
    candidates = [{k: fact.get(k) for k in ('id', 'actor', 'object', 'claim', 'instance_range', 'visible_spans')}
                  for fact in visual['facts'] if fact.get('level') == 'L2' and fact.get('kind') == 'action']
    if not candidates:
        return
    template = (HERE / 'visual_action_detail_prompt.txt').read_text(encoding='utf8')
    prompt = template + '\n' + json.dumps({'clip_id': case['id'], 'duration_seconds': manifest['duration'],
                                         'candidates': candidates}, ensure_ascii=False)
    stage_dir = directory / 'stages' / 'visual_action_details'
    provenance = {'clip_id': case['id'], 'clip_sha256': manifest['source_sha256'],
                  'visual_result_sha256': file_hash(directory / 'stages/visual_v2/result.json')}
    spec = describe_request('visual_action_details', prompt, files, cfg, provenance)
    expected = {row['id'] for row in candidates}
    frame_indices = {frame['index'] for frame in files}

    def validate(data):
        rows = data.get('action_details')
        if data.get('clip_id') != case['id'] or not isinstance(rows, list):
            raise ValueError('Return clip_id and an action_details list')
        if len(rows) != len(expected) or {row['id'] for row in rows} != expected:
            raise ValueError('Return exactly one row per supplied L2 ID')
        for row in rows:
            detail, frames, note = row['action_detail'], row['frame_indices'], row['review_note']
            if not isinstance(frames, list) or any(type(i) is not int or i not in frame_indices for i in frames):
                raise ValueError('Use only Source frame indices supplied with the images')
            if note is not None and not isinstance(note, str):
                raise ValueError('review_note must be text or null')
            if detail is None:
                if not note or not note.strip():
                    raise ValueError('Explain why the action cannot be confirmed')
            elif not isinstance(detail, str) or not detail.strip() or not frames:
                raise ValueError('Provide a nonempty action description and supporting frames')

    execute(stage_dir, spec, prompt, files, cfg, lambda: os.environ['QWEN_API_KEY'], validate)

def run(case, stage, manifest, cfg, visual_review):
    directory = HERE/'cases'/case['id']
    media = directory/'media'
    if stage == 'visual':
        files = [dict(kind='image', path=str(media/f['file']), **{k:f[k] for k in ('index','time','shot_id','sha256')}) for f in manifest['frames']]
    else:
        a=manifest['audio']
        if not a['present']:
            raise ValueError('Missing audio stream')
        files=[dict(kind='audio',path=str(media/a['file']),sha256=a['sha256'])]
    prompt = prompt_for(case,stage,manifest['duration'])
    if stage=='visual' and visual_review:
        prompt += '\n' + (HERE/'visual_review_rules.txt').read_text(encoding='utf8')
    spec = describe_request(stage,prompt,files,cfg,{'clip_sha256':manifest['source_sha256'],'clip_id':case['id']})
    field = 'facts' if stage=='visual' else 'audio_events'
    def validate(data):
        if not isinstance(data,dict) or data.get('clip_id')!=case['id'] or not isinstance(data.get(field),list):
            raise ValueError('Expected clip_id and '+field+' array')
        ids=[r.get('id') for r in data[field]]
        if not all(isinstance(i,str) and i for i in ids) or len(set(ids))!=len(ids):
            raise ValueError('Each event needs a distinct string ID')
    print(case['id'],stage,'starting',flush=True)
    result = execute(directory/'stages'/('audio_v2' if stage=='audio' else ('visual_v2' if visual_review else stage)),spec,prompt,files,cfg,lambda:os.environ['QWEN_API_KEY'],validate)
    if stage == 'visual' and visual_review:
        describe_actions(directory, case, manifest, result, files, cfg)
    print(case['id'],stage,'complete',flush=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids',nargs='*')
    parser.add_argument('--first-visual',action='store_true',help='Reproduce the first visual prompt')
    parser.add_argument('--workers',type=int,default=3)
    parser.add_argument('--stage',choices=['visual','audio','both'],default='both')
    args=parser.parse_args()
    config=read_json(ROOT/'sports_annotation/config/five_videos_live_compact.json')
    provider=config['provider']
    if provider['base_url']!='https://maas.qianwenaiapi.com/compatible-mode/v1':
        raise ValueError('Unexpected Qwen endpoint')
    selection=[read_json(p) for p in sorted((HERE/'cases').glob('*/source.json'))]
    settings={**config['media'],'max_frame_width':640,'jpeg_quality':80}
    failed=[]
    with ThreadPoolExecutor(args.workers) as pool:
        jobs={}
        for case in selection:
            if not args.ids and case.get('disposition') in ('extra_rejected_audio','extra_cut_control'):continue
            if args.ids and case['id'] not in args.ids: continue
            folder=HERE/'cases'/case['id']
            manifest=prepare(folder/'clip.mp4',folder/'media',settings)
            for stage in (['audio','visual'] if args.stage=='both' else [args.stage]):
                jobs[pool.submit(run,case,stage,manifest,provider,not args.first_visual)]=(case['id'],stage)
        for future in as_completed(jobs):
            try:future.result()
            except Exception as exc:
                failed.append(jobs[future]);print(jobs[future],str(exc)[:340],flush=True)
    if failed:sys.exit(1)
if __name__=='__main__':
    if '--legacy' in sys.argv or '--first-visual' in sys.argv:
        if '--legacy' in sys.argv:
            sys.argv.remove('--legacy')
        main()
    else:
        from unified_pipeline import main as unified_main
        sys.exit(unified_main())
