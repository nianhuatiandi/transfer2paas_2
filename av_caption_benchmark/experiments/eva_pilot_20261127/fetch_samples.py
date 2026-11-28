"""Fetch exact Shot2Story TAR members referenced in both EVA training releases."""
import hashlib
import json
import math
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
CACHE = Path(tempfile.gettempdir()) / 'eva_pair_audit_20261127'
EVA = '146a0b13c1b8fe93b16fc7b89b949436d1993c76'
REPO = 'mhan/shot2story-videos'
CHUNK = 10_240_000_000
TARGETS = [
    ('apple', '2VBRpUe8idw.10.mp4', '烹饪演示 · 糖煮苹果'),
    ('golf', 'Dkzp_IJaNpo.22.mp4', '体育转播 · 高尔夫'),
    ('timer', 'ijF-CYpTrwQ.6.mp4', '日常操作 · 灌溉定时器'),
]


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')


class Archive:
    def __init__(self):
        response = requests.get('https://huggingface.co/api/models/' + REPO, timeout=20)
        response.raise_for_status()
        self.sha = response.json()['sha']
        self.end = 16 * CHUNK + 3_542_210_560

    def read(self, start, length):
        data = bytearray()
        while len(data) < length:
            pos = start + len(data)
            idx, off = divmod(pos, CHUNK)
            n = min(CHUNK - off, length - len(data))
            name = 'release_134k_videos.tar.gz.a' + chr(ord('a') + idx)
            url = f'https://huggingface.co/{REPO}/resolve/{self.sha}/{name}'
            for attempt in range(4):
                try:
                    response = requests.get(url, params={'range_start':off,'range_end':off+n-1,'retry':attempt},
                                            headers={'Range':f'bytes={off}-{off+n-1}'}, timeout=(15,35))
                    response.raise_for_status()
                    if response.status_code != 206 or len(response.content) != n:
                        raise ValueError('Range response mismatch')
                    data.extend(response.content)
                    break
                except (requests.RequestException, ValueError):
                    if attempt == 3:
                        raise
                    time.sleep(1 + attempt)
        return bytes(data)

    def next_header(self, start):
        cursor = start // 512 * 512
        size = 1 << 20
        while cursor < self.end:
            b = self.read(cursor, min(size, self.end - cursor))
            i = b.find(b'release_134k_videos/')
            while i >= 0:
                if i % 512 == 0 and i + 512 <= len(b):
                    try:
                        item = tarfile.TarInfo.frombuf(b[i:i+512], 'utf8', 'strict')
                        if item.isfile() and item.name.endswith('.mp4'):
                            return cursor + i, item
                    except (tarfile.HeaderError, UnicodeError):
                        pass
                i = b.find(b'release_134k_videos/', i+1)
            cursor += len(b)
            size = min(4 << 20, 2 * size)
        raise EOFError('No member found')

    def locate(self, filename):
        target = filename.split('.')[0]
        lo, hi = 0, self.end
        while lo < hi:
            pos = lo if hi-lo < (8<<20) else (lo+hi)//2
            off, item = self.next_header(pos)
            name = Path(item.name).name
            ident = name.split('.')[0]
            if ident > target:
                if pos == lo:
                    break
                hi = pos // 512 * 512
            elif name == filename:
                return off, item
            elif ident == target and pos != lo:
                hi = pos // 512 * 512
            else:
                lo = off + 512 + math.ceil(item.size/512) * 512
        # A member of the target group could have been just beyond the upper bound.
        for _ in range(100):
            off, item = self.next_header(lo)
            name = Path(item.name).name
            if name == filename:
                return off, item
            if name.split('.')[0] > target:
                break
            lo = off + 512 + math.ceil(item.size/512) * 512
        raise FileNotFoundError(filename)


def main():
    rows = {}
    for kind in ('shot2story_caption_sft', 'stage2_caption_rl'):
        path = CACHE / (kind + '.jsonl')
        if not path.is_file():
            r = requests.get(f'https://huggingface.co/datasets/OPPOResearchInstitute/EVA-data/resolve/{EVA}/{path.name}',
                             timeout=120)
            r.raise_for_status()
            CACHE.mkdir(exist_ok=True)
            path.write_bytes(r.content)
        with path.open(encoding='utf8') as f:
            for line in f:
                row = json.loads(line)
                name = Path(row['video_path']).name
                if any(name == t[1] for t in TARGETS):
                    rows.setdefault(name, {})[kind] = row
    archive = Archive()

    def fetch(target):
        cid, name, domain = target
        folder = HERE/'cases'/cid
        folder.mkdir(parents=True, exist_ok=True)
        records = rows[name]
        assert len(records) == 2
        for version, row in records.items():
            save(folder/(version+'.json'), row)
        clip, locator = folder/'clip.mp4', folder/'source.json'
        if not clip.exists() or not locator.exists():
            off, item = archive.locate(name)
            data = archive.read(off+512, item.size)
            assert b'ftyp' in data[:64]
            clip.write_bytes(data)
            save(locator, dict(repo=REPO, revision=archive.sha, tar_member=item.name,
                               header_offset=off, size=item.size, eva_revision=EVA))
        digest = hashlib.sha256(clip.read_bytes()).hexdigest()
        print(cid, name, len(clip.read_bytes()), digest[:12], flush=True)
        return dict(id=cid, domain=domain, clip_sha256=digest, people_limit=3,
                    audio_source='same original MP4', filename=name)
    with ThreadPoolExecutor(3) as executor:
        cases = list(executor.map(fetch,TARGETS))
    save(HERE/'sample_manifest.json',cases)


if __name__ == '__main__':
    main()
