"""Optional curl streaming transport for large image requests on Windows."""
import json
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path


class CurlResponse:
    def __init__(self, process, first_line, status):
        self.process, self.first_line, self.status_code = process, first_line, status

    @property
    def text(self):
        return (self.first_line + self.process.stdout.read()).decode('utf-8', errors='replace')

    def iter_lines(self):
        if self.first_line:
            yield self.first_line.rstrip(b'\r\n')
        for line in self.process.stdout:
            yield line.rstrip(b'\r\n')


@contextmanager
def curl_post(url, body, key, provider):
    # The credential is passed through stdin, never via command-line arguments or a file.
    with tempfile.TemporaryDirectory(prefix='sports_api_upload_') as directory:
        work = Path(directory)
        body_path, headers_path, error_path = work / 'body.json', work / 'headers.txt', work / 'error.txt'
        body_path.write_bytes(body)
        args = ['curl.exe', '--silent', '--show-error', '--no-buffer', '--include', '--request', 'POST',
                '--connect-timeout', str(provider.get('connect_timeout_seconds', 30)),
                '--max-time', str(provider.get('request_timeout_seconds', 300)),
                '--header', 'Content-Type: application/json', '--header', 'Expect: 100-continue',
                '--dump-header', str(headers_path), '--data-binary', '@' + str(body_path), '--config', '-']
        config = 'url = ' + json.dumps(url) + '\nheader = ' + json.dumps('Authorization: Bearer ' + key) + '\n'
        with error_path.open('wb') as errors:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
            try:
                process.stdin.write(config.encode('utf-8'))
                process.stdin.close()
                status = None
                while True:
                    line = process.stdout.readline()
                    if not line:
                        process.wait(timeout=10)
                        error = error_path.read_text(encoding='utf-8', errors='replace').replace(key, '[REDACTED]')
                        raise RuntimeError('curl received no final HTTP headers: ' + error)
                    if line.startswith(b'HTTP/'):
                        status = int(line.split()[1])
                    elif not line.strip() and status is not None and status >= 200:
                        break
                # Parse headers from stdout: --dump-header can remain buffered until transfer end.
                first_line = process.stdout.readline()
                yield CurlResponse(process, first_line, status)
                return_code = process.wait(timeout=10)
                if return_code:
                    raise RuntimeError(error_path.read_text(encoding='utf-8', errors='replace').replace(key, '[REDACTED]'))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
