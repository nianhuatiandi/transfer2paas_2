import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

repo = 'nianhuatiandi/transfer2paas_2'
path = Path(__file__).resolve().parent.parent / 'transfer2paas_2' / 'standing_long_jump_1039046118_0-7s.mp4'
data = path.read_bytes()
blob_sha = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n', capture_output=True, text=True, env=env, timeout=30)
if result.returncode:
    raise SystemExit('GitHub credential lookup failed; no credentials printed.')
credentials = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
token = credentials.get('password')
if not token:
    raise SystemExit('No GitHub credential available.')
headers = {'Authorization': 'Bearer ' + token, 'Accept': 'application/vnd.github+json', 'User-Agent': 'local-video-upload', 'X-GitHub-Api-Version': '2022-11-28'}
url = 'https://api.github.com/repos/' + repo + '/contents/' + path.name

def request(method, target, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(target, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404 and method == 'GET':
            return None
        raise RuntimeError('GitHub API returned HTTP ' + str(exc.code)) from None

info = request('GET', 'https://api.github.com/repos/' + repo)
branch = info['default_branch']
existing = request('GET', url + '?ref=' + branch)
if existing and existing['sha'] != blob_sha:
    raise SystemExit('A different file already exists at the destination; leaving it untouched.')
if not existing:
    response = request('PUT', url, {'message': 'Add standing long jump video clip from 0 to 7 seconds', 'content': base64.b64encode(data).decode(), 'branch': branch})
    print('Commit:', response['commit']['sha'])
verified = request('GET', url + '?ref=' + branch)
assert verified['sha'] == blob_sha and verified['size'] == len(data)
print('Verified:', verified['html_url'])
print('Bytes:', verified['size'])
