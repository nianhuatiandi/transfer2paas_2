"""Score each case once its immutable caption exists, then aggregate all 405."""
import argparse,concurrent.futures as cf,getpass,json,os,subprocess,sys,time
from pathlib import Path

HERE=Path(__file__).resolve().parent
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--official-root",type=Path,required=True)
    p.add_argument("--revision",default="v6");args=p.parse_args()
    rev=HERE/"revisions"/args.revision
    env=os.environ.copy();env["PYTHONIOENCODING"]="utf-8"
    env["OPENAI_API_KEY"]=env.get("OPENAI_API_KEY") or getpass.getpass("OpenAI key: ")
    rows=json.loads((HERE/"sample_manifest.json").read_text("utf8"))
    cmd=[sys.executable,str(HERE.parent/"motionatlas_pilot_20261127/run_motionatlas_luna.py"),"--annotation-root",str(rev),"--mcqs",
         str(HERE/"evaluation/official_questions.json"),"--sample-manifest",str(HERE/"sample_manifest.json"),"--expected-questions","405",
         "--official-root",str(args.official_root),"--workers","4"]
    def one(cid):
        with (HERE/"logs"/f"{cid}_{args.revision}_judge.txt").open("a",encoding="utf8") as out:
            return subprocess.run(cmd+["--case-id",cid],env=env,stdout=out,stderr=subprocess.STDOUT).returncode
    ids=[s["id"] for s in rows];scheduled=set();pending={};errors=[]
    with cf.ThreadPoolExecutor(2) as pool:
        while len(scheduled)<len(ids) or pending:
            for cid in ids:
                if cid in scheduled or not (rev/"cases"/cid/"annotations.json").is_file():continue
                scheduled.add(cid)
                if (rev/"luna"/f"metrics_{cid}.json").is_file(): continue
                pending[pool.submit(one,cid)]=cid
            for task in list(pending):
                if task.done():
                    cid=pending.pop(task);ret=task.result();print(cid,"judge returned",ret,flush=True)
                    if ret:errors.append(cid)
            if len(scheduled)<len(ids) or pending:time.sleep(4)
    if errors:raise RuntimeError("Please resume failed case(s): "+str(errors))
    subprocess.run(cmd,env=env,check=True)
if __name__=="__main__":main()
