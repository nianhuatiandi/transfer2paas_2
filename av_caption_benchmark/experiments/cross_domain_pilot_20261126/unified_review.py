"""Render the common review format for sport and everyday clips."""
import json
import os
from html import escape
from pathlib import Path
from urllib.parse import quote

STYLE = '<style>body{max-width:980px;margin:2em auto;padding:0 1em;font:16px/1.65 system-ui;color:#183b42}video{max-width:100%;max-height:48vh}li{margin:1em 0}button{cursor:pointer}a{color:#056d78}</style>'


def clock(event):
    return f"{event['start']:.3f}–{event['end']:.3f} 秒"


def track_caption(visual):
    lines=[]
    for t in visual["motion_tracks"]:
        lines.append(f"{t['shot_id']}　{t['actor_id'] or '场景'}　{t['identity']}")
        if t.get("native_facts"):
            lines.append("连续原视频观察")
            lines.extend(t["native_facts"])
        if "integrated_facts" in t:
            if visual.get("caption_detail_policy")=="retain_evidence":
                # Preserve localized observations that the single integrated paragraph can omit.
                seen=set()
                for facet in ("pose","contact","camera"):
                    for x in t["inspections"][facet]:
                        fact=x["description"].strip()
                        if fact not in seen:
                            lines.append(f"{x['start']:g}–{x['end']:g} 秒　{fact}")
                            seen.add(fact)
                lines.append("短时间窗的局部观察")
                for window in t["window_review"]:
                    for fact in window["facts"]:
                        if fact.strip() not in seen:
                            lines.append(f"{window['start']:g}–{window['end']:g} 秒　{fact}")
                            seen.add(fact.strip())
                lines.append("全片复核后的动作顺序")
                lines.extend(fact for fact in t["integrated_facts"] if fact.strip() not in seen)
            else:
                lines.extend(t["integrated_facts"])
            lines.append("")
            continue
        if "inspections" in t:
            for facet, label in (("pose","身体与运动"),("contact","接触与反应"),("camera","空间与镜头")):
                lines.append(label)
                for x in t["inspections"][facet]:
                    lines.append(f"{x['start']:g}–{x['end']:g} 秒　{x['description']}")
            lines.append("")
            continue
        lines.append(t["context"])
        for s in t["phases"]:
            lines.append(f"{s['start']:g}–{s['end']:g} 秒　{s['caption']}")
        lines.extend(["镜头与画面　"+t["camera"],""])
    return "\n".join(lines).strip()


def export_case(directory, clip, record, raw_stages=None):
    title = record['source']['domain']
    video = quote(Path(os.path.relpath(clip, directory)).as_posix(), safe='/')
    web = ['<!doctype html><meta charset="utf-8">', '<title>'+escape(title)+'</title>', STYLE,
           '<a href="../../试标总览.html">返回总览</a><h1>'+escape(title)+'</h1>',
           '<video id="clip" controls preload="metadata" src="'+video+'"></video>']
    plain = [title, 'Qwen 候选标注，时间相对裁片起点。']
    source = record['source']
    if 'main_subject_count' in source:
        selection = f"主要执行者 {source['main_subject_count']} 位（{source['subject_kind']}）。{source['selection_note']}"
        web.append('<p>'+escape(selection)+'</p>')
        plain.append(selection)
    stage_links = []
    for name, caption in [('visual','视觉初标'),('audio','原声听标'),('review','音画联合复核'),('audio_transcript','逐字转写')]:
        if record['audio'] is None and name != 'visual':
            continue
        stage = (raw_stages or directory/'stages')/name
        meta = json.loads((stage/'metadata.json').read_text('utf8'))
        raw = stage / meta.get('accepted_response_path','response.txt')
        prompt = stage/'imported_prompt.txt' if not meta.get('api_call_made',True) else raw.parent/'prompt.txt'
        urls = [quote(Path(os.path.relpath(f,directory)).as_posix()) for f in (prompt,raw)]
        stage_links.append(f'{caption}（<a href="{urls[0]}">指令</a> · <a href="{urls[1]}">原文</a>）')
    web.append('<p>'+'　'.join(stage_links)+'</p>')

    def section(name, rows):
        web.append('<h2>'+escape(name)+'</h2><ul>')
        plain.extend(['',name])
        for start, lines in rows:
            plain.extend(lines)
            button = '' if start is None else f'<button data-t="{start}">▶ {start:.2f} s</button> '
            web.append('<li>'+button+'<br>'.join(escape(line) for line in lines)+'</li>')
        web.append('</ul>')

    visual = record['visual']
    if visual.get('motion_tracks'):
        section('逐主体视觉复核 · 裁判输入',[(None,[line for line in track_caption(visual).splitlines() if line])])
    section('人物与执行段', [(None,[a['id']+'　'+a['description']]) for a in visual['actors']] +
            [(e['start'],[e['id']+'　'+clock(e)+'　'+e['description']]) for e in visual['executions']])
    actions = []
    for a in sorted(visual['actions'], key=lambda a:(a['start'],a['id'])):
        lines = [f"{a['id']}　{a['actor_id']}　{a['kind']} / {a['label']}　{clock(a)}",
                 '动作简述　'+a['brief'], '详细描述　'+a['detail']]
        lines.extend(f"画面证据　{e['time']:g} 秒　{e['observation']}" for e in a['evidence'])
        lines.extend(f"子阶段　{clock(s)}　{s['label']}　{s['detail']}" for s in a['subphases'])
        lines.extend(f"关键点　{k['time']}　{k['name']}" for k in a['key_moments'])
        actions.append((a['start'],lines))
    section('视觉动作 · 联合复核后' if record['audio'] is not None else '视觉动作 · 无声帧初标',actions)
    if record['audio'] is None:
        section('音频与同期关系',[(None,['此输入缺少可核验的原声音轨，仅完成视觉初标。'])])
    else:
        section('原声独立听写',[(e['start'],[e['id']+'　'+clock(e)+'　'+e['kind']+' / '+e['layer'],
                                    e['description']] + ([str(e.get('speaker_id') or '')+'　'+e['transcript']] if e['transcript'] else []))
                           for e in record['audio']['events']])
        section('动作与声音的名义时间交集',[(p['intersection'][0],[p['action_id']+' × '+p['audio_id']+f"　{p['overlap_s']:g} 秒（{p['audio_layer']}）"])
                                       for p in record['relations']['pairs'] if p['nominal_overlap']])
    section('待核对',[(None,[str(w)]) for w in record['warnings']])
    web.append('<script>document.addEventListener("click",e=>{if(e.target.hasAttribute("data-t")){clip.currentTime=Number(e.target.dataset.t);clip.play()}})</script>')
    (directory/'审阅.html').write_text('\n'.join(web),encoding='utf8')
    (directory/'人工审阅.txt').write_text('\n'.join(plain)+'\n',encoding='utf-8-sig')


def export_index(out, cases):
    out.mkdir(parents=True, exist_ok=True)
    lines = ['<!doctype html><meta charset="utf-8"><title>联合复核试标</title>',STYLE,
             '<h1>联合复核试标</h1><p>初标及联合复核均包含动作简述与详细描述。最终语音来自独立听写，关系按名义时间区间求交。</p><ul>']
    for case in cases:
        directory=out/'cases'/case['id']
        if (directory/'审阅.html').exists():
            data=json.loads((directory/'annotations.json').read_text('utf8'))
            count=sum(a['kind']=='motion' for a in data['visual']['actions'])
            label=f"{case['domain']}　{count} 个主要动作"
            if data['audio'] is None:
                label+='　仅视觉'
            lines.append('<li><a href="cases/'+quote(case['id'])+'/审阅.html">'+escape(label)+'</a></li>')
        else:
            lines.append('<li>'+escape(case['domain'])+'　尚无完整结果</li>')
    (out/'试标总览.html').write_text('\n'.join(lines+['</ul>']),encoding='utf8')
