通用运动音视频标注管线 v0.1

长视频标注（仓库根目录运行）
  python -m sports_annotation long input.mp4 --out runs/my_video
  python -m sports_annotation long input.mp4 --out runs/my_video --lexicon sports_annotation/lexicons/badminton_bwf_v01.json --vosk-model PATH_TO_INSTALLED_MODEL
默认每 15 秒设一个主窗，两侧各保留最多 3 秒上下文。每窗独立看画面、听原声，再带原声复核动作。接缝用重叠原片判定是否为同一次动作或发声。分句另行复听，时间还原到原片时钟后计算动作、子阶段和声音的交集。词表可选。可选的独立词级核对需要本地 vosk 包和适配音频语言的模型。
输出目录含 caption.json、审阅.txt、各窗原始答复和用量。caption.json 的 edges 为动作级交叠，phase_edges 为子阶段交叠。review_flags 记录时间、跨窗身份等疑点，unlocalized_speech 保存无法定位的候选。正式评测前需复核。用相同参数与输出目录可继续此前运行。

用途
为 1–2 名主要参与者的短运动视频生成候选标注。动作和音频分别识别，时间关系由程序计算。
支持羽毛球、立定跳远、保龄球、高尔夫；两个保龄球案例使用相同术语表。
模型输出与同模型复核均不等于人工 GT。本版本不评估语言指代、声音来源或因果关系。

目录
  config/five_videos.json  五条测试视频、模型接口、采样和复核参数
  prompts/shared.txt      共同的证据、人物、时间轴和不确定性规则
  prompts/visual.txt      视觉独立标注
  prompts/audio.txt       独立音频事件；不做语音转写/OCR
  prompts/review.txt      音画证据复核；不直接预测对应关系
  prompts/omni_sports_caption.txt  基于用户提供的 Qwen 描述模板改写的完整音视频 caption prompt
  prompts/omni_sports_visual.txt  同一描述框架的独立视觉阶段（自然语言输出）
  prompts/omni_sports_audio.txt   同一描述框架的独立音频阶段（自然语言输出）
  prompts/omni_sports_review.txt  联合复核补充要求，与完整 caption prompt 一起使用
  lexicons/*.json        四类运动词表和判定条件
  lexicons/badminton_bwf_v01.json / .txt  BWF 教材依据的分层羽毛球词表草案，用于独立实验入口
  references/bwf_coach_level1_2017/     BWF 原始教材、页码索引及现有 case 的词表映射试用
  schemas.py             共享 JSON Schema，随请求写入 prompt
  media.py               真实 PTS、切镜、采样、保持偏移的音轨提取
  relations.py           半开区间交集及边界不确定性传播
  client.py              显式 API 调用、原始回答、费用使用记录、缓存
  pipeline.py            流程和结果汇总
  tests/                 合成数据/模拟响应测试；不是五条视频的标注结果
  runs/                  本地运行记录，已由 .gitignore 排除

BWF 分层羽毛球实验
  python -m sports_annotation.hierarchical_experiment --run-dir sports_annotation/runs/badminton_bwf_hierarchical_v02
  加 --dry-run 只准备媒体和请求。默认沿用 five_videos_general_rules.json 的模型与媒体参数。
  使用 prompts/hierarchical_visual.txt、prompts/hierarchical_review.txt 和原独立 audio.txt。
  新动作字段：movement_roles、body_parts、subphases。阶段与子阶段不增加主技术动作计数。
  输入为本地 10 fps 抽帧加真实时间戳，复核按原采样设置补帧；未设置 API fps。
  原始回答、输入、模型用量和协议快照存入运行目录；只对有效名义区间计算时间交集。
  此实验保留时间/证据问题供人工审阅，不把同模型复核称为人工 GT。
  2026-11-25 首轮：runs/badminton_bwf_hierarchical_20261125_v01/；三个请求已完成。
  该轮复核纠正了第二镜头的人物角色，却新增疑似重复动作；先读 badminton/本轮结果审阅说明.txt。
  修改代码、prompt 或词表后须使用新的运行目录，不能覆盖原协议快照。

完整音视频描述 prompt
prompts/omni_sports_caption.txt 保留自然语言时间线，输出 Storyline、Atomic Actions、Audio Events、
Temporal Correspondence 四部分；去掉 OCR、逐字转写、语义指代和声音与可见人物的身份绑定。
这是供同时输入画面与音频时使用的独立完整 prompt，不要与 shared.txt 的 JSON 输出要求拼接。
现有 CLI 仍使用 visual/audio/review 分阶段 JSON 管线；尚未切换为这一自然语言输出格式。
该 prompt 中的对应列表由模型给出，仅供人工阅读，不能替代 relations.py 根据独立时间区间计算的结果。

一次性与分阶段自然语言 caption 对比
  python -m sports_annotation.caption_experiment --case badminton --run-dir sports_annotation/runs/badminton_caption_compare_20261125_v01
默认使用 five_videos_live_compact.json。一次性 single 同时输入基础帧与音频；visual 仅画面，audio 仅音频，
review 输入相同基础帧、原始音频及 visual/audio 候选，不额外增加复核帧。对应四个独立请求，
其中分阶段方案使用三个请求，因此这不是计算预算相等的实验。小幅时间误差不触发重试。
自然语言输出不经 JSON Schema 解析，不写入原管线的 result.json；原文存入各阶段 response.txt。
完整 prompt、媒体哈希、模型使用量和所有失败尝试分别留存；连接中断最多追加一次重试。
--dry-run 只准备 single/visual/audio 请求，不发送 API；review 请求需候选生成后才能准备。
这两种新方案均未输入人工修正或 GT；时间对应由模型直接列出，尚未经过程序重新计算或人工验证。

环境与安装
从仓库根目录运行。Python 3.10+，本机需 FFmpeg。
  python -m pip install -r sports_annotation/requirements.txt
支持在 PATH 中查找 FFmpeg；Windows 还会检测本机 FormatFactory 的 ffmpeg.exe。
也可以在 config 的 media.ffmpeg 中设置绝对路径。

当前机器已经准备好独立环境：
  E:\Download\sports_video_data\.tools\.venv_sports_annotation\Scripts\python.exe
下方 python 可替换为该路径；PowerShell 执行引号内路径时在前面加 &。

第一步：纯离线准备，不需要密钥，不发送任何模型请求
  python -m sports_annotation prepare --run-dir sports_annotation/runs/pilot_v01
生成每个视频的真实帧时间戳、JPEG、同步 WAV、逻辑镜头和视觉/音频完整 prompt。
也可使用：
  python -m sports_annotation run --dry-run --run-dir sports_annotation/runs/pilot_v01

第二步：先运行独立视觉和音频候选阶段（会调用 API）
  python -m sports_annotation run --run-dir sports_annotation/runs/pilot_v01
默认读取 QWEN_API_KEY；没有此环境变量时，在终端隐藏输入密钥。密钥不写入配置、prompt 或日志。
base_url/model 在 config 中可配置，当前沿用已有成功调用的地址和模型名称。
provider.extra_body 默认 enable_thinking=false，按所用服务的能力修改；不会自动换接口或参数重试。
官方输入格式参考：
  https://help.aliyun.com/en/model-studio/qwen-omni
  https://help.aliyun.com/en/model-studio/qwen-api-via-openai-chat-completions

第三步：先准备局部复核输入，仍不调用 API
  python -m sports_annotation review --dry-run --run-dir sports_annotation/runs/pilot_v01
这一步需要候选阶段成功完成。保留全部基础帧，在关键点和边界附近补充真实原帧率帧。
额外帧受 max_review_frames 和请求字节预算限制；保留全部基础帧，并为音轨、prompt 留出空间。
未提供的加密帧数量写入 review_plan.json 和复核 prompt。

第四步：运行证据复核（会调用 API）
  python -m sports_annotation review --run-dir sports_annotation/runs/pilot_v01
也可以一次运行候选与复核：
  python -m sports_annotation run --with-review --run-dir sports_annotation/runs/pilot_v01
每条短片通常是视觉、音频、复核三个请求。默认逐视频逐阶段执行。
完整返回但未通过 JSON/范围校验时，最多增加一次带具体错误反馈的模型重试，原回答和重试均保留。
可设置 provider.max_validation_repairs=0 禁用。网络失败、超时或异常长字符串中断不会自动重试。
相同输入成功完成的阶段直接复用。失败的阶段再次执行同一命令时才重试。

只运行一个/几个视频
  python -m sports_annotation run --case badminton --case standing_jump --run-dir sports_annotation/runs/pilot_v01
可选 ID：badminton, standing_jump, bowling_two_handed, bowling_one_handed, golf_instruction。

重新校验和汇总已有输出，不调用 API
  python -m sports_annotation assemble --run-dir sports_annotation/runs/pilot_v01
  python -m sports_annotation validate --run-dir sports_annotation/runs/pilot_v01
validate 同时重新生成确定性汇总，不改变模型原始回答。模型结果缺失/失败时会明确报错。

版本与恢复
准备阶段冻结配置、代码、prompt、词表和源视频哈希；请求签名还包括实际媒体附件、模型参数和候选内容。
相同目录只用于原样续跑。修改 prompt/词表/代码/采样参数后使用新的 --run-dir，例如 runs/pilot_v02。
不要手改已完成模型 result.json；缓存会检查哈希。人工修订应另存，避免混同模型输出。
RUNNING.lock 表示正在调用；进程崩溃后先确认其已停止，再清理该阶段的锁文件。
中断/截断/不合法 JSON 不算完成；原始 partial 回答仍保留。不通过程序静默修补模型事实或边界。
若使用模型反馈重试，metadata.json 的 accepted_response_path 指向接受的原始回答；基础 response.txt 保留第一次回答。

时间与切镜
读取每帧实际 PTS，适用于变帧率。10 fps 是本地目标采样密度，不是 API fps 参数；实际帧清单为准。
音轨按源 PTS 对齐到同一片头零点，保留原始音画偏移。为统一长度补齐的静音不算真实声音。
首轮保留原分辨率；max_frame_width 可配置，但不会放大小尺寸视频。
默认使用 FFmpeg scene 阈值产生待核查切点，不把该后备检测器称为 AutoShot。
若已有 AutoShot 结果，在某条 case 的 cuts_file 指定仓库内 JSON：
  [3.866667, 7.633333]
或 {"detected_cut_seconds": [3.866667, 7.633333]}。
切点按实际帧边界对齐。短于 4 秒的逻辑镜头仍保留，多个镜头可打包在一次请求里。
本版本面向当前短片；超过 max_clip_seconds 的输入明确拒绝，不偷偷裁掉尾部或重新归零。
长视频滑窗、自动人物跟踪和局部人物裁切尚未实现。

外部语音接口
每条 case 可设置 external_speech_file，路径相对仓库根目录。文件格式：
  {"source_sha256":"对应 MP4 的 SHA256", "time_origin":"clip_start", "events":[...]}
events 使用 schemas.py 的 AUDIO_EVENT 结构，kind 必须为 speech。每项包含：
  id, kind, layer, start, end, start_range, end_range, speaker_id,
  description, evidence([{time,observation}]), confidence, transcript。
transcript 可为 null；不要求做语言含义分析。外部分段必须已经对齐到当前片段零点。
启用后 Qwen 音频阶段只标非语音，外部语音在合并时加入。复核阶段不得改写外部语音字段。
字幕/OCR 无论何时都不作为视觉动作或音频内容的证据。

输出（每个 case 目录）
  media/manifest.json       源哈希、PTS、逻辑镜头、实际采样帧、音频有效区间
  media/review_plan.json    复核选帧及未覆盖的加密帧
  stages/<stage>/prompt.txt 完整实际请求 prompt，含 schema 和时间戳
  stages/<stage>/request.json  请求签名和媒体摘要，不存 base64 或密钥
  stages/<stage>/response.txt  原始完整模型文本
  stages/<stage>/result.json   通过校验的模型 JSON
  stages/<stage>/metadata.json 状态、用量、耗时；成功才可续跑复用
  annotations.json         动作、音频、关系及来源
  relations.json           全部动作×音频配对和分层结果
  caption.txt              从结构化结果确定性生成的可读时间线
  review_queue.json        待人工核查的边界、切镜、低置信事件
  summary.json             数量、状态、模型用量；不是模型准确率

标注与关系规则
动作是 motion/held_pose/gesture 三种；完整 execution 是父级组织单元，不再次计入原子动作数。
同一时段多个肢体阶段、两个人的动作均可重叠。语音保持独立事件 ID，可以跨镜头。
默认主关系只包含 motion × foreground；姿态、手势、背景声放在 context_edges，仍完整保留。
区间为 [start,end)，仅接触端点不算重叠。
校验允许 1 毫秒的数值序列化误差，保留模型原值。关键点的估计时刻须在动作名义区间内，
关键点不确定范围可以延伸到动作自身的外层不确定范围。
证据时刻与输入帧相差 2–51 毫秒时，暂作为舍入后的证据时间接收，并写入 rounded_evidence_time 待审项；
不把最近帧自动等同于模型实际引用的帧。超过该范围仍拒绝。此容差不代表模型时间精度。
用 start_range/end_range 推导重叠时长的保守上下界：下界>0 为 overlap，上界=0 为 disjoint，其余 uncertain。
这表示对模型给出的边界范围进行计算，不是经校准的置信概率。nominal_overlap 另存，避免掩盖临界情况。
所有非重叠配对也保留；没有观测到一个动作不等于证明它不存在。
对应关系只表示时间交集，不表示语音在谈论动作、人物在发声或该动作产生声音。

离线测试
  python -m unittest discover -s sports_annotation/tests -v
覆盖多对多时间关系、临界交集、背景/姿态分层、错误引用、外部语音锁定、模拟 API 缓存/截断，
以及真实 FFmpeg/PyAV 处理的变帧率合成片和有偏移的音轨。测试不访问实际模型服务。
