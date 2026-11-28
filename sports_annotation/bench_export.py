"""Serialize English reference rows, their evidence, and the matching review view."""
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
from urllib.parse import quote
from html import escape

from .io_utils import file_hash, object_hash, read_json, write_json
from .long_timeline import intersections
from .bench import ask
from .long_video import reference, wav_slice, PROMPTS

FLAG_NAMES={
    "跨窗实例身份待核":"Ambiguous instance across windows", "在采样窗边缘截断":"Truncated by a sampling window",
    "跨窗边界冲突":"Conflicting window boundaries", "交叠不足0.2秒":"Overlap shorter than 0.2 s",
    "词时标与复听边界差异超过0.65秒":"Word times differ from relistening by more than 0.65 s",
    "短语未获独立词时标支持":"Short utterance lacks independent word timing",
    "仍可能含多个分句":"Possible compound utterance", "同句发言次数待核":"Repeated utterance unresolved",
    "可能为同一说话人重叠，需复听":"Possible overlapping turns from the same voice",
    "分句边界未解":"Clause boundary unresolved","复听未定位":"Could not localize on replay",
    "复听范围未能对应":"Replay span did not match"
}

def review_sounds(root,audio,duration):
    rows=[e for e in audio if e["kind"]!="speech"]
    grouped=defaultdict(list)
    for e in rows:
        grouped[int((e["start"]+e["end"])/30)].append(e)
    for i,group in grouped.items():
        lo=max(0,min(e["start"] for e in group)-.5)
        hi=min(duration,max(e["end"] for e in group)+.5)
        folder=root/f"sound_review{i:05}"
        folder.mkdir(exist_ok=True)
        wav=folder/"excerpt.wav"
        wav_slice(root/"full.wav",wav,lo,hi)
        candidates=[{"id":e["id"],"start":round(e["start"]-lo,3),"end":round(e["end"]-lo,3),"description":e["text"]} for e in group]
        def check(obj):
            rr=obj.get("checks")
            if not isinstance(rr,list) or sorted(str(r.get("id")) for r in rr)!=sorted(e["id"] for e in group):
                raise ValueError("Return every supplied ID once.")
            for r in rr:
                if r.get("verdict") not in ("supported","unclear","absent") or not r.get("detail") or not r.get("label"):
                    raise ValueError("Each check needs verdict, English label and English detail.")
        msg=(PROMPTS/"bench/sound_review.en").read_text("utf8")+"\n"+json.dumps(candidates,ensure_ascii=False)
        ans=ask(folder,"check",msg,[reference("audio",wav)],check)
        byid={r["id"]:r for r in ans["checks"]}
        for e in group:
            r=byid[e["id"]]
            if r["verdict"]=="supported":
                e.update(label=r["label"],text=r["detail"])
            else:
                e["review_flags"].append("Non-speech sound "+r["verdict"]+" on acoustic replay")

def temporal(visual,audio):
    raw=intersections(visual,audio)
    sounds={a["id"]:a for a in audio}
    result=[]
    for e in raw:
        a=sounds[e["audio"]]
        lo,hi=e["intersection"]
        uncertainty=a.get("boundary_ranges",{"start":[a["start"]]*2,"end":[a["end"]]*2})
        core=[max(lo,uncertainty["start"][1]),min(hi,uncertainty["end"][0])]
        flags=[FLAG_NAMES.get(f,f) for f in e["review_flags"]]
        if core[1]-core[0]<.2-1e-8 and a.get("boundary_ranges"):
            flags.append("Overlap depends on a disputed speech boundary")
        result.append({"visual_id":e["visual"],"audio_id":e["audio"],"type":"temporal_overlap",
             "start":e["intersection"][0],"end":e["intersection"][1],
             "robust_interval":core if core[1]>core[0] else None,"review_flags":flags})
    return result

def bound_adjacent_turns(rows):
    marker="Possible overlapping turns from the same voice"
    turns=[e for e in rows if e["kind"]=="speech" and marker in e["review_flags"]]
    unresolved=set()
    updated=set()
    for i,left in enumerate(turns):
        for right in turns[i+1:]:
            if right["start"]>=left["end"]: break
            a,b=right["start"],left["end"]
            names=(left["id"],right["id"])
            if (left["actor"]!=right["actor"] or b-a>.40 or left["start"]>=a or right["end"]<=b
                    or left["transcript_original"]==right["transcript_original"]):
                unresolved.update(names)
                continue
            for e,side in ((left,"end"),(right,"start")):
                e.setdefault("boundary_ranges",{"start":[e["start"]]*2,"end":[e["end"]]*2})[side]=[a,b]
            updated.update(names)
    for e in turns:
        if e["id"] in updated-unresolved:
            e["review_flags"].remove(marker)

def package(header,rows,*,status,scored_only=False):
    chosen=[{**e,**({"phases":[p for p in e["phases"] if not p.get("review_flags")]} if "phases" in e else {})}
            for e in rows if not e["review_flags"]] if scored_only else rows
    v=[e for e in chosen if e["modality"]=="visual"]
    a=sorted((e for e in chosen if e["modality"]=="audio"),key=lambda e:e["start"])
    ps=[{**p,"review_flags":[*e["review_flags"],*p.get("review_flags",[])]} for e in v for p in e["phases"]]
    rel=temporal(v,a)
    prel=temporal(ps,a)
    if scored_only:
        rel=[x for x in rel if not x["review_flags"]]
        prel=[x for x in prel if not x["review_flags"]]
    return {**header,"reference_status":status,"events":chosen,"relations":rel,"phase_relations":prel}

def save(root,src,protocol,cast,vis,aud,missing):
    from .bench_facts import inspect_facts
    from .bench_adjudicate import validate
    scopes=read_json(root/"reference_protocol.json")["scopes"]
    inspect_facts(root,src,protocol["duration"],vis,scopes,3,cast)
    review_sounds(root,aud,protocol["duration"])
    path=Path(__file__).parent
    release_protocol={"version":"1.0","model":protocol["model"],"reference_type":"machine-reviewed",
                      "prompts":{p.name:file_hash(p) for p in sorted((PROMPTS/"bench").iterdir()) if p.is_file()},
                      "implementation":{p.name:file_hash(p) for p in sorted([*path.glob("bench*.py"),*path.glob("long_*.py")])},
                      "input_manifest":protocol}
    write_json(root/"release_protocol.json",release_protocol)
    header={"schema":"av-events/1.0","description_language":"en","source_sha256":protocol["source_sha256"],
            "protocol_sha256":object_hash(release_protocol),
            "duration_seconds":protocol["duration"],"actors":cast,"clock":"source seconds, half-open intervals",
            "relation_semantics":"Evidence of temporal co-occurrence only. Speaker identity and acoustic causation are separate claims."}
    rows=[]
    for e in vis+aud:
        flags=[FLAG_NAMES.get(f,f) for f in e["review_flags"]]
        v=e["kind"] in ("visible_speech","gesture","motion","state")
        row={k:e[k] for k in ("id","kind","actor","start","end","sources")}
        row.update(modality="visual" if v else "audio",review_flags=flags)
        if v:
            row.update({k:e[k] for k in ("actor_id","activity","label","brief","detail","phases")})
            row.update(fact_verdict=e["fact_verdict"],fact_evidence=e["fact_evidence"])
            row["fact_evidence_clock_origin"]=e["fact_clock_origin"]
            row["actor_scope"]="event" if row["actor_id"].startswith("local_") else "clip"
            if e["kind"]=="visible_speech":
                row.update(posture=e["posture"],visual_evidence=e["evidence"])
                if e.get("posture_evidence"):
                    row["posture_evidence"]=e["posture_evidence"]
        elif e["kind"]=="speech":
            row.update(label="Speech",detail=e["english"],transcript_original=e["text"],layer=e["layer"],
                       timing_method=e["timing_evidence"]["method"],qwen_interval=e["timing_evidence"]["qwen_range"])
            if "word_match" in e["timing_evidence"]:
                row["word_interval"]=[e["timing_evidence"]["word_match"][k] for k in ("start","end")]
        else:
            row.update(label=e["label"],detail=e["text"],layer=e["layer"],source_attribution="unassigned")
        rows.append(row)
    rows.sort(key=lambda e:(e["start"],e["end"],e["id"]))
    bound_adjacent_turns(rows)
    raw=package(header,rows,status="model_annotations_with_review_flags")
    ready=package(header,rows,status="machine_reviewed_silver",scored_only=True)
    validate(raw)
    validate(ready)
    write_json(root/"annotations.json",raw)
    write_json(root/"reference.json",ready)
    queue={"flagged_events":[e["id"] for e in rows if e["review_flags"]],
           "unlocalized_transcript_candidates":missing,
           "uncertain_visible_intervals":[]}
    for path in sorted(root.glob("shot*/audit.json")):
        data=read_json(path)
        for key in ("uncertain_muted_local","uncertain_joint_local"):
            for e in data[key]:
                if isinstance(e,dict):
                    queue["uncertain_visible_intervals"].append({"scope":path.parent.name,"source_start":data["scope"]["span"][0],
                                                              "evidence_stage":key,"local_report":e})
    write_json(root/"review_queue.json",queue)
    render(root,src,raw,ready)

def render(root,src,raw,ready):
    safeids={e["id"] for e in ready["events"]}
    table=[]
    listing=[]
    def play(a,b):
        return f'<button data-a="{a:.4f}" data-b="{b:.4f}">{a:.2f}–{b:.2f} s</button>'
    for e in raw["events"]:
        a,b=e["start"],e["end"]
        meta=" · ".join([e["id"],e["kind"],e["actor"]])
        info=(e.get("brief","")+" "+e["detail"]).strip()
        if e["kind"]=="visible_speech":
            info+=" Posture: "+e["posture"]+". Visible evidence: "+e["visual_evidence"]
        note="Included in silver reference" if e["id"] in safeids else "Review: "+", ".join(e["review_flags"])
        original=e.get("transcript_original")
        extra=("<blockquote>"+escape(original)+"</blockquote>") if original else ""
        stages="".join(f'<li>{play(p["start"],p["end"])} {escape(p["label"])}</li>' for p in e.get("phases",[]))
        table.append(f'<tr id="{e["id"]}"><td>{play(a,b)}<small>{escape(meta)}</small></td><td><strong>{escape(e["label"])}</strong><p>{escape(info)}</p>{extra}<ul>{stages}</ul><small>{escape(note)}</small></td></tr>')
        listing.append(f'{a:.2f}–{b:.2f} s | {meta} | {e["label"]}\n{info}'+(f'\nOriginal: {original}' if original else '')+'\n'+note)
    lookup={e["id"]:e["label"] for e in raw["events"]}
    groups=[]
    for x in ready["relations"]:
        v,a=x["visual_id"],x["audio_id"]
        groups.append(f'<li>{play(x["start"],x["end"])} <a href="#{v}">{v} {escape(lookup[v])}</a> / <a href="#{a}">{a}</a></li>')
    try:
        url=quote(Path(os.path.relpath(src,root)).as_posix(),safe="/.")
    except ValueError:
        url=src.as_uri()
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Event reference review</title><style>body{max-width:1040px;margin:auto;padding:16px;font:16px/1.5 system-ui;color:#182e3d}video{width:100%;max-height:35vh;background:black;position:sticky;top:0;z-index:1}td{padding:10px;border-bottom:1px solid #cdd5d8;vertical-align:top}small{display:block;color:#475c65}p,ul,blockquote{margin:.35em 0}button{cursor:pointer;color:#174a67}tr{scroll-margin-top:36vh}</style><h1>Event reference review</h1>'''
    page+=f'<video id="v" controls playsinline preload="metadata" src="{escape(url)}"></video><table><tr><th>Time and actor</th><th>Event and evidence</th></tr>{"".join(table)}</table><h2>Scored temporal overlaps</h2><ul>{"".join(groups)}</ul>'
    page+='''<script>const v=document.querySelector("video");let timer;document.addEventListener("click",e=>{const b=e.target.closest("button[data-a]");if(!b)return;clearInterval(timer);v.currentTime=+b.dataset.a;v.play().catch(()=>{});timer=setInterval(()=>{if(v.currentTime>=+b.dataset.b){v.pause();clearInterval(timer)}},25)});</script></html>'''
    (root/"review.html").write_text(page,encoding="utf8")
    (root/"events.txt").write_text("\n\n".join(listing)+"\n",encoding="utf8")
