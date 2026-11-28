"""Visually reconcile full-scene, body and interaction evidence in a unified annotation."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from functools import partial
import getpass
import json
import math
import os
from pathlib import Path

import av
from PIL import Image, ImageOps
from motion_tracks import sample, pipeline, describe_request, execute, file_hash, images, read_json, write_json
from sports_annotation.io_utils import parse_model_json

HERE=Path(__file__).resolve().parent
PROMPT=HERE/"unified_prompts/motion_inspection_v3.json"


def boxes_valid(result, indices):
    items=result["boxes"]
    if {x["frame"] for x in items}!=indices or len(items)!=len(indices):
        raise ValueError("Return one box for each exact input source frame")
    for x in items:
        left,top,right,bottom=x["xyxy"]
        if not(0<=left<right<=1000 and 0<=top<bottom<=1000):
            raise ValueError("Box must be in 0-1000 xyxy coordinates")


def facts_valid(result,indices):
    if not result["observations"]:
        raise ValueError("Missing observations")
    for x in result["observations"]:
        if x["from_frame"] not in indices or x["to_frame"] not in indices or x["to_frame"]<x["from_frame"] or not x["description"].strip():
            raise ValueError("Only use supplied source frame numbers and a non-empty observation")


def panels(original, frames, boxes, directory, shot_id):
    directory.mkdir(exist_ok=True,parents=True)
    byindex={f["index"]:f for f in frames}
    anchor=sorted((b["frame"],b["xyxy"]) for b in boxes)
    results=[]
    with av.open(str(original)) as media:
        for idx,frame in enumerate(media.decode(video=0)):
            if idx not in byindex: continue
            im=frame.to_image().convert("RGB")
            left=next((a for a in reversed(anchor) if a[0]<=idx),anchor[0])
            right=next((a for a in anchor if a[0]>=idx),anchor[-1])
            t=(idx-left[0])/(right[0]-left[0]) if right[0]>left[0] else 0
            x,y,r,b=[(a+(v-a)*t)/1000 for a,v in zip(left[1],right[1])]
            w,h=im.size
            dx=max(.025,(r-x)*.18);dy=max(.025,(b-y)*.18)
            crop=im.crop((max(0,math.floor((x-dx)*w)),max(0,math.floor((y-dy)*h)),min(w,math.ceil((r+dx)*w)),min(h,math.ceil((b+dy)*h))))
            views=[ImageOps.contain(z,(820,660),Image.Resampling.LANCZOS) for z in (im,crop)]
            sheet=Image.new("RGB",(sum(z.width for z in views)+8,max(z.height for z in views)),(32,32,32))
            sheet.paste(views[0],(0,0));sheet.paste(views[1],(views[0].width+8,0))
            path=directory/f"{idx:06d}.jpg"
            sheet.save(path,quality=89)
            results.append(dict(kind="image",path=str(path),index=idx,time=byindex[idx]["time"],shot_id=shot_id,sha256=file_hash(path)))
    if len(results)!=len(frames): raise ValueError("Source decode lost one or more anchored frames")
    return results


def inspect_actor(cid,track,ann,manifest,media,original,out,prior,provider,key,prompts):
    aid=track["actor_id"]
    shot=track["shot_id"]
    subs=[f for f in manifest["frames"] if f["shot_id"]==shot]
    frames=sample(subs,24)
    byindex={f["index"]:f["time"] for f in frames}
    root=out/"stages"/(aid or shot+"-scene")
    identity="\n目标外观线索："+track["identity"]
    prov={"source_sha256":manifest["source_sha256"],"shot_id":shot,"actor_id":aid}

    def call(name,prompt,refs,validator):
        desc=describe_request(name,prompt,refs,provider,prov)
        folder=root/name
        field="boxes" if name=="localize" else "observations"
        def unpack(obj):
            obj={field:obj} if isinstance(obj,list) else deepcopy(obj)
            if field=="boxes":
                rows={r.get("frame"):r for r in obj.get(field,[]) if isinstance(r,dict)}
                normalized=[]
                for f in refs:
                    row=rows.get(f["index"],{})
                    box=row.get("xyxy",row.get("bbox_2d"))
                    valid=(isinstance(box,list) and len(box)==4 and all(isinstance(v,(int,float)) for v in box)
                           and 0<=box[0]<box[2]<=1000 and 0<=box[1]<box[3]<=1000)
                    normalized.append({"frame":f["index"],"xyxy":box if valid else [0,0,1000,1000],
                                       **({} if valid else {"view":"full_frame_fallback"})})
                obj[field]=normalized
            if field=="observations":
                indices=sorted(byindex)
                for row in obj.get(field,[]):
                    lo,hi=row["from_frame"],row["to_frame"]
                    if isinstance(lo,int) and isinstance(hi,int) and indices[0]<=lo<=hi<=indices[-1] and (lo not in byindex or hi not in byindex):
                        # Retain the model's estimates; place reading bounds on enclosing observed frames.
                        row["reported_frame_range"]=[lo,hi]
                        row["from_frame"]=max(i for i in indices if i<=lo)
                        row["to_frame"]=min(i for i in indices if i>=hi)
            return obj
        # Accept a bare row array from a completed response without reissuing the request.
        if (folder/"response.txt").is_file() and (folder/"metadata.json").is_file():
            meta=read_json(folder/"metadata.json")
            if meta.get("signature")==desc["signature"] and meta.get("http_status")==200 and meta.get("finish_reason")=="stop":
                try:
                    obj=unpack(parse_model_json((folder/"response.txt").read_text("utf-8")))
                    validator(obj)
                except (ValueError,KeyError,TypeError): pass
                else:
                    write_json(folder/"validated.json",obj)
                    return obj
        raw=execute(folder,desc,prompt,refs,provider,lambda:key,lambda obj:validator(unpack(obj)))
        return unpack(raw)

    loc=sample(frames,5)
    boxes=call("localize",prompts["localize"]+identity,images(media,loc),partial(boxes_valid,indices={f["index"] for f in loc}))["boxes"]
    zoom=panels(original,frames,boxes,root/"paired_frames",shot)
    plain=images(media,frames)
    notes=[{"brief":a["brief"],"detail":a["detail"],"phases":a["subphases"],"evidence":a["evidence"]}
           for a in ann["visual"]["actions"] if a["actor_id"]==aid and a["shot_id"]==shot]
    draft="\n旧笔记（可能有误）："+json.dumps([notes,prior],ensure_ascii=False,separators=(",",":"))
    result={}
    for facet in ("pose","contact","camera"):
        refs=plain if facet=="camera" else zoom
        prompt="\n".join((prompts["common"],prompts[facet],identity,draft))
        obs=call(facet,prompt,refs,partial(facts_valid,indices=set(byindex)))["observations"]
        for x in obs:
            x["start"],x["end"]=byindex[x["from_frame"]],byindex[x["to_frame"]]
            x["action_ids"]=[a["id"] for a in ann["visual"]["actions"] if a["shot_id"]==shot and a["actor_id"]==aid
                             and a["start"]<=x["end"] and a["end"]>=x["start"]]
        result[facet]=obs
    return cid,{**track,"inspections":result}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ("media-run","track-run","clips","output"):
        p.add_argument("--"+k,type=Path,required=True)
    p.add_argument("--workers",type=int,default=5)
    p.add_argument("--prompt",type=Path,default=PROMPT)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    if args.output.resolve() in {args.track_run.resolve(),args.media_run.resolve()}: p.error("Use a new output directory")
    prompts=read_json(args.prompt)
    provider=read_json(pipeline.PACKAGE/"runs/badminton_bwf_hierarchical_20261125_v01/protocol.json")["config"]["provider"]
    key=os.environ.get(provider["api_key_env"]) or getpass.getpass("Qwen key: ")
    cases={}; jobs={}; gathered={}
    with ThreadPoolExecutor(args.workers) as pool:
        for path in sorted((args.track_run/"cases").glob("*/annotations.json")):
            if args.case_id and path.parent.name!=args.case_id: continue
            ann=read_json(path);cid=path.parent.name
            cases[cid]=ann
            original=args.clips/cid/"clip.mp4"; media=args.media_run/"cases"/cid/"media"
            manifest=read_json(media/"manifest.json")
            if file_hash(original)!=manifest["source_sha256"] or manifest["source_sha256"]!=ann["source"]["clip_sha256"]:
                raise ValueError("Media provenance mismatch")
            for i,track in enumerate(ann["visual"]["motion_tracks"]):
                job=pool.submit(inspect_actor,cid,track,ann,manifest,media,original,args.output/"cases"/cid,
                                track,provider,key,prompts)
                jobs[job]=(cid,i)
        if not jobs: raise ValueError("No input tracks")
        errors=[]
        for job in as_completed(jobs):
            cid,i=jobs[job]
            try:
                _,value=job.result();gathered[cid,i]=value
                print(cid,i,"inspected",flush=True)
            except Exception as exc:
                print(cid,i,str(exc)[:330],flush=True);errors.append((cid,i,str(exc)[:330]))
        if errors: raise RuntimeError(str(errors))
    for cid,ann in cases.items():
        ann["visual"]["motion_tracks"]=[gathered[cid,i] for i in range(len(ann["visual"]["motion_tracks"]))]
        ann["visual_refinement"]["inspection_template_sha256"]=file_hash(args.prompt)
        write_json(args.output/"cases"/cid/"annotations.json",ann)


if __name__=="__main__":
    main()
