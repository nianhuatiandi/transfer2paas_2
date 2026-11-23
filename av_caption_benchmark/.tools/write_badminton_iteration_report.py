import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
runs = [
    ('v0.4', '20261123_000311_v04', 'single call', ['badminton_metadata.json']),
    ('v0.5', '20261123_000758_v05', 'single call; prompt-only change', ['badminton_metadata.json']),
    ('v0.6', '20261123_001444_pipeline_v06', 'three visual shots plus separate audio', ['audio_metadata.json', 'visual_S01_metadata.json', 'visual_S02_metadata.json', 'visual_S03_metadata.json']),
    ('v0.7', '20261123_002028_pipeline_v07', 'review two visual shots; reuse audio and closing shot', ['review_S01_metadata.json', 'review_S02_metadata.json']),
]
results = []
for version, directory, method, files in runs:
    folder = root / 'qwen3.8_omni_results' / directory
    metadata = [json.loads((folder / f).read_text(encoding='utf-8')) for f in files]
    response = (folder / 'badminton_response.txt').read_text(encoding='utf-8')
    results.append({'version': version, 'directory': str(folder), 'method': method,
                    'new_api_requests': len(files), 'new_tokens': sum(m['usage']['total_tokens'] for m in metadata),
                    'all_requests_complete': all(m['status'] == 'complete' for m in metadata),
                    'closing_subtitle_present': '你们是不是经常遇到这个问题' in response,
                    'forehand_high_serve_labels': response.count('Technique: forehand high serve'),
                    'limitations': 'Manual observations are not a labelled benchmark or accuracy score.'})
record = {'model': 'qwen3.8-omni-flash', 'video': 'badminton_lift_31679122798_first8s.mp4',
          'rounds': results, 'total_new_requests': sum(r['new_api_requests'] for r in results),
          'total_new_tokens': sum(r['new_tokens'] for r in results)}
destination = root / 'badminton_pipeline'
(destination / 'iteration_comparison.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
report = '''羽毛球标注迭代记录（2026-11-23）

范围：同一段裁剪后 8 秒视频；Qwen3.8-Omni-Flash。

v0.4：单次调用，使用扩充术语与证据约束的 prompt。结果仅描述两个镜头，漏掉片尾正面人物镜头；动作 ID 虽连续，实际开始时间未全局排序。
v0.5：仅修改 prompt，强调观察范围、无法观察的片尾与全局排序。模型开始承认最后一秒未观察到，排序改善；仍未看到片尾镜头。不能据此认定 prompt 已解决输入覆盖。
v0.6：改为本地解码、实际 10 fps 抽帧，保留各镜头首尾帧；按约 3.867 秒、7.633 秒切镜分开分析；全片音频单独转写；程序合并。补齐第三个镜头、ACTIVE 胸前文字和片尾中文字幕。仍发现训练喂球误标为正手发高远球。
v0.7：新增手抛喂球与球拍喂球标签，补充正手发高远球的下手发球判据；对两个运动镜头进行独立证据复审，复用音频和片尾结果。最终没有正手发高远球标签；合并结果覆盖三个镜头、16 个候选动作条目。

当前入口：python .tools/run_badminton_pipeline.py
重审运动镜头：python .tools/refine_badminton_pipeline.py qwen3.8_omni_results/<baseline_pipeline_directory>
仅重新合并：python .tools/run_badminton_pipeline.py --resume qwen3.8_omni_results/<run_directory> --assemble-only

本地校验：四章节顺序、故事时间轴无空档、动作开始时间排序、ID、允许标签、人物引用与镜头范围通过检查。对单帧字幕采用真实源帧显示区间；对 0.1 秒估计导致的小幅跨镜头边界作显式裁剪，原始模型 JSON 保留。像素坐标声称未经跟踪器测量，在输出中明确标注未验证。

限制与后续方向：
- 模型对部分挑球仍使用 upward return，对并步没有足够证据时使用更宽标签；不能把较多专业标签当作更准确。
- 原始画面中小人物的脚部和羽毛球较难分辨。进一步改善应优先增加人物/脚部/球拍局部画面并保留全场参照，或用人工标注验证；不应为了命中标签降低证据要求。
- 音频已独立处理，但转写尚未人工核验。声音与人物、击球瞬间的对应关系没有自动强行绑定。
- v0.6 同时改变了输入和管道，v0.7 加入复审；这些差异不能归功于 prompt 文字本身。只在这一段视频上检查，尚不能声称跨视频准确率提高。
- 场景检测阈值 0.12 需要在其他视频上复查。全部帧/阶段 JSON/prompt/用量记录可追溯。
'''
(destination / 'iteration_report.txt').write_text(report, encoding='utf-8')
print(json.dumps({'requests': record['total_new_requests'], 'tokens': record['total_new_tokens'], 'rounds': [{k: v for k, v in r.items() if k not in ['directory', 'limitations']} for r in results]}, ensure_ascii=True, indent=2))
