from collections import Counter
from html import escape
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent

def read(path):
    return json.loads(path.read_text('utf8'))

def safe(x):
    return escape(str(x))

def word_range(words,first,last,minimum=0):
    i=next(i for i,w in enumerate(words) if w['start']>=minimum and w['word']==first)
    j=next(j for j in range(i,len(words)) if words[j]['word']==last)
    return [words[i]['start'],words[j]['end']]

def replay_button(cid,start,end=None):
    label=f'{start:.2f}' if end is None else f'{start:.2f}–{end:.2f}'
    return f'<button data-case="{cid}" data-t="{start}">▶ {label} s</button>'

def anchor_examples():
    rows=[]
    for cid,vid,spec in [
        ('timer','V2',[('unplug','power',0),('label','tape',0)]),
        ('apple','V4',[('individual','here',10),('whole','weeks',12)])]:
        d=HERE/'cases'/cid;ws=read(d/'independent_asr.json')['words']
        ann=read(d/'consensus.json')
        v=next(x for x in ann['groups']['visual'] if x['id']==vid)
        for a,b,m in spec:
            if not any(w['word']==a and w['start']>=m for w in ws):
                if cid=='apple' and a=='individual':a="i'm"
                else:raise ValueError(a)
            lo,hi=word_range(ws,a,b,m)
            overlap=max(0,min(hi,v['end'])-max(lo,v['start']))
            rows.append(dict(case=cid,visual=v['example']['label'],visual_range=[v['start'],v['end']],
                             phrase=f'{a} … {b}',word_range=[lo,hi],overlap=round(overlap,3)))
    return rows

def main():
    sampled=read(HERE/'selection.json'); probes=read(HERE/'probes.json'); support=read(HERE/'probe_support.json')
    totals={m:Counter() for m in ('visual','audio')}; scores={};bycat={};articles=[];edges_total=short=0
    rawids=[];clocknotes=0
    for c in sampled:
        cid=c['id'];folder=HERE/'cases'/cid;co=read(folder/'consensus.json')
        bycat.setdefault(c['category'],[]).append(c)
        for k,gs in co['groups'].items():totals[k].update(g['votes'] for g in gs)
        edges=[e for e in co['edges'] if e['keep']];edges_total+=len(edges);short+=sum(e['short'] for e in edges)
        vid={m:read(folder/f'{m}_draws.json') for m in ('visual','audio')}
        article=f'<article id="s-{cid}"><h2>{safe(c["title"])}</h2><p>{safe(c["category"])} · {c["duration"]:.2f} 秒 · <a href="cases/{cid}/selection.json">来源和片段边界</a></p><video id="{cid}" controls preload="metadata" src="cases/{cid}/clip.mp4"></video>'
        article+=f'<details><summary>原片抽帧</summary><img src="cases/{cid}/frames.jpg" alt="按时间抽取的原片画面"></details>'
        if (folder/'review_detail.jpg').exists():article+=f'<p><a href="cases/{cid}/review_detail.jpg">局部连续帧</a></p>'
        article+='<h3>回看原片的视觉检查项</h3><table><tr><th>事实及定位</th><th>参考</th><th>第 1 / 2 / 3 轮是否写出</th></tr>'
        for q,ss in zip(probes[cid],support[cid]):
            yes=[bool(z) for z in ss]
            for n,ids in enumerate(ss,1):
                for token in ids:
                    r,i=map(int,token.split('.'));assert r==n and 0<=i<len(vid['visual'][n-1]['events'])
            for k,hits in zip(('round1','round2','round3','both_first_two','majority'),[*yes,all(yes[:2]),sum(yes)>=2]):
                bucket=scores.setdefault(k,Counter());bucket['positive_supported' if q[0] else 'negative_asserted']+=int(hits)
            answer='见于原片' if q[0] else '原片不支持'
            article+='<tr><td>'+safe(q[1])+'<br><small>'+safe(q[2])+'</small></td><td>'+answer+'</td><td>'+' / '.join('写出' if x else '未写出' for x in yes)+'</td></tr>'
        article+='</table>'
        if (folder/'replay.json').exists():
            rc=read(folder/'replay.json');article+='<details><summary>对候选事实定向回看原片的回答</summary><ul>'
            for q,z in zip(rc['claims'],rc['checks']):
                article+=f'<li>{safe(q["claim"])}<br>{safe(z["verdict"])} · {safe(z["evidence"])}</li>'
            article+='</ul></details>'
        for m,title in [('visual','视觉动作'),('audio','语音与声音')]:
            gs=co['groups'][m];article+=f'<h3>{title}的三轮配对</h3><table><tr><th>区间中位数</th><th>候选陈述（代表轮次）</th><th>支持轮数</th></tr>'
            for g in gs:
                e=g['example'];desc=e['brief'] if m=='visual' else (e['text'] or e['label'])
                article+=f'<tr><td>{replay_button(cid,g["start"],g["end"])}</td><td>{g["id"]} · {safe(desc)}</td><td>{g["votes"]}/3<br><small>{safe(", ".join(g["members"]))}</small></td></tr>'
            article+='</table><details><summary>三轮完整描述、原始回复及子阶段</summary>'
            for n,draw in enumerate(vid[m],1):
                raw=folder/draw['source'];clocknotes+=len(draw['clock_notes'])
                if raw.suffix=='.json':
                    meta=next(read(f) for f in sorted(raw.with_suffix('').rglob('metadata.json')) if read(f).get('status')=='complete')
                else:meta=read(raw.parent/'metadata.json')
                rawids.append(meta['response_id'])
                article+=f'<h4>第 {n} 轮 · <a href="cases/{cid}/{safe(draw["source"])}">生成记录</a></h4><ol start="0">'
                for e in draw['events']:
                    parts=[e['actor'],e.get('brief') or e.get('text') or e['label']]
                    if e.get('detail'):parts.append(e['detail'])
                    if e.get('phases'):parts.append(e['phases'])
                    article+='<li>'+replay_button(cid,e['start'],e['end'])+' '+safe(' · '.join(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False) for x in parts))+'</li>'
                article+='</ol>'
            article+='</details>'
        article+='<details><summary>多数轮支持的时段重叠（包含背景与状态）</summary><ul>'
        for e in edges:
            lo,hi=e['median_intersection']
            article+='<li>'+replay_button(cid,lo,hi)+f' {e["visual"]} × {e["audio"]}；共同支持轮次 '+', '.join(e['overlap_rounds'])+'</li>'
        article+=f'</ul><a href="cases/{cid}/consensus.json">全部配对、边界分歧与交集候选</a></details></article>'
        articles.append(article)
    pos=sum(q[0] for qs in probes.values() for q in qs);neg=sum(len(qs) for qs in probes.values())-pos
    anchors=anchor_examples()
    assert len(sampled)==12 and all(len(v)==2 for v in bycat.values()) and len(set(rawids))==len(rawids)==72
    data=dict(cases=len(sampled),domains=len(bycat),independent_outputs=len(set(rawids)),votes=totals,
              positive_probes=pos,negative_probes=neg,scores=scores,stable_edges=edges_total,
              stable_edges_under_point2=short,normalized_event_bounds=clocknotes,word_checks=anchors)
    (HERE/'summary.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
    head='<h1>六类视频的三轮标注试验</h1><p>12 条开发片段。Qwen 3.8 Omni Flash 对同一片段做三次独立盲标，每次分别读取无声连续视频和独立音轨。视觉输入为原生 10 fps 视频及每秒两张定位帧；听写沿用原语言。三轮温度均为 0.65，各轮看不到其他输出。两类专业运动附项目词表。</p>'
    head+='<table><tr><th>领域</th><th>两个不同源的片段</th></tr>'
    for k,cs in bycat.items():head+='<tr><td>'+safe(k)+'</td><td>'+'　'.join(f'<a href="#s-{c["id"]}">{safe(c["title"])} ({c["duration"]:.1f} s)</a>' for c in cs)+'</td></tr>'
    head+='</table><h2>投票与核对结果</h2>'
    head+=f'<p>复核 {pos} 条可见事实和 {neg} 条原片不支持的陈述。按整条事实是否被原文支持计数，人物、方向须一致，动作表与子阶段均可提供依据。“未写出”表示没有可用证据。参考由本次原片审阅建立，未做双人独立标注。本试验统计内容覆盖，不能当作整段 caption 的准确率。</p><table><tr><th>策略</th><th>写出的可见事实</th><th>写入的不支持陈述</th></tr>'
    for k,n in [('round1','第 1 轮'),('round2','第 2 轮'),('round3','第 3 轮'),('both_first_two','前两轮都提到'),('majority','三轮至少两票')]:
        s=scores[k];head+=f'<tr><td>{n}</td><td>{s["positive_supported"]}/{pos}</td><td>{s["negative_asserted"]}/{neg}</td></tr>'
    head+='</table><p>自由描述按人物或声源、对象、方向和动作实例做文本配对。同轮不能重复计票，区间 IoU 至少 0.25，分句与大段、单次与整串动作应分开。保留两票以上的事件区间中位数，代表轮次的详细措辞仍须复核。匹配器同样会出错。每条链接标有轮次及原文行号。</p>'
    head+=f'<p>视觉配对得到 {totals["visual"][3]} 组三票、{totals["visual"][2]} 组两票、{totals["visual"][1]} 组一票；声音分别为 {totals["audio"][3]}、{totals["audio"][2]}、{totals["audio"][1]} 组。两端实例在同两轮实际重叠且中位区间有交集，才保留同期候选。共 {edges_total} 条，含背景与状态；其中 {short} 条中位交集短于 0.2 秒。实例复现不代表细节、人物属性或精确边界都已证实。</p>'
    head+='<h3>用独立语音识别检查分句</h3><p>Vosk small-en-us 0.15 的词级边界，使用同一原声。下表比较代表词组与视觉区间的交集；词时刻为独立模型估计。钟表精度与文字识别仍需人工听校。</p><table><tr><th>动作</th><th>所听词组</th><th>词组秒数</th><th>相交秒数</th></tr>'
    for a in anchors:
        lo,hi=a['word_range'];head+=f'<tr><td>{safe(a["visual"])}</td><td>{safe(a["phrase"])}</td><td>{lo:.2f}–{hi:.2f}</td><td>{a["overlap"]:.2f}</td></tr>'
    head+='</table><p>旧版 v6 把局部复核写入 motion_tracks，音画关系仍沿用早期动作表。试验版在新表上重新求交。多数决仍会丢掉只出现一次的回位、双人动作及按压细节，也可能共同合并相邻指令。建议用定向回放处理这些分歧，并在最终动作、语音表更新后重新计算关联。</p>'
    head+='<p>音乐类还暴露出前景定义的问题。吉他样本三轮听标都把吉他声列为背景，而画面主体的活动就是演奏。可分别记录声音在混音中的显著度，以及它是否属于画面主体活动。羽毛球回位只在第三轮子阶段写出；棒球短暂搂肩经密集抽帧确认，对应的初始稀疏抽帧参考已纠正。定向回看是同一模型带候选陈述的复核，不能充当独立裁判。</p>'
    head+='<p><a href="summary.json">统计与词级核对</a> · <a href="probe_support.json">逐项文本证据编号</a> · <a href="probes.json">核查项与画面位置</a> · <a href="selection.json">选片来源</a> · <a href="prompts/visual.txt">视觉指令</a> · <a href="prompts/audio.txt">音频指令</a> · <a href="prompts/match.txt">配对指令</a> · <a href="prompts/verify.txt">回看指令</a></p>'
    css='body{max-width:1120px;margin:2em auto;padding:0 4%;font:16px/1.6 system-ui;color:#19373c}article{border-top:3px solid #9ab8b2;margin:35px 0;padding:15px 0}video,img{max-width:100%;max-height:52vh}table{border-collapse:collapse;width:100%;margin:1em 0}td,th{text-align:left;padding:5px 10px;border-bottom:1px solid #cfdddb}button,summary{cursor:pointer}a{color:#006356}small{color:#4e6668}details{margin:10px 0}video{background:#111}'
    js="document.addEventListener('click',e=>{let b=e.target.closest('button[data-t]');if(b){let v=document.getElementById(b.dataset.case);v.currentTime=+b.dataset.t;v.play()}})"
    (HERE/'六类视频_三轮标注审阅.html').write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>六类视频三轮标注</title><style>'+css+'</style>'+head+''.join(articles)+'<script>'+js+'</script></html>',encoding='utf8')

if __name__=='__main__':main()
