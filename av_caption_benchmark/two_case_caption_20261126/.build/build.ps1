$ErrorActionPreference = 'Stop'
$work = Split-Path $PSScriptRoot -Parent
$repo = (Resolve-Path (Join-Path $work '../..')).Path
$previous = Join-Path $repo 'av_caption_benchmark/idea_talk_20261125_senior/.build/build_deck.ps1'
$functions = Get-Content -LiteralPath $previous -Encoding UTF8 -Raw
$functions = $functions.Substring($functions.IndexOf('function Font('))
$functions = $functions.Substring(0,$functions.IndexOf('# 01:'))
$script:ink = 0x332D23
$script:navy = 0x6B4321
$script:blue = 0xAE7232
$script:muted = 0x77716A
$script:pale = 0xF8F4EE
$script:notes = @()
. ([scriptblock]::Create($functions))

function ReadText([string]$path) {
    Get-Content -LiteralPath $path -Encoding UTF8 -Raw
}
function Span($event) { '{0:F2}–{1:F2}' -f $event.start,$event.end }
function ShowVideo($slide,$path) {
    [void]$slide.Shapes.AddMediaObject2($path,0,-1,44,128,382,214.875)
    [void](Txt $slide '放映时点击视频播放原声' 44 355 382 25 15 $script:muted)
}
function ModelSlide($title,$folder,$excerpts) {
    $slide = Base $title '模型原文节选 · 完整输出见本页备注'
    $notes = @()
    $models = @('AVOCADO','AVOWED','DIADEM')
    for ($i=0; $i -lt $models.Count; $i++) {
        $model = $models[$i]
        $file = Join-Path $folder ($model.ToLowerInvariant() + '.txt')
        $raw = ReadText (Join-Path $repo $file)
        $entry = $excerpts[$i]
        foreach ($quote in $entry.quotes) {
            if (-not $raw.Contains($quote)) { throw "Excerpt differs from source: $file / $quote" }
        }
        $top = 133 + $i * 119
        [void](Txt $slide $model 44 ($top+1) 148 30 22 $script:navy $true)
        if ($entry.scope) { [void](Txt $slide $entry.scope 44 ($top+34) 148 73 14 $script:muted) }
        [void](Txt $slide ($entry.quotes -join " […] ") 206 $top 710 109 19 $script:ink)
        if ($i -lt 2) {
            $line = $slide.Shapes.AddLine(44,($top+111),916,($top+111))
            $line.Line.ForeColor.RGB = 0xE2E0DC
            $line.Line.Weight = 0.8
        }
        $notes += "$model`r来源 $file`r$($raw.Trim())"
    }
    Notes $slide ($notes -join "`r`r")
}

$badRel = 'sports_annotation/runs/badminton_bwf_gpt_sol_qwen_transcript_20261125_v05/badminton/qwen_bwf_with_transcript'
$jumpRel = 'sports_annotation/runs/standing_jump_caption_20261125_v01/standing_jump'
$badDir = Join-Path $repo $badRel
$jumpDir = Join-Path $repo $jumpRel
$bad = ReadText (Join-Path $badDir 'annotations.json') | ConvertFrom-Json
$jump = ReadText (Join-Path $jumpDir 'annotations.json') | ConvertFrom-Json
$badVideo = Join-Path $repo 'badminton_lift_31679122798_first8s.mp4'
$jumpVideo = Join-Path $repo 'standing_long_jump_1039046118_0-7s.mp4'
if ((Get-FileHash $badVideo).Hash -ne $bad.source_sha256 -or (Get-FileHash $jumpVideo).Hash -ne $jump.source_sha256) {
    throw 'Embedded videos differ from the annotation inputs.'
}
$draft = Join-Path $PSScriptRoot 'two_cases_draft.pptx'
$renders = Join-Path $PSScriptRoot 'renders'
[void](New-Item -ItemType Directory -Force -Path $renders)
$app = New-Object -ComObject PowerPoint.Application
$deck = $app.Presentations.Add(0)
$deck.PageSetup.SlideWidth = 960
$deck.PageSetup.SlideHeight = 540
$deck.DefaultLanguageID = 2052
try {
    $slide = Base '运动音视频 Caption Bench'
    [void](Txt $slide "看完同一段运动视频，模型能否说清`r谁做了什么动作，动作发生时有哪些声音？" 44 116 872 103 30 $script:navy $true)
    $rows = @(@('评测对象','检查什么'),
        @('专业动作','人物、动作实例及可见细节，如并步、挑球、蹬伸起跳'),
        @('独立时间','分别记录动作与音频的起止时间。语音可以跨镜头。'),
        @('同期关系','检查每段音频与哪些具体动作重叠，以及重叠多久。'))
    [void](Tab $slide $rows @(180,696) 44 245 876 177 20)
    [void](Txt $slide '同一原片供各模型生成描述，评测侧提取原文已表达的信息，再与人工核验标注对照。' 44 443 876 47 18 $script:ink)
    Notes $slide "本 Bench 计划面向 1–2 位主要参与者、可以拆解为专业动作的运动片段。关注时间共现。动作和音频独立定界，允许多对多对应。模型保留原生输出，评价侧只抽取文本已表达的信息。我们管道的输出是标注候选，需用原帧和原声人工核验。本次只展示两段片子的真实输出，无模型分数。方案来源 av_caption_benchmark/CURRENT_PROPOSAL.md。"

    $slide = Base '羽毛球 0–8 s · 我们的管道输出' '采用 BWF 术语整理动作，用 Qwen 独立生成原声转写'
    ShowVideo $slide $badVideo
    $badLabels = [ordered]@{
        A_S01_FEED_1 = '远端陪练手喂球'
        A_S01_LUNGE_1 = '近端球员向右前方跨弓步'
        A_S01_STROKE_1 = '近端球员正手挑球'
        A_S01_RECOVER_1 = '近端球员并步回位'
    }
    $rows = ,@('首轮动作候选','区间 / s')
    foreach ($id in $badLabels.Keys) {
        $event = $bad.visual.actions | Where-Object id -eq $id
        $rows += ,@($badLabels[$id],(Span $event))
    }
    [void](Tab $slide $rows @(313,151) 456 128 464 216 18)
    $u = $bad.audio.events | Where-Object id -eq 'U001'
    $stroke = $bad.relations.pairs | Where-Object { $_.audio_id -eq 'U001' -and $_.action_id -eq 'A_S01_STROKE_1' }
    $overlap = '{0:F2}–{1:F2} s' -f $stroke.intersection[0],$stroke.intersection[1]
    [void](Txt $slide ("语音 U001   " + (Span $u) + ' s   “' + $u.transcript + '”') 44 399 876 32 23 $script:navy $true)
    [void](Txt $slide "对应示例   U001 与首轮正手挑球重叠 $overlap" 44 441 876 29 19 $script:ink)
    [void](Txt $slide '展示 Qwen 候选中的首轮动作与一条时间关系。动作与音频边界待人工核验。' 44 480 830 24 14 $script:muted)
    Notes $slide ("来源 $badRel/badminton_BWF_人工审阅.txt`r原片 李宇轩教练 0–8 s。右前方使用屏幕坐标。下方只列出一条音频关系，管道的所有候选和原有警告见下文。`r`r" + (ReadText (Join-Path $badDir 'badminton_BWF_人工审阅.txt')).Trim())

    ModelSlide '羽毛球 · 三种模型的输出' 'badminton_captions' @(
        @{scope='整段描述'; quotes=@(
            'The man in the foreground moves to his left to return a shuttlecock.',
            'The first player then hits another shot, and the second player moves to the net to return it. The first player follows up with a powerful overhead smash.')},
        @{scope="镜头描述与语音转写"; quotes=@(
            'He holds a racket in his right hand and executes a series of athletic movements, shifting his weight and swinging the racket to strike the shuttlecock.',
            '00:00.930 - 00:01.560',
            'Content: "往这边跳"')},
        @{scope='整段描述'; quotes=@(
            'He gives a brief, direct command, "往这边跳," in a matter-of-fact manner.',
            'The man in the foreground, seen from behind, wears a black t-shirt, light-colored shorts, and athletic shoes. He moves with agility, lunging and jumping to return shots.')}
    )

    $slide = Base '立定跳远 0–7 s · 我们的管道输出' '同一提问跨过 2.08 s 的切镜，覆盖正面讲解与侧面跳远'
    ShowVideo $slide $jumpVideo
    $jumpLabels = [ordered]@{
        A001 = '讲解（含手势）'
        A003 = '向后摆臂'
        A004 = '下蹲蓄力'
        A006 = '蹬伸起跳'
        A007 = '腾空'
        A009 = '落地缓冲'
    }
    $rows = ,@('画面动作候选','区间 / s')
    foreach ($id in $jumpLabels.Keys) {
        $event = $jump.visual.actions | Where-Object id -eq $id
        $rows += ,@($jumpLabels[$id],(Span $event))
    }
    [void](Tab $slide $rows @(313,151) 456 124 464 247 17)
    $u = $jump.audio.events | Where-Object id -eq 'U001'
    $g = $jump.relations.pairs | Where-Object { $_.audio_id -eq 'U001' -and $_.action_id -eq 'A001' }
    $j = $jump.visual.executions | Where-Object id -eq 'E001'
    $left = '{0:F2}–{1:F2} s' -f $g.intersection[0],$g.intersection[1]
    $right = '{0:F2}–{1:F2} s' -f ([Math]::Max($j.start,$u.start)),([Math]::Min($j.end,$u.end))
    [void](Txt $slide ("U001   " + (Span $u) + ' s   “' + $u.transcript + '”') 44 392 876 53 20 $script:navy $true)
    [void](Txt $slide "与讲解重叠 $left，与跳远全过程重叠 $right" 44 451 876 27 19 $script:ink)
    [void](Txt $slide '以上区间为 Qwen 候选与程序求交结果，边界待人工核验。' 44 484 830 22 14 $script:muted)
    Notes $slide ("来源 $jumpRel/caption.txt`r跑步的子章老师 0–7 s。表格节选部分动作。跳远全过程对应 E001，范围 2.08–5.48 s。`r`r" + (ReadText (Join-Path $jumpDir 'caption.txt')).Trim())

    ModelSlide '立定跳远 · 三种模型的输出' 'standing_long_jump_captions' @(
        @{scope='整段描述'; quotes=@(
            'The scene cuts to a wide shot of the same man on a red running track. He is in the middle of a powerful vertical jump, with his arms raised high above his head.',
            'The camera remains in a wide, static shot as the man lands from his jump and begins to move forward.')},
        @{scope="镜头 00:02.000`r至 00:07.000"; quotes=@(
            'Rising from the squat, he propels himself forward and to the right, executing a forward roll across the red surface.',
            'His voice continues as a voice-over, completing the previous thought with "竿见影", then asking "如同作弊一般提升立定跳远的成绩呢", and concluding with "今天给大家介绍三个方法".')},
        @{scope='整段描述'; quotes=@(
            'The camera remains static as the man performs a powerful vertical jump, his body extending upwards and out of the frame. The shot holds on the empty space where he was standing, with the background of the track, fence, and building unchanged.')}
    )
    $deck.SaveAs($draft,24)
    $deck.Export($renders,'PNG',1600,900)
    Write-Output "Saved $($deck.Slides.Count) slides"
} finally {
    $deck.Saved=-1
    $deck.Close()
    $app.Quit()
}
