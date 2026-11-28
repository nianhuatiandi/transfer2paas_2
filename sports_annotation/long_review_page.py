"""Render the audio-led, local media review from the final caption table."""
from html import escape
from pathlib import Path
from urllib.parse import quote
import os

def render(root, source, table):
    def playback(a,b):
        return f'<button type="button" data-a="{a:.6f}" data-b="{b:.6f}">{a:.2f}–{b:.2f} 秒</button>'
    def h(txt):
        return escape(str(txt), quote=True)
    try:
        url=quote(Path(os.path.relpath(source,root)).as_posix(),safe="/.")
    except ValueError:
        url=source.as_uri()
    visual={v["id"]:v for v in table["visual"]}
    edges={}
    for e in table["edges"]:
        edges.setdefault(e["audio"],[]).append(e)
    rows=[]
    for a in table["audio"]:
        method=a.get("timing_evidence",{}).get("method")
        timing={"qwen_and_asr":"Qwen 复听，独立词时标支持","qwen_audio_relisten":"Qwen 局部复听"}.get(method,"Qwen 听音")
        tags=" · ".join([timing,*a["review_flags"]])
        matches=[]
        for e in edges.get(a["id"],[]):
            v=visual[e["visual"]]
            flag=" · "+"、".join(e["review_flags"]) if e["review_flags"] else ""
            matches.append(f'<li>{playback(*e["intersection"])} {h(v["actor"])} · {h(v["label"])}<small>{h(v["id"]+flag)}</small></li>')
        rows.append(f'<tr><td>{playback(a["start"],a["end"])} <small>{h(a["id"])}</small><p>{h(a["text"])}</p><small>{h(tags)}</small></td><td><ul>{"".join(matches) or "<li>未提取到重叠动作</li>"}</ul></td></tr>')
    page='''<!DOCTYPE html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>动作与声音对照</title><style>
body{font:16px/1.5 system-ui,sans-serif;max-width:1000px;margin:auto;padding:16px;color:#172b3c}video{width:100%;max-height:36vh;background:#161a1e}header{position:sticky;top:0;background:white}table{width:100%;border-collapse:collapse}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #bbb;padding:.7rem}td:first-child{width:40%}ul{padding:0;margin:0;list-style:none}li{margin:0 0 .45rem}button{cursor:pointer;color:#074c78;background:#eff6fb;border:1px solid #a0b3bf;border-radius:3px;padding:.2rem .4rem}small{display:block;color:#425666}p{margin:.35rem 0}</style>
<h1>动作与声音对照</h1><p>左侧播放一句话或一段声音，右侧播放它与某个动作重叠的片段。时间均从原片开头计。</p>'''
    page+=f'<header><video id="v" src="{h(url)}" controls playsinline preload="metadata"></video></header><table><thead><tr><th>语音与声音</th><th>同期动作</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
    page+='''<script>const v=document.querySelector("video");let timer;
document.addEventListener("click",e=>{const b=e.target.closest("button[data-a]");if(!b)return;clearInterval(timer);const a=Number(b.dataset.a),z=Number(b.dataset.b);
v.currentTime=a;v.play().catch(()=>{});timer=setInterval(()=>{if(v.currentTime>=z){v.pause();clearInterval(timer)}},25)});v.addEventListener("ended",()=>clearInterval(timer));</script></html>'''
    temp=root/"审阅.html.tmp"
    temp.write_text(page,encoding="utf8")
    temp.replace(root/"审阅.html")
