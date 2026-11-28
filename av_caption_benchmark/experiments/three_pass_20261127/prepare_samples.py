import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import av

HERE = Path(__file__).resolve().parent
CROSS = HERE.parent/'cross_domain_pilot_20261126'
EVA = HERE.parent/'eva_pilot_20261127'
sys.path.insert(0,str(EVA))
from fetch_samples import Archive, REPO
sys.path.insert(0,str(HERE.parents[2]))
from sports_annotation.media import ffmpeg_path

EXISTING = [
    ('sport01','运动与体能','羽毛球喂球与上网',CROSS),
    ('sport02','运动与体能','立定跳远讲解与示范',CROSS),
    ('sal02','家务与个人照护','清洁水槽处理器',CROSS),
    ('ugc02','家务与个人照护','头发分缝与梳理',CROSS),
    ('timer','工具、维修与手作','灌溉定时器拆装',EVA),
    ('apple','烹饪与饮食制作','苹果燕麦制作',EVA),
    ('ugc03','烹饪与饮食制作','越式三明治制作',CROSS),
    ('dia01','人际互动与情景表演','双人桌边交接',CROSS),
]
NEW = [
    ('sew','工具、维修与手作','缝纫机送料与折边','-bfX4SxO9h0.24.mp4',None),
    ('greet','人际互动与情景表演','两名球员赛后致意','JSQWkIvK7qs.6.mp4',7.0),
    ('guitar','音乐演奏与节奏表演','分屏吉他节奏教学','gI8lfbTYqwQ.15.mp4',12.0),
    ('drums','音乐演奏与节奏表演','架子鼓与镲片演示','M1KSdLZYg-c.6.mp4',9.0),
]

def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')

def link_file(src,dst):
    if dst.exists():return
    try:os.link(src,dst)
    except OSError:shutil.copyfile(src,dst)

def finish(cid,category,name,s,offset):
    d=HERE/'cases'/cid
    clip=d/'clip.mp4'
    with av.open(str(clip)) as f:
        dur=f.duration/av.time_base
        assert len(f.streams.audio)==1 and len(f.streams.video)==1
    row=dict(id=cid,category=category,title=name,source=s,source_start=offset,
             duration=dur,sha256=hashlib.sha256(clip.read_bytes()).hexdigest())
    write(d/'selection.json',row)
    print(cid,round(dur,2),flush=True)
    return row

def main():
    selected=[]
    for cid,cat,name,root in EXISTING:
        d=HERE/'cases'/cid;d.mkdir(exist_ok=True,parents=True)
        link_file(root/'cases'/cid/'clip.mp4',d/'clip.mp4')
        old=next(r for r in json.loads((root/'sample_manifest.json').read_text('utf8')) if r['id']==cid)
        if root==EVA:
            old.update(media=json.loads((root/'cases'/cid/'source.json').read_text('utf8')))
        selected.append(finish(cid,cat,name,old,old.get('source_window_seconds',[0])[0]))
    arch=Archive()
    def fetch(item):
        cid,cat,name,filename,limit=item;d=HERE/'cases'/cid;d.mkdir(exist_ok=True,parents=True)
        original=d/'source.mp4';info=d/'archive.json'
        if not original.exists() or not info.exists():
            offset,member=arch.locate(filename)
            b=arch.read(offset+512,member.size)
            assert b'ftyp' in b[:64]
            original.write_bytes(b)
            write(info,dict(repo=REPO,revision=arch.sha,member=member.name,offset=offset,bytes=member.size,
                            source_sha256=hashlib.sha256(b).hexdigest(),source_dataset='EVA-data / Shot2Story'))
        dest=d/'clip.mp4'
        if not dest.exists():
            if limit:
                subprocess.run([ffmpeg_path(),'-loglevel','error','-i',str(original),'-t',str(limit),
                                '-map','0:v:0','-map','0:a:0','-c:v','libx264','-crf','16','-c:a','aac',
                                '-b:a','160k','-movflags','+faststart','-y',str(dest)],check=True)
            else:link_file(original,dest)
        return finish(cid,cat,name,json.loads(info.read_text('utf8')),0)
    with ThreadPoolExecutor(4) as pool:selected.extend(pool.map(fetch,NEW))
    write(HERE/'selection.json',selected)

if __name__=='__main__':main()
