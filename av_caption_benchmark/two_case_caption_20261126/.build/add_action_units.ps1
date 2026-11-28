$ErrorActionPreference = 'Stop'
$work = Split-Path $PSScriptRoot -Parent
$repo = (Resolve-Path (Join-Path $work '../..')).Path
$builder = Join-Path $repo 'av_caption_benchmark/idea_talk_20261125_senior/.build/build_deck.ps1'
$functions = Get-Content -LiteralPath $builder -Encoding UTF8 -Raw
$functions = $functions.Substring($functions.IndexOf('function Font('))
$functions = $functions.Substring(0,$functions.IndexOf('# 01:'))
$script:ink = 0x332D23
$script:navy = 0x6B4321
$script:muted = 0x77716A
$script:pale = 0xF8F4EE
$script:notes = @()
. ([scriptblock]::Create($functions))

$source = Join-Path $work 'output/运动音视频CaptionBench_双案例对照.pptx'
$draft = Join-Path $PSScriptRoot 'two_cases_units_draft.pptx'
$renders = Join-Path $PSScriptRoot 'renders_units'
[void](New-Item -ItemType Directory -Force -Path $renders)
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Open($source,-1,0,0)
try {
    $slide = Base '已有 Bench 把动作拆到哪一层？' '四种任务采用不同标注单位，有的标分界，有的标动作片段。'
    $slide.MoveTo(2)
    $rows = @(
        @('Benchmark','最细标注单位','划分规则与例子'),
        @('Kinetics-GEBD','事件变化的边界', "比当前事件细一层。论文举例把跳远分为`r助跑、跳跃和落地，并标出转换时刻。"),
        @('FineGym','体操技术元素', "按项目、动作组、元素分类，例如团身前空翻。`r完整动作与元素片段分别标起止。"),
        @('HAA500','单次动作或连续片段', "每类设定规则。一次俯卧撑从最高点回到最高点，`r跑步等连续动作则截取合适长度。"),
        @('FineBadminton','以一拍击球为中心的记录', "围绕击球时刻记录球种、人物及执行细节，`r再加入战术和评价。")
    )
    [void](Tab $slide $rows @(166,238,472) 44 126 876 287 18)
    [void](Txt $slide '我们的主评单位是可独立定位的功能动作，例如正手挑球和并步回位。' 44 436 876 31 20 $script:navy $true)
    [void](Txt $slide '完整执行之下是功能动作，还可细分为单一身体部位的连续可见运动。' 44 476 876 26 17 $script:ink)
    Notes $slide "Kinetics-GEBD 的任务是定位自然感知的变化点。原论文 §3.2 直接用跳远说明多个粒度都可能合理，并要求标到当前事件下一级。边界可以用时刻或短范围表示。https://arxiv.org/abs/2101.10511`rFineGym §3.1–3.2、图 2 区分 Event、Set、Element 三层类别，以及完整动作和子动作两层时间标注。https://openaccess.thecvf.com/content_CVPR_2020/papers/Shao_FineGym_A_Hierarchical_Video_Dataset_for_Fine-Grained_Action_Understanding_CVPR_2020_paper.pdf`rHAA500 补充材料 §1 区分离散与连续动作。离散类按本类规则裁成一次完整实例，连续类截取合适长度。https://openaccess.thecvf.com/content/ICCV2021/supplemental/Chung_HAA500_Human-Centric_Atomic_ICCV_2021_supplemental.pdf`rFineBadminton §3.1–3.2 的基础动作、战术语义和决策评价是三个语义层级，公开主数据围绕每次击球组织，也记录步法等细节。https://arxiv.org/html/2508.07554v1`r本项目采用完整执行、功能动作、身体部位运动三级组织。功能动作要求动作模式与作用可辨识，可用区间独立定位。引拍和随挥可作为挑球的内部阶段。一个身体部位的原语以相同参照及运动谓词下的最大可见连续区间为单位。步法和挥拍允许重叠。详见 sports_annotation/protocols/three_level_action_standard_v1.txt。"
    for ($i=1; $i -le $deck.Slides.Count; $i++) {
        $page = $deck.Slides.Item($i)
        $folio = @($page.Shapes | Where-Object { $_.HasTextFrame -eq -1 -and [Math]::Abs($_.Left-880) -lt 1 -and [Math]::Abs($_.Top-503) -lt 1 })
        if ($folio.Count -ne 1) { throw "Missing or ambiguous slide number at slide $i" }
        $box = $folio[0]
        $box.TextFrame.TextRange.Text = ([string]$i).PadLeft(2,'0')
        Font $box.TextFrame.TextRange 14 $script:muted
    }
    $deck.SaveCopyAs($draft,24)
    $deck.Export($renders,'PNG',1600,900)
    Write-Output "Saved $($deck.Slides.Count) slides"
} finally {
    $deck.Saved=-1
    $deck.Close()
    $app.Quit()
}
