# 运动音视频 caption · v0.8 多运动适配版

8 个视频均使用 Qwen3.8-Omni-Flash。切镜后将不足 4 秒的镜头合并进相邻片段，保留原切点和两侧的采样帧。表中动作数是模型输出，音频与动作的时间戳以各视频片头为零点。

| 样例 | 视频分辨率 / 送模帧宽 | 原镜头数 → 推理段数 | 视频时长¹ | 动作数 | 视频与结果 |
|---|---|---|---:|---:|---|
| 羽毛球 | 1280×720 / 960 px | 3 → 1 | 8.00 s | 16 | [MP4](../../../badminton_lift_31679122798_first8s.mp4) · [caption](badminton/caption.txt) · [JSON](badminton/combined_annotations.json) · [prompt](badminton/prompts) · [原始回答](badminton/responses) · [输入参数](badminton/run.json) |
| 立定跳远 | 1920×1080 / 960 px | 2 → 1 | 7.00 s | 9 | [MP4](../../../standing_long_jump_1039046118_0-7s.mp4) · [caption](jump/caption.txt) · [JSON](jump/combined_annotations.json) · [prompt](jump/prompts) · [原始回答](jump/responses) · [输入参数](jump/run.json) |
| 网球发球 | 320×240 / 960 px | 1 → 1 | 7.60 s | 7 | [MP4](../autoshot_10fps/tennis/video.mp4) · [caption](tennis/caption.txt) · [JSON](tennis/combined_annotations.json) · [prompt](tennis/prompts) · [原始回答](tennis/responses) · [输入参数](tennis/run.json) |
| 滑板 | 1024×576 / 960 px | 1 → 1 | 5.50 s | 3 | [MP4](../autoshot_10fps/skate/video.mp4) · [caption](skate/caption.txt) · [JSON](skate/combined_annotations.json) · [prompt](skate/prompts) · [原始回答](skate/responses) · [输入参数](skate/run.json) |
| 双手保龄球 | 960×540 / 960 px | 1 → 1 | 8.60 s | 7 | [MP4](../autoshot_10fps/bowling/video.mp4) · [caption](bowling/caption.txt) · [JSON](bowling/combined_annotations.json) · [prompt](bowling/prompts) · [原始回答](bowling/responses) · [输入参数](bowling/run.json) |
| 双手保龄球（同一动作高清版） | 1920×1080 / 1920 px | 1 → 1 | 8.60 s | 7 | [MP4](bowling_1080p/video.mp4) · [caption](bowling_1080p/caption.txt) · [JSON](bowling_1080p/combined_annotations.json) · [prompt](bowling_1080p/prompts) · [原始回答](bowling_1080p/responses) · [输入参数](bowling_1080p/run.json) |
| 单手保龄球 | 1920×1080 / 1920 px | 1 → 1 | 5.51 s | 6 | [MP4](bowling_loft_1080p/video.mp4) · [caption](bowling_loft_1080p/caption.txt) · [JSON](bowling_loft_1080p/combined_annotations.json) · [prompt](bowling_loft_1080p/prompts) · [原始回答](bowling_loft_1080p/responses) · [输入参数](bowling_loft_1080p/run.json) |
| 高尔夫挥杆 | 1920×1080 / 1920 px | 4 → 1 | 5.21 s | 10 | [MP4](golf_1080p/video.mp4) · [caption](golf_1080p/caption.txt) · [JSON](golf_1080p/combined_annotations.json) · [prompt](golf_1080p/prompts) · [原始回答](golf_1080p/responses) · [输入参数](golf_1080p/run.json) |

¹ 时长取视频轨时间轴。立定跳远采样 12.5 fps，滑板 12 fps，其余约 10 fps。高清样例的采样帧宽为原生 1920 像素。

羽毛球、立定跳远与高清高尔夫使用合并后的片段重新执行视觉识别、视觉复核和音视频对齐。其余五例的分段、采样帧和音轨与上一轮相同，复用同次输出。

## 这批实际使用的 prompt

羽毛球的共享说明、视觉识别与复核模板沿用[归档 v0.8 原文](../../badminton_prompt_v0.8.txt)。其他运动采用专项词表，并改写了视觉识别与复核指令；立定跳远本次使用该适配版。八例的独立音频模板与音视频对齐基础模板均沿用归档版。羽毛球、立定跳远和高尔夫在视觉、复核和音视频对齐请求中额外写明段内切点和跨切点的证据要求。每例的 `prompts/` 收录四个实际请求的完整文本，含当次帧时标或候选标注。[归档分阶段模板](../../badminton_pipeline/README.txt)。

每例的 `responses/` 保存对应四个阶段采用的模型回答原文。羽毛球首次视觉回答末尾有闭合括号错位，恢复 JSON 时核对过所有字段和值；该回答原文仍按收到的内容保存。最终 `combined_annotations.json` 含复核后的动作、独立音轨、声画对齐和原始切点。

## 高清视频来源

- 双手保龄球取自2.00–10.60 秒，保留原声并转码为 MP4。作者为 RCraig09。[来源](https://commons.wikimedia.org/wiki/File:20190818_Zach_Wilkins_two-handed_bowling.webm) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- 单手保龄球取自全长，保留原声并转码为 MP4。作者为 RCraig09。[来源](https://commons.wikimedia.org/wiki/File:20190818_EJ_Tackett_lofting_bowling_ball.webm) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)
- 高尔夫取自10.35–15.55 秒，保留原声并转码为 MP4。作者为 U.S. Navy / Seaman Gary Buckles。[来源](https://commons.wikimedia.org/wiki/File:Diego_Garcia_Long_Drive_Challenge_%28957829%29.webm) · [Public domain in the United States](https://creativecommons.org/publicdomain/mark/1.0/)

[原有五例及视频来源](../autoshot_10fps/README.md)。
