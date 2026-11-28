"""Run the shared Qwen pipeline on the selected MotionAtlas media."""
import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import escape
from urllib.parse import quote

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'cross_domain_pilot_20261126'))
import unified_pipeline as pipeline
from unified_review import STYLE, export_case

OUT = HERE / 'results_main3'

def export_overview(cases):
    rows = []
    for case in cases:
        case_id = case['id']
        directory = OUT/'cases'/case_id
        record_file = directory/'annotations.json'
        if not record_file.is_file():
            rows.append('<tr><td>'+escape(case['domain'])+'</td><td colspan="5">尚无通过校验的结果</td></tr>')
            continue
        record = pipeline.read_json(record_file)
        clip = HERE/'cases'/case_id/'clip.mp4'
        export_case(directory, clip, record)
        source_id = ', '.join(map(str,case['sample_ids']))
        status = '视觉、听标、联合复核、转写' if record['audio'] is not None else '仅视觉 · 原版与上游均无音轨'
        prefix = 'cases/'+quote(case_id)+'/'
        links = ('<a href="'+prefix+'审阅.html">播放与审阅</a> · <a href="'+prefix+'annotations.json">JSON</a>'
                 +' · <a href="../cases/'+quote(case_id)+'/'+quote(case['local_original'])+'">原版 MP4</a>')
        rows.append('<tr>'+''.join('<td>'+escape(str(v))+'</td>' for v in
                    (source_id, case['domain'], f"{case['main_subject_count']} 位{case['subject_kind']}",
                     f"{record['duration_seconds']:.2f} 秒",status))+'<td>'+links+'</td></tr>')
    html = ['<!doctype html><meta charset="utf-8"><title>MotionAtlas 五条试标</title>',STYLE,
            '<style>table{border-collapse:collapse}td,th{padding:.6em;text-align:left;border-bottom:1px solid #ccd7d6}</style>',
            '<h1>MotionAtlas 五条试标</h1><p>主要动作由 1–3 位主体完成。短暂入镜的路人和背景观众单独说明。'
            '动作、转写与同期关系均为模型候选，时间从各官方片段起点计算。</p>',
            '<table><thead><tr><th>官方样本 ID</th><th>场景</th><th>主要主体</th><th>时长</th>'
            '<th>完成的标注</th><th>文件</th></tr></thead><tbody>',*rows,'</tbody></table>',
            '<p><a href="../sample_manifest.json">选片记录</a> · <a href="../media_audit.json">官方媒体音轨检查</a>'
            ' · <a href="../upstream_audio_audit.json">上游文件与逐帧核验</a></p>']
    OUT.mkdir(exist_ok=True,parents=True)
    (OUT/'试标总览.html').write_text('\n'.join(html),'utf8')


def run(case, config):
    source = HERE / 'cases' / case['id']
    task = 'both' if case['audio_source'] else 'visual'
    visual = pipeline.process_case(case, OUT, config, task, source)
    if task == 'both':
        return
    directory = OUT / 'cases' / case['id']
    manifest = pipeline.read_json(directory / 'media/manifest.json')
    warnings = visual['uncertainties'] + pipeline.visual_timing_notes(visual, manifest, manifest['frames'])
    record = dict(model=config['provider']['model'], protocol=pipeline.VERSION, human_verified=False,
                  source=case, duration_seconds=manifest['duration'], shots=manifest['shots'],
                  input_frames={'visual':len(manifest['frames'])}, visual_origin='stages/visual',
                  audio_origin=None, visual=visual, audio=None, relations=None, warnings=warnings)
    pipeline.write_json(directory/'annotations.json', record)
    export_case(directory, source/'clip.mp4', record)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--export', action='store_true')
    args = parser.parse_args()
    cases = pipeline.read_json(HERE/'sample_manifest.json')
    if args.export:
        export_overview(cases)
        sys.exit(0)
    selected = [c for c in cases if not args.ids or c['id'] in args.ids]
    if set(args.ids) - {c['id'] for c in selected}:
        parser.error('Unknown sample ID')
    config = pipeline.read_json(pipeline.PACKAGE/'runs/badminton_bwf_hierarchical_20261125_v01/protocol.json')['config']
    failed = []
    with ThreadPoolExecutor(args.workers) as pool:
        jobs = {pool.submit(run,c,config):c['id'] for c in selected}
        for f in as_completed(jobs):
            try:
                f.result()
            except Exception as exc:
                print(jobs[f], 'FAILED', str(exc)[:700], flush=True)
                failed.append(jobs[f])
    export_overview(cases)
    sys.exit(int(bool(failed)))
