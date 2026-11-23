# 研究与实验方案的演变

本文件解释历史记录与当前方案的关系。原始 prompt、响应和报告均保留原文；有差异时，当前研究范围以 [CURRENT_PROPOSAL.md](CURRENT_PROPOSAL.md) 为准。

| 阶段 | 已做工作或讨论 | 当前如何使用 |
| --- | --- | --- |
| 视频裁剪与传输 | 羽毛球保留开头 8 秒；立定跳远先裁 1–7 秒，后更正为 0–7 秒；下载远端生成结果 | 0–7 秒是当前立定跳远输入，1–7 秒作为历史版本留档 |
| 两个视频的初始测试 | 用两个 prompt 调用 Qwen，记录响应与配置 | 案例探索，不能视为 benchmark 分数 |
| 专业术语迭代 | 修改并步、挑球等判断条件，减少证据不足的细分类命名 | 术语必须可观察且可复核；不把保守描述直接当成专业 GT |
| 分阶段管道 | 视觉、音频、复核、对齐逐步拆分，发展至 v0.8 | 保存所有版本；v0.8 是模型复核稿，不是人工 GT |
| FPS 对照 | 区分显式时间戳抽帧与 API fps 参数，并测试参数位置 | 已有单次诊断结果，尚无重复实验或统一输入预算结论 |
| 初始 benchmark 调研 | 70 篇范围索引，比较动作、caption、音视频评测及 benchmark 主导工作 | 历史文献基础，不以模型训练论文替代 benchmark 创新分析 |
| dense caption 转结构 | 讨论保持模型原生 prompt、事后结构化及信息损失 | 当前保留该方向；尚未证明无损或完成通用转换器 |
| 早期动作—话语关联设想 | 曾涉及解说语义指向、跨镜头指代、声音来源等问题 | 这些不能自动当作当前研究要求 |
| 当前边界确认 | 只要求动作和音频在时间上的共现；外部字幕管道只负责 GT | 这是当前任务定义，允许多对多和跨镜头时间重叠 |
| ACL 路线深化 | 80 篇索引、近邻工作核查、原子动作时间审计与 7 项实验计划 | 提供研究路线和待验证假设，不表示已完成或可保证录用 |

## 研究报告索引

| 文件 | 适用说明 |
| --- | --- |
| [atomic_av_caption_benchmark_20261123/report.txt](research/atomic_av_caption_benchmark_20261123/report.txt) | 初始范围综述；部分任务讨论早于最终边界确认 |
| [skilled_action_speech_alignment_20261123/report.txt](research/skilled_action_speech_alignment_20261123/report.txt) | 历史动作与话语对齐设想；语义指向部分不属于当前核心任务 |
| [dense_to_structured_caption_20261123/report.txt](research/dense_to_structured_caption_20261123/report.txt) | 文本转换与已有管线比较；来源代码用 URL/版本记录，不重复发布源码 |
| [badminton_case_comparison_20261123/report.txt](research/badminton_case_comparison_20261123/report.txt) | 羽毛球案例与已有专业运动方法比较 |
| [acl_publication_roadmap_20261123/report.txt](research/acl_publication_roadmap_20261123/report.txt) | 当前范围下的最新综合分析与投稿工作计划 |

## 需要保留的纠错记录

旧请求曾把 `fps: 10` 放在 `video_url` 内部。对照实验中，这种写法与默认请求返回相同的视频 token 数；改为与 `type`、`video_url` 同级后，视频 token 数显著增加。历史请求和原始响应仍保留，以免覆盖诊断依据。

v0.8 的 `related_actions` 不是按当前定义生成的完整时间共现图。最新案例审计按区间重新求交，揭示漏连的并行动作，以及旧文字说明里“4.6 秒早于 4.52 秒”的时间比较错误。该审计使用已有模型时间戳，不能替代原始音视频的人工逐帧校验。
