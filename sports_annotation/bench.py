"""English event references for the audiovisual caption benchmark."""
import argparse
import json
import re
from bisect import bisect_left
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av
from .hierarchical_experiment import runtime_lexicon
from .io_utils import file_hash, read_json, write_json
from .client import describe_request
from .long_video import CFG, PROMPTS, ask as ask_stage, events, media, run_lock, windows
from .long_words import recognize
from .media import ffmpeg_path, run_ffmpeg

TEMPLATES = PROMPTS / "bench"
KINDS = {"motion", "gesture", "state", "visible_speech"}
POSTURES = {"standing", "seated", "moving", "lying", "unclear"}

def ask(folder,stage,text,refs,validator):
    existing=folder/stage/"attempt1/request.json"
    if existing.exists():
        signature=describe_request(stage,text,refs,CFG,{"attempt":1})["signature"]
        if read_json(existing)["signature"]!=signature:
            folder=folder/"revisions"/signature[:20]
    return ask_stage(folder,stage,text,refs,validator)

def template(name):
    return (TEMPLATES / (name+".txt")).read_text("utf8")

def english(value):
    return isinstance(value,str) and bool(re.search(r"[A-Za-z]",value)) and not re.search(r"[\u3400-\u9fff]",value)

def visual_events(obj, length, cast, *, strict=False):
    roster={p["id"]:p["appearance"] for p in cast}
    rows=obj.get("events") if isinstance(obj,dict) else obj
    if not isinstance(rows,list):
        raise ValueError("Provide an events array.")
    def clock(raw):
        e=raw.copy()
        for field in ("start","end"):
            if field not in e and field+"_time" in e:
                e[field]=e.pop(field+"_time")
        return e
    normalized=[]
    for item in rows:
        e=clock(item)
        if not e.get("actor_id") or e["actor_id"] not in roster:
            desc=str(e.get("actor") or "")
            ids=set(re.findall(r"\bP[1-3]\b",desc+" "+str(e.get("label",""))))
            ids.update(k for k,s in roster.items() if s.lower() in desc.lower())
            e["actor_id"]=next(iter(ids)) if len(ids)==1 and ids.issubset(roster) else "unknown"
        if not isinstance(e.get("actor"),str) or not e["actor"].strip():
            e["actor"]=roster.get(e.get("actor_id"),"unidentified participant")
        if not e.get("activity"):
            e["activity"]="On-camera communication" if e.get("kind") in ("gesture","visible_speech") else "Physical activity"
        if not strict and not e.get("brief") and e.get("label"):
            e["brief"]=e["label"]
        if e.get("kind")=="visible_speech" and not strict:
            if e.get("posture") not in POSTURES:
                e["posture"]="unclear"
            if isinstance(e.get("evidence"),list):
                e["evidence"]="; ".join(str(x) for x in e["evidence"] if isinstance(x,str))
            if not e.get("evidence"):
                e["evidence"]="No separate facial evidence supplied in this proposal."
            if e.get("label") in roster or not e.get("label"):
                e["label"]="Speak on camera"
        phases=[clock(p) for p in e.get("phases",[]) or [] if isinstance(p,dict)]
        e["phases"]=[p for p in phases if p.get("label") and "start" in p and "end" in p]
        if len(e["phases"])!=len(item.get("phases",[]) or []):
            e["phase_note"]="Incomplete phase data withheld"
        normalized.append(e)
    result=events(normalized,"visual",length,communication=True)
    for row in result:
        for key in ("activity","actor","label","brief","detail"):
            if not english(row.get(key)):
                raise ValueError(f"Provide {key} in English for every visual event.")
        if row.get("actor_id") not in {p["id"] for p in cast}|{"unknown"}:
            raise ValueError("Use an actor_id from the roster or unknown.")
        if any(not english(p["label"]) for p in row["phases"]):
            raise ValueError("Write phase labels in English.")
        if row["kind"]=="visible_speech" and (row.get("posture") not in POSTURES or not english(row.get("evidence"))):
            raise ValueError("Visible speech requires posture and English facial evidence.")
    return result

def audio_events(obj, length):
    raw=obj.get("events") if isinstance(obj,dict) else obj
    if not isinstance(raw,list):
        raise ValueError("Provide an events array.")
    prepared=[]
    for v in raw:
        e=v.copy()
        for key,alias in (("actor","speaker"),("kind","type"),("start","start_time"),("end","end_time"),("text","transcript")):
            if key not in e and alias in e:
                e[key]=e[alias]
        if not e.get("actor"):
            e["actor"]="unidentified voice" if e.get("kind")=="speech" else "unidentified source"
        e.setdefault("label",e.get("kind"))
        if not e.get("text") and e.get("kind") in ("music","sound","ambience"):
            e["text"]=e["label"] or e["kind"]
        prepared.append(e)
    rows=events(prepared,"audio",length)
    for e in rows:
        if not english(e["actor"]) or not english(e.get("label")) or (e["kind"]!="speech" and not english(e["text"])):
            raise ValueError("Use English for audio descriptors. Only verbatim speech uses the original language.")
    return rows

def roster_prompt(cast):
    return "\nFor every row include actor_id. Roster: "+json.dumps(cast,ensure_ascii=False)+". Use unknown when identity is ambiguous; still give an English visual descriptor."

def lexicon_terms(path):
    if not path:
        return ""
    lex=read_json(path)
    if "movement_terms" in lex:
        lex=runtime_lexicon(lex)
    terms=[t.get("official_en") or t["label"].replace("_"," ") for t in lex["terms"]]
    return "\nOptional domain terms, only when visibly supported: "+", ".join(terms)

def on_source_clock(rows,lo,window,mode):
    result=[]
    for n,row in enumerate(rows):
        e={**row,"phases":[p.copy() for p in row.get("phases",[])]} if mode=="visual" else row.copy()
        e["origin"]=f"{window}/{mode}/{n}"
        for t in [e,*e.get("phases",[])]:
            t["start"]=round(lo+t["start"],4)
            t["end"]=round(lo+t["end"],4)
        result.append(e)
    return result

def draft_window(w,root,refs,cast,terms):
    n=w["n"]
    folder=root/f"w{n:05}"
    lo,hi=w["span"]
    clock=f"\nExcerpt duration {hi-lo:.4f} seconds; timestamps start at zero."
    v,a=refs
    data=template("visual")+roster_prompt(cast)+terms+clock
    vc=lambda obj:visual_events(obj,hi-lo,cast)
    ac=lambda obj:audio_events(obj,hi-lo)
    proposal=ask(folder,"muted",data,v,vc)
    sounds=ask(folder,"listen",template("audio")+clock,a,ac) if a else {"events":[]}
    review=ask(folder,"joint",data+"\n"+template("review")+"\nCandidates: "+json.dumps(vc(proposal),ensure_ascii=False),v+a,vc)
    out={"visual":on_source_clock(vc(review),lo,folder.name,"visual"),
         "audio":on_source_clock(ac(sounds),lo,folder.name,"audio")}
    write_json(folder/"draft.json",out)
    return out

def bind(path,manifest):
    if path.exists() and read_json(path)!=manifest:
        raise ValueError(f"Inputs or protocol changed at {path}. Select a different output directory.")
    write_json(path,manifest)

def run(args):
    src,root=args.video.resolve(),args.out.resolve()
    root.mkdir(parents=True,exist_ok=True)
    with run_lock(root):
        with av.open(str(src)) as c:
            if not c.streams.video or not c.duration:
                raise ValueError("A finite video stream is required.")
            duration=c.duration/1e6
            has_audio=bool(c.streams.audio)
        win=list(windows(duration,15,3))
        protocol={"schema":"av-events/1.0","source_sha256":file_hash(src),"duration":duration,"windows":win,
                  "model":CFG["model"],"lexicon_sha256":file_hash(args.lexicon) if args.lexicon else None,
                  "draft_prompt_sha256":{n:file_hash(TEMPLATES/(n+".txt")) for n in ("cast","visual","review","audio")}}
        bind(root/"manifest.json",protocol)
        wav=None
        if has_audio:
            wav=root/"full.wav"
            if not wav.exists():
                tmp=root/"full.part.wav"
                run_ffmpeg(ffmpeg_path(),"-v","error","-copyts","-start_at_zero","-i",src,"-map","0:a:0","-vn",
                           "-af","aresample=16000:async=1:first_pts=0","-ac","1","-ar","16000","-c:a","pcm_s16le","-y",tmp)
                tmp.replace(wav)
        refs=[media(root/f"w{w['n']:05}"/"media",src,wav,*w["span"]) for w in win]
        anchors=[]
        for w,(v,_) in zip(win,refs):
            for frame in v[1:]:
                t=round(w["span"][0]+frame["time"],4)
                if w["core"][0]<=t<w["core"][1]:
                    anchors.append({**frame,"time":t,"index":len(anchors),"shot_id":"source"})
        count=min(len(anchors),32)
        picked=[anchors[round(i*(len(anchors)-1)/max(count-1,1))] for i in range(count)]
        def cast_check(obj):
            people=obj.get("people")
            if not isinstance(people,list) or len(people)>3 or any(p.get("id")!=f"P{i}" or not english(p.get("appearance")) for i,p in enumerate(people,1)):
                raise ValueError("Use ordered IDs P1, P2, P3 and an English appearance. Report at most three main people.")
        cast=ask(root,"cast",template("cast"),picked,cast_check)["people"]
        terms=lexicon_terms(args.lexicon)
        with ThreadPoolExecutor(args.jobs) as ex:
            records=list(ex.map(lambda w:draft_window(w,root,refs[w["n"]],cast,terms),win))
        if args.proposal_only:
            return
        from .bench_reference import finalize
        words=recognize(wav,args.vosk_model,root/"words.json") if args.vosk_model and wav else []
        finalize(root,src,wav,win,records,cast,terms,protocol,words,args.jobs)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("video",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--lexicon",type=Path)
    p.add_argument("--vosk-model",type=Path)
    p.add_argument("--jobs",type=int,default=4)
    p.add_argument("--proposal-only",action="store_true",help="Save the first pass before verification.")
    args=p.parse_args(argv)
    if args.jobs<1:
        p.error("--jobs must be positive")
    run(args)

if __name__=="__main__":
    main()
