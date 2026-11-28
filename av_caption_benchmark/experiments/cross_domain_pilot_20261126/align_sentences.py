"""Localize multiple sentences that Qwen transcribed as one audio event."""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from run_pilot import HERE, ROOT, describe_request, execute, read_json

def sentence_parts(text):
    # Keep punctuation and only treat English periods at word boundaries as stops.
    return [p.strip() for p in re.split(r'(?<=[。！？])|(?<=[.!?])\s+',text.strip()) if p.strip()]

def align(folder):
    events=read_json(folder/'stages/audio_v2/result.json')['audio_events']
    anchors=[]
    for event in events:
        if event.get('type')!='speech' or not event.get('transcript'):continue
        parts=sentence_parts(event['transcript'])
        if len(parts)<2:continue
        for n,part in enumerate(parts,1):
            anchors.append(dict(id=f"{event['id']}.{n}",parent_id=event['id'],transcript=part))
    if not anchors:return
    m=read_json(folder/'media/manifest.json')
    d=m['duration']
    prompt=('只听本段原声。另一遍听写把数个句子并在一条记录中。请逐句复听定位，每个句子给单独起止。'
            '不要依字数分配时间，不用画面或字幕。若所给文字与所闻不符、词不可辨或定位无依据，请返回 instance_range=null 且说明原因。'
            '保留所给 id 和文本；允许间隙及截断。输出 JSON，唯一顶层字段 sentences。每条包括 id、transcript、instance_range（秒数数组或 null）、'
            'boundary_ranges（start 与 end 各自的可信候选数值区间，不确定就填 null）、evidence（听到的句首句尾线索或不确定原因）。'
            f'片头为零，片长 {d:.6f} 秒。候选句子：'+json.dumps(anchors,ensure_ascii=False))
    cfg=read_json(ROOT/'sports_annotation/config/five_videos_live_compact.json')['provider']
    assert cfg['base_url']=='https://maas.qianwenaiapi.com/compatible-mode/v1'
    files=[dict(kind='audio',path=str(folder/'media/audio.wav'),sha256=m['audio']['sha256'])]
    spec=describe_request('audio_sentences',prompt,files,cfg,dict(clip_id=folder.name,previous_audio='audio_v2',audio_only=True))
    def validate(data):
        rows=data.get('sentences',[])
        if [(r.get('id'),r.get('transcript')) for r in rows]!=[(r['id'],r['transcript']) for r in anchors]:raise ValueError('Return one row per given ID, preserving exact text and order')
        previous={}
        for r,a in zip(rows,anchors):
            span=r.get('instance_range')
            if span is None:continue
            if not (isinstance(span,list) and len(span)==2 and all(type(x) in (float,int) for x in span) and 0<=span[0]<span[1]<=d+0.001):raise ValueError('Invalid clip-global range')
            parent=a['parent_id']
            if span[0]<previous.get(parent,0):raise ValueError('A single speaker cannot have overlapping sentence intervals')
            previous[parent]=span[1]
    execute(folder/'stages/audio_sentences',spec,prompt,files,cfg,lambda:os.environ['QWEN_API_KEY'],validate)
    print(folder.name,'sentence alignment complete',flush=True)
if __name__=='__main__':
    clips=[p.parents[2] for p in HERE.glob('cases/*/stages/audio_v2/result.json')]
    with ThreadPoolExecutor(3) as pool:list(pool.map(align,clips))
