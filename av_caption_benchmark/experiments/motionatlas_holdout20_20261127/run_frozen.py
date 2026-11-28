"""Run each frozen v6 stage with its original prompt, allowing independent case recovery."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import getpass,json,os,subprocess,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
SHARED=HERE.parent/"cross_domain_pilot_20261126"
BASE=HERE/"base"; OUT=HERE/"revisions"


def run_case(cid,env,geometry):
    if not (BASE/"cases"/cid/"annotations.json").is_file(): return "awaiting base"
    log=HERE/"logs";log.mkdir(exist_ok=True)
    stages=[
        ("v2","motion_tracks.py",["--source",BASE]),
        ("v3","motion_inspection.py",["--media-run",BASE,"--track-run",OUT/"v2","--clips",HERE/"cases"]),
        ("geom","measure_camera.py",["--media-run",BASE]),
        ("v4","motion_windows.py",["--media-run",BASE,"--prior",OUT/"v3"]),
        ("v5","retain_visual_evidence.py",["--source",OUT/"v4"]),
        ("v6","native_motion.py",["--media-run",BASE,"--prior",OUT/"v5","--clips",HERE/"cases"])]
    for version,script,options in stages:
        dest=OUT/("v4" if version=="geom" else version)
        artifact=dest/"cases"/cid/("camera_measurements.json" if version=="geom" else "annotations.json")
        if artifact.is_file():continue
        command=[geometry if version=="geom" else sys.executable,SHARED/script,*options,"--output",dest,"--case-id",cid]
        if version not in ("geom","v5"):command.extend(["--workers","2"])
        print(cid,version,flush=True)
        with (log/(cid+"_"+version+".txt")).open("a",encoding="utf8") as f:
            result=subprocess.run(list(map(str,command)),env=env,stdout=f,stderr=subprocess.STDOUT)
        if result.returncode or not artifact.is_file():return "failed "+version
    return "complete"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--geometry-python",required=True);p.add_argument("--workers",type=int,default=6)
    p.add_argument("ids",nargs="*");args=p.parse_args()
    env=os.environ.copy();env["PYTHONIOENCODING"]="utf-8"
    env["QWEN_API_KEY"]=env.get("QWEN_API_KEY") or getpass.getpass("Qwen key: ")
    ids=[r["id"] for r in json.loads((HERE/"sample_manifest.json").read_text("utf8"))]
    if set(args.ids)-set(ids):p.error("Unknown case")
    failed=[]
    with ThreadPoolExecutor(args.workers) as pool:
        jobs={pool.submit(run_case,c,env,args.geometry_python):c for c in (args.ids or ids)}
        for f in as_completed(jobs):
            status=f.result();cid=jobs[f];print(cid,status,flush=True)
            if status!="complete":failed.append((cid,status))
    if failed:raise SystemExit(1)

if __name__=="__main__":main()
