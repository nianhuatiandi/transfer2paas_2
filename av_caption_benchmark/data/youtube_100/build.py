import collections
import concurrent.futures
import html
import json
import random
import re
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent
TARGETS = {
    "Sport": 20,
    "Tools and craft": 16,
    "Daily life and care": 16,
    "Food and cooking": 16,
    "Music and performance": 16,
    "Talk and instruction": 16,
}
SEED = 28112026

def thumb(row):
    key = row["video_id"]
    out = ROOT / "previews" / (key + ".jpg")
    for name in ("hqdefault.jpg", "mqdefault.jpg"):
        if out.exists():
            break
        try:
            result = requests.get(f"https://i.ytimg.com/vi/{key}/{name}", timeout=(6, 10))
            if result.ok:
                from io import BytesIO
                with Image.open(BytesIO(result.content)) as im:
                    if im.width >= 320:
                        im.convert("RGB").save(out, quality=88)
        except (OSError, requests.RequestException):
            continue
    return key, out.relative_to(ROOT).as_posix() if out.exists() else None

def choose(candidates, old):
    rows = []
    ids = set(old)
    shuffle = random.Random(SEED)
    for category, quota in TARGETS.items():
        buckets = collections.defaultdict(list)
        for r in candidates:
            if r["category"] == category and r["video_id"] not in ids:
                buckets[r["topic"]].append(r)
        groups = list(buckets.values())
        for g in groups:
            g.sort(key=lambda r:r["video_id"])
            shuffle.shuffle(g)
        shuffle.shuffle(groups)
        counts = collections.Counter()
        count = 0
        while count < quota and groups:
            for group in list(groups):
                if not group:
                    groups.remove(group)
                    continue
                ix = min(range(len(group)), key=lambda i:counts[group[i].get("channel") or group[i]["video_id"]])
                r = group.pop(ix)
                key = r["video_id"]
                if key in ids:
                    continue
                ids.add(key)
                counts[r.get("channel") or key] += 1
                rows.append(r)
                count += 1
                if count == quota:
                    break
        if count != quota:
            raise ValueError(f"{category}: {count}/{quota} distinct results")
    return rows

def main():
    pool = json.loads((ROOT/"pool.json").read_text(encoding="utf8"))
    reject_path = ROOT/"excluded.json"
    rejects = set(json.loads(reject_path.read_text(encoding="utf8"))) if reject_path.exists() else set()
    prior = ROOT.parent/"bench_collection_400_hd"/"manifest.jsonl"
    old = set()
    if prior.exists():
        for line in prior.read_text(encoding="utf8").splitlines():
            origin = json.loads(line).get("origin","")
            if origin.startswith("youtube:"):
                old.add(origin.split(":",1)[1])
    rows=choose([r for r in pool if r["video_id"] not in rejects],old)
    (ROOT/"previews").mkdir(exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(12) as executor:
        images = dict(executor.map(thumb, rows))
    for r in rows:
        r.update(preview=images[r["video_id"]], local_video=None, media_review="Pending playback and stream verification")
    (ROOT/"manifest.jsonl").write_text("".join(json.dumps(r,ensure_ascii=False)+"\n" for r in rows),encoding="utf8")
    counts = dict(collections.Counter(r["category"] for r in rows))
    topics = dict(collections.Counter(r["topic"] for r in rows))
    info=dict(counts=counts,topic_counts=topics,total=len(rows),thumbnail_count=sum(bool(r["preview"]) for r in rows),sampling_seed=SEED,candidate_count=len({r["video_id"] for r in pool})-len(rejects))
    (ROOT/"summary.json").write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding="utf8")
    esc=html.escape
    controls='<label>Category <select id="category"><option value="">All</option>'+''.join(f'<option>{esc(c)}</option>' for c in TARGETS)+'</select></label> <span id="count"></span>'
    cards=[]
    for r in rows:
        title=esc(r["title"]);url=esc(r["youtube_url"],quote=True);cat=esc(r["category"],quote=True)
        preview=f'<img loading="lazy" src="{r["preview"]}" alt="YouTube thumbnail">' if r["preview"] else ""
        chapter=""
        for item in r.get("chapters",[])[:3]:
            chapter+=f' <a href="{url}&amp;t={item["seconds"]}s">{esc(item["timestamp"]+" "+item["label"])}</a>'
        cards.append(f'<article data-category="{cat}"><a class="cover" href="{url}">{preview}</a><div><h2><a href="{url}">{title}</a></h2><p>{cat} · {esc(r["topic"])}</p><p>{esc(r.get("channel") or "")}</p><p>{chapter}</p></div></article>')
    js="<script>const f=document.querySelector('#category'),c=document.querySelector('#count');function show(){let n=0;for(const x of document.querySelectorAll('article')){x.hidden=!!(f.value&&f.value!==x.dataset.category);if(!x.hidden)n++}c.textContent=n+' shown'}f.onchange=show;show();</script>"
    head='<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>YouTube video candidates</title><style>body{font:16px system-ui;color:#17283a;max-width:1000px;margin:2rem auto;padding:0 1rem}article{display:flex;gap:1rem;border-bottom:1px solid #dce1e5;padding:1rem 0}article[hidden]{display:none}img{width:min(240px,35vw);height:auto}h2{font-size:1.05rem;margin:0}p{margin:.45rem 0}a{color:#005e79}.cover:empty{display:none}</style>'
    (ROOT/"index.html").write_text(head+'<h1>100 YouTube video candidates</h1><p>Stratified sample from indexed YouTube search results. Playback, resolution, audio, and principal-person counts await media verification.</p><p><a href="manifest.jsonl">Manifest</a> · <a href="summary.json">Sampling summary</a></p>'+controls+''.join(cards)+js+'</html>',encoding="utf8")
    print(json.dumps(info,ensure_ascii=True))

if __name__ == "__main__":
    main()
