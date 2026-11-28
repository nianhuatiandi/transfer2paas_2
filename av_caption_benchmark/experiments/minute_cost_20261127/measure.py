"""Count Unicode characters and price recorded provider usage, including completed but rejected replies."""
from collections import Counter, defaultdict
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent
CASE = ROOT / "badminton_60s"

def read(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def save(p, s):
    with p.open("w", encoding="utf-8", newline="\n") as f:
        f.write(s)

def render(data):
    texts = []
    lines = []
    retained = {}
    body_by_mode = {}
    for mode, title in [("visual", "视觉动作与状态"), ("audio", "音频事件")]:
        before = len(texts)
        lines.append(title)
        retained[mode] = []
        for g in data["groups"][mode]:
            if g["votes"] < 2:
                continue
            e = g["example"].copy()
            e.update(id=g["id"], start=g["start"], end=g["end"], support=g["votes"])
            retained[mode].append(e)
            label = e['label']
            if mode == 'audio' and label == e['text']:
                label = {'speech':'语音','sound':'音效','music':'音乐','ambience':'环境声'}.get(e['kind'], e['kind'])
            lines.append(f'{e["id"]}  {e["start"]:.2f}–{e["end"]:.2f} s  {e["actor"]} · {label}')
            fields = [e["brief"], e.get("detail", "")] if mode == "visual" else [e["text"]]
            for value in fields:
                if isinstance(value, str) and value:
                    texts.append(value)
                    lines.append(value)
            for p in e.get("phases", []):
                if not isinstance(p, dict):
                    continue
                name = p.get("label","")
                if isinstance(name, str) and name:
                    texts.append(name)
                    lines.append(f'  {p.get("start", "?")}–{p.get("end", "?")} s  {name}')
        body_by_mode[mode] = sum(len(x) for x in texts[before:])
        lines.append("")
    retained["edges"] = [{"visual":e["visual"], "audio":e["audio"], "intersection":e["median_intersection"]}
                         for e in data["edges"] if e["keep"]]
    lines.append("动作与音频重叠")
    for e in retained["edges"]:
        a, b = e["intersection"]
        lines.append(f'{e["visual"]} × {e["audio"]}  {a:.2f}–{b:.2f} s')
    txt = "\n".join(lines).rstrip() + "\n"
    compact = json.dumps(retained, ensure_ascii=False, separators=(",",":"))
    return {"body_chars":sum(len(x) for x in texts), "reader_txt_chars":len(txt), "compact_json_chars":len(compact),
            "body_chars_by_mode":body_by_mode,"events":{m:len(arr) for m,arr in retained.items()}}, txt, compact

def cost(inp, cached, out):
    return ((inp-cached)*.8 + cached*.1 + out*2.7) / 1_000_000

def read_usage():
    calls, seen = [], set()
    for path in sorted(CASE.rglob("metadata.json")):
        meta = read(path)
        if not meta.get("api_call_made"):
            continue
        raw = path.parent / "response.txt"
        if not raw.exists():
            raw = path.parent / "response.partial.txt"
        rid = meta.get("response_id")
        if rid and rid in seen:
            raise ValueError("Duplicate response id in costs")
        if rid:
            seen.add(rid)
        usage = meta.get("usage") or {}
        stage = read(path.parent / "request.json")["stage"]
        inp, out = usage.get("prompt_tokens"), usage.get("completion_tokens")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens",0)
        if raw.exists():
            raw_chars = len(raw.read_text("utf8"))
        else:
            raw_chars = 0
        row = dict(path=path.relative_to(ROOT).as_posix(), stage=stage, status=meta["status"], response_id=rid,
                   http_status=meta.get("http_status"), error=meta.get("error"), usage=usage, response_chars=raw_chars,
                   calculated_yuan=cost(inp,cached,out) if inp is not None and out is not None else None)
        calls.append(row)
    by_stage = defaultdict(Counter)
    for r in calls:
        u = r["usage"]
        items=dict(calls=1, calls_with_usage=int(bool(u)), complete=int(r["status"]=="complete"),
                   input=u.get("prompt_tokens",0), output=u.get("completion_tokens",0),
                   cached=u.get("prompt_tokens_details",{}).get("cached_tokens",0),
                   response_chars=r["response_chars"], calculated_yuan=r["calculated_yuan"] or 0)
        by_stage[r["stage"]].update(items)
        by_stage["all"].update(items)
    return calls, by_stage

def main():
    data = read(CASE/"consensus.json")
    counts, txt, compact = render(data)
    save(ROOT/"羽毛球60秒_标注.txt", txt)
    save(ROOT/"caption.json", compact)
    calls, groups = read_usage()
    short = []
    for p in sorted((ROOT.parent/"three_pass_20261127/cases").glob("*/consensus.json")):
        metrics, _, _ = render(read(p))
        short.append({"id":p.parent.name, "duration":read(p.parent/"selection.json")["duration"], **metrics})
    short_summary = {k:{"min":min(r[k] for r in short), "median":median(r[k] for r in short),
                       "max":max(r[k] for r in short)} for k in ("duration","body_chars","reader_txt_chars","compact_json_chars")}
    result = {"sample":read(CASE/"selection.json"), "model":"qwen3.8-omni-flash", "counts":counts,
              "by_stage":groups,"requests":calls,"previous_12":short,"previous_summary":short_summary,
              "pricing_cny_per_million":{"input":0.8,"cached_input":0.1,"output":2.7,
                 "source":"https://platform.qianwenai.com/docs/models/qwen3-8-omni-flash"},
              "body_characters":"Visual brief, detail, phase labels and audio text of retained events, counted in Unicode code points, including punctuation. The representative's details and phases do not individually receive votes.",
              "reader_characters":"All Unicode characters in the UTF-8 review TXT (LF), including headings, timestamps, IDs, relations, punctuation and whitespace.",
              "json_characters":"All Unicode characters in compact caption.json (UTF-8, unescaped Unicode).",
              "cost_basis":"Provider usage, including usable/rejected records with usage. Accounts, promotions, tax and discounts are not queried."}
    save(ROOT/"用量与费用.json", json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps(dict(counts=counts,by_stage=groups,short=short_summary), ensure_ascii=True))

if __name__ == "__main__":
    main()
