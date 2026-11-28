from collections import Counter
from pathlib import Path
import hashlib
import html
import json
import av

ROOT = Path(__file__).resolve().parent
REPO = "https://huggingface.co/datasets/OmniCapBench/OmniCapBench"
REV = "bd6448a01238f125eaf128b8ae35c20cc3b37374"
SAMPLES = {
    "01_under_1min": ("Under 1 minute", (134, 282, 428)),
    "02_1_to_3min": ("1–3 minutes", (516, 598, 627)),
    "03_3_to_5min": ("3–5 minutes", (716, 719, 733)),
}

def esc(value):
    return html.escape(str(value))

def para(value):
    return f"<p>{esc(value)}</p>" if value else ""

def interval(bounds):
    if not bounds or len(bounds) != 2:
        return ""
    start,end=map(float,bounds)
    return f'<button data-start="{start}" data-end="{end}">{start:.2f}–{end:.2f}s</button>'

def details(title, content):
    return f"<details><summary>{esc(title)}</summary>{content}</details>"

def render(gt):
    cap=gt["mtss_caption"]
    shots=[]
    for s in cap["shots"]:
        title=f"{s['shot_id']} · {s.get('shot_transfer','')}"
        body=interval(s.get("time_range"))
        body+=para("References "+", ".join(map(str,s.get("references_in_shot",[]))))
        body+=para("Active audio events "+", ".join(map(str,s.get("active_events",[]))))
        body+="".join(interval(t.get("sub_shot_time"))+para(t.get("sub_shot_content")) for t in s["visual_description"])
        shots.append(details(title,body))
    events=[]
    for e in cap["events"]:
        c=e["content"]
        body=interval(e.get("time_range"))
        if c.get("speaker"):
            body+=para(f"Speaker {c['speaker']}")
        body+=para(c.get("line"))+para(c.get("description"))
        events.append(details(f"{e['event_id']} · {e['type']}",body))
    refs=[]
    for r in cap["references"]:
        body=para(r.get("semantic_description"))
        body+=para(r.get("appearance_anchor",{}).get("id_features",{}).get("detail_description"))
        refs.append(details(f"{r['ref_id']} · {r['type']}",body))
    return "".join(f"<section><h2>{title}</h2>{''.join(rows)}</section>" for title,rows in
                   (("Shots and subshots",shots),("Audio events",events),("References",refs)))

def page(title, body):
    style="""<style>body{font:16px system-ui;max-width:1050px;margin:2rem auto;padding:0 1rem;color:#203242}a{color:#006279}video{width:min(100%,740px);max-height:62vh;background:#111}details{border-bottom:1px solid #ccd7df;padding:.6rem 0}summary,button{cursor:pointer}table{width:100%;border-collapse:collapse}th,td{text-align:left;border-bottom:1px solid #ccd7df;padding:.55rem .3rem}</style>"""
    return f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>{style}{body}</html>'

JS="""<script>
const v=document.querySelector('video');let stop=0;
document.addEventListener('click',e=>{const b=e.target.closest('button[data-start]');if(b){v.currentTime=+b.dataset.start;stop=+b.dataset.end;v.play()}});
v.addEventListener('timeupdate',()=>{if(stop&&v.currentTime>=stop){v.pause();stop=0}});
</script>"""

def records(name, key):
    out={}
    for line in (ROOT/name).read_text(encoding="utf8").splitlines():
        data=json.loads(line)
        out[data[key]]=(line,data)
    return out

def main():
    gt_entries=records("_official_eval.jsonl","video_path")
    meta=records("_official_metadata.jsonl","file_name")
    manifest=[]
    blocks=[]
    for folder,(label,ids) in SAMPLES.items():
        blocks.append(f'<h2>{label}</h2><table><tr><th>ID</th><th>Duration</th><th>Official category</th><th>Shots</th><th>Subshots</th><th>Audio events</th></tr>')
        for n in ids:
            k=f"{n:06d}"
            rel=f"{folder}/{k}"
            p=ROOT/rel
            name=f"{k}.mp4"
            official=f"test/videos/{name}"
            line,gt=gt_entries[official]
            assert gt["mtss_caption"]==meta[f"videos/{name}"][1]["mtss_caption"]
            (p/"official_gt.jsonl").write_text(line+"\n",encoding="utf8")
            (p/"official_gt.json").write_text(json.dumps(gt,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
            with av.open(str(p/name)) as c:
                d=c.duration/av.time_base
                assert c.streams.audio and c.streams.video
                v=c.streams.video[0]
                assert next(c.decode(v),None) is not None
                dimensions=[v.width,v.height]
            assert abs(d-gt["duration_sec"])<1
            cap=gt["mtss_caption"]
            shots=len(cap["shots"])
            subs=sum(len(s["visual_description"]) for s in cap["shots"])
            events=len(cap["events"])
            types=Counter(e["type"] for e in cap["events"])
            category=f"{gt['category_l1']} / {gt['category_l2']}"
            src=f"{REPO}/blob/{REV}/{official}"
            stat=f"{d:.2f}s · {dimensions[0]}×{dimensions[1]} · {shots} shots · {subs} subshots · {events} audio events"
            body=f'<p><a href="../../index.html">All samples</a></p><h1>{k} · {esc(category)}</h1><p>{stat}</p><video controls preload="metadata" src="{name}"></video><p><a href="{name}">MP4</a> · <a href="official_gt.json">Official GT JSON</a> · <a href="official_gt.jsonl">Original evaluation line</a> · <a href="{src}">Official source</a></p>'+render(gt)+JS
            (p/"index.html").write_text(page(k,body),encoding="utf8")
            manifest.append(dict(id=k,bucket=gt["duration_bucket"],duration_s=round(d,3),category=category,dimensions=dimensions,references=len(cap["references"]),shots=shots,subshots=subs,audio_events=events,audio_types=types,file=f"{rel}/{name}",ground_truth=f"{rel}/official_gt.json",sha256=hashlib.sha256((p/name).read_bytes()).hexdigest(),source=src))
            blocks.append(f'<tr><td><a href="{rel}/index.html">{k}</a></td><td>{d:.2f}s</td><td>{esc(category)}</td><td>{shots}</td><td>{subs}</td><td>{events}</td></tr>')
            print(k,round(d,2),category,shots,subs,events)
        blocks.append("</table>")
    (ROOT/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf8")
    head=f'<h1>OmniCapBench official samples</h1><p>Nine full videos with their original evaluation records, three per official duration bucket.</p><p><a href="manifest.json">Manifest</a> · <a href="{REPO}">Dataset release</a></p>'
    (ROOT/"index.html").write_text(page("OmniCapBench official samples",head+"".join(blocks)),encoding="utf8")

if __name__=="__main__":
    main()
