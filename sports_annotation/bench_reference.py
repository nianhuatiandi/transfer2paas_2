"""Produce shot-audited English events and a machine-reviewed reference subset."""
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .bench import TEMPLATES, ask, bind, english, file_hash, media, on_source_clock, roster_prompt, template, visual_events
from .io_utils import read_json, write_json
from .long_clauses import align
from .long_timeline import seam_review, stitch
from .media import ffmpeg_path, run_ffmpeg

def shot_scopes(src,duration):
    log=run_ffmpeg(ffmpeg_path(),"-v","info","-i",src,"-an","-vf",
        "scale=320:-2,select='gt(scene,0.12)',showinfo","-vsync","vfr","-f","null","-")
    cuts=[0.]
    for hit in re.findall(r"pts_time:([-0-9.e+]+)",log):
        t=float(hit)
        if t-cuts[-1]>=.25 and duration-t>=.25:
            cuts.append(t)
    cuts.append(duration)
    scopes=[]
    for lo,hi in zip(cuts,cuts[1:]):
        count=max(1,math.ceil((hi-lo)/12))
        for i in range(count):
            a,b=lo+i*(hi-lo)/count,lo+(i+1)*(hi-lo)/count
            scopes.append({"n":len(scopes),"core":[round(a,5),round(b,5)],
                           "span":[round(max(0,a-.7),5),round(min(duration,b+.7),5)]})
    return scopes

def agreement(a,b):
    if a["kind"]!=b["kind"] or a["actor_id"]!=b["actor_id"]:
        return False
    inter=min(a["end"],b["end"])-max(a["start"],b["start"])
    return inter>=.4*min(a["end"]-a["start"],b["end"]-b["start"])

def inspect(scope,root,src,wav,drafts,cast,terms):
    n=scope["n"]
    folder=root/f"shot{n:05}"
    lo,hi=scope["span"]
    length=hi-lo
    v,a=media(folder/"media",src,wav,lo,hi)
    clock=f"\nExcerpt length {length:.4f} seconds; zero is the first frame. "
    roster=roster_prompt(cast)
    def check_speakers(obj):
        rows=visual_events(obj,length,cast)
        for row in rows:
            if row["kind"]!="visible_speech":
                raise ValueError("Only include visible_speech in this pass.")
        if not isinstance(obj.get("uncertain",[]),list):
            raise ValueError("uncertain must be an array")
    screen=ask(folder,"face",template("speaker_check")+clock+roster,v,check_speakers)
    speech=visual_events(screen,length,cast)
    proposals=[]
    for e in drafts:
        overlap=min(hi,e["end"])-max(lo,e["start"])
        if overlap<=0:
            continue
        proposals.append({**{k:e[k] for k in ("actor_id","kind","label","brief","detail")},
                          "start":round(max(lo,e["start"])-lo,3),"end":round(min(hi,e["end"])-lo,3)})
    msg=(template("inspect")+clock+roster+terms+"\nWindow proposals, some may be too broad: "+
         json.dumps(proposals,ensure_ascii=False)+"\nIndependent muted-face observations: "+json.dumps(speech,ensure_ascii=False))
    vc=lambda obj:visual_events(obj,length,cast)
    decision=ask(folder,"inspect",msg,v+a,vc)
    local=vc(decision)
    for e in local:
        flags=[]
        if e["kind"]=="visible_speech":
            matched=[r for r in speech if agreement(r,e)]
            if not matched:
                flags.append("Visible speaker not corroborated in the muted face pass")
            elif not english(matched[0].get("evidence")) or "No separate facial evidence" in matched[0]["evidence"]:
                flags.append("Independent face cue was not described")
            if e["evidence"].startswith("No separate facial evidence"):
                if matched and not flags:
                    e["evidence"]=matched[0]["evidence"]
                else:
                    flags.append("Facial evidence missing")
            if matched and e["posture"]=="unclear" and matched[0].get("posture")!="unclear":
                e["posture"]=matched[0]["posture"]
        if e.get("certainty")=="uncertain":
            flags.append("Uncertain in local audiovisual review")
        if e["actor_id"]=="unknown":
            flags.append("Actor identity unresolved")
        if e["kind"]!="state" and len(e["detail"].split())<5:
            flags.append("Insufficient observable detail")
        if e["brief"]==e["label"]:
            e["brief"]=e["detail"].split(". ")[0].rstrip(".")+"."
        e["quality_notes"]=flags
    for r in speech:
        if not any(agreement(r,e) for e in local):
            local.append({**r,"quality_notes":["Muted face observation not corroborated in joint review"]})
    out={"visual":on_source_clock(local,lo,folder.name,"visual"),"audio":[]}
    write_json(folder/"audit.json",{"scope":scope,"muted_visible_speech":speech,"observations":out["visual"],
               "uncertain_muted_local":screen.get("uncertain",[]),"uncertain_joint_local":decision.get("uncertain",[])})
    return out

def stitch_modality(root,src,wav,scopes,records,kind):
    subset=[{"visual":row["visual"] if kind=="visual" else [],"audio":row["audio"] if kind=="audio" else []} for row in records]
    def one(i):
        left,right=scopes[i:i+2]
        return seam_review(root/f"{kind}_seam{i:05}",right["core"][0],[right["span"][0],left["span"][1]],subset[i],subset[i+1],src,wav,ask,media,template,english=True)
    with ThreadPoolExecutor(3) as pool:
        seams=list(pool.map(one,range(len(scopes)-1)))
    write_json(root/f"{kind}_seams.json",seams)
    table,halo=stitch(scopes,subset,seams,scopes[-1]["core"][1],prefer_core_bounds=True)
    by_id={e["origin"]:e for record in subset for e in record[kind]}
    for e in table[kind]:
        flags=set(e["review_flags"])
        for k in e["sources"]:
            flags.update(by_id[k].get("quality_notes",[]))
        e["review_flags"]=sorted(flags)
    write_json(root/f"{kind}_context_only.json",halo)
    return table[kind]

def finalize(root,src,wav,win,records,cast,terms,protocol,words,jobs):
    scopes=shot_scopes(src,protocol["duration"])
    manifest={"draft":protocol,"scopes":scopes,"templates":{p.name:file_hash(p) for p in sorted(TEMPLATES.glob("*.txt"))}}
    bind(root/"reference_protocol.json",manifest)
    drafts=[e for r in records for e in r["visual"]]
    with ThreadPoolExecutor(jobs) as ex:
        inspected=list(ex.map(lambda scope:inspect(scope,root,src,wav,drafts,cast,terms),scopes))
    visual=stitch_modality(root,src,wav,scopes,inspected,"visual")
    sound=stitch_modality(root,src,wav,win,records,"audio")
    audio,missing=align(root,wav,sound,win,words,jobs,english=True,request=ask) if wav else ([],[])
    from .bench_export import save
    save(root,src,protocol,cast,visual,audio,missing)
