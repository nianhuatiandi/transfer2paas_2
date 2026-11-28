"""Count EVA audio-to-visual questions using the released one-based judge indices."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

HERE=Path(__file__).resolve().parent


def count(records):
    videos=queries=multi=multi_action=0
    for record in records:
        videos+=1
        for query in record['a2v_query_list']:
            candidates=query['visual_candidates_for_judge']
            indices=query['selected_visual_indices_new']
            if len(set(indices))!=len(indices) or not all(type(i)==int and 1<=i<=len(candidates) for i in indices):
                raise ValueError('Invalid candidate reference')
            labels=[candidates[i-1]['type'].lower() for i in indices]
            queries+=1
            multi+=len(labels)>1
            multi_action+=labels.count('action')>=2
    return dict(videos=videos,queries=queries,multiple_visual_events=multi,at_least_two_action_labels=multi_action)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=Path(tempfile.gettempdir())/'eva_pair_audit_20261127')
    args=parser.parse_args()
    result={}
    for stage in ('stage1_caption_rl','stage2_caption_rl'):
        data=(args.directory/(stage+'.jsonl')).read_bytes()
        result[stage]=dict(sha256=hashlib.sha256(data).hexdigest(),**count(json.loads(line) for line in data.splitlines()))
    result['pilot']=count(json.loads(f.read_text('utf8')) for f in (HERE/'cases').glob('*/stage2_caption_rl.json'))
    (HERE/'official_query_counts.json').write_text(json.dumps(result,indent=2),encoding='utf8')
