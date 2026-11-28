"""Build the offline, media-linked comparison from the two saved annotations."""
from collections import Counter
from html import escape
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'cross_domain_pilot_20261126'))
from unified_review import export_case, track_caption


def read(path):
    return json.loads(path.read_text('utf8'))


def h(value):
    return escape(str(value))


def seek(cid,t,label):
    return f'<button data-clip="{h(cid)}" data-time="{float(t):.4f}">{h(label)}</button>'


def official_questions(row):
    parts=[]
    for q in row['a2v_query_list']:
        candidates=q['visual_candidates_for_judge']
        selected=q['selected_visual_indices_new']
        if not all(1<=i<=len(candidates) for i in selected):
            raise ValueError('Invalid candidate index')
        choices=''.join(f'<li class="{"yes" if i in selected else ""}">'+
                        ('✓ ' if i in selected else '')+
                        f'[{h(v["type"])}] {h(v["content"])}</li>'
                        for i,v in enumerate(candidates,1))
        parts.append('<details><summary>'+h(q['content'])+
                     f' <small>（选中 {len(selected)} 项）</small></summary><ol>'+choices+'</ol></details>')
    return ''.join(parts)


def ours(cid,ann):
    actions=ann['visual']['actions']
    audio=ann['audio']['events']
    items=[]
    for a in sorted(actions,key=lambda v:(v['start'],v['id'])):
        clock=seek(cid,a['start'],f"{a['start']:.2f}–{a['end']:.2f} s")
        items.append('<details><summary>'+clock+' '+h(a['brief'])+'</summary><p>'+
                     h(a['id'])+' · '+h(a['kind'])+' · '+h(a['detail'])+'</p></details>')
    sounds=[]
    for e in sorted(audio,key=lambda v:v['start']):
        pairs=[p for p in ann['relations']['pairs'] if p['audio_id']==e['id'] and p['nominal_overlap']]
        links=[]
        for edge in pairs:
            lo,hi=edge['intersection']
            links.append(seek(cid,lo,f"{edge['action_id']} {lo:.2f}–{hi:.2f}"))
        sounds.append('<details><summary>'+seek(cid,e['start'],f"{e['start']:.2f}–{e['end']:.2f} s")+
                      ' '+h(e.get('transcript') or e['description'])+'</summary><p>'+h(e['id'])+
                      ' · '+h(e['kind'])+' · '+h(e['layer'])+'</p><p>与动作区间的名义交集（秒） '+
                      (' '.join(links) or '无')+'</p></details>')
    return '<h4>动作与状态</h4>'+''.join(items)+'<h4>语音、声音与同期动作</h4>'+''.join(sounds)


def main():
    rows=[]
    cases=read(HERE/'sample_manifest.json')
    findings=read(HERE/'case_notes.json')
    for case in cases:
        cid=case['id']
        folder=HERE/'cases'/cid
        eva=read(folder/'stage2_caption_rl.json')
        sft=read(folder/'shot2story_caption_sft.json')
        assert eva['video_path']==sft['video_path']
        annfolder=HERE/'revisions/v6/cases'/cid
        ann=read(annfolder/'annotations.json')
        export_case(annfolder,folder/'clip.mp4',ann,HERE/'base/cases'/cid/'stages')
        # The common review renderer assumes an experiment-level index two directories up.
        review=annfolder/'审阅.html'
        review.write_text(review.read_text('utf8').replace('../../试标总览.html','../../../../EVA与我们的标注对照.html'),encoding='utf8')
        counts=Counter(a['kind'] for a in ann['visual']['actions'])
        speech=sum(e['kind']=='speech' for e in ann['audio']['events'])
        evavis=eva['event_list']['visual']
        section=f'<article id="case-{cid}"><h2>{h(case["domain"])}</h2><p>{h(case["filename"])} · {ann["duration_seconds"]:.2f} 秒</p>'
        section+=f'<video id="{cid}" controls preload="metadata" src="cases/{cid}/clip.mp4"></video>'
        section+=f'<details><summary>查看带原片时间戳的核对帧</summary><a href="cases/{cid}/evidence.jpg"><img style="max-width:100%" src="cases/{cid}/evidence.jpg" alt="原片抽帧与时间戳"></a></details>'
        section+='<h3>复核观察</h3><ul>'+''.join('<li>'+h(v)+'</li>' for v in findings[cid])+'</ul>'
        section+='<div class="cols"><section><h3>EVA 公开标注</h3><p class="caption">'+h(sft['caption'])+'</p>'
        section+=f'<p>强化学习记录有 {len(evavis)} 个视觉事件，其中 {sum(x["type"]=="action" for x in evavis)} 个标为 action，另有 {len(eva["event_list"]["audio"])} 个音频事件。</p>'
        for name,title in [('visual','视觉事件清单'),('audio','声音事件清单')]:
            section+='<details><summary>'+title+'</summary><ol>'+''.join(
                '<li>['+h(e['type'])+'] '+h(e['content'])+'</li>'
                for e in eva['event_list'][name])+'</ol></details>'
        section+='<h4>GRPO 训练用音到画同期查询</h4><p>✓ 表示计算同步奖励时使用的参考选项，编号取自 selected_visual_indices_new。</p>'+official_questions(eva)
        section+=f'<p><a href="cases/{cid}/shot2story_caption_sft.json">SFT 原文</a> · <a href="cases/{cid}/stage2_caption_rl.json">官方事件与全部选项</a> · <a href="cases/{cid}/source.json">视频来源和定位</a></p></section>'
        section+='<section><h3>我们的管道输出</h3><p>'+h('，'.join(f'{k} {v}' for k,v in counts.items()))+f'；语音 {speech} 条、其他声音 {len(ann["audio"]["events"])-speech} 条。点击时间回看。</p>'
        section+=ours(cid,ann)
        section+='<details><summary>v6 视觉复核全文</summary><pre>'+h(track_caption(ann['visual']))+'</pre></details>'
        section+=f'<p><a href="revisions/v6/cases/{cid}/审阅.html">完整中文审阅与原始响应</a> · <a href="revisions/v6/cases/{cid}/annotations.json">最终 JSON</a></p></section></div></article>'
        rows.append(section)
    intro='<h1>EVA 与我们的音视频标注对照</h1><p>三段来自 Shot2Story 的完整原片。EVA 一侧展示 SFT 训练用英文 caption 和 GRPO 训练用事件与同期查询。这三条公开记录的事件没有数值起止字段。我们的 Qwen 标注仅以原媒体为输入。动作与声音区间求交，极短重叠及模型时间边界均需要复核。两边均为模型候选。</p>'
    counts=read(HERE/'official_query_counts.json')
    pilot,stage=counts['pilot'],counts['stage2_caption_rl']
    intro+=f'<p>这三条定向选出的片段有 {pilot["queries"]} 条音到画训练查询，其中 {pilot["multiple_visual_events"]} 条选中多项，各含一项 action 和镜头或环境。完整 GRPO Stage 2 的 {stage["queries"]:,} 条训练查询中，有 {stage["at_least_two_action_labels"]:,} 条同时选中至少两个 action（{100*stage["at_least_two_action_labels"]/stage["queries"]:.1f}%）。该标签还可指物体动作。<a href="official_query_counts.json">两阶段全量计数和文件哈希</a> · <a href="audit_queries.py">计数代码</a></p>'
    intro+='<p>观察以原片抽帧与两套文本为依据，此次未逐句进行独立听写。视觉 v6 的复核文本与动作表分别保留，操作方向、物体身份或时间边界可能互相矛盾。</p>'
    intro+='<nav>'+ '　'.join(f'<a href="#case-{c["id"]}">{h(c["domain"])}</a>' for c in cases)+'</nav>'
    css='body{max-width:1450px;margin:28px auto;padding:0 3%;font:16px/1.65 system-ui;color:#1c3436}article{border-top:2px solid #749290;margin:30px 0;padding:15px 0}video{width:min(100%,700px);max-height:42vh;background:#182323}.cols{display:grid;grid-template-columns:1fr 1fr;gap:2rem}section{min-width:0}.caption{line-height:1.65}button{cursor:pointer;padding:3px 7px;font:inherit;font-size:.84em}details{padding:5px 0;border-bottom:1px solid #d3dedd}summary{cursor:pointer}.yes{color:#05644b;font-weight:600}a{color:#006b79}pre{white-space:pre-wrap;overflow-wrap:anywhere}small{color:#526566}@media(max-width:850px){.cols{grid-template-columns:1fr}}'
    js="document.addEventListener('click',e=>{let b=e.target.closest('button[data-time]');if(!b)return;e.preventDefault();let v=document.getElementById(b.dataset.clip);v.currentTime=Number(b.dataset.time);v.play()})"
    (HERE/'EVA与我们的标注对照.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>EVA 与我们的音视频标注对照</title><style>'+css+'</style>'+intro+''.join(rows)+'<script>'+js+'</script></html>',encoding='utf8')


if __name__=='__main__':
    main()
