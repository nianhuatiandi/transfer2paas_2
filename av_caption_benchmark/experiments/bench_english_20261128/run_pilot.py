"""Reproduce the English event-reference pilot from local source clips."""
import argparse
import sys
import tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from sports_annotation.bench import run
from sports_annotation.long_video import credential

CASES={"badminton":"cn","sew":"en","sport02":"cn","sal02":"en","apple":"en","drums":"en","dia01":None,"day01":"en","day02":"en"}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("cases",nargs="+",choices=list(CASES))
    p.add_argument("--draft",action="store_true")
    p.add_argument("--live",action="store_true",help="Prompt once for live API calls; cached reruns can omit this.")
    args=p.parse_args()
    if args.live:
        credential()
    asr=Path(tempfile.gettempdir())/"av_threepass_asr_20261127"
    sys.path.insert(0,str(asr/"deps"))
    def one(name):
        source=(HERE.parent/"minute_cost_20261127/badminton_60s/clip.mp4" if name=="badminton" else
                HERE.parent/"three_pass_20261127/cases"/name/"clip.mp4")
        if name in ("day01","day02"):
            source=HERE.parent/"cross_domain_pilot_20261126/cases"/name/"clip.mp4"
        lex={"badminton":"badminton_bwf_v01.json","sport02":"standing_jump.json"}.get(name)
        m={"cn":"vosk-model-small-cn-0.22","en":"vosk-model-small-en-us-0.15"}.get(CASES[name])
        run(SimpleNamespace(video=source,out=HERE/"cases"/name,lexicon=ROOT/"sports_annotation/lexicons"/lex if lex else None,
                            jobs=3,proposal_only=args.draft,vosk_model=asr/m if m else None))
        print("ready",name,flush=True)
    with ThreadPoolExecutor(2) as pool:
        futures={pool.submit(one,c):c for c in args.cases}
        failures=[]
        for task in as_completed(futures):
            try: task.result()
            except Exception as exc:
                failures.append((futures[task],str(exc)))
                print("stopped",*failures[-1],flush=True)
        if failures: raise RuntimeError(failures)

if __name__=="__main__":
    main()
