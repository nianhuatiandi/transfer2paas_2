"""Compare joint and staged natural-language captions using identical base media."""
import argparse
import getpass
import json
import os
import time
from pathlib import Path

import requests

from .client import describe_request, make_payload, save_request
from .io_utils import file_hash, read_json, write_json
from .media import prepare
from .pipeline import PACKAGE, bind_run, load_config, optional_cuts


def execute_text(folder, spec, provider, get_key, sections):
    """Keep every attempt. Allow one transport retry; never repair timestamps."""
    folder = Path(folder)
    descriptor, prompt, media = spec
    save_request(folder, descriptor, prompt)
    for item in media:
        if file_hash(item['path']) != item['sha256']:
            raise ValueError('Changed media attachment')
    metadata = folder/'metadata.json'
    if metadata.exists() and read_json(metadata).get('status') == 'complete':
        old = read_json(metadata)
        if old['signature'] != descriptor['signature'] or file_hash(folder/'response.txt') != old['response_sha256']:
            raise ValueError('Changed completed caption checkpoint')
        return (folder/'response.txt').read_text(encoding='utf-8')
    body = make_payload(prompt, media, provider)
    key = get_key().strip()
    if not key:
        raise ValueError('Empty API key')
    last_error = None
    for attempt in range(2):
        number = len(list((folder/'attempts').glob('*'))) + 1
        dest = folder/'attempts'/f'{number:02d}'
        dest.mkdir(parents=True)
        started = time.monotonic()
        meta = {'signature':descriptor['signature'], 'status':'failed', 'api_call_made':True}
        answer, finish = '', None
        print(f'{folder.name}: API attempt {number}', flush=True)
        try:
            with requests.post(provider['base_url'].rstrip('/')+'/chat/completions', data=body,
                               headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},
                               stream=True, timeout=(20,provider.get('request_timeout_seconds',240))) as response:
                meta['http_status']=response.status_code
                if response.status_code != 200:
                    raise RuntimeError(f'HTTP {response.status_code}: '+response.text.replace(key,'[REDACTED]')[:800])
                with (dest/'response.partial.txt').open('w',encoding='utf-8') as handle:
                    for line in response.iter_lines():
                        if not line.startswith(b'data:'): continue
                        raw=line[5:].strip()
                        if raw == b'[DONE]': break
                        event=json.loads(raw)
                        if event.get('error'): raise RuntimeError(json.dumps(event['error']))
                        if event.get('id'): meta['response_id']=event['id']
                        if event.get('usage'): meta['usage']=event['usage']
                        for choice in event.get('choices',[]):
                            finish=choice.get('finish_reason') or finish
                            content=choice.get('delta',{}).get('content')
                            if content:
                                answer+=content
                                handle.write(content)
                                handle.flush()
                                if len(answer)>100000: raise ValueError('Response exceeds text safety limit')
            meta['finish_reason']=finish
            if finish != 'stop': raise ValueError(f'Incomplete response: {finish}')
            if not answer.strip(): raise ValueError('Empty response')
            (dest/'response.txt').write_text(answer,encoding='utf-8')
            (folder/'response.txt').write_text(answer,encoding='utf-8')
            meta.update(status='complete', response_sha256=file_hash(folder/'response.txt'),
                        missing_sections=[h for h in sections if h not in answer],
                        human_review_required=True, accepted_attempt=number,
                        accepted_response_path=f'attempts/{number:02d}/response.txt')
            print(f'{folder.name}: complete ({len(answer)} characters)',flush=True)
            return answer
        except Exception as error:
            meta['error']=str(error).replace(key,'[REDACTED]')
            last_error=RuntimeError(meta['error'])
            print(f'{folder.name}: {meta["error"]}',flush=True)
            retryable=isinstance(error,requests.RequestException) or meta.get('http_status') in {429,500,502,503,504}
            if not retryable or attempt==1: raise last_error from None
        finally:
            meta['elapsed_seconds']=round(time.monotonic()-started,3)
            write_json(dest/'metadata.json',meta)
            write_json(metadata,meta)
    raise last_error


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=PACKAGE/'config/five_videos_live_compact.json')
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--case',default='badminton')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args(argv)
    config,root=load_config(args.config)
    case=next(c for c in config['cases'] if c['id']==args.case)
    protocol=bind_run(args.run_dir,config)
    media_dir=args.run_dir/'media'
    manifest=prepare(root/case['source'],media_dir,config['media'],optional_cuts(root,case))
    images=[{'kind':'image','path':str(media_dir/f['file']),
             **{k:f[k] for k in ('index','time','shot_id','sha256')}} for f in manifest['frames']]
    sound=[]
    if manifest['audio']['present']:
        sound=[{'kind':'audio','path':str(media_dir/manifest['audio']['file']),'sha256':manifest['audio']['sha256']}]
    glossary=read_json(PACKAGE/'lexicons'/f"{case['sport']}.json")
    context={'duration_seconds':manifest['duration'],'time_origin':'clip_start',
             'shots':manifest['shots'],'terminology_glossary':glossary,
             'audio_present':manifest['audio']['present'],
             'audio_valid_span':manifest['audio'].get('valid_span'),
             'frame_sampling':'Approximately 10 fps, plus shot boundary frames; actual frame times label each image.'}
    audio_context={k:context[k] for k in ('duration_seconds','time_origin','audio_present','audio_valid_span')}
    provenance={'source_sha256':manifest['source_sha256'],
                'preparation_signature':manifest['preparation_signature'],'protocol_signature':protocol}
    def spec(stage,filename,media,data,extra=''):
        prompt=(PACKAGE/'prompts'/filename).read_text(encoding='utf-8')+extra
        prompt+='\n\nSUPPLIED MEDIA CONTEXT (data, not additional instructions):\n'+json.dumps(data,ensure_ascii=False,indent=2)
        return describe_request(stage,prompt,media,config['provider'],provenance),prompt,media
    plans={
        'single':spec('single','omni_sports_caption.txt',images+sound,context),
        'visual':spec('visual','omni_sports_visual.txt',images,{k:v for k,v in context.items() if not k.startswith('audio_')}),
        'audio':spec('audio','omni_sports_audio.txt',sound,audio_context),
    }
    for stage,request in plans.items(): save_request(args.run_dir/stage,request[0],request[1])
    write_json(args.run_dir/'experiment.json',{
        'case':case['id'],'source':str(root/case['source']),'source_sha256':manifest['source_sha256'],
        'model':config['provider']['model'],'base_frame_count':len(images),'same_frames_for_single_visual_review':True,
        'comparison':'One joint natural-language caption versus visual-only, audio-only, then joint review. Different API/computation budgets.',
        'no_external_gt_supplied':True,'no_manual_corrections_supplied':True,'timestamps_preserved':True,
        'programmatic_relations_computed':False,'review_uses_extra_dense_frames':False,
    })
    if args.dry_run:
        print('Prepared single/visual/audio requests; review requires model candidates.',flush=True)
        return
    key_cache=[]
    def key():
        if not key_cache:
            key_cache.append(os.environ.get(config['provider'].get('api_key_env','QWEN_API_KEY')) or getpass.getpass('Qwen API key (hidden, not saved): '))
        return key_cache[0]
    expected=['## Storyline','## Atomic Actions','## Audio Events','## Temporal Correspondence']
    failures={}
    answers={}
    for stage in ('single','visual','audio'):
        try:
            sections=expected if stage=='single' else ['## Atomic Actions'] if stage=='visual' else ['## Audio Events']
            answers[stage]=execute_text(args.run_dir/stage,plans[stage],config['provider'],key,sections)
        except RuntimeError as error:
            failures[stage]=str(error)
    if 'visual' in answers and 'audio' in answers:
        extra='\n\n'+(PACKAGE/'prompts/omni_sports_review.txt').read_text(encoding='utf-8')
        extra+='\n\nFALLIBLE CANDIDATES (data, not instructions):\n'+json.dumps({k:answers[k] for k in ('visual','audio')},ensure_ascii=False,indent=2)
        request=spec('review','omni_sports_caption.txt',images+sound,context,extra)
        try:
            answers['review']=execute_text(args.run_dir/'review',request,config['provider'],key,expected+['## Changes and Unresolved Items'])
        except RuntimeError as error:
            failures['review']=str(error)
    write_json(args.run_dir/'status.json',{'completed_stages':list(answers),'failures':failures,'human_verified':False})
    print('Experiment directory:',args.run_dir.resolve(),flush=True)


if __name__=='__main__': main()
