"""Inspect overlapping short windows then resolve competing descriptions against the frames."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import getpass
import json
import os
from pathlib import Path

from motion_tracks import pipeline, images, sample, describe_request, execute, file_hash, read_json, write_json
from sports_annotation.io_utils import parse_model_json

HERE=Path(__file__).resolve().parent
PROMPTS=HERE/"unified_prompts/motion_windows_v4.json"


def facts(obj):
    seq=obj.get("facts") if isinstance(obj,dict) else obj
    if not isinstance(seq,list) or not seq:
        raise ValueError("Return a JSON object containing an array of non-empty text facts.")
    result=[]
    for item in seq:
        if isinstance(item,str) and item.strip():
            result.append(item)
        elif isinstance(item,dict) and isinstance(item.get("facts"),list):
            prefix="　".join(f"{k}={v}" for k,v in item.items() if k!="facts")
            for line in facts(item["facts"]):
                result.append(f"{prefix}　{line}" if prefix else line)
        elif isinstance(item,dict) and any(isinstance(v,str) and len(v.strip())>=6 for v in item.values()):
            result.append("　".join(f"{k}={v}" if isinstance(v,(float,int)) else
                                   (v if isinstance(v,str) else json.dumps(v,ensure_ascii=False))
                                   for k,v in item.items()))
        else:
            raise ValueError("A fact must contain a visible description")
    return result


def windows(frames,length=13,overlap=3):
    pos=0
    while pos<len(frames):
        yield frames[pos:pos+length]
        if pos+length>=len(frames): break
        pos+=length-overlap


def inspect(cid,i,track,visual,media,out,provider,key,template):
    m=read_json(media/"manifest.json")
    flow=read_json(out/"camera_measurements.json")
    if flow["source_sha256"]!=m["source_sha256"]: raise ValueError("Camera evidence source mismatch")
    shot=track["shot_id"]; actor=track["actor_id"]
    frames=[f for f in m["frames"] if f["shot_id"]==shot]
    directory=out/"stages"/(actor or shot+"-scene")
    provenance={"source_sha256":m["source_sha256"],"shot_id":shot,"actor_id":actor}
    target="\n主体外观线索："+track["identity"]
    signals=[q for q in flow["pairs"] if q["shot_id"]==shot]

    def call(stage,instruction,fs):
        refs=images(media,fs)
        desc=describe_request(stage,instruction,refs,provider,provenance)
        folder=directory/stage
        if (folder/"metadata.json").exists():
            m=read_json(folder/"metadata.json")
            if m.get("status")=="failed" and m.get("finish_reason")=="stop" and m.get("signature")==desc["signature"] and (folder/"response.txt").is_file():
                try: lines=facts(parse_model_json((folder/"response.txt").read_text("utf8")))
                except (ValueError,TypeError,KeyError): pass
                else:
                    write_json(folder/"validated.json",lines)
                    return lines
        return facts(execute(folder,desc,instruction,refs,provider,lambda:key,facts))

    reports=[]
    for j,group in enumerate(windows(frames),1):
        subset=[q for q in signals if group[0]["index"]<=q["frames"][0] and q["frames"][1]<=group[-1]["index"]]
        measurements="\n供核查的全图一致特征位移估计（可能受前景影响；dx 向右、dy 向下为正，单位为每秒画面宽/高的百分比；scale>1 表示画面特征放大）。只有在固定背景也支持时才据此解释运镜："+json.dumps(subset,separators=(",",":"))
        lines=call(f"window_{j:02d}",template["window"]+target+measurements,group)
        reports.append({"start":group[0]["time"],"end":group[-1]["time"],"facts":lines})
    base=[{field:a[field] for field in ("label","start","end","detail","evidence","subphases")}
          for a in visual["actions"] if a["shot_id"]==shot and a["actor_id"]==actor]
    prior={facet:[x["description"] for x in items] for facet,items in track.get("inspections",{}).items()}
    candidates=json.dumps({"first_pass":base,"region_review":prior,"independent_windows":reports},ensure_ascii=False,separators=(",",":"))
    final=call("integrate",template["merge"]+target+"\n待核实候选记录："+candidates,sample(frames,24))
    return cid,i,{**track,"window_review":reports,"integrated_facts":final}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for s in ("media-run","prior","output"): p.add_argument("--"+s,type=Path,required=True)
    p.add_argument("--workers",type=int,default=6)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    if args.output.resolve() in (args.prior.resolve(),args.media_run.resolve()): p.error("Choose a new output directory")
    provider=read_json(pipeline.PACKAGE/"runs/badminton_bwf_hierarchical_20261125_v01/protocol.json")["config"]["provider"]
    key=os.environ.get(provider["api_key_env"]) or getpass.getpass("Qwen key: ")
    cases={};jobs={};template=read_json(PROMPTS)
    with ThreadPoolExecutor(args.workers) as pool:
        for f in sorted((args.prior/"cases").glob("*/annotations.json")):
            if args.case_id and f.parent.name!=args.case_id: continue
            a=read_json(f);cid=f.parent.name;cases[cid]=a
            for i,t in enumerate(a["visual"]["motion_tracks"]):
                task=pool.submit(inspect,cid,i,t,a["visual"],args.media_run/"cases"/cid/"media",
                                 args.output/"cases"/cid,provider,key,template)
                jobs[task]=(cid,i)
        if not jobs: raise ValueError("No input tracks")
        errors=[]
        for task in as_completed(jobs):
            try:
                cid,i,t=task.result();cases[cid]["visual"]["motion_tracks"][i]=t;print(cid,i,"done",flush=True)
            except Exception as exc: errors.append((jobs[task],str(exc)[:450]));print(errors[-1],flush=True)
        if errors: raise RuntimeError(str(errors))
    for cid,a in cases.items():
        a["visual_refinement"]["window_prompt_sha256"]=file_hash(PROMPTS)
        write_json(args.output/"cases"/cid/"annotations.json",a)


if __name__=="__main__":
    main()
