from pathlib import Path
from collections import Counter
import html
import json
import re

ROOT = Path(__file__).resolve().parents[1] / 'research' / 'atomic_av_caption_benchmark_20261123'
papers_file = ROOT / 'papers.json'
catalog = json.loads(papers_file.read_text(encoding='utf-8'))
analysis = json.loads((ROOT / 'analysis.json').read_text(encoding='utf-8'))
papers = catalog['papers']
for p in papers:
    if p['id'] == 'R22':
        p.update(year=2018, publication='AAAI 2018；arXiv 初版 2017')
    if p['id'] == 'R63':
        p.update(year=2022, publication='ICASSP 2022；arXiv 初版 2021')
    if p['id'] in {'R34', 'R36'}:
        p['review_depth'] = '重点核对原文方法、评测或补充材料段落'
papers_file.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

lookup = {p['id']: p for p in papers}
assert len(papers) == len(lookup) == 70
assert len({p['title'].casefold() for p in papers}) == 70
assert len({p['url'] for p in papers}) == 70
all_refs = set(re.findall(r'\[(R\d+)\]', json.dumps(analysis, ensure_ascii=False)))
assert all_refs <= lookup.keys(), sorted(all_refs - lookup.keys())

def rich(text):
    escaped = html.escape(text)
    return re.sub(r'\[(R\d+)\]', lambda m: f'<a class="citation" href="#paper-{m[1]}" title="{html.escape(lookup[m[1]]["name"], quote=True)}">[{m[1]}]</a>', escaped)

parts = []
plain = [analysis['title'], f'检索截止：{analysis["as_of"]}', '']
for i, section in enumerate(analysis['sections'], 1):
    parts.append(f'<section id="section-{i}"><h2><span>{i:02}</span>{html.escape(section["title"])}</h2>')
    plain.extend([f'{i:02}. {section["title"]}', ''])
    for p in section.get('paragraphs', []):
        parts.append(f'<p>{rich(p)}</p>')
        plain.extend([p, ''])
    if 'table' in section:
        table = section['table']
        parts.append('<div class="table-wrap"><table><thead><tr>')
        parts.extend(f'<th>{html.escape(x)}</th>' for x in table['columns'])
        parts.append('</tr></thead><tbody>')
        plain.extend([' | '.join(table['columns']), ''])
        for row in table['rows']:
            parts.append('<tr>' + ''.join(f'<td>{rich(x)}</td>' for x in row) + '</tr>')
            plain.append(' | '.join(row))
        plain.append('')
        parts.append('</tbody></table></div>')
    parts.append('</section>')

parts.append('<section id="official"><h2><span>13</span>会议官方依据</h2><ul>')
plain.extend(['13. 会议官方依据（不计入70篇论文）', ''])
for source in analysis['official_sources']:
    parts.append(f'<li><a href="{html.escape(source["url"])}" target="_blank" rel="noopener noreferrer">{html.escape(source["title"])}</a></li>')
    plain.extend([source['title'], source['url'], ''])
parts.append('</ul></section>')

counts = Counter(p['category'] for p in papers)
options = ''.join(f'<option value="{html.escape(c)}">{html.escape(c)} · {n}</option>' for c, n in counts.items())
parts.append('<section id="bibliography"><h2><span>14</span>70篇论文：来源、工作与项目意义</h2>')
parts.append('<p class="muted">会议与预印本状态按本次核验记录。标题或编号可定位论文；“项目意义”是本报告的分析，不是原论文的自我评价。</p>')
parts.append(f'<div class="filters"><label>检索<input id="search" type="search" placeholder="题目、术语、年份或编号" autocomplete="off"></label><label>方向<select id="category"><option value="">全部方向 · 70</option>{options}</select></label><button id="reset" type="button">重置</button><output id="count" aria-live="polite">70 / 70 篇</output></div>')
plain.extend(['14. 70篇论文清单', ''])
for p in papers:
    haystack = ' '.join(str(v) for v in p.values()).casefold()
    parts.append(f'<article class="paper" id="paper-{p["id"]}" data-category="{html.escape(p["category"], quote=True)}" data-search="{html.escape(haystack, quote=True)}">')
    parts.append(f'<div class="paper-top"><span class="pid">{p["id"]}</span><span class="tag">{html.escape(p["category"])}</span><span class="year">{p["year"]}</span></div>')
    parts.append(f'<h3><a href="{html.escape(p["url"], quote=True)}" target="_blank" rel="noopener noreferrer">{html.escape(p["title"])}</a></h3>')
    parts.append(f'<p class="publication">{html.escape(p["publication"])}</p>')
    parts.append(f'<p><b>工作：</b>{html.escape(p["contribution"])}</p><p><b>对项目的意义：</b>{html.escape(p["relevance"])}</p>')
    parts.append(f'<p class="depth">{html.escape(p["review_depth"])}</p></article>')
    plain.extend([f'[{p["id"]}] {p["title"]}', f'{p["year"]} | {p["publication"]} | {p["category"]}', f'来源：{p["url"]}', f'工作：{p["contribution"]}', f'对项目的意义：{p["relevance"]}', f'核验深度：{p["review_depth"]}', ''])
parts.append('<p id="empty" hidden>没有匹配的论文，请调整检索词。</p></section>')

css = '''
:root{color-scheme:light;--ink:#172c3d;--muted:#526578;--accent:#126d78;--line:#d9e2e7;--paper:#fff;--bg:#f5f7f9}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:24px}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;line-height:1.85;font-size:16px}a{color:var(--accent);text-underline-offset:3px}a:hover{text-decoration-thickness:2px}header{background:#102d3c;color:#f5fbff;padding:52px max(24px,calc((100vw - 1120px)/2));border-bottom:5px solid #37a2a4}header .eyebrow{font-size:13px;letter-spacing:.12em;color:#a6d8df}h1{font-size:clamp(27px,4vw,40px);line-height:1.4;max-width:920px;margin:12px 0 20px}header p{max-width:900px;color:#cee0e7;margin:0}nav{display:flex;gap:12px;flex-wrap:wrap;margin-top:23px}nav a{color:#e8f8fb;border:1px solid #678c9b;padding:6px 13px;border-radius:6px;text-decoration:none;font-size:14px}.stats{display:flex;gap:14px;flex-wrap:wrap;margin:24px 0 0}.stat{font-size:13px;color:#c8dfe5}.stat b{font-size:22px;color:#fff;margin-right:6px}main{max-width:1120px;margin:0 auto;padding:16px 24px 70px}section{background:var(--paper);border:1px solid var(--line);padding:28px 32px;border-radius:10px;margin:22px 0}h2{font-size:23px;line-height:1.5;margin:0 0 18px}h2 span{font-size:13px;color:#527b87;display:block;margin-bottom:4px;letter-spacing:.12em}p{margin:13px 0}section:first-child p:first-of-type{font-weight:600;border-left:4px solid #168590;padding-left:18px}.citation{font-size:.83em;margin:0 2px;text-decoration:none;white-space:nowrap}.table-wrap{overflow:auto;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px;min-width:640px;line-height:1.7}th,td{padding:13px 14px;border:1px solid var(--line);vertical-align:top;text-align:left}th{background:#edf4f6;font-weight:650}td:first-child{width:24%;font-weight:600}.muted,.publication,.depth{color:var(--muted);font-size:13px}.filters{display:flex;gap:12px;align-items:end;flex-wrap:wrap;background:#edf4f6;border:1px solid #d9e5e9;border-radius:8px;padding:15px;margin:20px 0}.filters label{font-size:12px;display:flex;flex-direction:column;gap:5px}.filters label:first-child{flex:1;min-width:220px}input,select,button{font:inherit;color:var(--ink);background:white;border:1px solid #a8bec8;border-radius:5px;padding:9px 11px;min-height:41px}button{cursor:pointer}output{font-size:13px;white-space:nowrap;padding-bottom:8px}.paper{padding:23px 0;border-bottom:1px solid var(--line);scroll-margin-top:22px}.paper:last-of-type{border-bottom:0}.paper:target{background:#edf9f5;box-shadow:0 0 0 14px #edf9f5}.paper-top{display:flex;align-items:center;gap:10px}.pid{font-family:monospace;font-weight:700;color:#147282}.tag{font-size:11px;padding:2px 8px;background:#edf2f5;border-radius:4px;color:#536a79}.year{margin-left:auto;font-size:12px;color:#617789}h3{font-size:17px;line-height:1.55;margin:9px 0}h3 a{text-decoration:none}.paper p{font-size:14px;margin:7px 0}.paper .depth{font-size:12px}footer{color:var(--muted);font-size:13px;text-align:center;padding:25px}[hidden]{display:none!important}:focus-visible{outline:3px solid #e2a23c;outline-offset:3px}
@media(max-width:640px){header{padding:30px 20px}main{padding:5px 12px 35px}section{padding:20px 18px}h2{font-size:20px}.filters{align-items:stretch}.filters label{width:100%}.stats{gap:9px 18px}}
@media print{body{background:white;font-size:11pt}header{background:white;color:#172c3d;border-bottom:2px solid #126d78;padding:0 0 18px}header p,header .eyebrow,.stat,.stat b{color:#172c3d}nav,.filters{display:none}main{max-width:none;padding:0}section{border:0;border-radius:0;padding:12px 0;margin:10px 0}h2,h3{break-after:avoid}.paper{break-inside:avoid}.paper[hidden]{display:block!important}a{color:inherit}.table-wrap{overflow:visible}table{min-width:0;font-size:9pt}}
'''
script = '''
const input=document.getElementById('search'), category=document.getElementById('category'), cards=[...document.querySelectorAll('.paper')];
function filter(){const q=input.value.trim().toLocaleLowerCase(), cat=category.value;let n=0;for(const el of cards){el.hidden=!(el.dataset.search.includes(q)&&(!cat||el.dataset.category===cat));if(!el.hidden)n++;}document.getElementById('count').textContent=n+' / '+cards.length+' 篇';document.getElementById('empty').hidden=n!==0;}
input.addEventListener('input',filter);category.addEventListener('change',filter);document.getElementById('reset').addEventListener('click',()=>{input.value='';category.value='';filter();});
function revealHash(){if(location.hash.startsWith('#paper-')){const el=document.getElementById(location.hash.slice(1));if(el){if(el.hidden){input.value='';category.value='';filter();}el.scrollIntoView();}}}
window.addEventListener('hashchange',revealHash);window.addEventListener('load',revealHash);
'''
stats = ''.join(f'<span class="stat"><b>{n}</b>{html.escape(c)}</span>' for c, n in counts.items())
document = f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(analysis['title'])}</title><style>{css}</style></head><body><header><div class="eyebrow">RESEARCH REVIEW · 2026-11-23</div><h1>细粒度原子动作<br>音视频 Caption Benchmark</h1><p>70篇论文调研、创新性判断、GT与judge设计，以及ACL / ICML投稿定位。核心范围：可按一致标准拆分动作、人物不超过2人的完整音视频。</p><div class="stats">{stats}</div><nav aria-label="报告导航"><a href="#section-1">研究判断</a><a href="#section-3">近邻对比</a><a href="#section-7">Judge设计</a><a href="#section-10">投稿定位</a><a href="#bibliography">70篇文献</a></nav></header><main>{''.join(parts)}</main><footer>定向范围综述 · 论文事实与研究建议分开表述 · 未执行新的benchmark实验</footer><script>{script}</script></body></html>'''
(ROOT / 'report.html').write_text(document, encoding='utf-8')
(ROOT / 'report.txt').write_text('\n'.join(plain), encoding='utf-8')
(ROOT / 'bibliography.txt').write_text('\n'.join(f'[{p["id"]}] {p["title"]}\n{p["publication"]}\n{p["url"]}\n' for p in papers), encoding='utf-8')

from bs4 import BeautifulSoup
soup = BeautifulSoup(document, 'html.parser')
ids = [el['id'] for el in soup.find_all(id=True)]
assert len(ids) == len(set(ids))
assert len(soup.select('article.paper')) == 70
assert all(a['href'][1:] in ids for a in soup.select('a[href^="#"]'))
assert '\ufffd' not in document
validation = {'paper_count':len(papers), 'unique_titles':70, 'unique_source_urls':70, 'category_counts':dict(counts), 'report_sections':len(analysis['sections']), 'paper_links_in_report':len(soup.select('article.paper h3 a')), 'internal_links_valid':True, 'duplicate_html_ids':False, 'replacement_characters':0, 'raw_model_calls_in_this_task':0}
(ROOT / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(json.dumps(validation, ensure_ascii=True))
print(str(ROOT / 'report.html'))
