"""Score the five saved Qwen visual annotations with the released MotionAtlas judge prompt.

Pass --official-root pointing to the official checkout's evaluation directory at
0f7a2590478ba742e5b46a99eafccd196e7b1c23 and --mcqs pointing to released mcqs.jsonl.
The key is read from OPENAI_API_KEY or a hidden prompt.
"""
import argparse
import concurrent.futures
import getpass
import hashlib
import json
import os
from pathlib import Path
from html import escape
import re
import sys
import time

import requests

ROOT = Path(__file__).resolve().parent
MODEL = "gpt-6-luna"
ENDPOINT = "https://api.openai.com/v1/chat/completions"
REVISION = "0f7a2590478ba742e5b46a99eafccd196e7b1c23"
OUTPUT = ROOT / "gpt6_luna_caption_judge"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, value):
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def interval(item):
    return f"{item['start']:g}–{item['end']:g} 秒"


def visual_caption(visual):
    if "motion_tracks" in visual:
        sys.path.insert(0,str(ROOT.parent/"cross_domain_pilot_20261126"))
        from unified_review import track_caption
        return track_caption(visual)
    lines = [visual["scope_note"]]
    for p in visual["actors"]:
        lines.append(f"{p['id']}　{p['description']}")
    for v in visual["executions"]:
        lines.append(f"{v['id']}　{v['actor_id']}　{interval(v)}　{v['description']}")
    for a in visual["actions"]:
        lines.extend(["", f"{a['id']}　{a['actor_id']}　{interval(a)}　{a['label']}",
                      a["brief"], a["detail"]])
        for f in a.get("evidence", []):
            lines.append(f"画面证据 {f['time']:g} 秒　{f['observation']}")
        for s in a.get("subphases", []):
            lines.append(f"子阶段 {interval(s)}　{s['label']}　{s['detail']}")
            for f in s.get("evidence", []):
                lines.append(f"画面证据 {f['time']:g} 秒　{f['observation']}")
        for k in a.get("key_moments", []):
            lines.append(f"关键点 {k['time']:g} 秒　{k['name']}")
    lines.extend(visual.get("uncertainties", []))
    return "\n".join(lines).strip()


def api_call(key, prompt, config):
    options = dict(config)
    for attempt in range(7):
        try:
            r = requests.post(ENDPOINT, allow_redirects=False, timeout=(12, 110),
                              headers={"Authorization": "Bearer " + key},
                              json={"model": MODEL, "messages": [{"role": "user", "content": prompt}], **options})
        except (requests.ConnectionError, requests.Timeout):
            if attempt >= 4:
                raise RuntimeError("OpenAI connection or read timeout") from None
            time.sleep(2**attempt)
            continue
        if r.status_code == 200:
            body = r.json()
            choice = body["choices"][0]
            msg = choice['message'].get("content") or ""
            if choice["finish_reason"]=="length" and not msg and options["max_completion_tokens"]<4096:
                options["max_completion_tokens"] *= 2
                continue
            if choice["finish_reason"]!="stop" or not msg.strip():
                raise RuntimeError(f"Unusable completion, finish_reason={choice['finish_reason']}")
            return msg, {"response_id": body["id"], "model": body["model"], "usage": body.get("usage", {}),
                         "finish_reason": choice["finish_reason"], "request_settings": options}
        try:
            error = r.json()["error"]
        except (ValueError, KeyError):
            error = {}
        param = error.get("param")
        if r.status_code == 400 and param in ("temperature", "top_p") and param in options:
            del options[param]
            continue
        if (r.status_code in (408, 429, 500, 502, 503, 504) and
                error.get("code") != "insufficient_quota" and attempt < 5):
            wait = r.headers.get("Retry-After", "")
            time.sleep(min(60, float(wait) if wait.replace(".", "", 1).isdigit() else 2**(attempt+1)))
            continue
        msg = re.sub(r"sk-[\w-]+", "[redacted]", str(error.get("message", "")))[:320]
        raise RuntimeError(f"OpenAI HTTP {r.status_code}: {error.get('code')} {msg}")
    raise RuntimeError("OpenAI request attempts exhausted")


def update_comparison(records, metrics, by_case):
    path = ROOT / "标注与官方GT对照.html"
    page = path.read_text("utf-8")
    start, stop = "<!--luna:start-->", "<!--luna:end-->"
    page = re.sub(re.escape(start) + ".*?" + re.escape(stop), "", page, flags=re.S)
    data = {r["id"]:r for r in records}
    visited = set()
    classes = {"correct":"答对","miss":"信息缺失","wrong":"答错"}
    colors = {"correct":"yes","miss":"no","wrong":"diff"}
    def augment(match):
        html = match.group()
        qid = re.search(r"<small>(sample_[^<]+)</small>", html).group(1)
        r = data[qid]
        visited.add(qid)
        group = r["classification"]
        option = escape(r["options"][r["judge_index"]])
        block = (f'<div class="luna-result"><span class="flag {colors[group]}">GPT-6 Luna · {classes[group]}</span> '
                 f'<b>{r["judge_answer"]}.</b> <span lang="en">{option}</span> '
                 f'<a href="gpt6_luna_caption_judge/answers/{qid}.json">实际 prompt 与答复</a></div>')
        return re.sub(r'(<p class="key">.*?</p>)', lambda m:m.group()+start+block+stop,html,count=1,flags=re.S)
    page = re.sub(r'<article class="qa"[^>]*>.*?</article>',augment,page,flags=re.S)
    if visited!=set(data):
        raise ValueError("Comparison page and official question IDs differ")
    names = {"ma02":"双人排球","ma31":"气球与纸屑","ma25":"厨房备菜","ma12":"阳台人物","ma36":"第一人称游戏"}
    rows = []
    for cid,title in names.items():
        m = by_case[cid]
        rows.append(f'<tr><td>{title}</td><td>{m["total"]}</td><td>{m["correct"]}</td><td>{m["miss"]}</td>'
                    f'<td>{m["wrong"]}</td><td>{m["accuracy"]:.1%}</td><td>{m["weighted_score"]:.3f}</td>'
                    f'<td><a href="gpt6_luna_caption_judge/captions/{cid}.txt">输入文本</a></td></tr>')
    style = """<style>.luna-result{margin:6px 0 10px;padding:7px 10px;background:#f3f5fa;border-radius:4px;overflow-wrap:anywhere}.luna-result a{font-size:12px}.luna-summary{border:1px solid #c5d5d2;background:white;border-radius:7px;margin:8px 0 16px;padding:9px 12px}.luna-summary summary{font-size:15px;color:#254944}.luna-table{overflow-x:auto}.luna-table table{width:100%;border-collapse:collapse;font-size:14px;white-space:nowrap}.luna-table th,.luna-table td{text-align:left;border-bottom:1px solid #d6e2df;padding:5px}</style>"""
    summary = (f'<details class="luna-summary" open><summary><b>GPT-6 Luna 读标注答题</b>　'
               f'{metrics["correct"]}/{metrics["total"]} 答对 · 准确率 {metrics["accuracy"]:.1%} · 加权分 {metrics["weighted_score"]:.3f}</summary>'
               f'<div class="luna-table"><table><thead><tr>{"".join("<th>"+s+"</th>" for s in ["视频","题数","答对","信息缺失","答错","准确率","加权分","Caption"])}</tr></thead>'
               f'<tbody>{"".join(rows)}</tbody></table></div><p class="hint">裁判每次只收到同一条视频的中文视觉标注、一道英文原题与原选项。'
               '模型答对得 1 分，选“未提及 / 不清楚”等缺失选项且与 GT 不同得 0 分，其余答错得 −0.5 分；加权分按题平均。'
               '本次 47 题的 GT 均为具体事实选项。上游 MotionBench 的独立排球题不在统计内。</p>'
               f'<a href="https://github.com/Kagura-0001/MotionAtlas/blob/{REVISION}/evaluation/motionatlas_bench/judge_captions.py">官方裁判 prompt</a>　'
               '<a href="gpt6_luna_caption_judge/metrics.json">完整指标</a></details>')
    if "<main><nav" not in page:
        raise ValueError("Comparison page layout changed")
    page = page.replace("<main><nav","<main>"+start+style+summary+stop+"<nav",1)
    temp=path.with_name(path.name+".tmp")
    temp.write_text(page,encoding="utf-8")
    temp.replace(path)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--official-root",type=Path,required=True)
    parser.add_argument("--mcqs",type=Path,required=True)
    parser.add_argument("--sample-manifest",type=Path,default=ROOT/"sample_manifest.json")
    parser.add_argument("--expected-questions",type=int,default=47)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--case-id",help="Evaluate this completed case and save its partial metrics separately.")
    parser.add_argument("--annotation-root",type=Path,default=ROOT/"results_main3",
                        help="Unified annotation version to evaluate; custom versions get an independent luna/ result.")
    args=parser.parse_args()
    sys.path.insert(0,str(args.official_root.resolve()))
    from motionatlas_bench.judge_captions import build_judge_prompt, classify_judge_answer
    from motionatlas_bench.prompt import parse_answer_letter, is_correct
    from motionatlas_bench.score import compute_judge_metrics

    baseline=args.annotation_root.resolve()==(ROOT/"results_main3").resolve()
    out=OUTPUT if baseline else args.annotation_root/"luna"
    out.mkdir(exist_ok=True)
    for name in ("captions","answers"):
        (out/name).mkdir(exist_ok=True)
    source=read(args.sample_manifest)
    case_ids={i:m["id"] for m in source for i in m["sample_ids"]}
    paths={i:m["official_path"] for m in source for i in m["sample_ids"]}
    rows=read(args.mcqs) if args.mcqs.suffix==".json" else [
        json.loads(line) for line in args.mcqs.read_text("utf-8").splitlines() if line.strip()]
    rows=[q for q in rows if q["sample_id"] in case_ids]
    if len(rows)!=args.expected_questions or len({q['id'] for q in rows})!=len(rows) or {q['sample_id'] for q in rows}!=set(case_ids):
        raise ValueError("Unexpected official question set")
    if args.case_id:
        if baseline or args.case_id not in case_ids.values():
            parser.error("Choose a known case within a separate annotation revision.")
        case_ids={sid:cid for sid,cid in case_ids.items() if cid==args.case_id}
        rows=[q for q in rows if q["sample_id"] in case_ids]
    captions={}
    for sid,cid in case_ids.items():
        annotation=read(args.annotation_root/"cases"/cid/"annotations.json")
        if annotation["source"]["official_path"]!=paths[sid]:
            raise ValueError(f"Annotation and question media differ: {cid}")
        captions[sid]=visual_caption(annotation["visual"])
        (out/"captions"/f"{cid}.txt").write_text(captions[sid],encoding="utf-8")

    key=None
    pending=[]
    data={}
    for q in rows:
        sid=q["sample_id"]
        assert paths[sid]==q["video_path"] and q["answer"]==q["options"][q["answer_index"]]
        # The official judge builder reads only the question and options.
        prompt=build_judge_prompt({"question":q["question"],"options":q["options"]},captions[sid])
        path=out/"answers"/(q["id"]+".json")
        if path.exists():
            old=read(path)
            if old["prompt"]!=prompt or old["requested_model"]!=MODEL or old["judge_index"] is None:
                raise ValueError(f"Existing result incompatible with this run: {q['id']}")
            data[q["id"]]=old
        else:
            pending.append((q,prompt,path))
    if pending:
        key=os.environ.get("OPENAI_API_KEY") or getpass.getpass("OpenAI key: ")

    def answer(task,config):
        q,prompt,path=task
        text,meta=api_call(key,prompt,config)
        letter,index=parse_answer_letter(text,len(q["options"]))
        if index is None:
            raise ValueError(f"Unparseable answer to {q['id']}")
        correct=is_correct(q,index)
        record={**q,"case":case_ids[q["sample_id"]],"requested_model":MODEL,"api":meta,"prompt":prompt,
                "raw_response":text,"judge_answer":letter,"judge_index":index,"is_correct":correct,
                "classification":classify_judge_answer(q,index,correct)}
        save(path,record)
        return record

    settings={"max_completion_tokens":512,"temperature":0,"top_p":1}
    if pending:
        first=answer(pending[0],settings)
        data[first["id"]]=first
        print("First completion received.",flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures=[pool.submit(answer,task,first["api"]["request_settings"]) for task in pending[1:]]
            for f in concurrent.futures.as_completed(futures):
                item=f.result()
                data[item["id"]]=item
                if len(data)%10==0: print(f"{len(data)}/{len(rows)}",flush=True)
    records=[data[q["id"]] for q in rows]
    metrics=compute_judge_metrics(records)
    by_case={cid:compute_judge_metrics([r for r in records if r["case"]==cid])
             for cid in case_ids.values()}
    stats_path=out/(f"metrics_{args.case_id}.json" if args.case_id else "metrics.json")
    save(stats_path,{"official_code_revision":REVISION,"model":MODEL,"overall":metrics,
         "by_case":by_case,"store_of_reference":f"Official MotionAtlas-Bench MCQs from {len(source)} selected videos",
         "caption_input":("Existing Qwen Chinese visual descriptions of all actors, actions, evidence, phases and uncertainties." if baseline else
                          "Revised per-subject visual caption with frame-grounded phases and camera context.")+
                         " No audio, videos, target masks or previous coverage notes passed to the judge.",
         "caption_sha256":{case_ids[sid]:hashlib.sha256(c.encode()).hexdigest() for sid,c in captions.items()},
         "usage":{k:sum(r["api"]["usage"].get(k,0) for r in records) for k in ("prompt_tokens","completion_tokens","total_tokens")}})
    if baseline:
        update_comparison(records,metrics,by_case)
    print({k:metrics[k] for k in ("total","correct","miss","wrong","accuracy","weighted_score")})


if __name__=="__main__":
    main()
