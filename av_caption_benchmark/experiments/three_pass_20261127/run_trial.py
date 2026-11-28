import argparse
import getpass
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import av

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from sports_annotation.client import execute,describe_request
from sports_annotation.media import ffmpeg_path
from sports_annotation.io_utils import read_json,write_json,file_hash
from sports_annotation.hierarchical_experiment import runtime_lexicon

CFG=read_json(HERE.parents[2]/'sports_annotation/runs/badminton_bwf_hierarchical_20261125_v01/protocol.json')['config']['provider']
CFG={**CFG,'max_tokens':6000,'connect_timeout_seconds':75,'max_validation_repairs':0,
     'extra_body':{**CFG['extra_body'],'temperature':0.65}}
FF=ffmpeg_path()

def media(folder):
    src=folder/'clip.mp4';m=folder/'media';m.mkdir(exist_ok=True)
    for name,opts in [('silent.mp4',['-map','0:v:0','-an','-c:v','copy']),
                      ('audio.wav',['-map','0:a:0','-vn','-ac','1','-ar','16000','-c:a','pcm_s16le'])]:
        if not (m/name).exists():
            subprocess.run([FF,'-v','error','-i',str(src),*opts,'-y',str(m/name)],check=True)
    images=[]
    with av.open(str(m/'silent.mp4')) as f:
        assert len(f.streams.audio)==0
        target=0
        for idx,frame in enumerate(f.decode(video=0)):
            t=float(frame.pts*frame.time_base)
            if t+0.001<target:continue
            p=m/f'{idx:04}.jpg'
            if not p.exists():
                im=frame.to_image();im.thumbnail((640,420));im.save(p,quality=82)
            images.append(dict(kind='image',index=idx,time=t,shot_id='clip',path=str(p),sha256=file_hash(p)))
            target+=0.5
    return {'visual':[dict(kind='video',path=str(m/'silent.mp4'),sha256=file_hash(m/'silent.mp4'),fps=10),*images],
            'audio':[dict(kind='audio',path=str(m/'audio.wav'),sha256=file_hash(m/'audio.wav'))]}

def request(dest,name,prompt,refs,provenance,validator,cfg):
    for attempt in range(3):
        target=dest if attempt==0 else dest/f'retry{attempt}'
        desc=describe_request(name,prompt,refs,cfg,provenance)
        try:
            out=execute(target,desc,prompt,refs,cfg,lambda:os.environ['QWEN_API_KEY'],validator)
        except Exception as exc:
            if attempt==2 or any(s in str(exc) for s in ['HTTP 401','quota','balance']):raise
            continue
        return out

def normalize(raw,mode,duration):
    if isinstance(raw,list): raw={'events':raw}
    events=raw['events'];assert isinstance(events,list)
    out=[];limits=[]
    for i,orig in enumerate(events):
        e=orig.copy()
        fields=['actor','kind','start','end']+(['brief','label'] if mode=='visual' else ['text','layer'])
        if any(k not in e for k in fields):raise ValueError('Missing required core field')
        if mode=='visual':
            if e['kind'] not in ('motion','gesture','state'):raise ValueError('Unknown visual kind')
            e.setdefault('phases',[]);e.setdefault('detail','')
        else:
            if e['kind'] not in ('speech','sound','music','ambience') or e['layer'] not in ('foreground','background'):raise ValueError('Unknown audio kind')
            e.setdefault('label',e['text'])
        lo,hi=float(e['start']),float(e['end'])
        if not (math.isfinite(lo) and math.isfinite(hi) and lo<hi and lo<duration and hi>0):raise ValueError('Invalid bounds')
        if lo<0 or hi>duration:
            limits.append({'index':i,'reported':[lo,hi],'issue':'clipped to available media'})
        e['start']=max(lo,0);e['end']=min(hi,duration)
        out.append(e)
    return dict(events=out,uncertainties=raw.get('uncertainties',[]),clock_notes=limits)

def annotate(folder,sel,refs,mode,round_id,validator_override=None):
    dest=folder/f'round{round_id}'/mode
    prompt=(HERE/'prompts'/(mode+'.txt')).read_text('utf8')+f"\n片长 {sel['duration']:.3f} 秒。"
    if mode=='visual' and sel['id'] in ('sport01','sport02'):
        terms_file='badminton_bwf_v01.json' if sel['id']=='sport01' else 'standing_jump.json'
        lex=read_json(HERE.parents[2]/'sports_annotation/lexicons'/terms_file)
        if sel['id']=='sport01':lex=runtime_lexicon(lex)
        terms=[x.get('zh') or x.get('label') for x in lex['terms']]
        prompt+='\n可选领域词，须有画面证据也可用日常语言：'+'、'.join(terms)
    def check(out):
        normalize(out,mode,sel['duration'])
    v=request(dest,mode,prompt,refs,dict(clip=sel['sha256'],round=round_id),validator_override or check,CFG)
    write_json(folder/f'round{round_id}'/(mode+'.json'),v)

def main():
    parser=argparse.ArgumentParser(description='Generate three independent audiovisual annotation passes.')
    parser.add_argument('--jobs',type=int,default=8)
    args=parser.parse_args()
    selection=read_json(HERE/'selection.json')
    pending=[]
    for case in selection:
        folder=HERE/'cases'/case['id']
        for mode in ('visual','audio'):
            if (folder/f'{mode}_draws.json').exists():continue
            for n in (1,2,3):
                if not (folder/f'round{n}'/(mode+'.json')).exists():pending.append((folder,case,mode,n))
    if not pending:return
    if not os.getenv('QWEN_API_KEY'):os.environ['QWEN_API_KEY']=getpass.getpass('Qwen credential: ')
    ref_cache={folder:media(folder) for folder in {x[0] for x in pending}}
    errors=[]
    with ThreadPoolExecutor(args.jobs) as workers:
        jobs={workers.submit(annotate,folder,case,ref_cache[folder][mode],mode,n):(case['id'],mode,n)
              for folder,case,mode,n in pending}
        for job in as_completed(jobs):
            try:job.result()
            except Exception as exc:errors.append((jobs[job],str(exc)[:250]))
    if errors:raise RuntimeError(errors)

if __name__=='__main__':main()
