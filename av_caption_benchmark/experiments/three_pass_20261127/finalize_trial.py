"""Normalize independent raw samples, align instances, and derive reproducibility and overlaps."""
import argparse
import itertools
import json
import os
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed

from run_trial import HERE,CFG,annotate,media,request,read_json,write_json,normalize
import getpass

def recover(folder,sel,n,mode,refs):
    base=folder/f'round{n}'/mode
    renewal=folder/'renew'/f'round{n}'/mode
    def find():
        for path in [base,*sorted(base.glob('retry*')),renewal,*sorted(renewal.glob('retry*'))]:
            f=path/'response.txt'
            if not f.exists():continue
            try:
                s=f.read_text('utf8').strip()
                if s.startswith('```'):s='\n'.join(s.splitlines()[1:]).removesuffix('```').strip()
                v=normalize(json.loads(s),mode,sel['duration'])
            except (ValueError,KeyError,TypeError,AssertionError,AttributeError):continue
            v['source']=f.relative_to(folder).as_posix()
            return v
    res=find()
    if res is None:
        # A fresh directory plus identical task instructions for a round lacking a usable response.
        repair=folder/'renew';repair.mkdir(exist_ok=True)
        if not (repair/f'round{n}'/(mode+'.json')).exists():
            annotate(repair,sel,refs[mode],mode,n,lambda v:normalize(v,mode,sel['duration']))
        v=read_json(repair/f'round{n}'/(mode+'.json'))
        res=normalize(v,mode,sel['duration']);res['source']=(repair/f'round{n}'/(mode+'.json')).relative_to(folder).as_posix()
    return res

def interval_iou(a,b):
    inter=max(0,min(a['end'],b['end'])-max(a['start'],b['start']))
    return inter/(max(a['end'],b['end'])-min(a['start'],b['start']))

def match_and_vote(folder,mode,draws):
    byid={f'{n}.{i}':e for n,d in enumerate(draws,1) for i,e in enumerate(d['events'])}
    table={k:{f:v for f,v in e.items() if f in ('actor','kind','label','brief','text','start','end')} for k,e in byid.items()}
    prompt=(HERE/'prompts/match.txt').read_text('utf8')+'\n'+json.dumps(table,ensure_ascii=False,separators=(',',':'))
    def check(out):
        used=set()
        for g in out['groups']:
            if not isinstance(g,list) or not 2<=len(g)<=3 or len({s.split('.')[0] for s in g})!=len(g) or any(s not in byid or s in used for s in g):raise ValueError('Invalid grouping')
            used.update(g)
    cfg={**CFG,'extra_body':{**CFG['extra_body'],'temperature':0.0}}
    raw=request(folder/'verification'/'match'/mode,'align_instances',prompt,[],{'task':mode},check,cfg) if byid else {'groups':[]}
    resolved=[];grouped=set()
    for ids in raw['groups']:
        # Split doubtful pairs; keep the best compatible pair when the third interval drifts.
        def compatible(x,y):
            a,b=byid[x],byid[y]
            return (not(mode=='audio' and ('speech' in (a['kind'],b['kind'])) and a['kind']!=b['kind'])
                    and not(mode=='visual' and ('state' in (a['kind'],b['kind'])) and a['kind']!=b['kind'])
                    and interval_iou(a,b)>=0.25)
        pairs=list(itertools.combinations(ids,2))
        if all(compatible(*z) for z in pairs): chosen=ids
        else:
            allowed=[z for z in pairs if compatible(*z)]
            if not allowed:continue
            chosen=max(allowed,key=lambda z:interval_iou(byid[z[0]],byid[z[1]]))
        resolved.append(list(chosen));grouped.update(chosen)
    resolved.extend([k] for k in byid if k not in grouped)
    results=[]
    for ids in resolved:
        members=[byid[i] for i in ids]
        lo,hi=(statistics.median(e[f] for e in members) for f in ('start','end'))
        ref=min(ids,key=lambda i:abs(byid[i]['start']-lo)+abs(byid[i]['end']-hi))
        results.append(dict(members=ids,votes=len(ids),start=lo,end=hi,representative=ref,
                            example=byid[ref],start_spread=max(e['start'] for e in members)-min(e['start'] for e in members),
                            end_spread=max(e['end'] for e in members)-min(e['end'] for e in members)))
    for i,row in enumerate(sorted(results,key=lambda x:(x['start'],x['end'])),1):
        row['id']=('V' if mode=='visual' else 'A')+str(i)
    return sorted(results,key=lambda x:(x['start'],x['end'])),byid

def edges(vgroups,agroups,vs,ass):
    rows=[]
    for v,a in itertools.product(vgroups,agroups):
        if min(v['votes'],a['votes'])<2:continue
        vm={k.split('.')[0]:vs[k] for k in v['members']}
        am={k.split('.')[0]:ass[k] for k in a['members']}
        shared=sorted(vm.keys()&am.keys()); hit=[]
        for k in shared:
            if min(vm[k]['end'],am[k]['end'])>max(vm[k]['start'],am[k]['start']):hit.append(k)
        lo,hi=max(v['start'],a['start']),min(v['end'],a['end'])
        if hi>lo or hit:
            rows.append(dict(visual=v['id'],audio=a['id'],common_rounds=shared,overlap_rounds=hit,
                             median_intersection=[lo,hi] if hi>lo else None,
                             keep=hi>lo and len(hit)>=2,
                             layer_votes=[am[k]['layer'] for k in hit],
                             short=hi-lo<0.20))
    return rows

def one(folder):
    sel=read_json(folder/'selection.json');data={};groups={};by={};refs=media(folder)
    for mode in ('visual','audio'):
        draws=[recover(folder,sel,n,mode,refs) for n in (1,2,3)]
        data[mode]=draws
        write_json(folder/f'{mode}_draws.json',draws)
        groups[mode],by[mode]=match_and_vote(folder,mode,draws)
    overlap=edges(groups['visual'],groups['audio'],by['visual'],by['audio'])
    write_json(folder/'consensus.json',dict(groups=groups,edges=overlap))
    print('voted',folder.name,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('ids',nargs='*');args=p.parse_args()
    if not os.getenv('QWEN_API_KEY'):os.environ['QWEN_API_KEY']=getpass.getpass('Qwen credential: ')
    failures=[]
    with ThreadPoolExecutor(6) as pool:
        jobs={pool.submit(one,f.parent):f.parent.name for f in HERE.glob('cases/*/selection.json') if (not args.ids or f.parent.name in args.ids) and not (f.parent/'consensus.json').exists()}
        for job in as_completed(jobs):
            try:job.result()
            except Exception as ex:print('failed',jobs[job],str(ex)[:480],flush=True);failures.append(jobs[job])
    if failures:raise SystemExit(1)
