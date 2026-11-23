import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
seed = json.loads((ROOT.parent / 'atomic_av_caption_benchmark_20261123/papers.json').read_text(encoding='utf-8'))
papers = []
for old in seed['papers']:
    item = {k: v for k, v in old.items() if k != 'relevance'}
    item['historical_relevance_note'] = old.get('relevance', '')
    item['verification_provenance'] = 'Inherited from earlier 2026-11-23 survey; not all papers re-read this turn.'
    papers.append(item)
updates = {
    'R01': '专业层级和子动作边界已有先例。',
    'R02': '专业步骤与时间分解已有先例；质量评分不同于caption准确性。',
    'R20': '已核对全文评测节：原子动作、手归属、语义/时间/覆盖分项；直接视觉侧先例。',
    'R34': '已下载论文及补充：同期跨模态QA已有先例；其事件构建协议要求持续超过5秒。',
    'R35': '同步/先后与绑定已有先例；专业原子区间需另证增量。',
    'R38': '已核对原子subshot与重叠时间区间；EVSA为音频事件到镜头关联。',
    'R39': '已有时间定位、跨模态定位、同步及扰动诊断；不能把时序诊断泛称首次。',
    'R58': '已下载全文；以消除文本捷径支撑音频中心benchmark的有效性。',
    'R69': 'scene级时序caption；是时间和内容联合评分的必要对照。',
    'R70': '已下载全文；caption的信息覆盖/真实性及人类相关性是ACL评测论文先例。',
}
for p in papers:
    p['current_scope_note'] = updates.get(p['id'], '背景参照；应在原子动作描述与纯同期音画关系定义下使用。')
    if p['id'] in updates:
        p['current_review_note'] = updates[p['id']]
for row in json.loads((ROOT/'new_references.json').read_text(encoding='utf-8')):
    name, title, year, venue, url, contribution, relevance = row
    papers.append(dict(id=f'R{len(papers)+1:02d}',name=name,title=title,year=year,publication=venue,url=url,
                       contribution=contribution,current_scope_note=relevance,
                       verification_provenance='Primary source checked this turn or preceding case audit; see report for depth.'))
assert len(papers) == 80
assert len({p['id'] for p in papers}) == len(papers)
assert len({p['url'].rstrip('/') for p in papers}) == len(papers)
out = dict(as_of='2026-11-23', count=len(papers),
           scope='Sports-centered atomic action captions; audio-action temporal co-occurrence only; external transcription for GT only.',
           method='70-paper earlier scope review plus 10 relevant additions. Not a claim of full-text reading of all 80. Current report separates evidence from proposals.',
           papers=papers)
(ROOT/'bibliography.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
lines=['相关论文索引：80 项','日期：2026-11-23','阅读深度：此前70项范围综述+本轮10项补充；非80篇全文逐页精读。','当前任务：专业原子动作与音频片段的纯同期关系。历史语义指向建议不作为当前提案。','']
for p in papers:
    lines.extend([f"[{p['id']}] {p['name']} | {p['publication']}",p['title'],p['url'],
                  '已有贡献：'+p['contribution'],'当前对照：'+p['current_scope_note'],''])
(ROOT/'bibliography.txt').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'papers':len(papers),'outputs':['bibliography.json','bibliography.txt']}))
