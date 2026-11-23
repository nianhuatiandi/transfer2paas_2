import getpass
import json
import requests

base_url = 'https://maas.qianwenaiapi.com/compatible-mode/v1'
model = 'qwen3.8-omni-flash'
key = getpass.getpass('API key (hidden): ').strip()
try:
    response = requests.post(
        base_url + '/chat/completions',
        headers={'Authorization': 'Bearer ' + key},
        json={'model': model, 'messages': [{'role': 'user', 'content': '只回复：调用成功'}], 'stream': True, 'enable_thinking': False, 'max_tokens': 32, 'stream_options': {'include_usage': True}},
        stream=True, timeout=(15, 60),
    )
    print('HTTP:', response.status_code, flush=True)
    if response.status_code != 200:
        print(response.text.replace(key, '[REDACTED]')[:1500], flush=True)
        raise SystemExit(1)
    text = ''
    usage = None
    for line in response.iter_lines():
        if not line.startswith(b'data: '):
            continue
        payload = line[6:]
        if payload == b'[DONE]':
            break
        chunk = json.loads(payload)
        for choice in chunk.get('choices', []):
            text += choice.get('delta', {}).get('content') or ''
        if chunk.get('usage'):
            usage = chunk['usage']
    print('Model:', model)
    print('Reply:', text.replace(key, '[REDACTED]'))
    print('Usage:', json.dumps(usage, ensure_ascii=False))
    if not text:
        raise SystemExit('No text reply received.')
except requests.RequestException as exc:
    print('Request failed:', str(exc).replace(key, '[REDACTED]'))
    raise SystemExit(1)
