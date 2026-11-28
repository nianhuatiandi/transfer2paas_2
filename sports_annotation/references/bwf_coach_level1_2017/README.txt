BWF 羽毛球技术材料与词表索引
整理日期：2026-11-25

原始材料
  BWF_Coaches_Manual_Level1_2017_EN.pdf
  名称：BWF Badminton Coach Education: Coaches' Manual, Level 1
  发布者：Badminton World Federation（世界羽联）
  版本：2017 年 9 月第二版；282 个 PDF 页面；ISBN 978-967-15281-7-4。
  下载地址：https://www.badminton-israel.co.il/newsNdata/General/CoachEducationBWF/BWF_Coach_Manual_Level_1.pdf
  文件大小：5,636,154 字节。
  SHA256：f8643a9ea0227a74cc82170f152b166e4481e9ff90b055da9eb0c9360c994bd7
  已核对版权页：BWF 官方编写；实际下载站点为以色列羽协的公开副本。
  该版本可用于核对这里的术语出处，不代表已经确认其为最新版本。

官方教材中的词表在哪里
  第 51 页（PDF 第 75 页）：模块 6，Components of Badminton Movements。
    列出 8 类移动组成；同页另列移动周期的 4 个阶段。
  第 53 页（PDF 第 77 页）：分腿启动步。
  第 57 页（PDF 第 81 页）：跑步、并步、后交叉步、单脚小跳/转体。
  第 61 页（PDF 第 85 页）：弓步、跳跃与落地相关技术。
  第 64 页（PDF 第 88 页）：移动组合；示例包括后退步或并步返回。
  第 84 页（PDF 第 111 页）：模块 7，Basic Strokes 的通用四阶段描述框架。
  第 85—128 页（PDF 第 112—155 页）：20 个击球技术小节及教学练习。
    总目录在 PDF 第 7—8 页；具体技术出处见词表逐项页码。
  第 101 页（PDF 第 128 页）：反手挑球。
  第 103 页（PDF 第 130 页）：正手挑球。
  第 35—38 页（PDF 第 52—55 页）：手喂球、球拍喂球及训练组织形式。

本项目整理的文件
  ../../lexicons/badminton_bwf_v01.json
    分层、机器可读的试用词表，包含来源和项目补充规则。
  ../../lexicons/badminton_bwf_v01.txt
    同一词表的中文阅读版，逐项列出英文、中文工作译名和两种页码。
  badminton_case_vocab_trial.txt
    对现有羽毛球模型结果进行词表映射试用；不是重新标注的 GT。
  page_previews/
    若干关键页面的渲染预览，用于核对表格和页码；完整内容以原 PDF 为准。

本项目与官方材料的边界
  教材提供的是技术术语、技术说明、训练方法及阶段结构。
  BWF 没有在这份教材中给出我们的 JSON 词表、原子动作计数或视频时间边界协议。
  中文是本项目工作译名；有疑义的术语保留英文，并标出待专业教练核对。
  项目补充的未知类、时间关键点、并行/计数规则均在 JSON 中单独标明。
  20 个击球条目目前均有名称索引和出处；只有本次重点移动/挑球项有较详细的视频证据规则。
  此草案已通过独立 hierarchical_experiment.py 接入实验，原扁平管线保持原接口。
  实际运行：sports_annotation/runs/badminton_bwf_hierarchical_20261125_v01/。
  已完成视觉、独立音频、联合复核三个请求；首轮结果存在疑似重复动作和标签/日志不一致，不能直接作为 GT。
  本目录 badminton_case_vocab_trial.txt 是实际调用之前的映射试用记录；本轮结果与审阅说明在上述运行目录。

关键发现
  “并步”是移动技术，“回位”是阶段/作用，不能把二者放在同一扁平列表重复计数。
  击球技术下可保留准备、引拍、向前挥拍、随挥；触球可另外保留关键时刻。
  挑球同时包括较平的进攻性挑球和较高的防守性挑球，不能一律要求高弧线。
  教材第 101 页的一个表头印为 FOREHAND SWING；本词表子阶段框架引用第 84 页，未擅改原 PDF。

官方资源入口（可核对材料体系）
  BWF：https://development.bwfbadminton.com/coaches/level-1
  Badminton Europe：https://development.badmintoneurope.com/cms/?cmsid=341&pageid=5514
  BWF 入口本次通过浏览工具访问失败，因此下载使用上述羽协公开副本。
