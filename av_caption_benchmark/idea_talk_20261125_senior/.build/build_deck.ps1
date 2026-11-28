$ErrorActionPreference = 'Stop'
$work = Split-Path $PSScriptRoot -Parent
$repo = 'E:\Download\sports_video_data\transfer2paas_2_git'
$assets = Join-Path $PSScriptRoot 'assets'
$out = Join-Path $work 'output'
$renders = Join-Path $PSScriptRoot 'renders'
$draft = Join-Path $PSScriptRoot 'candidate.pptx'
$video = Join-Path $repo 'video\av_caption_benchmark__transfer2paas_2__badminton_lift_31679122798_first8s.mp4'
$script:ink = 0x332D23
$script:navy = 0x6B4321
$script:blue = 0xAE7232
$script:muted = 0x77716A
$script:orange = 0x3186BD
$script:pale = 0xF8F4EE
$script:gray = 0xDFE1E3
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Add(0)
$deck.PageSetup.SlideWidth = 960
$deck.PageSetup.SlideHeight = 540
$deck.DefaultLanguageID = 2052
$script:notes = @()
$script:bounds = @()

function Font($range, [double]$size, [int]$color, [bool]$bold=$false) {
    $range.Font.Name = 'Times New Roman'
    $range.Font.NameFarEast = '宋体'
    $range.Font.NameAscii = 'Times New Roman'
    $range.Font.NameOther = 'Times New Roman'
    $range.Font.Size = $size
    $range.Font.Color.RGB = $color
    $range.Font.Bold = $(if ($bold) {-1} else {0})
    $range.ParagraphFormat.SpaceAfter = 0
    $range.ParagraphFormat.SpaceBefore = 0
}
function Txt($slide,[string]$text,[double]$x,[double]$y,[double]$w,[double]$h,[double]$size=20,[int]$color=$script:ink,[bool]$bold=$false) {
    $s = $slide.Shapes.AddTextbox(1,$x,$y,$w,$h)
    $s.TextFrame.MarginLeft=0; $s.TextFrame.MarginRight=0
    $s.TextFrame.MarginTop=0; $s.TextFrame.MarginBottom=0
    $s.TextFrame.WordWrap=-1; $s.TextFrame.AutoSize=0
    $s.TextFrame.TextRange.Text=$text
    Font $s.TextFrame.TextRange $size $color $bold
    # PowerPoint may resize an empty text box when margins change; restore intended bounds.
    $s.Width=$w; $s.Height=$h
    return $s
}
function Base([string]$title,[string]$subtitle='') {
    $s=$deck.Slides.Add($deck.Slides.Count+1,12)
    $s.FollowMasterBackground=0
    $s.Background.Fill.Solid(); $s.Background.Fill.ForeColor.RGB=0xFFFFFF
    [void](Txt $s $title 42 25 876 54 31 $script:navy $true)
    if ($subtitle) {[void](Txt $s $subtitle 44 83 870 30 17 $script:muted)}
    [void](Txt $s ([string]$s.SlideIndex).PadLeft(2,'0') 880 503 38 23 14 $script:muted)
    return $s
}
function Pic($slide,[string]$name,[double]$x,[double]$y,[double]$w,[double]$h) {
    $s=$slide.Shapes.AddPicture((Join-Path $assets $name),0,-1,$x,$y,$w,$h)
    return $s
}
function Foot($slide,[string]$text) {[void](Txt $slide $text 44 467 830 32 13 $script:muted)}
function Notes($slide,[string]$text) {
    $n=$slide.NotesPage.Shapes.Placeholders.Item(2)
    $n.TextFrame.TextRange.Text=$text
    Font $n.TextFrame.TextRange 14 $script:ink
    $script:notes += [pscustomobject]@{slide=$slide.SlideIndex; text=$text}
}
function Tab($slide,$rows,$widths,[double]$x,[double]$y,[double]$w,[double]$h,[double]$size=19) {
    $shape=$slide.Shapes.AddTable($rows.Count,$rows[0].Count,$x,$y,$w,$h)
    $t=$shape.Table
    for($c=1;$c -le $widths.Count;$c++) {$t.Columns.Item($c).Width=$widths[$c-1]}
    for($r=1;$r -le $rows.Count;$r++) {
        for($c=1;$c -le $rows[0].Count;$c++) {
            $cell=$t.Cell($r,$c)
            $cell.Shape.TextFrame.MarginLeft=10; $cell.Shape.TextFrame.MarginRight=10
            $cell.Shape.TextFrame.MarginTop=7; $cell.Shape.TextFrame.MarginBottom=5
            $cell.Shape.TextFrame.VerticalAnchor=3
            $cell.Shape.TextFrame.TextRange.Text=[string]$rows[$r-1][$c-1]
            if($r -eq 1) {
                $cell.Shape.Fill.ForeColor.RGB=$script:navy
                Font $cell.Shape.TextFrame.TextRange $size 0xFFFFFF $true
            } else {
                $cell.Shape.Fill.ForeColor.RGB=$(if($r%2 -eq 0){$script:pale}else{0xFFFFFF})
                Font $cell.Shape.TextFrame.TextRange $size $script:ink
            }
            for($b=1;$b -le 4;$b++) {$cell.Borders.Item($b).ForeColor.RGB=0xFFFFFF; $cell.Borders.Item($b).Weight=1}
        }
    }
    return $shape
}

# 01: a concise cover, with one source frame.
$s=Base '细粒度运动音视频描述评测'
[void](Txt $s '研究想法与待讨论问题' 44 96 840 36 24 $script:muted)
[void](Txt $s "Caption 能否保留专业动作`r及其与音频的时间关系？" 44 175 465 125 30 $script:ink $true)
[void](Pic $s 'frame_000090.jpg' 535 165 383 215.44)
[void](Txt $s "面向 1–2 人的运动视频`r以羽毛球解释标注与评测" 44 338 450 65 21 $script:ink)
Foot $s '研究讨论稿   2026.11.25   当前处于方案与案例验证阶段'
Notes $s "建议用时 40 秒。今天希望师兄首先判断：这个问题是否值得作为独立 benchmark 做下去。我们以人物不超过 2 人、能够按明确规范拆解的运动视频为范围，评价自然语言描述保留了哪些动作和时间结构。标注规范、指标和数据规模仍有待验证，不能把当前模型草稿当作专家 GT。`r来源：用户研究讨论；sports_annotation/protocols/three_level_action_standard_v1.txt。画面来自用户提供的李宇轩教练 8 秒羽毛球教学片段，frame 90，原始时间 3.0 秒。"

# 02: embed the original clip, not a linked external resource.
$s=Base '先看这段 8 秒羽毛球视频' '先观察人物和脚步，再听语音及短促声'
$movie=$s.Shapes.AddMediaObject2($video,0,-1,44,132,620,348.75)
[void](Txt $s '谁做了什么？' 700 151 216 40 23 $script:navy $true)
[void](Txt $s '同类动作是哪一次？' 700 239 216 72 23 $script:navy $true)
[void](Txt $s "动作发生时，`r哪些声音也在发生？" 700 337 216 92 23 $script:navy $true)
[void](Txt $s '放映时点击视频播放原声' 44 490 600 22 14 $script:muted)
Notes $s "建议用时 60 秒，播放原片一遍，必要时再听一遍。先不要告诉师兄我们预期有几次动作，让他观察不同人物、步法、击球及回位。要区分人物的移动方向、挥拍方向与球的飞行方向。最后的镜头切换不应机械决定音频句子的边界。`r素材：用户本地 video/av_caption_benchmark__transfer2paas_2__badminton_lift_31679122798_first8s.mp4。作者水印为李宇轩教练。视频原声嵌入本 PPTX，素材为研究讨论示例。"

# 03: three distinct frames and the preferred BWF candidate excerpt.
$s=Base '细粒度标注具体要保留什么' '同一人的步法与挥拍允许重叠，动作实例分别定时'
foreach($item in @(@('frame_000012.jpg',44,0.4),@('frame_000030.jpg',340,1.0),@('frame_000042.jpg',636,1.4))) {
    [void](Pic $s $item[0] $item[1] 122 280 157.5)
    [void](Txt $s (([string]$item[2])+' s') $item[1] 284 280 23 16 $script:muted)
}
$rows=@(@('动作候选','区间 / s','需保留的信息'),@('弓步跨出','0.40–1.00','人物、跨出方向、支撑变化'),@('正手挑球','0.80–1.30','持拍侧、挥拍方式、可见出球'),@('并步回位','1.10–1.50','真实脚序、回位方向与结束位置'))
[void](Tab $s $rows @(220,180,476) 44 315 876 140 18)
Foot $s '取自用户认可的 BWF 版本模型草稿。术语、脚序及边界仍需人工复核。'
Notes $s "建议用时 70 秒。这三条来自当前较好的 BWF 分层标注版本，展示我们想保留的字段，而不是宣称它们已经成为正确 GT。弓步与挑球时间重叠，挑球随挥也可能与回位开始重叠。因此不能要求同一人的全部动作排成互斥片段。并步回位仍需要看脚的连续顺序，不能因为有回位就直接叫并步。单帧仅辅助展示，类别和边界必须结合连续帧判断。`r来源：sports_annotation/runs/badminton_bwf_hierarchical_20261125_v01/badminton/annotations.json，A_S01_LUNGE_1、A_S01_STROKE_1、A_S01_RECOVER_1。图片为原片 0.4、1.0、1.4 秒的源帧。"

# 04: project hierarchy, with clearly separated phase/state concepts.
$s=Base '拟议的三层动作标准' '先固定标注单位，再讨论最细层是否值得作为主评任务'
$rows=@(@('层级','含义','羽毛球示例'),@('L1  完整过程','围绕一次核心尝试的执行过程','一次上网回球及回位'),@('L2  功能动作','具有独立功能的可辨识技术实例','弓步、挑球、并步回位'),@('L3  身体运动','某部位的一种可见运动连续片段','腿前移、膝屈曲、持拍臂上挥'))
[void](Tab $s $rows @(180,370,326) 44 128 876 205 19)
[void](Txt $s '引拍、随挥：内部阶段     触球：关键点     保持准备：状态' 44 355 876 52 21 $script:ink)
[void](Txt $s '建议先以 L2 为主评，L3 用于可见细节充分的诊断子集。' 44 419 876 34 22 $script:navy $true)
Foot $s 'BWF 提供部分技术术语。本项目定义层级、边界和计数规则；L3 示例尚非已核验标注。'
Notes $s "建议用时 80 秒。三层是本项目操作定义，不是 BWF 官方发布的三层机器标注标准。L1 组织完整执行过程，L2 是功能动作，L3 是部位运动。L3 相对于注册词表不可再拆：主体、部位、参照和运动谓词保持不变时，保留最大连续片段；谓词改变、明确方向反转或新的重复实例才切分。速度变化或纯阶段变化不自动切分。一个简单 L2 可以只对应一个可见 L3，不为凑层级编细节。三层分别计数，不能相加。建议请师兄判断是否用 L2 主评，避免 L3 大幅增加标注成本却没有额外解释力。`r来源：sports_annotation/protocols/three_level_action_standard_v1.txt，第 1、2、4、5、9 节。BWF 教练教材第二版，2017，模块 6、7；公开副本：https://www.badminton-israel.co.il/newsNdata/General/CoachEducationBWF/BWF_Coach_Manual_Level_1.pdf。"

# 05: editable native interval data plot.
$s=Base '动作与音频采用独立时间轴' '对应关系指时间共现，允许一对多与多对多'
$axisLeft=160; $axisRight=620; $scale=($axisRight-$axisLeft)/1.4
for($tick=2;$tick -le 16;$tick+=2) {
    $value=$tick/10.0
    $xx=$axisLeft+($value-0.2)*$scale
    $grid=$s.Shapes.AddLine($xx,136,$xx,378)
    $grid.Line.ForeColor.RGB=0xDFE1E3; $grid.Line.Weight=0.6
    [void](Txt $s ($value.ToString('0.0',[Globalization.CultureInfo]::InvariantCulture)) ($xx-14) 383 42 25 16 $script:muted)
}
$intervals=@(@('弓步',0.4,1.0),@('挑球',0.8,1.3),@('回位',1.1,1.5),@('语音 U1',0.96,1.44))
for($i=0;$i -lt $intervals.Count;$i++) {
    $row=$intervals[$i]; $yy=145+$i*60
    [void](Txt $s $row[0] 44 $yy 104 30 20 $script:ink)
    $left=$axisLeft+($row[1]-0.2)*$scale; $width=($row[2]-$row[1])*$scale
    $bar=$s.Shapes.AddShape(1,$left,$yy,$width,30)
    $bar.Name='interval_'+$i+'_'+$row[1]+'_'+$row[2]
    $bar.Fill.ForeColor.RGB=$(if($i -eq 3){$script:orange}else{$script:blue})
    $bar.Line.Visible=0
    $label=$row[1].ToString('0.00',[Globalization.CultureInfo]::InvariantCulture)+'–'+$row[2].ToString('0.00',[Globalization.CultureInfo]::InvariantCulture)
    $labelShape=Txt $s $label ($left+4) ($yy+4) ($width-8) 24 16 0xFFFFFF
    $labelShape.TextFrame.TextRange.ParagraphFormat.Alignment=2
}
[void](Txt $s '时间 / s' 44 383 104 27 16 $script:muted)
[void](Txt $s 'U1：0.96–1.44 s' 660 137 258 38 24 $script:navy $true)
[void](Txt $s "与挑球重叠 0.34 s`r与回位重叠 0.34 s" 660 196 258 85 22 $script:ink)
[void](Txt $s "与弓步仅重叠 0.04 s`r这条边对边界误差敏感" 660 299 258 80 19 $script:muted)
[void](Txt $s '关系不要求“话语在讲这个动作”，也不要求声音由该动作产生。' 44 429 876 35 21 $script:ink)
Foot $s '以上是模型候选区间的名义交集，尚非真实对齐结论。切镜不强制切开持续语音。'
Notes $s "建议用时 80 秒。这页用当前模型草稿的区间做确定性计算。U1 是第一段语音，不以转写语义决定动作归属。它与挑球相交 0.34 秒，与回位也相交 0.34 秒；与弓步相交只有 0.04 秒，必须考虑边界不确定性，不能直接称为可靠的关系 GT。一般情况下，同一动作还可以同时与语音和非语音短声重叠，不同人物也各有时间轴。持续背景音乐单独处理，避免把几乎全连接的简单关系当成主要成绩。端点相接不算重叠。当前 U004 的候选区间 6.96–8.00 秒还跨越 7.633 秒切镜，说明镜头不能替代音频分段。`r来源：原 BWF 视觉草稿的前三个动作，及 sports_annotation/runs/badminton_bwf_gpt_sol_qwen_transcript_20261125_v05/badminton/audio_transcript.json，U001。交集公式 max(0,min(end_a,end_u)-max(start_a,start_u))。"

# 06: annotation and expert verification.
$s=Base '模型生成候选，人工建立 GT' '视觉与音频独立标注，避免用一种模态的预期补全另一种模态'
$rows=@(@('步骤','输入与产出','关键检查'),@('视觉候选','画面与技术词表；人物、动作、细节、边界','重复实例、身体左右、回位、遮挡'),@('音频候选','原始音频；逐字原话、声音事件、各自边界','听不清保留未知；跨切镜语音持续'),@('人工复核','标注员复核，专项人员仲裁；抽样独立双标','术语一致性、实例一致性、边界偏差'),@('冻结与派生','冻结节点和时间；代码计算关系与交集','版本记录、边界不确定、有效评估范围'))
[void](Tab $s $rows @(146,395,335) 44 132 876 283 18)
[void](Txt $s '抽帧约 10 fps 可生成候选，精细 GT 仍需回看原帧与原音频。' 44 432 876 38 21 $script:navy $true)
Notes $s "建议用时 60 秒。当前 Qwen 是辅助标注器，不是 GT 的最终裁决者。视觉候选只用画面，音频候选只用音频。本轮音频已从只描述声音改为逐字转写，但文字和时间还需听音核验。不能让多个标注员都只接受同一模型答案，因此应保留一个从原始素材独立双标的子集，估计模型锚定偏差和人工一致性。专业动作由专项人员仲裁。原始视频时钟、镜头边界、动作边界与音频边界分开保存。术语、边界及同义词规则冻结后再测试模型。`r来源：本地 sports_annotation 标注管线、audio_transcript.txt 与三层规范 v1。所有 GT 流程为拟议研究设计，尚未完成专家验证。"

# 07: native caption compatibility and faithful extraction.
$s=Base '评价侧解析模型的原生 Caption' '保留模型原有提示词与输出形式，逐项核对文本实际表达的信息'
[void](Txt $s '示意 Caption' 44 132 355 36 23 $script:navy $true)
[void](Txt $s '“球员挑球后回位，期间传来口令。”' 44 188 355 128 29 $script:ink)
[void](Txt $s '每个结构字段保留原文证据。' 44 348 355 65 22 $script:ink)
$rows=@(@('可恢复的信息','解析结果'),@('动作内容','挑球、回位'),@('具体回位步法','未交代'),@('动作和语音边界','未提供独立时间'),@('精确音画对应','不足以恢复实例级关系'))
[void](Tab $s $rows @(225,270) 425 132 495 277 18)
[void](Txt $s '解析器不读取视频或 GT 补全答案；缺失、错误和解析失败分开记录。' 44 431 876 40 20 $script:navy $true)
Notes $s "建议用时 70 秒。这一条解决专用 caption 模型固定提示词和自由文本输出的接入问题。解析器只能读预测 caption，并记录原文证据位置，不能再看视频或 GT 补时间、补术语。示例中的回位不能自动变为并步，‘期间’也不足以决定口令与哪个具体动作重叠。没有时间的描述仍可得到内容正确性评价，精确时间列为缺失。转换不能预先声称无损，必须人工审计信息遗漏和新增事实。OmniCapBench 附录已经有 video-blind 的事后解析轨道，因此‘自由 caption 转结构’本身不是充分的新颖性。`r来源：用户研究设想；OmniCapBench，Appendix B.5–B.6，https://arxiv.org/html/2610.12458v1 。引号中的 caption 为本稿构造示例。"

# 08: interpretable metric groups.
$s=Base '分开评价内容、时间与关系' '先匹配人物、动作及具体轮次，再检查时间信息和音画关系'
$rows=@(@('评价对象','建议报告','防止什么问题'),@('动作与细节','实例 P / R / F1；可见细节准确率与覆盖率','泛称一次动作掩盖遗漏和重复'),@('动作、音频时间','时间提供率；边界误差；tIoU','只对少数容易样本报定位成绩'),@('动作—音频关系','边 P / R / F1；交集区间质量','全连边刷召回；混淆重复实例'),@('整体与条件成绩','端到端分数；两端识别正确时的条件分数','分清内容漏检与关系错配'))
[void](Tab $s $rows @(170,354,352) 44 132 876 280 18)
[void](Txt $s 'LLM judge 辅助核对语义等价；时间与区间关系交由确定性代码。' 44 431 876 38 20 $script:navy $true)
Notes $s "建议用时 80 秒。这里是指标设计建议，尚未形成经人工效度验证的统一总分。匹配应考虑人物、动作类别或等价描述以及可辨识轮次；只说反复挥拍不能自动得到每个实例的信用。匹配内容后分别评价动作和音频定位。没有独立时间时保留时间缺失，不能由解析器伪造。关系评分同时报告端到端表现和两个节点已经认对时的条件表现。持续背景声、短瞬态、语音、短动作等需要分组。LLM judge 只做有限的语义核对，需与人工结果校准，报告模型、提示词敏感性和解析器误差。tIoU 使用区间交集长度除以并集长度。`r来源：本项目 CURRENT_PROPOSAL.md 第 5 节；指标为拟议组合，不宣称 P/R/F1、tIoU 或区间求交是新算法。"

# 09: multiple-answer quiz as a caption utility diagnostic.
$s=Base '多选题作为补充诊断' '主轨道只让答题者读 Caption，测量描述保留了多少可用信息'
[void](Txt $s '示意 Caption：第二次挑球尚在随挥时，球员开始回位。这段时间听到计数“二”。' 44 128 876 79 25 $script:ink)
[void](Txt $s '听到“二”时，哪些动作正在发生？' 44 224 876 37 24 $script:navy $true)
[void](Txt $s "A   保持准备姿态`rB   第二次挑球`rC   回位移动" 44 281 390 128 21 $script:ink)
[void](Txt $s "D   另一人物手喂球`rE   描述未提供足够信息`r示意答案：B、C" 500 281 420 128 21 $script:ink)
[void](Txt $s '报告集合 F1 与全对率，随机化选项；“信息不足”作为独立回答。' 44 427 876 42 20 $script:navy $true)
Foot $s '多选题形式本身已有先例。直接看音视频答题的理解轨道，需与 Caption 保真轨道分开报告。'
Notes $s "建议用时 70 秒。多对多关系自然适合允许多个正确选项，但形式本身不构成充分创新。这道题是构造示例，不是已完成的人类核验题。基于 caption 的答题者不能接触视频或 GT；问题和正确答案由经核验的 GT 构造，并审查是否存在题面泄漏或语言常识捷径。选项避免给出能直接推算答案的全部时间戳。‘信息不足’单独选，不与其他选项混选。集合 F1 惩罚全选，严格全对率反映完整关系恢复。可以另设直接看音视频的问答轨道，但它评价的是原始理解，不能混同 caption 的信息保真。`r相关来源：CapQuiz，ACL 2026，https://aclanthology.org/2026.acl-long.777/ 。CapQuiz 用人工验证的多项选择问答评价 caption 的信息覆盖和事实性。"

# 10: honest positioning relative to the closest work.
$s=Base '已有工作覆盖了哪些部分' '研究价值需要通过标注单位与增量证据来证明'
$rows=@(@('相关工作','已有能力或设计','本项目需要进一步证明'),@('FineBadminton','专业羽毛球动作、多层语义与理解评测','独立步法/挥拍及音频关系有何额外价值'),@('OmniCapBench','结构化单位、音画关联、事后解析轨道','专业动作实例级关系带来哪些新诊断'),@('FAVE','音画时间对齐、事件关系与片段描述','短动作、重复实例与并发关系的增量'),@('CapQuiz','通过问答检查 Caption 的信息保真','多对多时间问题是否提高人工效度'))
[void](Tab $s $rows @(177,335,364) 44 132 876 280 18)
[void](Txt $s '不能仅以“更细、三层、能转 JSON、改成多选”作为创新结论。' 44 431 876 38 21 $script:navy $true)
Notes $s "建议用时 80 秒。这里重点请师兄判断项目能否与最接近工作拉开可验证的差异。FineBadminton 已有基础动作、战术语义和决策评价等层次，不能声称专业动作标签本身新颖。OmniCapBench 已有实体、视觉片段和音频事件的结构化诊断，EVSA 检查音频事件与视觉镜头关联，附录也测试了事后解析。FAVE 已针对音画时间对齐、事件关系和片段描述建立评测。CapQuiz 已通过人工核验问题测试 caption 信息保真。因此差异应落在独立、并发、密集重复的专业动作实例，以及这种单位是否能解释现有指标忽略的错误。以上差异是待验证的研究主张，不是对既有论文的绝对能力否定。`r来源：FineBadminton, ACM MM 2025, https://arxiv.org/html/2508.07554v1 ; OmniCapBench, https://arxiv.org/html/2610.12458v1 ; FAVE, CVPR 2026, https://openaccess.thecvf.com/content/CVPR2026/html/Lu_FAVE_A_Structured_Benchmark_for_Fine-Grained_Audio-Visual_Temporal_Evaluation_in_CVPR_2026_paper.html ; CapQuiz, ACL 2026, https://aclanthology.org/2026.acl-long.777/ 。"

# 11: a controlled example, explicitly not a measured existing-metric failure.
$s=Base '增量证据先从受控对照开始' '保持动作和语音内容不变，只交换它们对应的实例'
$rows=@(@('构造版本','第 1 次挑球','第 2 次挑球'),@('Caption A','期间出现语音“一”','期间出现语音“二”'),@('Caption B','期间出现语音“二”','期间出现语音“一”'))
[void](Tab $s $rows @(200,338,338) 44 138 876 166 23)
[void](Txt $s '若参考关系为 A，且只评价这两条边：' 44 329 876 38 22 $script:ink)
[void](Txt $s '关系 F1：A = 1.00，B = 0.00' 44 377 876 45 29 $script:navy $true)
[void](Txt $s '还需实测：现有指标能否区分？人类偏好是否支持这种差异？' 44 437 876 38 21 $script:ink)
Foot $s '构造示例及确定性计分，不是真实模型成绩；未宣称 BLEU、CIDEr 或其他指标已经失效。'
Notes $s "建议用时 70 秒。两份 caption 的人物、动作、次数、语音内容完全相同，只有对应实例不同。设示意 GT 为两条边 (A1,U一)、(A2,U二)，A 恢复两条，B 预测两条对调边，因此这个两边子问题的 F1 分别为 1 和 0。这是证明评测对象确实不同的逻辑例子，但还不是发表所需的实验证据。下一步必须在同一批 caption 上实际运行已有指标，检查它们的区分能力，并用盲评的人类判断做外部标准。再加入真实模型的错位、重复合并、人物交换和边界偏移样本，避免只在人工设计的题上有效。`r来源：本稿构造的受控示例；计分由集合交集确定，不引用外部实验分数。"

# 12: make the falsifiable novelty claim explicit.
$s=Base '创新性需要怎样的证据' '贡献候选是可复核资源、评测协议和新增诊断能力'
$rows=@(@('候选贡献','支持它的证据','可能否定它的结果'),@('专业动作与双时间轴资源',"专家可一致标注`r并覆盖真实并发与重复",'粒度无法稳定复现，主要靠模型猜测'),@('Caption 时间信息保真评测','解析可审计，能区分未说、说错和错配','分数主要由解析器或输出格式决定'),@('对现有评测的增量','新错误类型影响人工判断或模型结论','现有基准、指标已经能同样解释问题'))
[void](Tab $s $rows @(231,330,315) 44 133 876 245 18)
[void](Txt $s '必须比较强分解基线：动作定位 + 音频分段 + 区间求交。' 44 403 876 45 23 $script:navy $true)
Foot $s '区间求交是既有计算。核心问题是能否识别、定位并在描述中保留正确的事件实例。'
Notes $s "建议用时 70 秒。这里不主张单纯将两个时间区间取交集是一种新对齐算法。最重要的反例基线是：视觉模型独立定位动作，音频系统独立分段，再确定性求交。如果这个简单基线已经满足全部目标，我们需要说清楚 caption 作为语言表示还增加了什么挑战，例如事件信息被合并、省略、指代不清，或者动作与声音的对应在文本中丢失。拟议贡献是一个经专家确认的资源、一套信息保真的评价协议，以及能改变研究判断的增量证据，三者都必须验证。`r来源：本项目 CURRENT_PROPOSAL.md 第 4–6 节。该页为研究假设和建议实验，未完成统计验证。"

# 13: separate existing material from the next experiment.
$s=Base '当前基础与最小验证实验' '先验证必要性和标注可复现性，再决定是否扩大规模'
[void](Txt $s '已有基础' 44 131 385 36 25 $script:navy $true)
[void](Txt $s "5 个运动视频试验素材`r羽毛球多轮 Qwen 标注草稿`rBWF 术语整理与项目分层规范`r独立音频转写和区间关系计算" 44 185 390 180 21 $script:ink)
[void](Txt $s '尚无稳定专家 GT 或正式模型排名。' 44 387 390 64 20 $script:muted)
[void](Txt $s '建议先做 30 段、覆盖 3 类运动' 491 131 427 64 25 $script:navy $true)
[void](Txt $s "1   独立双标，核对实例与边界一致性`r2   原生 Caption 与强分解基线对照`r3   真实错误加受控错配，运行已有指标`r4   人类盲评，审计解析器与 judge" 491 211 427 178 21 $script:ink)
[void](Txt $s "按源视频划分数据`r控制帧率、输入预算及输出长度" 491 406 427 57 19 $script:muted)
Notes $s "建议用时 70 秒。现有本地 video 目录提供五个试验素材；当前可供展示的是羽毛球 BWF 视觉草稿及新的 Qwen 音频转写。另一次三层试跑暴露出 L3 过粗和错误传播，因此不能说自动标注已经成熟。所选 GPT-6.2 Sol 的完整图像标注尚未返回结果，本稿不展示不存在的 GPT 成绩。建议先做 30 段、3 类运动作为可调整的小规模计划，规模并不是保证发表的门槛。独立专家标签、解析器审计、盲评和强基线都完成后，再讨论扩展。视频源及重剪版本应放在同一数据划分，控制输入帧率、分辨率和输出长度，避免资源差异主导结论。`r来源：本地 video 目录；sports_annotation/runs/badminton_bwf_hierarchical_20261125_v01；badminton_bwf_gpt_sol_qwen_transcript_20261125_v05；three_level 试跑审阅说明。30 段和 3 类为建议计划，尚未执行。"

# 14: explicit questions and decisions for the senior researcher.
$s=Base '希望请师兄优先判断的问题' '首先确认研究问题与创新性是否成立'
[void](Txt $s '1' 45 137 45 43 30 $script:blue $true)
[void](Txt $s '主线是否应收敛为 Caption 中动作—音频时间信息的保真？' 104 138 812 66 25 $script:ink)
[void](Txt $s '2' 45 226 45 43 30 $script:blue $true)
[void](Txt $s 'L2 作为主评，L3 只做诊断子集，粒度与工作量是否合理？' 104 227 812 66 25 $script:ink)
[void](Txt $s '3' 45 315 45 43 30 $script:blue $true)
[void](Txt $s '哪组实验最能证明超出 OmniCapBench、FAVE 等工作的价值？' 104 316 812 66 25 $script:ink)
[void](Txt $s '4' 45 404 45 43 30 $script:blue $true)
[void](Txt $s '扩充数据前，需要拿到什么证据，才能决定继续或调整方向？' 104 405 812 66 25 $script:ink)
Notes $s "最后预留至少 3–5 分钟讨论，整稿主体约 10–15 分钟。优先问第一项，让师兄判断研究对象是否值得独立做。第二项避免在标注细节上无限扩张，第三项要求把新颖性变成可运行的比较，第四项将讨论落实到下一阶段的决策条件。希望最终带走一个聚焦的问题、一套暂定粒度、一个优先对照实验，以及对扩展数据的判断标准。不要把‘能否发 ACL’作为唯一问题，而要问哪些证据能支持它作为语言与多模态评价研究。"

if($deck.Slides.Count -ne 14){throw 'Unexpected slide count'}
for($i=1;$i -le $deck.Slides.Count;$i++) {
    $slide=$deck.Slides.Item($i)
    for($j=1;$j -le $slide.Shapes.Count;$j++) {
        $shape=$slide.Shapes.Item($j)
        if($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
            $tr=$shape.TextFrame.TextRange
            $script:bounds += [pscustomobject]@{slide=$i;shape=$shape.Name;text=$tr.Text;left=$shape.Left;top=$shape.Top;width=$shape.Width;height=$shape.Height;boundWidth=$tr.BoundWidth;boundHeight=$tr.BoundHeight}
        }
    }
}
$deck.SaveAs($draft,24)
$deck.Export($renders,'PNG',1600,900)
$script:notes | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'speaker_notes.json') -Encoding UTF8
$script:bounds | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'text_bounds.json') -Encoding UTF8
$deck.Close()
$app.Quit()
Write-Output ('Built 14 slides: '+$draft)
