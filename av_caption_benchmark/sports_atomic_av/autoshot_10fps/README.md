# 以专业原子动作为中心的运动音视频 caption

本目录收录五段视频和 Qwen3.8-Omni-Flash 的英文模型输出。管道先用 AutoShot 切镜，按每秒 10 帧准备各镜头的视觉输入，再合并动作、独立音频事件及时间共现关系。TXT 保存模型生成的整段 caption，JSON 保存同次输出的动作和音频起止时间（相对片头，单位为秒）。网球另附姿态复核后的版本。

| 运动 | 输入视频 | 英文 caption | 带时间戳的完整输出 |
|---|---|---|---|
| 羽毛球 | [MP4](../../../badminton_lift_31679122798_first8s.mp4) | [TXT](badminton/caption.txt) | [JSON](badminton/caption.json) |
| 立定跳远 | [MP4](../../../standing_long_jump_1039046118_0-7s.mp4) | [TXT](jump/caption.txt) | [JSON](jump/caption.json) |
| 网球 | [MP4](tennis/video.mp4) | [TXT](tennis/caption.txt) | [JSON](tennis/caption.json) |
| 网球（姿态复核版） | [MP4](tennis/video.mp4) | [TXT](tennis/caption_reviewed.txt) | [JSON](tennis/caption_reviewed.json) |
| 保龄球 | [MP4](bowling/video.mp4) | [TXT](bowling/caption.txt) | [JSON](bowling/caption.json) |
| 滑板 | [MP4](skate/video.mp4) | [TXT](skate/caption.txt) | [JSON](skate/caption.json) |

## 视频来源

羽毛球和立定跳远链接到本仓库已有的原视频，已按文件内容校验。其余三段来自 Wikimedia Commons。

- 滑板 · Medvedev · 原片 0.5–6 秒。片段保留原声，重新编码为 MP4，并沿用来源许可。[来源](https://commons.wikimedia.org/wiki/File:Kickflip.ogv) · [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0)
- 保龄球 · RCraig09 · 原片 2–10.6 秒。片段保留原声，重新编码为 MP4，并沿用来源许可。[来源](https://commons.wikimedia.org/wiki/File:20190818_Zach_Wilkins_two-handed_bowling.webm) · [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0)
- 网球 · User:Evdcoldeportes · 原片 58–65.6 秒。片段保留原声，重新编码为 MP4，并沿用来源许可。[来源](https://commons.wikimedia.org/wiki/File:EVD-tenis-004.ogv) · [CC BY-SA 2.5 co](https://creativecommons.org/licenses/by-sa/2.5/co/deed.en)
