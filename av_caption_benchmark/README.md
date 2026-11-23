# 专业原子动作音视频 Caption Benchmark：研究归档

归档日期：2026-11-23。这里汇总当前研究想法与已有本地结果，不代表已建成或已发表的 benchmark。

目前的核心问题是：**音视频 caption 是否准确保留专业原子动作、音频片段各自的时间信息，以及二者的同期关系？** 当前定义只要求时间共现，不评价一句解说在语义上指向哪个动作，也不把声音与动作同时出现解释为因果关系。

## 阅读顺序

1. [当前研究方案](CURRENT_PROPOSAL.md)：已确认范围、候选贡献、评测设计与待验证问题。
2. [已有结果](RESULTS.md)：全部 8 个 Qwen 运行目录、帧率对照、案例审计、视频和复现说明。
3. [方案演变](DECISIONS.md)：历史 prompt 与调研如何衔接到当前定义。
4. [ACL 调研与路线报告](research/acl_publication_roadmap_20261123/report.txt)：最接近工作的比较、评测协议、投稿工作量与建议实验。
5. [80 篇文献索引](research/acl_publication_roadmap_20261123/bibliography.txt)及[机器可读索引](research/acl_publication_roadmap_20261123/bibliography.json)：包含此前 70 篇范围综述与本轮新增 10 项；不表示 80 篇都做了全文逐页精读。

## 目录

| 路径 | 内容与状态 |
| --- | --- |
| `badminton_prompt*.txt`、`jump_prompt.txt` | 历版专业动作描述 prompt，保留原文 |
| [badminton_pipeline](badminton_pipeline/) | 音频、视觉、复核和对齐 prompt，以及迭代说明 |
| [qwen3.8_omni_results](qwen3.8_omni_results/) | 模型原始响应、结构化输出、配置、使用量、校验及来源记录 |
| [research](research/) | 多轮调研、案例比较、80 篇索引和实验计划 |
| [.tools](.tools/) | 16 个历史处理、运行、复核、上传下载和调研脚本 |
| [transfer2paas_2](transfer2paas_2/) | 实验输入裁剪片段；立定跳远当前使用 0–7 秒版本 |
| [media](media/) | 本地已有的生成视频和并排比较视频 |
| [assets/source_frames_and_previews.zip](assets/source_frames_and_previews.zip) | 288 张原始抽帧、接触表和预览图，保留原始相对路径 |
| [PUBLICATION_MANIFEST.json](PUBLICATION_MANIFEST.json) | 474 个原始文件的路径、字节数、SHA256、存储位置和归档范围 |
| [PUBLICATION_FILES.json](PUBLICATION_FILES.json) | 实际提交文件的大小、SHA256 和 Git blob SHA；不包含该清单自身 |

## 恢复图像文件

为了避免数百张抽帧分散浏览，图片集中存入 ZIP。下载仓库后，在 `av_caption_benchmark` 目录运行：

```shell
python -m zipfile -e assets/source_frames_and_previews.zip .
```

解压会恢复 `qwen3.8_omni_results/.../media/frames/`、`.tools/` 和研究预览图等原始相对路径。ZIP 中没有模型密钥或浏览器配置。

## 归档边界

保留所有已盘点的本地自写研究材料和实验结果，包括不完善的历史输出；新说明文件负责标注其状态，不修改原始实验记录。仓库原有的 caption 和生成结果继续保留。

论文 PDF、抽取全文、第三方仓库源码和下载的数据集样例未重复发布；对应来源 URL、版本和 SHA256 保存在各研究目录的 `sources/manifest.json` 中。历史报告中指向这些本地缓存的路径，需按来源清单重新下载后才能使用。完整未裁剪源视频、重复仓库下载包、浏览器配置、Python 缓存和 Git 内部数据不属于本次研究结果归档。

历史 JSON 中的绝对路径和来源字段保持原样，供追溯实验；在其他设备上重新运行时需要调整配置。自动检查结果与模型复核不能代替人工专业标注。
