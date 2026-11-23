import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
full = root / 'qwen3.8_omni_results/20261123_120119_fps_comparison'
tail = root / 'qwen3.8_omni_results/20261123_120317_fps_tail_comparison'
all_results = {'full_clip': json.loads((full / 'comparison_summary.json').read_text(encoding='utf-8')),
               'focused_tail': json.loads((tail / 'comparison_summary.json').read_text(encoding='utf-8'))}
for name, folder in [('full_clip', full), ('focused_tail', tail)]:
    config = json.loads((folder / 'test_config.json').read_text(encoding='utf-8'))
    prompt_files = sorted(folder.glob('*_prompt.txt'))
    assert len({p.read_bytes() for p in prompt_files}) == 1
    for mode, result in all_results[name].items():
        result['tail_subtitle_read'] = '你们是不是经常遇到这个问题' in json.dumps(result['tail'], ensure_ascii=False)
    all_results[name + '_config'] = config
all_results['conclusions'] = [
    'Correct content-part sibling fps=10 changes native video token usage from 4754 to 23762, approximately 5x; the legacy nested video_url.fps produces the same 4754 as the default.',
    'Native fps=10 omitted the final shot in the broad task but described it when explicitly asked about the final 0.5 s; omission is not proof that the server supplied no tail frames.',
    'Local frames plus video read the final subtitle in both tasks. This path includes explicitly timestamped pictures and guaranteed source-shot endpoint frames, so it is not identical to a bare native fps setting.',
    'The local path uses 49945 total input tokens versus native fps10 24190 for the broad task; this comparison includes image/text overhead and different modality preprocessing, not just frame rate.',
    'These are single diagnostic trials per task/mode, not a statistically controlled accuracy benchmark. Different output event counts are not accuracy scores.',
    'The tests use non-thinking mode, identical prompts within each task, and the same model/video/output limit. The production pipeline has different stage prompts and uses thinking mode for visual review.'
]
dump_path = full / 'experiment_report.json'
dump_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2), encoding='utf-8')
text = '''10 fps 输入方式对照（2026-11-23）

视频：同一段 8 秒羽毛球片段，Qwen3.8-Omni-Flash，同一接口。
每种方式每个任务各调用一次；同一任务使用相同问题、非思考模式、max_tokens=4096。
本地图片组保持当前管道的 960x540 JPEG 和 84 张时间戳帧，同时发送默认参数原视频以保留音频。

全片任务：
1. 默认原视频：视频 4754 tokens；总输入 5182；回答描述 2 镜头，漏掉片尾正面镜头。
2. 旧写法 video_url 内 fps=10：视频 4754 tokens；总输入 5182；仍描述 2 镜头，漏片尾。
3. 正确同层 fps=10：视频 23762 tokens；总输入 24190；仍在这次全片回答中漏掉片尾。
4. 默认原视频 + 本地 10 fps 图片及首尾补帧：视频 4754 + 图片 43008 tokens；总输入 49945；描述 3 镜头，并读出片尾字幕。

片尾聚焦任务（明确只问 7.5–8 秒）：
- 正确同层 fps=10：能描述正面人物、粉色短裤、ACTIVE 胸前字样；本次没有读出最后一帧中文字幕。
- 本地图片组：同样描述片尾正面人物，并读出“你们是不是经常遇到这个问题”。

解释：
- 早期实现的 fps 参数位置错误。官方示例是 {type: video_url, video_url: {url: ...}, fps: 10}，不是放在 video_url 内部。旧代码已修正。
- 正确设置明显改变了视频处理 token 数，且聚焦提问能看到片尾；不能把全片回答漏写等同于服务器没有提供片尾帧。
- 本地方法的差异包括可审计的实际帧时间、镜头首尾强制补帧、图片独立处理与额外时间戳文本；它不是简单地把同样 10 fps 换一种传法。
- 本次本地组输入 token 约为正确 API fps10 的 2.06 倍。没有比较实际账单，缓存命中和模态计费会影响费用。
- 不能从单次测试推出哪种方式普遍更准确。模型仍可能漏读和误描述，两组都有内容错误；本实验只比较输入方式及明确可核对的片尾现象。

原始数据见本目录及 ../20261123_120317_fps_tail_comparison/。
官方参数示例：https://platform.qianwenai.com/docs/developer-guides/multimodal/vision
'''
(full / 'experiment_report.txt').write_text(text, encoding='utf-8')
print('Saved:', full / 'experiment_report.txt')
