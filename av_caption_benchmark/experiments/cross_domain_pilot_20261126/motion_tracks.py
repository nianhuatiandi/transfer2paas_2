"""Refine any completed unified annotation by rereading its frames per shot and actor."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
import getpass
import json
import os
from pathlib import Path

import unified_pipeline as pipeline
from sports_annotation.bwf_model_comparison import images
from sports_annotation.client import describe_request, execute as execute_stage
from sports_annotation.io_utils import file_hash, read_json, write_json, parse_model_json

HERE = Path(__file__).resolve().parent
DEFAULT_PROMPT = HERE / "unified_prompts/motion_tracks_v2.txt"


def execute(stage,desc,prompt,refs,provider,key,validator):
    """Retry transport faults using the same request body with a distinct checkpoint."""
    def network_failure(err):
        return any(x in str(err).lower() for x in ("connection","ssl","timed out","timeout","http 429","http 502","http 503","http 504","reset by peer"))
    attempt=stage/"transport_retry"
    previous=read_json(stage/"metadata.json") if (stage/"metadata.json").exists() else {}
    error=previous.get("error","") if previous.get("status")=="failed" else ""
    if not (network_failure(error) or "degenerate response" in error.lower()):
        try:return execute_stage(stage,desc,prompt,refs,provider,key,validator)
        except RuntimeError as exc:
            error=str(exc)
            if not network_failure(error) and "degenerate response" not in error.lower():raise
    if "degenerate response" in error.lower():
        clean=prompt+"\nSerialization retry: write compact JSON. Keep each descriptive string to one or two sentences. Stop when the requested observations are complete."
        d=describe_request(desc["stage"],clean,refs,provider,{**desc["provenance"],"format_retry_of":desc["signature"]})
        return execute_stage(stage/"format_retry",d,clean,refs,provider,key,validator)
    wire={**provider,"transport":"curl"}
    desc2=describe_request(desc["stage"],prompt,refs,wire,{**desc["provenance"],"transport_retry_of":desc["signature"]})
    return execute_stage(attempt,desc2,prompt,refs,wire,key,validator)


def sample(frames, limit):
    if len(frames) <= limit:
        return frames
    return [frames[round(i * (len(frames)-1) / (limit-1))] for i in range(limit)]


def validate(output, indices):
    for name in ("context","camera"):
        if not isinstance(output.get(name), str) or not output[name].strip():
            raise ValueError("Missing caption field: "+name)
    if not isinstance(output.get("phases"),list) or not output["phases"]:
        raise ValueError("Missing phase descriptions")
    for phase in output["phases"]:
        lo, hi = phase["from_frame"], phase["to_frame"]
        if lo not in indices or hi not in indices or lo>hi or not phase["caption"].strip():
            raise ValueError("Use supplied frame numbers for a visible phase")


def refine(directory, output, prompt_file, provider, key, frame_limit):
    ann=read_json(directory/"annotations.json")
    media=directory/"media"
    manifest=read_json(media/"manifest.json")
    if manifest["source_sha256"]!=ann["source"]["clip_sha256"]:
        raise ValueError("Media and annotations differ")
    template=prompt_file.read_text("utf-8").strip()
    tracks=[]
    for shot in manifest["shots"]:
        frames=sample([f for f in manifest["frames"] if f["shot_id"]==shot["id"]],frame_limit)
        if not frames:
            continue
        times={f["index"]:f["time"] for f in frames}
        actors=[a for a in ann["visual"]["actors"] if a["shot_id"]==shot["id"]]
        for actor in actors or [{"id":None,"description":"可见的主要物体及环境变化"}]:
            prompt=template+"\n追踪对象（上一阶段生成的辨认线索）："+actor["description"]
            refs=images(media,frames)
            provenance={"source_sha256":manifest["source_sha256"],"shot_id":shot["id"],
                        "actor_id":actor["id"],"prompt_file_sha256":file_hash(prompt_file)}
            desc=describe_request("motion_track",prompt,refs,provider,provenance)
            stage=output/"stages"/(actor["id"] or (shot["id"]+"-scene"))
            print(directory.name,stage.name,flush=True)
            def normalize(raw):
                result=deepcopy(raw)
                if len(times)==1 and any((s.get("from_frame") not in times or s.get("to_frame") not in times) for s in result.get("phases",[])):
                    frame=next(iter(times))
                    result["phases"]=[{"from_frame":frame,"to_frame":frame,"caption":result["context"]}]
                    result["camera"]="单帧，仅能观察当前构图。"
                    result["single_frame_fallback"]=True
                for phase in result.get("phases",[]):
                    lo,hi=phase["from_frame"],phase["to_frame"]
                    if isinstance(lo,int) and isinstance(hi,int) and min(times)<=lo<=hi<=max(times) and (lo not in times or hi not in times):
                        phase["reported_frame_range"]=[lo,hi]
                        phase["from_frame"]=max(i for i in times if i<=lo)
                        phase["to_frame"]=min(i for i in times if i>=hi)
                validate(result,times)
                return result
            raw=None
            if (stage/"metadata.json").exists() and (stage/"response.txt").exists():
                meta=read_json(stage/"metadata.json")
                if meta.get("signature")==desc["signature"] and meta.get("status")=="failed" and meta.get("finish_reason")=="stop":
                    try: raw=normalize(parse_model_json((stage/"response.txt").read_text("utf8")))
                    except (ValueError,TypeError,KeyError,AttributeError): pass
                    if raw: write_json(stage/"validated.json",raw)
            if raw is None: raw=normalize(execute(stage,desc,prompt,refs,provider,lambda:key,normalize))
            track=deepcopy(raw)
            track.update(actor_id=actor["id"],shot_id=shot["id"],identity=actor["description"])
            for phase in track["phases"]:
                lo,hi=phase["from_frame"],phase["to_frame"]
                phase["start"],phase["end"]=times[lo],times[hi]
                phase["action_ids"]=[a["id"] for a in ann["visual"]["actions"]
                                     if a["actor_id"]==actor["id"] and a["shot_id"]==shot["id"]
                                     and a["start"]<=times[hi] and a["end"]>=times[lo]]
            tracks.append(track)
    ann["visual"]["motion_tracks"]=tracks
    ann["visual_refinement"]={"template_sha256":file_hash(prompt_file),"base_annotation_sha256":file_hash(directory/"annotations.json"),
                              "model":provider["model"],"max_frames_per_shot":frame_limit}
    write_json(output/"annotations.json",ann)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True,help="Unified output containing cases/*/annotations.json and prepared media")
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--prompt",type=Path,default=DEFAULT_PROMPT)
    p.add_argument("--frames",type=int,default=32)
    p.add_argument("--workers",type=int,default=4)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    if args.frames<2 or args.output.resolve()==args.source.resolve():
        p.error("Use at least two frames and a separate output directory.")
    paths=sorted((args.source/"cases").glob("*/annotations.json"))
    if args.case_id: paths=[p for p in paths if p.parent.name==args.case_id]
    if not paths:
        p.error("No input annotations found")
    config=read_json(pipeline.PACKAGE/"runs/badminton_bwf_hierarchical_20261125_v01/protocol.json")["config"]
    provider=config["provider"]
    key=os.environ.get(provider["api_key_env"]) or getpass.getpass("Qwen key: ")
    with ThreadPoolExecutor(args.workers) as pool:
        jobs={pool.submit(refine,f.parent,args.output/"cases"/f.parent.name,args.prompt,provider,key,args.frames):f.parent.name for f in paths}
        errors=[]
        for job in as_completed(jobs):
            try: job.result()
            except Exception as e: errors.append((jobs[job],str(e)))
        if errors: raise RuntimeError(str(errors))


if __name__=="__main__":
    main()
