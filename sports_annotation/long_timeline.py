"""Reconcile neighbouring windows and derive temporal intersections on the source clock."""
from collections import Counter, defaultdict
from statistics import median
import json

from .io_utils import write_json

def seam_review(folder, cut, span, left, right, source, audio, ask, media, prompt, *, english=False):
    lo,hi=span
    pairs=[]
    for m in ("visual","audio"):
        for a in left[m]:
            for b in right[m]:
                if a["kind"]!=b["kind"]:
                    continue
                if min(a["end"],b["end"],hi) + .25 <= max(a["start"],b["start"],lo):
                    continue
                pairs.append((a,b))
    if not pairs:
        return []
    fields=("origin","actor","kind","brief","text","label","start","end")
    display=lambda e:{k:e[k] for k in fields if k in e}
    data=[[str(i),display(a),display(b)] for i,(a,b) in enumerate(pairs,1)]
    vis,aud=media(folder/"media",source,audio,lo,hi)
    def check(obj):
        items=obj.get("pairs",[])
        if [str(r[0]) for r in items] != [r[0] for r in data]:
            raise ValueError("Return exactly one row for each pair ID, in order")
        if any(len(r) not in (2,3) or r[1] not in ("same","different","unclear") or
               (len(r)==3 and not isinstance(r[2],str)) for r in items):
            raise ValueError("Use arrays [ID, same/different/unclear, optional full speech text]")
    clock=f"\nSource seam at {cut:.3f} s. Excerpt starts at {lo:.3f} s.\n" if english else f"\n接缝在原片 {cut:.3f} 秒。所附媒体起点在原片 {lo:.3f} 秒。\n"
    msg=prompt("seam")+clock+json.dumps(data,ensure_ascii=False)
    obj=ask(folder,"seam",msg,vis+aud,check)
    return [dict(left=a["origin"],right=b["origin"],verdict=r[1],quote=r[2] if len(r)>2 else "")
            for (a,b),r in zip(pairs,obj["pairs"])]

def stitch(windows, records, decisions, duration, *, prefer_core_bounds=False):
    entries={}
    parent={}
    flagged=defaultdict(set)
    quotes={}
    def find(key):
        while parent[key]!=key:
            parent[key]=parent[parent[key]]
            key=parent[key]
        return key
    for w,record in zip(windows,records):
        for m,rows in record.items():
            for e in rows:
                k=e["origin"]
                entries[k]=(w,m,e)
                parent[k]=k
    for rows in decisions:
        counts=Counter(k for r in rows if r["verdict"]=="same" for k in (r["left"],r["right"]))
        for row in rows:
            a,b=row["left"],row["right"]
            actors=[entries[k][2].get("actor_id","unknown") for k in (a,b)]
            if row["verdict"]=="same" and "unknown" not in actors and actors[0]!=actors[1]:
                for k in (a,b):
                    flagged[k].add("Conflicting actor IDs in a proposed seam match")
                continue
            if row["verdict"]=="unclear" or (row["verdict"]=="same" and max(counts[a],counts[b])>1):
                for k in (a,b):
                    flagged[k].add("跨窗实例身份待核")
            elif row["verdict"]=="same":
                parent[find(b)]=find(a)
                if row["quote"] and entries[a][2]["kind"]=="speech":
                    quotes[a]=row["quote"]
    groups=defaultdict(list)
    for k in entries:
        groups[find(k)].append(entries[k])
    out={"visual":[],"audio":[]}
    overflow=[]
    for members in groups.values():
        def owned(w,e):
            mid=(e["start"]+e["end"])/2
            return w["core"][0]<=mid<w["core"][1]
        if not any(owned(w,e) for w,m,e in members):
            overflow.extend(e["origin"] for w,m,e in members)
            continue
        def truncated(w,e,side):
            t=w["span"][0 if side=="start" else 1]
            return 0<t<duration and abs(e[side]-t)<.18
        def boundary(side):
            vals=[e[side] for w,m,e in members if not truncated(w,e,side)]
            if prefer_core_bounds:
                owned_bounds=[e[side] for w,_,e in members if w["core"][0]<=e[side]<=w["core"][1] and not truncated(w,e,side)]
                vals=owned_bounds or vals
            return round(median(vals) if vals else (min if side=="start" else max)(e[side] for w,m,e in members),3)
        lo,hi=boundary("start"),boundary("end")
        w,m,ref=max(members,key=lambda row:(
            -int(truncated(row[0],row[2],"start"))-int(truncated(row[0],row[2],"end")),
            owned(row[0],row[2]), row[2]["end"]-row[2]["start"]))
        flags={f for w,_,e in members for f in flagged[e["origin"]]}
        if any(all(truncated(w,e,side) for w,_,e in members) for side in ("start","end")):
            flags.add("在采样窗边缘截断")
        flags.update(e["needs_review"] for _,_,e in members if e.get("needs_review"))
        if lo>=hi:
            lo,hi=ref["start"],ref["end"]
            flags.add("跨窗边界冲突")
        item={**ref,"start":lo,"end":hi,"sources":[e["origin"] for _,_,e in members]}
        item.pop("origin",None)
        quote=next((quotes[e["origin"]] for _,_,e in members if e["origin"] in quotes),None)
        if ref["kind"]=="speech":
            # A short seam replay may only hear the tail. Keep the quote and its own clock together.
            item["start"],item["end"]=ref["start"],ref["end"]
            if quote:
                item["seam_excerpt"]=quote
            item["alternate_quotes"]=[{"text":e["text"],"start":e["start"],"end":e["end"],"origin":e["origin"]}
                                      for _,_,e in members if e["origin"]!=ref["origin"] and e["text"]!=ref["text"]]
        if item.get("phases"):
            phases=[]
            for p in item["phases"]:
                a,b=max(lo,p["start"]),min(hi,p["end"])
                if b>a:
                    phases.append({**p,"start":a,"end":b})
            item["phases"]=phases
        item["review_flags"]=sorted(flags)
        if m=="audio" and item["kind"] in ("sound","ambience"):
            item["source_status"]="仅依据听感描述，具体发声物体待核"
        out[m].append(item)
    for m,rows in out.items():
        rows.sort(key=lambda e:(e["start"],e["end"],e["sources"][0]))
        for i,e in enumerate(rows,1):
            e["id"]=("V" if m=="visual" else "A")+f"{i:04}"
            for j,p in enumerate(e.get("phases",[]),1):
                p["id"]=e["id"]+f".P{j:02}"
    return out,overflow

def intersections(visual,audio):
    # Left-closed/right-open intervals. Keep boundary-sensitive and unresolved edges visible in review.
    edges=[]
    pending=0
    active=[]
    for v in sorted(visual,key=lambda r:r["start"]):
        while pending<len(audio) and audio[pending]["start"]<v["end"]:
            active.append(audio[pending])
            pending+=1
        active=[a for a in active if a["end"]>v["start"]]
        for a in active:
            lo,hi=max(v["start"],a["start"]),min(v["end"],a["end"])
            if lo>=hi:
                continue
            flags=set(v.get("review_flags",[])) | set(a.get("review_flags",[]))
            if hi-lo<.2-1e-8:
                flags.add("交叠不足0.2秒")
            edges.append({"visual":v["id"],"audio":a["id"],"intersection":[lo,hi],"review_flags":sorted(flags)})
    return edges

def save_caption(root,table):
    table["edges"]=intersections(table["visual"],table["audio"])
    phases=[{**p,"review_flags":v["review_flags"]} for v in table["visual"] for p in v.get("phases",[])]
    table["phase_edges"]=intersections(phases,table["audio"])
    write_json(root/"caption.json",table)
    text=[]
    for m,title in (("visual","视觉动作和状态"),("audio","语音和声音")):
        text.append(title)
        for e in table[m]:
            tag="【"+"；".join(e["review_flags"])+"】" if e["review_flags"] else ""
            text.append(f'{e["id"]}  {e["start"]:.2f}–{e["end"]:.2f} s  {e["actor"]}  {e.get("label",e["kind"])} {tag}')
            if m=="visual":
                text.extend([e["brief"],e["detail"]])
                text.extend(f'  {p["start"]:.2f}–{p["end"]:.2f} s  {p["label"]}' for p in e.get("phases",[]))
            else:
                text.append(e["text"])
                if e.get("timing_evidence"):
                    text.append("  定时依据："+("Qwen 复听与独立词时标" if e["timing_evidence"]["method"]=="qwen_and_asr" else "Qwen 局部复听"))
                elif e.get("source_status"):
                    text.append("  "+e["source_status"])
        text.append("")
    text.append("同一时段的动作和声音")
    lookup={e["id"]:e for e in table["audio"]+table["visual"]}
    for edge in table["edges"]:
        v,a=lookup[edge["visual"]],lookup[edge["audio"]]
        lo,hi=edge["intersection"]
        flag=" 【"+"；".join(edge["review_flags"])+"】" if edge["review_flags"] else ""
        text.append(f'{lo:.2f}–{hi:.2f} s  {v["id"]} {v["label"]} × {a["id"]} {a["text"]}{flag}')
    if table.get("unlocalized_speech"):
        text.append("\n待核的语音候选")
        text.extend(f'{e["candidate"]} · {e["reason"]}' for e in table["unlocalized_speech"])
    tmp=root/"审阅.txt.tmp"
    tmp.write_text("\n".join(text)+"\n",encoding="utf8")
    tmp.replace(root/"审阅.txt")

def assemble(root,src,audio,manifest,records,ask,media,prompt,words,jobs):
    windows=manifest["windows"]
    decisions=[]
    for i,(left,right) in enumerate(zip(windows,windows[1:])):
        cut=right["core"][0]
        span=[right["span"][0],left["span"][1]]
        pairs=seam_review(root/f"seam{i:05d}",cut,span,records[i],records[i+1],src,audio,ask,media,prompt)
        decisions.append(pairs)
    write_json(root/"seams.json",decisions)
    table,halo=stitch(windows,records,decisions,manifest["duration"])
    write_json(root/"context_only.json",halo)
    if audio:
        from .long_clauses import align
        table["audio"],table["unlocalized_speech"]=align(root,audio,table["audio"],windows,words,jobs)
    table.update(duration=manifest["duration"],source_sha256=manifest["source_sha256"],status="model_preannotation")
    save_caption(root,table)
    from .long_review_page import render
    render(root,src,table)
