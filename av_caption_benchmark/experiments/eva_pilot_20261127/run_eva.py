"""Run the unchanged audiovisual annotation stages and the frozen v6 visual stages."""
import argparse
import audioop
import getpass
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import av

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'motionatlas_holdout20_20261127'))
sys.path.insert(0, str(HERE.parent / 'cross_domain_pilot_20261126'))
import run_frozen
import unified_pipeline as pipeline
from sports_annotation.media import ffmpeg_path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--geometry-python', required=True)
    parser.add_argument('--wait-for-media', action='store_true')
    parser.add_argument('--case-id', choices=('apple','timer','golf'))
    args=parser.parse_args()
    if not os.environ.get('QWEN_API_KEY'):
        os.environ['QWEN_API_KEY']=getpass.getpass('Qwen credential: ')
    run_frozen.HERE=HERE
    run_frozen.BASE=HERE/'base'
    run_frozen.OUT=HERE/'revisions'
    cfg=pipeline.read_json(pipeline.PACKAGE/'runs/badminton_bwf_hierarchical_20261125_v01/protocol.json')['config']
    cfg['provider']['connect_timeout_seconds']=90
    for _ in range(180 if args.wait_for_media else 0):
        if (HERE/'sample_manifest.json').is_file():
            break
        time.sleep(5)
    cases=pipeline.read_json(HERE/'sample_manifest.json')
    if args.case_id:
        cases=[c for c in cases if c['id']==args.case_id]

    def one(case):
        cid=case['id']
        source=HERE/'cases'/cid
        clip=source/'clip.mp4'
        row=pipeline.read_json(source/'shot2story_caption_sft.json')
        with av.open(str(clip)) as cont:
            stream=cont.streams.audio[0]
            duration=cont.duration/av.time_base
            pcm=subprocess.check_output([ffmpeg_path(),'-v','error','-i',str(clip),'-map','0:a:0',
                                         '-ac','1','-ar','16000','-f','s16le','pipe:1'])
            peak=audioop.max(pcm,2)
            if abs(duration-row['duration']) > 0.3 or peak<=0:
                raise ValueError(f'{cid} duration or audio mismatch: {duration}, {peak}')
            pipeline.write_json(source/'media_check.json',dict(duration=duration,eva_duration=row['duration'],
                                audio_codec=stream.codec_context.name,audio_peak_native_units=peak))
        base=HERE/'base'/'cases'/cid/'annotations.json'
        if not base.exists():
            for attempt in range(3):
                try:
                    pipeline.process_case(case, HERE/'base', cfg, 'both', source)
                    break
                except RuntimeError:
                    if attempt==2:
                        raise
                    time.sleep(3)
        status=run_frozen.run_case(cid,os.environ.copy(),args.geometry_python)
        if status!='complete':
            raise ValueError(f'{cid}: {status}')
        return cid
    errors=[]
    with ThreadPoolExecutor(3) as workers:
        jobs={workers.submit(one,c):c['id'] for c in cases}
        for future in as_completed(jobs):
            try:
                print(future.result(),'complete',flush=True)
            except Exception as exc:
                errors.append((jobs[future],str(exc)))
                print(jobs[future],type(exc).__name__,str(exc)[:1500],flush=True)
    if errors:
        sys.exit(1)


if __name__=='__main__':
    main()
