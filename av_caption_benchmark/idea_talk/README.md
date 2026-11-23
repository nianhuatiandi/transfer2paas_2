# 以专业原子动作为中心的细粒度音视频描述评测

这份 11 页中文研究提案适合约 8–10 分钟的教师汇报。开场播放羽毛球训练原片，比较黑衣人两次并步后的出球方向，再用现场计数解释如何评估一句语音与多个动作的时间重叠。第 4 页是单片试评，第 10–11 页是拟开展的数据建设和读者实验。

- [下载 PowerPoint](https://raw.githubusercontent.com/nianhuatiandi/transfer2paas_2/main/av_caption_benchmark/idea_talk/sports-caption-proposal.pptx)。第 2 页内嵌含原声的 8 秒 MP4，在 PowerPoint 放映中点击画面。逐页讲稿也保存在备注中。
- [打开静态 PDF](sports-caption-proposal.pdf)。适合预览和转发，保留视频封面。
- [下载离线素材包](https://raw.githubusercontent.com/nianhuatiandi/transfer2paas_2/main/av_caption_benchmark/idea_talk/materials.zip)。内含两段原始视频、实际模型描述、逐帧截图、参考标注、评分、讲稿及文件索引。
- [阅读逐页讲稿](speaker-notes.md)。

## 案例来源

| 材料 | 用途 |
|---|---|
| [羽毛球原片](../../badminton_lift_31679122798_first8s.mp4) | 第 1–3 页的 30 fps 原片和原声 |
| [四个原始 caption 与 MotionAtlas 补充输出](../../badminton_captions/) | AVoCaDO、AVowed、DiaDem、TimeChat 的原始 2 fps 比较 |
| [Qwen 早期输出](../qwen3.8_omni_results/20261122_212122/badminton_response.txt) | 第 8 页的真实计数错位例子，专用提示词的一次运行 |
| [立定跳远原片](../../standing_long_jump_1039046118_0-7s.mp4) | 第 10 页的单次动作示例 |
| [逐项判定报告](pilot/report.md) · [参考事件表](pilot/gt.json) · [评分及原文证据](pilot/scores.json) | 人物、动作和语音区间、共现关系、可辨认程度与排除项 |
| [术语提示词与手册页码](pilot/badminton_vocabulary_prompt.txt) | 并步、低手回球、回位等术语的操作性定义 |
| [原帧与轨迹图](assets/) | 羽毛球全景取第 20 帧、喂球取第 177 帧，两张出球图取第 33 和 95 帧，均从零计数。黄线为连续帧的可见球路示意。立定跳远示意取第 115 帧。 |

案例参考来自一次助手判读。视觉以原始帧复核，语音结合原音轨、历史候选和独立 ASR。动作和语音端点是估计。300 条为目标规模，30 条为试标计划，正式参考集仍需专项人员独立标注与仲裁。

## 相关文献

- 人物在跨事件描述中的指代一致性及下游验证。[CapRiCorn-1K，EMNLP 2026](https://aclanthology.org/2026.emnlp-main.272/)
- 按实体、镜头和音频事件组织细粒度音视频评估。[OmniCapBench](https://arxiv.org/abs/2610.12458)
- 羽毛球多层级视频理解。[FineBadminton](https://arxiv.org/abs/2508.07554)
