"""Windowed audiovisual captioning. Run python -m sports_annotation.long_video --help."""
import argparse
import getpass
import json
import math
import os
import re
import shutil
import wave
from itertools import count
from contextlib import contextmanager
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av
from .client import describe_request, execute
from .hierarchical_experiment import runtime_lexicon
from .io_utils import file_hash, read_json, write_json, parse_model_json
from .media import ffmpeg_path, run_ffmpeg

PACKAGE = Path(__file__).resolve().parent
PROMPTS = PACKAGE / "prompts"
CFG = read_json(PACKAGE / "config/five_videos_live_compact.json")["provider"]
CFG = {**CFG, "max_tokens":6000, "max_validation_repairs":0,
       "extra_body":{**CFG["extra_body"], "temperature":0.15}}
KEY_LOCK=Lock()

def credential():
    with KEY_LOCK:
        if not os.getenv("QWEN_API_KEY"):
            os.environ["QWEN_API_KEY"]=getpass.getpass("Qwen credential: ")
        return os.environ["QWEN_API_KEY"]

def prompt(name):
    return (PROMPTS / f"long_{name}.txt").read_text("utf8")

def ask(folder, stage, text, refs, validator):
    prior = ""
    fresh=0
    for attempt in count():
        dest = folder / stage / f"attempt{attempt+1}"
        retry = "\nReturn the complete JSON again. Fix this validation error: " if text[0].isascii() else "\n上次未通过格式检查，请重新看片或听音，以相同任务输出完整 JSON。具体问题："
        msg = text if not prior else text + retry + prior
        cfg=CFG
        previous_request=dest/"request.json"
        if previous_request.exists():
            if read_json(previous_request).get("inference",{}).get("transport")=="curl":
                cfg={**CFG,"transport":"curl"}
        elif any(s in prior for s in ("SSLError","ProxyError","ConnectionReset","Connection aborted","ConnectTimeout")) and shutil.which("curl.exe"):
            cfg={**CFG,"transport":"curl"}
        desc = describe_request(stage, msg, refs, cfg, {"attempt":attempt+1})
        meta = dest / "metadata.json"
        if meta.exists():
            old = read_json(meta)
            if old["signature"] != desc["signature"]:
                raise ValueError("Stage inputs changed. Choose a fresh output directory: " + str(dest))
            if old["status"] == "failed":
                raw=dest/"response.txt"
                if old.get("finish_reason")=="stop" and raw.exists():
                    try:
                        recovered=parse_model_json(raw.read_text("utf8"))
                        validator(recovered)
                    except (ValueError,TypeError,KeyError,AttributeError,AssertionError):
                        pass
                    else:
                        write_json(dest/"recovered.json",recovered)
                        return recovered
                prior = old.get("error","invalid")[:400]
                continue
        if fresh>=3:
            raise RuntimeError(f"{folder.name}/{stage}: {prior}")
        fresh+=1
        try:
            return execute(dest, desc, msg, refs, cfg, credential, validator)
        except RuntimeError as exc:
            prior = str(exc)[:400]
            if any(x in prior.lower() for x in ("http 401","http 403","quota","balance")):
                raise

def windows(duration, core, pad):
    for n in range(math.ceil(duration/core)):
        lo, hi = round(n*core, 6), min(duration,round((n+1)*core,6))
        yield {"n":n, "core":[lo,hi], "span":[max(0,lo-pad),min(duration,hi+pad)]}

def reference(kind, path, **fields):
    return dict(kind=kind, path=str(path), sha256=file_hash(path), **fields)

def wav_slice(src, target, low, high):
    with wave.open(str(src),"rb") as inp:
        rate = inp.getframerate()
        first, last = round(low*rate), round(high*rate)
        inp.setpos(min(first,inp.getnframes()))
        data = inp.readframes(last-first)
        with wave.open(str(target),"wb") as out:
            out.setparams(inp.getparams())
            out.writeframes(data.ljust((last-first)*inp.getsampwidth()*inp.getnchannels(), b"\0"))

def media(folder, source, audio, lo, hi):
    folder.mkdir(parents=True,exist_ok=True)
    v = folder/"silent.mp4"
    if not v.exists():
        tmp = folder/"silent.part.mp4"
        run_ffmpeg(ffmpeg_path(), "-v","error","-ss",f"{lo:.6f}","-i",source,"-t",f"{hi-lo:.6f}",
                   "-map","0:v:0","-an","-vf","fps=10,scale=w='min(768,iw)':h=-2",
                   "-c:v","libx264","-preset","veryfast","-crf","18","-y",tmp)
        tmp.replace(v)
    visual = [reference("video",v,fps=10)]
    with av.open(str(v)) as container:
        for frame in container.decode(video=0):
            time = float(frame.pts*frame.time_base)
            if round(10*time)%5:
                continue
            jpg = folder/f"f{round(10*time):06d}.jpg"
            if not jpg.exists():
                img = frame.to_image()
                img.thumbnail((640,420))
                img.save(jpg, quality=82)
            visual.append(reference("image",jpg,time=time,index=round(time*10),shot_id="window"))
    aud = []
    if audio is not None:
        wav = folder/"audio.wav"
        wav_slice(audio,wav,lo,hi)
        aud = [reference("audio",wav)]
    return visual, aud

def events(obj, mode, length, *, communication=False):
    rows = obj.get("events") if isinstance(obj,dict) else obj
    if not isinstance(rows,list):
        raise ValueError("events must be an array")
    kinds = ("motion","gesture","state") if mode=="visual" else ("speech","sound","music","ambience")
    if communication and mode=="visual":
        kinds+=("visible_speech",)
    result = []
    for i, e in enumerate(rows):
        if not isinstance(e,dict) or e.get("kind") not in kinds:
            raise ValueError(f"events[{i}].kind must be one of {kinds}")
        required = ("actor","label","brief","detail") if mode=="visual" else ("actor","text","layer")
        for k in required:
            if not isinstance(e.get(k),str) or not e[k].strip():
                raise ValueError(f"events[{i}].{k} must be a nonempty string")
        if mode=="audio" and e["layer"] not in ("foreground","background"):
            raise ValueError(f"events[{i}].layer must be foreground or background")
        a,b = float(e["start"]),float(e["end"])
        if not (-.1 <= a < b <= length+.15 and b>0 and a<length):
            raise ValueError(f"events[{i}] range must be within 0 to {length:.3f}")
        row = {**e,"start":max(0,a),"end":min(length,b)}
        if mode=="visual":
            phases=[]
            for p in e.get("phases",[]) or []:
                if not isinstance(p,dict) or not isinstance(p.get("label"),str):
                    raise ValueError(f"events[{i}].phases must contain labelled intervals")
                low, high = float(p["start"]),float(p["end"])
                if not a-.15 <= low < high <= b+.15 or min(row["end"],high)<=max(row["start"],low):
                    raise ValueError(f"events[{i}].phases must lie inside parent")
                phases.append(dict(label=p["label"],start=max(row["start"],low),end=min(row["end"],high)))
            row["phases"] = phases
        result.append(row)
    return result

def compound(e):
    return (e["kind"]=="speech" and (e["end"]-e["start"]>5.5 or
            len([s for s in re.split(r"[。！？!?；;]|(?<=\w)\.\s+",e["text"]) if s.strip()])>1))

def process_window(w, root, source, audio, terms):
    folder = root/f"w{w['n']:05d}"
    lo, hi = w["span"]
    length = hi-lo
    vis, aud = media(folder/"media",source,audio,lo,hi)
    clock = f"\n本窗口长 {length:.3f} 秒，窗口起点是零。"
    vp = prompt("visual")+clock+terms
    vcheck = lambda obj:events(obj,"visual",length)
    acheck = lambda obj:events(obj,"audio",length)
    v0 = ask(folder,"visual",vp,vis,vcheck)
    a0 = ask(folder,"audio",prompt("audio")+clock,aud,acheck) if aud else {"events":[]}
    ar = events(a0,"audio",length)
    revised = []
    for i,e in enumerate(ar):
        if not compound(e):
            revised.append(e)
            continue
        start, end = max(0,e["start"]-.35), min(length,e["end"]+.35)
        wav = folder/f"refine_{i}.wav"
        wav_slice(audio,wav,lo+start,lo+end)
        def check_ref(obj):
            rr=events(obj,"audio",end-start)
            if any(v["kind"]!="speech" for v in rr):
                raise ValueError("only return speech")
        obj=ask(folder,f"clause_{i}",prompt("audio")+prompt("audio_refine")+f"\n音频长度 {end-start:.3f} 秒，起点为零。",
                [reference("audio",wav)],check_ref)
        candidates=events(obj,"audio",end-start)
        if not candidates:
            revised.append({**e,"needs_review":"复听未定位"})
        owned=[s for s in candidates if e["start"] <= start+(s["start"]+s["end"])/2 <= e["end"]]
        if candidates and not owned:
            revised.append({**e,"needs_review":"复听范围未能对应"})
        for s in owned:
            revised.append({**s,"start":s["start"]+start,"end":s["end"]+start,
                            **({"needs_review":"分句边界未解"} if compound(s) else {})})
    review = ask(folder,"review",vp+"\n"+prompt("review")+"\n视觉候选："+json.dumps(events(v0,"visual",length),ensure_ascii=False),
                 vis+aud,vcheck)
    local = {"visual":events(review,"visual",length),"audio":revised}
    for m, rr in local.items():
        for i,e in enumerate(rr):
            e["origin"]=f"w{w['n']:05d}/{m}/{i}"
            for item in [e,*e.get("phases",[])]:
                for k in ("start","end"):
                    item[k]=round(item[k]+lo,3)
    write_json(folder/"window.json",dict(window=w,**local))
    print("window ready",w["n"],flush=True)
    return local

@contextmanager
def run_lock(root):
    # OS locks release on process exit, including crashes. Each run writes shared media and final tables.
    with (root/".run.lock").open("a+b") as handle:
        handle.seek(0,2)
        if not handle.tell():
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name=="nt":
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another process is writing this run directory: "+str(root)) from exc
        yield

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video",type=Path)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--lexicon",type=Path)
    parser.add_argument("--vosk-model",type=Path,help="optional installed Vosk model for the spoken language; corroborates clause boundaries")
    parser.add_argument("--core",type=float,default=15)
    parser.add_argument("--context",type=float,default=3)
    parser.add_argument("--jobs",type=int,default=4)
    args=parser.parse_args(argv)
    if not (0 < args.context < args.core/2 and args.jobs>0):
        parser.error("use 0 < context < core/2, and jobs >= 1")
    src, root = args.video.resolve(), args.out.resolve()
    root.mkdir(parents=True,exist_ok=True)
    with run_lock(root):
        run(args,src,root)

def run(args,src,root):
    with av.open(str(src)) as c:
        if not c.streams.video or not c.duration:
            raise ValueError("a finite video duration is required")
        duration=c.duration/1e6
        has_audio=bool(c.streams.audio)
    manifest=dict(source_sha256=file_hash(src),duration=duration,core=args.core,context=args.context,
                  lexicon_sha256=file_hash(args.lexicon) if args.lexicon else None,
                  prompt_sha256={p.name:file_hash(p) for p in sorted(PROMPTS.glob("long_*.txt"))},
                  windows=list(windows(duration,args.core,args.context)))
    manifest_path=root/"manifest.json"
    if manifest_path.exists() and read_json(manifest_path)!=manifest:
        raise ValueError("Run directory bound to different source or protocol")
    write_json(manifest_path,manifest)
    audio=None
    if has_audio:
        audio=root/"full.wav"
        if not audio.exists():
            tmp=root/"full.part.wav"
            run_ffmpeg(ffmpeg_path(),"-v","error","-copyts","-start_at_zero","-i",src,"-map","0:a:0","-vn",
                       "-af","aresample=16000:async=1:first_pts=0","-ac","1","-ar","16000","-c:a","pcm_s16le","-y",tmp)
            tmp.replace(audio)
    terms=""
    if args.lexicon:
        lex=read_json(args.lexicon)
        if "movement_terms" in lex:
            lex=runtime_lexicon(lex)
        terms="\n可选领域词，须有画面依据，也可用普通动词："+ "、".join(t.get("zh") or t["label"] for t in lex["terms"])
    with ThreadPoolExecutor(args.jobs) as pool:
        records=list(pool.map(lambda w:process_window(w,root,src,audio,terms),manifest["windows"]))
    from .long_timeline import assemble
    words=[]
    if args.vosk_model and audio:
        from .long_words import recognize
        words=recognize(audio,args.vosk_model,root/"words.json")
    assemble(root,src,audio,manifest,records,ask,media,prompt,words,args.jobs)
    print(root/"caption.json",flush=True)

if __name__=="__main__":
    main()
