"""Recheck caption evidence with native silent video plus timestamped unaltered stills."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import getpass
import os
from pathlib import Path
import subprocess

import av
from motion_tracks import images, sample, describe_request, execute, file_hash, read_json, write_json, pipeline
from motion_windows import facts
from sports_annotation.media import ffmpeg_path

PROMPT=Path(__file__).resolve().parent/"unified_prompts/native_motion_v6.txt"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("prior","media-run","clips","output"): p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--workers",type=int,default=5)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    if args.output.resolve() in (args.prior.resolve(),args.media_run.resolve()): p.error("Use a fresh output root")
    provider=read_json(pipeline.PACKAGE/"runs/badminton_bwf_hierarchical_20261125_v01/protocol.json")["config"]["provider"]
    key=os.environ.get(provider["api_key_env"]) or getpass.getpass("Qwen key: ")
    template=PROMPT.read_text("utf8")

    def review(t,media,manifest,video,out):
        shot=next(s for s in manifest["shots"] if s["id"]==t["shot_id"])
        frames=sample([f for f in manifest["frames"] if f["shot_id"]==shot["id"]],8)
        refs=[video]+images(media,frames)
        prompt=template+f"\nInterval {shot['start']:g}–{shot['end']:g} s. Subject identification: "+t["identity"]
        desc=describe_request("native_motion",prompt,refs,provider,{"source_sha256":manifest["source_sha256"],"shot_id":shot["id"],"actor_id":t["actor_id"]})
        stage=out/"stages"/(t["actor_id"] or shot["id"]+"-scene")/"native_motion"
        return facts(execute(stage,desc,prompt,refs,provider,lambda:key,facts))

    pending={};cases={}
    with ThreadPoolExecutor(args.workers) as pool:
        for path in (args.prior/"cases").glob("*/annotations.json"):
            if args.case_id and path.parent.name!=args.case_id: continue
            a=read_json(path);cid=path.parent.name;cases[cid]=a
            media=args.media_run/"cases"/cid/"media";m=read_json(media/"manifest.json")
            orig=args.clips/cid/"clip.mp4";out=args.output/"cases"/cid
            if file_hash(orig)!=m["source_sha256"] or a["source"]["clip_sha256"]!=m["source_sha256"]: raise ValueError("Media changed")
            out.mkdir(parents=True,exist_ok=True)
            if m["audio"]["present"]:
                silent=out/"silent.mp4"
                subprocess.run([ffmpeg_path(),"-nostdin","-loglevel","error","-y","-i",str(orig),"-map","0:v:0","-an","-c:v","copy",str(silent)],check=True)
            else: silent=orig
            with av.open(str(silent)) as cont:
                if len(cont.streams.audio) or len(cont.streams.video)!=1: raise ValueError("Expected exactly one silent video stream")
            video={"kind":"video","path":str(silent),"sha256":file_hash(silent),"fps":10}
            for i,t in enumerate(a["visual"]["motion_tracks"]):
                pending[pool.submit(review,t,media,m,video,out)]=(cid,i)
        if not pending: raise ValueError("No input tracks")
        errors=[]
        for job in as_completed(pending):
            cid,i=pending[job]
            try: cases[cid]["visual"]["motion_tracks"][i]["native_facts"]=job.result();print(cid,i,"done",flush=True)
            except Exception as exc: errors.append((cid,i,str(exc)[:400]));print(errors[-1],flush=True)
        if errors: raise RuntimeError(str(errors))
    for cid,a in cases.items():
        a["visual_refinement"]["native_prompt_sha256"]=file_hash(PROMPT)
        write_json(args.output/"cases"/cid/"annotations.json",a)


if __name__=="__main__":
    main()
