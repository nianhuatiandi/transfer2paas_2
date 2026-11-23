# 已有结果与复现说明

截至 2026-11-23，本归档包含 8 个 Qwen 运行目录。以下统计来自已有记录；本次整理没有新增付费模型调用。

## 输入片段

| 文件 | 用途 |
| --- | --- |
| [badminton_lift_31679122798_first8s.mp4](transfer2paas_2/badminton_lift_31679122798_first8s.mp4) | 羽毛球源视频开头 8 秒，主案例 |
| [standing_long_jump_1039046118_0-7s.mp4](transfer2paas_2/standing_long_jump_1039046118_0-7s.mp4) | 立定跳远 0–7 秒，用户更正后的版本 |
| [standing_long_jump_1039046118_1-7s.mp4](transfer2paas_2/standing_long_jump_1039046118_1-7s.mp4) | 旧裁剪版本，仅供追溯 |

## 全部 Qwen 运行记录

| 目录 | 主要内容 |
| --- | --- |
| [20261122_212122](qwen3.8_omni_results/20261122_212122/) | 羽毛球与立定跳远的初始 prompt、响应、元数据 |
| [20261123_000311_v04](qwen3.8_omni_results/20261123_000311_v04/) | 羽毛球 v0.4 输出及 review checks |
| [20261123_000758_v05](qwen3.8_omni_results/20261123_000758_v05/) | 羽毛球 v0.5 输出及 review checks |
| [20261123_001444_pipeline_v06](qwen3.8_omni_results/20261123_001444_pipeline_v06/) | 分音频、分镜头视觉管道，含音频、帧 manifest、阶段 prompt 与响应 |
| [20261123_002028_pipeline_v07](qwen3.8_omni_results/20261123_002028_pipeline_v07/) | 视觉复核、来源追踪、组合结果及校验 |
| [20261123_011332_pipeline_v08_alignment](qwen3.8_omni_results/20261123_011332_pipeline_v08_alignment/) | 增加音画对齐、逐镜头结果、校验、最终文字响应 |
| [20261123_120119_fps_comparison](qwen3.8_omni_results/20261123_120119_fps_comparison/) | 4 种输入模式的完整片段对照及汇总报告 |
| [20261123_120317_fps_tail_comparison](qwen3.8_omni_results/20261123_120317_fps_tail_comparison/) | 针对最后 0.5 秒的两种输入模式诊断 |

推荐先看最新[羽毛球文字输出](qwen3.8_omni_results/20261123_011332_pipeline_v08_alignment/badminton_response.txt)、[对齐 JSON](qwen3.8_omni_results/20261123_011332_pipeline_v08_alignment/alignment.json)和[迭代比较](badminton_pipeline/iteration_comparison.json)。`.partial.txt` 也原样保留，用于追溯流式响应，不自动视为最终输出。

## 羽毛球案例：当前能说明什么

v0.8 模型输出包含 3 个镜头、16 个动作实例，主要是手抛喂球、跨步、向上回球和回位，各 4 个。当前结果没有把“并步”或“挑球”确认成已证实标签。动作持续时间均小于 1 秒，中位数约 0.40 秒，说明镜头粒度与动作粒度在这个案例中存在明显区别。

音频记录有 6 个片段，对应 5 个原始话语单位。旧 `related_actions` 共 4 条关联，每个片段只连到一个动作；按当前纯时间共现定义对已有区间求交，会得到 11 条正时长交集。后者是对模型时间戳的计算审计，不是新的人类标注。

例如 U03“一个。”的模型区间为 `[4.52, 4.76]`，同时与 A10 跨步 `[4.30, 4.80]`、A11 向上回球 `[4.40, 5.00]` 重叠。旧关联只记录 A11。这个例子说明当前任务需要允许一段音频同时连接多个动作；它不证明这句话在语义上解释了两个动作。

审计也发现约 0.04–0.06 秒的微小交集，必须结合边界不确定性处理。旧文字中把 4.6 秒接触点描述成先于 4.52 秒话语起点，是数值比较错误，应以明确区间及重新核验结果为准。

审计文件：[current_case_temporal_audit.json](research/acl_publication_roadmap_20261123/current_case_temporal_audit.json)。原始输出状态是模型复核稿，尚未完成独立专家逐帧/逐音频人工核验。

## FPS 对照结果

同一段 8 秒羽毛球视频，同一任务内使用相同 prompt、模型、非 thinking 模式和最大输出 token 数；每个条件只调用一次。

| 输入模式 | video tokens | image tokens | 总 input tokens | 完整片段回答中的镜头数 |
| --- | ---: | ---: | ---: | ---: |
| 默认视频 | 4,754 | — | 5,182 | 2 |
| 旧写法：`video_url` 内嵌 `fps: 10` | 4,754 | — | 5,182 | 2 |
| 正确位置：内容项同级 `fps: 10` | 23,762 | — | 24,190 | 2 |
| 本地 10fps 时间戳图像 + 原视频 | 4,754 | 43,008 | 49,945 | 3 |

正确位置的 API 参数改变了视频 token 使用量，但完整片段回答仍遗漏末尾短镜头；改为专门询问最后 0.5 秒时，该模式能描述正面人物镜头。因此，回答漏写不能证明服务端没有提供末尾画面。

本地图像模式包含 84 张 960×540 图像，含显式时间戳和镜头端点补帧，还同时发送原视频；其完整片段输入 token 约为正确 API 10fps 模式的 2.06 倍。两者不只是同一帧率的不同写法，还改变了模态表示、图像缩放、时间提示和输入预算。各模式均有内容错误，镜头数和 token 数不是准确率。

这组结果是诊断性单次观测，不支持“本地抽帧普遍优于 API fps”的统计结论，也不是费用对照。详见[实验报告](qwen3.8_omni_results/20261123_120119_fps_comparison/experiment_report.txt)、[机器可读报告](qwen3.8_omni_results/20261123_120119_fps_comparison/experiment_report.json)及每种模式的原始响应。

## 生成与对比视频

以下 5 个本地已有视频一并归档。文件名进行了简化，原始名称与哈希见 [PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json)。这里不声称它们已经过定量质量评估。

| 文件 | 内容标识 |
| --- | --- |
| [jimeng_3722.mp4](media/jimeng_3722.mp4) | 生成视频 3722 |
| [jimeng_6050.mp4](media/jimeng_6050.mp4) | 生成视频 6050 |
| [jimeng_6459.mp4](media/jimeng_6459.mp4) | 生成视频 6459 |
| [side_by_side_jimeng_3722_reference.mp4](media/side_by_side_jimeng_3722_reference.mp4) | 3722 与参考视频的并排比较 |
| [side_by_side_jimeng_reference.mp4](media/side_by_side_jimeng_reference.mp4) | 已有生成视频与参考视频的并排比较 |

仓库先前的 [badminton_captions](../badminton_captions/)、[badminton_t2v](../badminton_t2v/)、[standing_long_jump_captions](../standing_long_jump_captions/) 和 [humocam_m3_s2_contortion](../humocam_m3_s2_contortion/) 保留在原路径。

## 脚本和复现边界

历史脚本位于 [.tools](.tools/)，阶段 prompt 位于 [badminton_pipeline](badminton_pipeline/)。图像需按 [README](README.md) 的命令解压，恢复历史目录布局。

脚本记录了实验使用的模型标识 `qwen3.8-omni-flash` 和用户提供的 Base URL `https://maas.qianwenaiapi.com/compatible-mode/v1`；这里只作为运行来源记录，不据此认证服务商身份。模型 API 密钥通过交互输入，归档不包含密钥。

部分历史脚本包含本机 FFmpeg 路径 `C:/Program Files (x86)/FormatFactory/ffmpeg.exe`；换设备需先配置该路径和相应 Python 依赖。历史元数据中的绝对路径保留原样。上传、下载脚本会访问 GitHub，模型脚本会调用对应服务；本次归档只保存代码，不自动执行这些操作。

要复现实验，应先核对输入 SHA256、版本 prompt、模型及服务端设置、采样方式和各阶段 provenance。服务端模型更新、随机输出和路径依赖会影响复现；现有记录支持追溯这次运行，不等于保证逐字重现。
