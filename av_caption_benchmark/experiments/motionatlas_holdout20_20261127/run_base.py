"""Run the existing visual baseline for the frozen, silent official media."""
from concurrent.futures import ThreadPoolExecutor,as_completed
import getpass,os,sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'motionatlas_pilot_20261127'))
import run_samples

def main():
    run_samples.HERE=HERE
    run_samples.OUT=HERE/'base'
    pipe=run_samples.pipeline
    cases=pipe.read_json(HERE/'sample_manifest.json')
    cfg=pipe.read_json(pipe.PACKAGE/'runs/badminton_bwf_hierarchical_20261125_v01/protocol.json')['config']
    if not os.environ.get('QWEN_API_KEY'):os.environ['QWEN_API_KEY']=getpass.getpass("Qwen key: ")
    jobs={}
    def one(case):
        if (run_samples.OUT/'cases'/case['id']/'annotations.json').exists():return
        run_samples.run(case,cfg)
    with ThreadPoolExecutor(6) as ex:
        for c in cases:jobs[ex.submit(one,c)]=c['id']
        errors=[]
        for f in as_completed(jobs):
            try:f.result();print(jobs[f],"complete",flush=True)
            except Exception as e:errors.append((jobs[f],str(e)[:490]));print(errors[-1],flush=True)
    if errors:raise RuntimeError(str(errors))

if __name__=='__main__':main()
