$ErrorActionPreference = 'Stop'
$talk = Split-Path $PSScriptRoot -Parent
$repo = (Resolve-Path (Join-Path $talk '../..')).Path
$run = Join-Path $repo 'sports_annotation/runs/standing_jump_caption_20261125_v01/standing_jump'
$data = Get-Content -Encoding UTF8 -LiteralPath (Join-Path $run 'annotations.json') -Raw | ConvertFrom-Json
$speech = $data.audio.events | Where-Object id -eq 'U001'
$gesture = $data.visual.actions | Where-Object id -eq 'A001'
$takeoff = $data.visual.actions | Where-Object id -eq 'A006'
$flight = $data.visual.actions | Where-Object id -eq 'A007'
$jump = $data.visual.executions | Where-Object id -eq 'E001'
$cut = $data.shots[1].start
$edge = $data.relations.pairs | Where-Object { $_.audio_id -eq $speech.id -and $_.action_id -eq $gesture.id }
if (-not ($speech.start -lt $cut -and $speech.end -gt $cut -and $edge.nominal_overlap -and $takeoff.end -lt $speech.end)) {
    throw 'The selected model events do not support this example.'
}
function Span([double]$start,[double]$end) { '{0:F2}–{1:F2} s' -f $start,$end }
$speechTime = Span $speech.start $speech.end
$gestureTime = Span $gesture.start $gesture.end
$jumpTime = Span $jump.start $jump.end
$gestureOverlap = Span $edge.intersection[0] $edge.intersection[1]
$jumpOverlap = Span ([Math]::Max($jump.start,$speech.start)) ([Math]::Min($jump.end,$speech.end))
$takeoffTime = Span $takeoff.start $takeoff.end
$flightTime = Span $flight.start $flight.end
$cutTime = '{0:F2} s' -f $cut
$script:ink = 0x332D23
$script:navy = 0x6B4321
$script:muted = 0x77716A
$script:pale = 0xF8F4EE
$script:notes = @()
$builder = Get-Content -Encoding UTF8 -LiteralPath (Join-Path $PSScriptRoot 'build_deck.ps1') -Raw
$functions = $builder.Substring($builder.IndexOf('function Font('))
$functions = $functions.Substring(0,$functions.IndexOf('# 01:'))
. ([scriptblock]::Create($functions))

function ResetSlide($slide,[string]$title,[string]$subtitle='') {
    while ($slide.Shapes.Count -gt 0) { $slide.Shapes.Item($slide.Shapes.Count).Delete() }
    [void](Txt $slide $title 42 25 876 54 31 $script:navy $true)
    if ($subtitle) { [void](Txt $slide $subtitle 44 83 870 30 17 $script:muted) }
    [void](Txt $slide ([string]$slide.SlideIndex).PadLeft(2,'0') 880 503 38 23 14 $script:muted)
}

$source = Join-Path $talk 'output/细粒度运动音视频Bench_师兄讨论稿_v1.pptx'
$draft = Join-Path $PSScriptRoot 'standing_jump_deck_v2.pptx'
$render = Join-Path $PSScriptRoot 'renders_jump_v2'
[void](New-Item -Path $render -ItemType Directory -Force)
$video = Join-Path $repo 'video/av_caption_benchmark__transfer2paas_2__standing_long_jump_1039046118_0-7s.mp4'
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Open($source,-1,0,0)
try {
    $s = $deck.Slides.Item(5)
    ResetSlide $s '一句话跨过讲解与跳远两个镜头' "立定跳远 0–7 s 片段在 $cutTime 切镜，开场提问继续播放"
    [void]$s.Shapes.AddMediaObject2($video,0,-1,44,125,376,211.5)
    [void](Txt $s "U001 语音  $speechTime" 448 127 468 32 21 $script:navy $true)
    [void](Txt $s ('“' + $speech.transcript + '”') 448 170 468 95 22 $script:ink)
    [void](Txt $s "切镜前是面向镜头的讲解。`r切镜后是侧面拍摄的立定跳远。" 448 263 468 66 19 $script:ink)
    $rows = @(@('画面事件','事件区间','与 U001 的交集'),
              @('S01  讲解（含手势）',$gestureTime,$gestureOverlap),
              @('S02  立定跳远全过程',$jumpTime,$jumpOverlap))
    [void](Tab $s $rows @(368,254,254) 44 350 876 113 18)
    [void](Txt $s '放映时点击视频播放原声。区间为 Qwen 候选估计，交集按时间计算。' 44 481 830 29 14 $script:muted)
    Notes $s "建议用时 70 秒。点击左侧原声视频，听开头同一句提问是否在 2.08 秒的切镜后继续。音频阶段只听原声并输出 U001，视觉阶段独立输出 A001（面向镜头讲解，含手势）和 E001（一次立定跳远执行）。A001 的区间是讲解候选，手势的精细边界可以另行复核。E001 是 L1 容器，下面有向后摆臂、下蹲蓄力、蹬伸、腾空、收腿及落地等候选。表中展示场景层面的两条时间关系，动作级交集见第 9 页。讲解手势保留为场景事件，运动动作数量只计技术动作。语音关系的依据是实际区间交集。`r素材：跑步的子章老师《立定跳远成绩快速提升的 3 个方法》0–7 秒。结果：sports_annotation/runs/standing_jump_caption_20261125_v01/standing_jump/caption.txt 和 annotations.json。时间为模型候选，适于讨论，边界需人工复核。"

    $s = $deck.Slides.Item(9)
    ResetSlide $s '多选题检查同一句话覆盖的动作' '答题者只读 Caption，检查它能否支持恢复多条时间关系'
    [void](Txt $s '立定跳远 Caption 摘要' 44 125 876 31 21 $script:navy $true)
    [void](Txt $s '开场提问响起时，人物正面向镜头讲解并做手势。画面切到跑道后，同一句提问持续到示范者蹬伸起跳、腾空。' 44 166 876 74 23 $script:ink)
    [void](Txt $s '开场这句提问播放期间，哪些动作发生过？' 44 256 876 37 24 $script:navy $true)
    [void](Txt $s "A   第二次蹬伸起跳`rB   面向镜头做讲解手势`rC   第一次蹬伸起跳" 44 310 430 108 22 $script:ink)
    [void](Txt $s "D   跳完后起身展示`rE   描述未提供足够信息`r示例答案   B、C" 500 310 418 108 22 $script:ink)
    [void](Txt $s "动作级核对  A001 讲解手势 $gestureOverlap   A006 蹬伸起跳 $takeoffTime" 44 433 876 35 19 $script:navy $true)
    Foot $s '区间为两条关系的名义交集。正式题目需由人工复核，报告集合 F1 与全对率。'
    Notes $s "建议用时 70 秒。页面摘要根据同一实际片段的两段独立输出整理。B 指 A001，C 指 A006，都是 U001 的重叠动作。这里问的是同一段话播放期间有哪些动作发生过，两个动作可以发生在不同时间，也可以分属不同镜头。选项可再加入 A007 腾空等动作；本页题目只对呈现的选项评分。答题时遮住本页答案和时间提示。与 U001 重叠的其他候选还包括 A007 腾空 $flightTime。D 对应 A010，其开始时刻 5.56 秒晚于 U001 结束时刻 5.36 秒。正式评测需先核对候选边界与选项，再随机化选项并审查题面捷径。`r来源：本轮 caption.txt、relations.json。相关评测：CapQuiz，https://aclanthology.org/2026.acl-long.777/ 。"

    $s = $deck.Slides.Item(11)
    ResetSlide $s '受控对照只改一条时间关系' '两份描述保留同样的讲解、跳远和开场提问，仅改变语音何时结束'
    $rows = @(@('构造版本','讲解镜头中的开场提问','跳远镜头中的开场提问'),
              @('Caption A','提问与讲解手势重叠','切镜后继续，与跳远重叠'),
              @('Caption B','提问与讲解手势重叠','切镜前结束，跳远时已停止'))
    [void](Tab $s $rows @(196,340,340) 44 138 876 166 20)
    [void](Txt $s '以本案例的两条候选关系作参考，B 漏掉跳远期间的共现。' 44 330 876 38 22 $script:ink)
    [void](Txt $s '示意关系 F1   A = 1.00   B = 0.67' 44 379 876 44 28 $script:navy $true)
    [void](Txt $s '下一步在同一批描述上比较已有指标，并请人工盲评。' 44 439 876 35 21 $script:ink)
    Foot $s '以上分数只评价本页的两条关系，用于说明计分。'
    Notes $s "建议用时 70 秒。A 和 B 是按真实片段构造的成对描述。A 保留 (A001,U001) 和 (E001,U001)，B 保留第一条，遗漏第二条。限定在这两个画面事件，A 的 P 和 R 都是 1，B 的 P=1、R=0.5，F1=2/3。这里用 L1 跳远执行过程与场景讲解事件展示关系，再在正式任务按动作层级分别报告，避免把跳远整体与内部动作混加。所有分数为示意计算。需要实测已有指标和人工判断是否同样能发现错误，并加入真实模型的漏边、错边和时段偏移。`r来源：第 5 页的 Qwen 立定跳远候选和构造对照。"

    $s = $deck.Slides.Item(13)
    $existing = @($s.Shapes | Where-Object { $_.HasTextFrame -eq -1 -and $_.TextFrame.TextRange.Text -like '5 个运动视频试验素材*' })
    if ($existing.Count -ne 1) { throw 'Could not find the existing progress text.' }
    $box = $existing[0]
    $box.TextFrame.TextRange.Text = "5 个运动视频试验素材`r羽毛球 Qwen 标注与 BWF 词表`r立定跳远跨镜头 Caption`r独立音频转写与区间关系计算"
    Font $box.TextFrame.TextRange 21 $script:ink
    $note = $s.NotesPage.Shapes.Placeholders.Item(2)
    $note.TextFrame.TextRange.Text = $note.TextFrame.TextRange.Text + "`r本次补充：立定跳远 0–7 秒的两个独立 Qwen 阶段已完成。开场语音 U001 在 2.08 秒切镜后继续，覆盖讲解和跳远，详见第 5、9、11 页。"
    Font $note.TextFrame.TextRange 14 $script:ink

    if ($deck.Slides.Count -ne 14) { throw 'Unexpected slide count' }
    $deck.SaveCopyAs($draft,24)
    $deck.Export($render,'PNG',1600,900)
    Write-Output "Rendered 14 slides: $draft"
} finally {
    $deck.Saved=-1
    $deck.Close()
    $app.Quit()
}
