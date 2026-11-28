"""Load the pinned official release only after the sample IDs have been frozen."""
import getpass,hashlib,json,math,os
from collections import Counter
from pathlib import Path
import requests

HERE=Path(__file__).resolve().parent
samples=json.loads((HERE/"sample_manifest.json").read_text("utf8"))
targets={x["sample_ids"][0]:x["official_path"] for x in samples}
key=os.environ.get("HF_TOKEN") or getpass.getpass("HF key: ")
revision=samples[0]["revision"]
r=requests.get(f"https://huggingface.co/datasets/maxLWSv2/motionatlas-bench/resolve/{revision}/mcqs.jsonl",params={"download":"true"},
               headers={"Authorization":"Bearer "+key},timeout=90)
r.raise_for_status()
assert hashlib.sha256(r.content).hexdigest()=="21df0dfff06a3c3b522d76e7003d76a8c35f9a12da71384e82bc3c1a8415d004"
rows=[q for l in r.content.splitlines() if (q:=json.loads(l))["sample_id"] in targets]
assert {q["sample_id"] for q in rows}==set(targets) and len({q['id'] for q in rows})==len(rows)
assert all(q["video_path"]==targets[q["sample_id"]] and q["options"][q["answer_index"]]==q["answer"] for q in rows)
folder=HERE/"evaluation";folder.mkdir(exist_ok=True)
(folder/"official_questions.json").write_text(json.dumps(rows,ensure_ascii=False),encoding="utf8")
print(len(rows),"questions;",math.ceil(7*len(rows)/10),"correct needed for 70%; counts",dict(Counter(q["sample_id"] for q in rows)))
