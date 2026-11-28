"""Freeze disjoint videos and sample IDs using only visual screening, durations and IDs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import shutil

ROOT=Path(__file__).resolve().parent
REV="9059dbaf0f1683019916bad2c9f42c375d2706ea"
POOL=[1,3,4,6,7,8,13,14,15,16,17,19,20,21,22,23,27,28,30,33,34,39,41,42,43,45,47,49,50,53,54]
SELECTED_DESCRIPTIONS={
 1:("足球场控球",1),20:("林中人物",1),7:("动画角色在室内互动",3),22:("墓园行走",1),4:("动画角色与门",2),
 3:("床边与灯",1),16:("室内双人互动",2),33:("户外人物与动物",1),23:("两位动画人物交谈",2),
 28:("户外人物与印刷品",3),19:("海边双人活动",2),54:("雪地滑行",1),34:("三人围坐游戏",3),
 41:("林间骑行",1),8:("桌前操作",1),42:("室内就座",1),49:("双人舞动",2),50:("桌上彩色物件",1),
 53:("户外表演",1),43:("片场人物与道具",2)}

def read(p):return json.loads(p.read_text("utf8"))
def freeze(path,value):
    if path.exists() and read(path)!=value:raise ValueError(f"Frozen selection mismatch: {path}")
    if not path.exists():path.write_text(json.dumps(value,ensure_ascii=False,indent=2),"utf8")

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("cache",type=Path);cache=p.parse_args().cache
    base=read(ROOT.parent/"motionatlas_pilot_20261127/sample_manifest.json")
    old={s["official_sha256"] for s in base}
    ids=read(cache/"media_ids.json")
    metas={n:read(cache/"sources"/f"{n:02}.json") for n in POOL}
    strata=[[],[],[]]
    for n,m in metas.items():
        assert m['sha256'] not in old
        strata[0 if m["duration"]<=6 else 1 if m["duration"]<=12 else 2].append(n)
    rng=random.Random(20261127)
    chosen=[n for group,k in zip(strata,(7,7,6)) for n in rng.sample(group,k)]
    rows=[]
    for n in chosen:
        m=metas[n]; name,count=SELECTED_DESCRIPTIONS[n]; cid=f"ma{n:02}"
        official_id=rng.choice(sorted(ids[m['media']]))
        src=cache/"sources"/f"{n:02}.mp4";target=ROOT/"cases"/cid/"clip.mp4"
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            try:os.link(src,target)
            except OSError:shutil.copyfile(src,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==m["sha256"]
        rows.append(dict(id=cid,benchmark="MotionAtlas-Bench",domain=name,main_subject_count=count,
                         subject_kind="动画角色" if n in (3,4,7,23) else "真人",selection_note="按主要参与者筛选，路人、观众及背景角色不计。",
                         sample_ids=[official_id],people_limit=3,revision=REV,official_path=m['media'],local_original="clip.mp4",
                         source_window_seconds=[0,m["duration"]],official_sha256=m["sha256"],clip_sha256=m["sha256"],audio_source="official" if m["audio"] else None))
    assert len({s['sample_ids'][0] for s in rows})==len({s['official_sha256'] for s in rows})==20
    freeze(ROOT/"sample_manifest.json",rows)
    freeze(ROOT/"selection.json",dict(revision=REV,seed=20261127,eligible_screened_mp4_indices=POOL,
           excluded_development_sample_ids=sorted(i for s in base for i in s['sample_ids']),strata=["≤6 s","(6,12] s",">12 s"],
           draws=[7,7,6],drawn_media_indices=chosen,one_target_id_per_video=True,metric="Micro accuracy over all released questions for the 20 sample IDs"))
    print("Frozen 20 videos and 20 unique sample IDs.")

if __name__=="__main__":main()
