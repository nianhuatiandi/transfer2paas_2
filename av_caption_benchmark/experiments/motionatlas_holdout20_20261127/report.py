"""Check source identity, blind request texts, answers and denominators; render a local audit."""
import argparse
from collections import Counter
from html import escape
import hashlib,json,math,sys
from pathlib import Path
from urllib.parse import quote

HERE=Path(__file__).resolve().parent
def read(p):return json.loads(p.read_text("utf8"))
def link(path,label):
    if not path.is_file():raise ValueError(f"Missing file: {path}")
    return '<a href="'+quote(path.relative_to(HERE).as_posix())+'">'+escape(label)+'</a>'

def main():
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument("--official-root",type=Path,required=True)
    cli.add_argument("--revision",default="v6");cli.add_argument("--partial",action="store_true");args=cli.parse_args()
    sys.path.insert(0,str(args.official_root.resolve()))
    sys.path.insert(0,str(HERE.parent/"cross_domain_pilot_20261126"))
    from motionatlas_bench.judge_captions import build_judge_prompt,classify_judge_answer
    from unified_review import track_caption
    samples=read(HERE/"sample_manifest.json");official=read(HERE/"evaluation/official_questions.json")
    ref={q["id"]:q for q in official};folder=HERE/"revisions"/args.revision;judge=folder/"luna"
    m=None if args.partial else read(judge/"metrics.json")
    records={f.stem:read(f) for f in (judge/"answers").glob("*.json")}
    assert len(samples)==20 and len(ref)==405 and set(records)<=set(ref)
    if not args.partial: assert set(ref)==set(records)
    dev={v["clip_sha256"] for v in read(HERE.parent/"motionatlas_pilot_20261127/sample_manifest.json")}
    hashes={v["clip_sha256"] for v in samples}
    assert len(hashes)==20 and not hashes&dev
    assert len({r["api"]["response_id"] for r in records.values()})==len(records)
    classes=Counter();summaries=[];captions={};details=[];pending=[]
    labels={"correct":"答对","miss":"信息缺失","wrong":"答错"}
    for sample in samples:
        cid=sample["id"]; clip=HERE/"cases"/cid/"clip.mp4"
        assert hashlib.sha256(clip.read_bytes()).hexdigest()==sample["clip_sha256"]
        selected=sorted([q for q in official if q["sample_id"] in sample["sample_ids"]],key=lambda q:q["id"])
        if args.partial and not any(q["id"] in records for q in selected):
            pending.append((cid,sample["domain"],len(selected)))
            details.append(f'<section id="{cid}"><h2>{escape(sample["domain"])} · sample {sample["sample_ids"][0]}</h2><p>待完成该版本标注及 {len(selected)} 道裁判题。　'+link(clip,"原片")+'</p></section>')
            continue
        metrics=m or read(judge/f"metrics_{cid}.json")
        entry=read(folder/"cases"/cid/"annotations.json");capfile=judge/"captions"/(cid+".txt");cap=capfile.read_text("utf8")
        assert entry["source"]["clip_sha256"]==sample["clip_sha256"] and track_caption(entry["visual"])==cap
        assert metrics["caption_sha256"][cid]==hashlib.sha256(cap.encode()).hexdigest()
        captions[cid]=cap
        local=Counter()
        details.append(f'<section id="{cid}"><h2>{escape(sample["domain"])} · sample {sample["sample_ids"][0]}</h2><p>'+
                       link(clip,"视频")+'　'+link(capfile,"实际输入 caption")+'　'+link(folder/"cases"/cid/"annotations.json","完整标注")+'</p>')
        for q in selected:
            row=records[q["id"]]
            assert q["video_path"]==sample["official_path"] and q["answer"]==q["options"][q["answer_index"]]
            assert row["case"]==cid and row["api"]["model"]=="gpt-6-luna" and row["api"]["finish_reason"]=="stop"
            assert row["prompt"]==build_judge_prompt({"question":q["question"],"options":q["options"]},cap)
            correct=row["judge_index"]==q["answer_index"]
            cl=classify_judge_answer(q,row["judge_index"],correct)
            assert row["is_correct"]==correct and cl==row["classification"] and row["options"]==q["options"]
            classes[cl]+=1;local[cl]+=1
            details.append('<details><summary>'+labels[cl]+'　'+escape(q['question'])+'</summary><p>官方答案　'+escape(q['answer'])+
                '</p><p>Luna 选择　'+escape(q['options'][row['judge_index']])+'</p>'+
                link(judge/'answers'/(q['id']+'.json'),'完整 prompt、选项与原始答复')+'</details>')
        details.append('</section>')
        total=len(selected);assert total==metrics["by_case"][cid]["total"] and all(local[k]==metrics["by_case"][cid][k] for k in labels)
        summaries.append({"sample_id":sample["sample_ids"][0],"case":cid,"domain":sample["domain"],"duration_s":sample["source_window_seconds"][1],"total":total,
                          **{k:local[k] for k in labels},"accuracy":local["correct"]/total})
    answered=sum(classes.values());remaining=405-answered
    assert answered==len(records) and remaining==sum(n for _,_,n in pending)
    if m: assert m["overall"]["total"]==405 and all(m["overall"][k]==classes[k] for k in labels)
    need=math.ceil(.7*405);macro=sum(x["accuracy"] for x in summaries)/len(summaries)
    ceiling=classes['correct']+remaining
    stats={"revision":args.revision,"model":"gpt-6-luna","samples":20,"questions":405,"required":need,
           "met":True if classes["correct"]>=need else (False if ceiling<need else None),
           "complete":not remaining,"completed_samples":len(summaries),"judged_questions":answered,"remaining":remaining,
           "outcomes":dict(classes),"accuracy_on_judged":classes["correct"]/answered,"final_accuracy":None if remaining else classes["correct"]/405,
           "max_possible_correct":ceiling,"max_possible_accuracy":ceiling/405,"completed_macro_accuracy":macro,"by_case":summaries,"pending":pending}
    summary_path=folder/("partial_verified_summary.json" if remaining else "verified_summary.json")
    summary_path.write_text(json.dumps(stats,ensure_ascii=False,indent=2),"utf8")
    html=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>MotionAtlas-Bench 新增 20 条盲测</title>',
          '<style>body{max-width:1120px;margin:2rem auto;padding:0 14px;font:16px/1.65 "Microsoft YaHei",sans-serif;color:#163e43}a{color:#00685e}table{border-collapse:collapse;width:100%}td,th{padding:5px 8px;text-align:left;border-bottom:1px solid #cddcd7}th{background:#e9f4ef}summary{cursor:pointer}section{border-top:1px solid #cddcd7;margin:2em 0}details{padding:5px 0}.wrap{overflow:auto}</style>',
          '<h1>MotionAtlas-Bench 新增 20 条盲测</h1><p>版本 '+escape(args.revision)+' · Qwen 3.8 Omni Flash 生成标注 · GPT-6 Luna 使用官方文本裁判指令。</p>',
          f'<p><b>已完成 {len(summaries)}/20 条，答对 {classes["correct"]}/{answered}（{classes["correct"]/answered:.1%}）</b>，信息缺失 {classes["miss"]} 题，答错 {classes["wrong"]} 题。达标线为 {need}/405。已完成视频等权平均为 {macro:.1%}。</p>',
          (f'<p>Qwen 服务返回账户欠费错误，尚有 {remaining} 题待评。即使全部答对，整体最高为 {ceiling}/405（{ceiling/405:.1%}）。</p>' if remaining else ''),
          '<p>在查看新样本题目前，从已缓存并按主体筛过的 31 条官方 MP4 按时长抽出 7、7、6 条，每条保留一个官方目标的全部题。与上一轮五条视频的文件哈希不相交。评测覆盖视觉运动事实。</p>',
          link(HERE/"selection.json","抽样记录")+'　'+link(HERE/"sample_manifest.json","样本名单")+'　'+link(summary_path,"经核对的指标"),
          '<div class="wrap"><table><tr><th>官方样本</th><th>视频</th><th>秒</th><th>答对/题数</th><th>缺失</th><th>答错</th><th>准确率</th></tr>']
    for x in summaries:
        html.append(f'<tr><td>{x["sample_id"]}</td><td><a href="#{x["case"]}">{escape(x["domain"])}</a></td><td>{x["duration_s"]:.1f}</td><td>{x["correct"]}/{x["total"]}</td><td>{x["miss"]}</td><td>{x["wrong"]}</td><td>{x["accuracy"]:.1%}</td></tr>')
    for cid,domain,num in pending:
        s=next(s for s in samples if s["id"]==cid)
        html.append(f'<tr><td>{s["sample_ids"][0]}</td><td><a href="#{cid}">{escape(domain)}</a></td><td>{s["source_window_seconds"][1]:.1f}</td><td colspan="4">待评 {num} 题</td></tr>')
    (HERE/f'20条盲测_{args.revision}.html').write_text('\n'.join(html+['</table></div>',*details,'</html>']),encoding="utf8")
    print({k:stats[k] for k in ('met','judged_questions','accuracy_on_judged','max_possible_accuracy')},dict(classes))

if __name__=="__main__":main()
