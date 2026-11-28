import getpass
import json
import os
from concurrent.futures import ThreadPoolExecutor,as_completed
from run_trial import HERE,CFG,media,read_json,request,write_json

probes=read_json(HERE/'probes.json')
extra={'timer':['操作者明显把螺丝拧紧，能从可见的螺丝位移确定方向。'],
       'sew':['折边时手拿出金属别针并穿过布料固定。']}

def one(cid):
    folder=HERE/'cases'/cid
    selected=[p[1] for p in probes[cid]]+extra.get(cid,[])
    rows=[{'id':str(i+1),'claim':s} for i,s in enumerate(selected)]
    prompt=(HERE/'prompts/verify.txt').read_text('utf8')+'\n'+json.dumps(rows,ensure_ascii=False)
    refs=media(folder)
    d=read_json(folder/'selection.json')['duration']
    def check(out):
        vals=out['checks']
        if [str(i['id']) for i in vals]!=[r['id'] for r in rows]:raise ValueError('Missing verification IDs')
        for v in vals:
            if v['verdict'] not in ('supported','contradicted','unclear') or not v['evidence']:raise ValueError('Invalid verdict')
            t=v.get('time_s')
            if t is not None and not 0<=t<=d+.05:raise ValueError('Outside clip')
    cfg={**CFG,'extra_body':{**CFG['extra_body'],'temperature':0.1}}
    out=request(folder/'verification'/'replay','replay',prompt,refs['visual']+refs['audio'],{'source':cid},check,cfg)
    write_json(folder/'replay.json',{'claims':rows,'checks':out['checks']})
    print(cid,[a['verdict'] for a in out['checks']],flush=True)

if __name__=='__main__':
    if not os.getenv('QWEN_API_KEY'):os.environ['QWEN_API_KEY']=getpass.getpass('Qwen credential: ')
    with ThreadPoolExecutor(4) as ex:
        jobs=[ex.submit(one,c) for c in ['sport01','dia01','greet','timer','sew','ugc03'] if not (HERE/'cases'/c/'replay.json').exists()]
        for j in as_completed(jobs):j.result()
