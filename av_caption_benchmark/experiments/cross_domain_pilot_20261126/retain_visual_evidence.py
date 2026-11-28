"""Export full temporal and spatial evidence alongside the integrated caption."""
import argparse
import json
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--case-id",help="Process just one existing case without changing its inputs.")
    args=p.parse_args()
    if args.source.resolve()==args.output.resolve(): p.error("Use a new output path")
    files=sorted((args.source/"cases").glob("*/annotations.json"))
    if args.case_id: files=[p for p in files if p.parent.name==args.case_id]
    if not files: p.error("No input annotations")
    for f in files:
        ann=json.loads(f.read_text("utf8"))
        for t in ann["visual"]["motion_tracks"]:
            if not all(t.get(k) for k in ("integrated_facts","window_review","inspections")):
                raise ValueError("An input track is missing its detailed observations")
        ann["visual"]["caption_detail_policy"]="retain_evidence"
        dest=args.output/"cases"/f.parent.name/"annotations.json"
        dest.parent.mkdir(exist_ok=True,parents=True)
        dest.write_text(json.dumps(ann,ensure_ascii=False,indent=2),"utf8")


if __name__=="__main__":
    main()
