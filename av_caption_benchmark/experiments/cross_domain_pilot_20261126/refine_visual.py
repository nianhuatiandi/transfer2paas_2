"""Run the visual refinements on any unified case collection using one Qwen credential.

--source holds cases/<id>/annotations.json and media/manifest.json.
--clips holds <id>/clip.mp4. All stages write to subdirectories of --output.
--geometry-python selects a Python interpreter with cv2 and numpy for camera estimation.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

HERE=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source",type=Path,required=True)
    parser.add_argument("--clips",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--geometry-python",default=sys.executable)
    parser.add_argument("--workers",type=int,default=5)
    parser.add_argument("--through",choices=("v2","v3","v4","v5","v6"),default="v6")
    args=parser.parse_args()
    base=args.source.resolve();out=args.output.resolve(); clips=args.clips.resolve()
    if out==base or any(base==out/v for v in ("v2","v3","v4")):
        parser.error("Use a separate revision directory")
    # Fail on local dependencies before issuing paid calls.
    if args.through in ("v4","v5","v6"):
        subprocess.run([args.geometry_python,"-c","import cv2,numpy"],check=True)
    env=os.environ.copy()
    env["QWEN_API_KEY"]=env.get("QWEN_API_KEY") or getpass.getpass("Qwen key: ")
    def run(name,*parts,python=sys.executable):
        subprocess.run([python,str(HERE/name),*map(str,parts)],env=env,check=True)
    run("motion_tracks.py","--source",base,"--output",out/"v2","--workers",args.workers)
    if args.through!="v2":
        run("motion_inspection.py","--media-run",base,"--track-run",out/"v2","--clips",clips,"--output",out/"v3","--workers",args.workers)
    if args.through in ("v4","v5","v6"):
        run("measure_camera.py","--media-run",base,"--output",out/"v4",python=args.geometry_python)
        run("motion_windows.py","--media-run",base,"--prior",out/"v3","--output",out/"v4","--workers",args.workers)
    if args.through in ("v5","v6"):
        run("retain_visual_evidence.py","--source",out/"v4","--output",out/"v5")
    if args.through=="v6":
        run("native_motion.py","--media-run",base,"--prior",out/"v5","--clips",clips,"--output",out/"v6","--workers",args.workers)
    export_revision(base,clips,out/args.through)


def export_revision(base,clips,revision):
    from unified_review import export_case,export_index
    cases=[]
    for f in sorted((revision/"cases").glob("*/annotations.json")):
        ann=json.loads(f.read_text("utf8"));cid=f.parent.name
        export_case(f.parent,clips/cid/"clip.mp4",ann,base/"cases"/cid/"stages")
        cases.append(ann["source"])
    export_index(revision,cases)


if __name__=="__main__":
    main()
