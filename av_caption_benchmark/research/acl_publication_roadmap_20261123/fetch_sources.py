import concurrent.futures
import hashlib
import json
from pathlib import Path

import fitz
import requests

ROOT = Path(__file__).resolve().parent / 'sources'
ROOT.mkdir(parents=True, exist_ok=True)
SOURCES = {
    'fave': 'https://openaccess.thecvf.com/content/CVPR2026/papers/Lu_FAVE_A_Structured_Benchmark_for_Fine-Grained_Audio-Visual_Temporal_Evaluation_in_CVPR_2026_paper.pdf',
    'fave_supp': 'https://openaccess.thecvf.com/content/CVPR2026/supplemental/Lu_FAVE_A_Structured_CVPR_2026_supplemental.pdf',
    'capquiz': 'https://aclanthology.org/2026.acl-long.777.pdf',
    'tuna': 'https://aclanthology.org/2025.acl-long.91.pdf',
    'avut': 'https://aclanthology.org/2025.emnlp-main.333.pdf',
    'vidomni': 'https://aclanthology.org/2026.emnlp-main.104.pdf',
    'avtime': 'https://arxiv.org/pdf/2610.26046',
    'egoactionbench': 'https://arxiv.org/pdf/2611.03646',
    'kpm': 'https://arxiv.org/pdf/2602.17768',
}

def fetch(item):
    name, url = item
    result = {'name': name, 'url': url}
    try:
        response = requests.get(url, timeout=(12, 40))
        response.raise_for_status()
        data = response.content
        if not data.startswith(b'%PDF'):
            raise ValueError('Response is not a PDF')
        (ROOT / f'{name}.pdf').write_bytes(data)
        with fitz.open(stream=data, filetype='pdf') as doc:
            text = '\n\n'.join(f'--- PAGE {i + 1} ---\n{page.get_text()}' for i, page in enumerate(doc))
            result['pages'] = len(doc)
        (ROOT / f'{name}.txt').write_text(text, encoding='utf-8')
        result.update(status='downloaded_and_text_extracted', bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except Exception as exc:
        result.update(status='failed', error=str(exc))
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return result

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(fetch, SOURCES.items()))
    (ROOT / 'manifest.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
