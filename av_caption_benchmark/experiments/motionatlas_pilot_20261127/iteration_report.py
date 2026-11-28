"""Build a comparison of completed caption revisions from their real judge responses."""
from collections import Counter
from html import escape as h
import json
from pathlib import Path
from urllib.parse import quote

ROOT=Path(__file__).resolve().parent
LABELS={"correct":"答对","miss":"信息缺失","wrong":"答错"}
VERSIONS={"v1":"原动作标注","v2":"逐主体、逐阶段描述","v3":"全景与局部三项复核","v4":"短时间窗与全片证据复核","v5":"保留分部位与短窗证据","v6":"静音视频与抽帧共同复核"}


def load(p): return json.loads(p.read_text("utf-8"))


def link(p,title):
    if not p.is_file(): raise ValueError(f"Missing report dependency: {p}")
    return '<a href="'+quote(p.relative_to(ROOT).as_posix())+'">'+h(title)+'</a>'


def main():
    dirs=[("v1",ROOT/"gpt6_luna_caption_judge")]
    dirs += [(f.parent.parent.name,f.parent) for f in sorted((ROOT/"iterations").glob("v*/luna/metrics.json"))]
    versions={}
    for version,folder in dirs:
        rows={f.stem:load(f) for f in (folder/"answers").glob("*.json")}
        counts=Counter(r["classification"] for r in rows.values())
        m=load(folder/"metrics.json")
        assert m["model"]=="gpt-6-luna" and len(rows)==47 and len({r["api"]["response_id"] for r in rows.values()})==47
        assert all(counts[k]==m["overall"][k] for k in LABELS)
        if versions:
            for qid,base in versions["v1"][2].items():
                assert all(rows[qid][k]==base[k] for k in ("question","options","answer_index"))
        versions[version]=(folder,m,rows)
    latest=dirs[-1][0]
    head='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>通用视觉标注管道迭代评测</title><style>body{max-width:1200px;margin:2rem auto;padding:0 16px;color:#193b3c;font:16px/1.6 "Microsoft YaHei",sans-serif}a{color:#086961}table{border-collapse:collapse;width:100%;margin:8px 0 20px}th,td{padding:7px 9px;text-align:left;border-bottom:1px solid #cad7d4}th{background:#edf4f2}details{padding:.35rem 0}summary{cursor:pointer}small{color:#536969}.pred{margin:6px 0 14px}.wrap{overflow-x:auto}</style><h1>通用视觉标注管道迭代评测</h1>'''
    page=[head,'<p>固定为同一批 5 条视频、47 道官方题。每个版本统一作用于全部视频，各题使用同一版官方 MotionAtlas 裁判指令与 GPT-6 Luna。开发目标为至少 33/47。下列结果按题汇总；这 5 条视频参与了迭代。</p>',
          '<div class="wrap"><table><tr><th>版本</th><th>正确</th><th>信息缺失</th><th>答错</th><th>准确率</th><th>加权分</th><th>完整指标</th></tr>']
    for v,(folder,data,_) in versions.items():
        m=data["overall"]
        page.append(f'<tr><td>{v}　{h(VERSIONS.get(v,"视觉复核"))}</td><td>{m["correct"]}/47</td><td>{m["miss"]}</td><td>{m["wrong"]}</td><td>{m["accuracy"]:.1%}</td><td>{m["weighted_score"]:.3f}</td><td>{link(folder/"metrics.json","JSON")}</td></tr>')
    page.append('</table></div><p>加权分 =（答对数 − 0.5 × 答错数）/ 47。信息缺失按官方代码判定。以下“输入”可查看完整 caption，每道题可展开核对各版本原始请求和答复。</p>')
    if latest=="v6":
        page.append('<p>最终版用 Qwen 3.8 Omni Flash 对每个镜头中的每位主体应用同一组规则。区域放大用于身体与接触，重叠短窗用于过程变化，带 fps=10 参数的静音原片用于连续运动复核。最终裁判看到的是中文抽帧记录和英文连续视频补充。官方评测题、选项、GT 和先前答题结果均未作为标注模型的输入。此结果衡量同一开发集上的视觉事实覆盖。</p>')
        page.append('<p>'+link(ROOT/'iterations/v6/试标总览.html','打开五个视频及最终标注')+
                    '　<a href="../cross_domain_pilot_20261126/unified_prompts/native_motion_v6.txt">静音原片复核 prompt</a>　<a href="../cross_domain_pilot_20261126/refine_visual.py">通用管道入口</a></p>')
    for case in load(ROOT/"sample_manifest.json"):
        cid=case["id"]; page.append(f'<h2>{h(case["domain"])}</h2><p>')
        for v,(folder,data,_) in versions.items():
            m=data["by_case"][cid]
            page.append(f'{v}　{m["correct"]}/{m["total"]}（{link(folder/"captions"/(cid+".txt"),"输入")}）　')
        page.append('</p>')
        for qid,q in sorted(versions["v1"][2].items()):
            if q["case"]!=cid: continue
            last=versions[latest][2][qid]
            page.append(f'<details><summary>{h(q["question"])}　<small>{LABELS[q["classification"]]} → {LABELS[last["classification"]]}</small></summary>'
                        f'<p>官方答案　<b>{chr(65+q["answer_index"])}. {h(q["answer"])}</b></p>')
            for v,(folder,_,rows) in versions.items():
                r=rows[qid]
                page.append(f'<p class="pred">{v}　{LABELS[r["classification"]]}　{r["judge_answer"]}. {h(r["options"][r["judge_index"]])}　{link(folder/"answers"/(qid+".json"),"实际 prompt 与答复")}</p>')
            page.append('</details>')
    page.append('</html>')
    (ROOT/"管道迭代评测.html").write_text("\n".join(page),encoding="utf-8")
    old=ROOT/"标注与官方GT对照.html"
    html=old.read_text("utf-8")
    if 'href="管道迭代评测.html"' not in html:
        html=html.replace("</header>",'<p><a href="管道迭代评测.html">查看标注管道历次修改及逐题复评</a></p></header>',1)
        old.write_text(html,"utf-8")


if __name__=="__main__":
    main()
