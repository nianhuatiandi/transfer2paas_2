import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

root = Path(__file__).resolve().parent.parent
destination = root / 'github_download_20261122' / 'transfer2paas_2-main'
headers = {'User-Agent': 'local-video-download'}

def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
        return response.read()

tree = json.loads(get('https://api.github.com/repos/nianhuatiandi/transfer2paas_2/git/trees/main?recursive=1'))
assert not tree.get('truncated')
revision = tree['sha']
expected = {f['path']: f for f in tree['tree'] if f['type'] == 'blob'}
archive_path = root / ('transfer2paas_2-' + revision[:8] + '.zip')
if not archive_path.exists():
    data = get('https://codeload.github.com/nianhuatiandi/transfer2paas_2/zip/' + revision)
    with zipfile.ZipFile(io.BytesIO(data)) as check:
        assert check.testzip() is None
    archive_path.write_bytes(data)
archive = zipfile.ZipFile(archive_path)
baseline_path = root / 'transfer2paas_2-main.zip'
baseline = zipfile.ZipFile(baseline_path) if baseline_path.exists() else None
added, updated, preserved = [], [], []
for member in archive.infolist():
    if member.is_dir():
        continue
    relative = member.filename.split('/', 1)[1]
    if relative not in expected:
        continue
    content = archive.read(member)
    blob_sha = hashlib.sha1(b'blob ' + str(len(content)).encode() + b'\0' + content).hexdigest()
    assert blob_sha == expected[relative]['sha'], relative
    target = destination / relative
    assert target.resolve().is_relative_to(destination.resolve())
    if target.exists():
        local = target.read_bytes()
        if local == content:
            continue
        baseline_name = 'transfer2paas_2-main/' + relative
        if baseline is None or baseline_name not in baseline.namelist() or local != baseline.read(baseline_name):
            preserved.append(relative)
            continue
        updated.append(relative)
    else:
        added.append(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    assert target.read_bytes() == content
print(json.dumps({'revision': revision, 'destination': str(destination), 'archive': str(archive_path), 'added_videos': [p for p in added if p.endswith('.mp4')], 'other_added_count': sum(not p.endswith('.mp4') for p in added), 'updated': updated, 'local_modifications_preserved': preserved}, ensure_ascii=False, indent=2), flush=True)
