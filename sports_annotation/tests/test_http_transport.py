import shutil
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from sports_annotation.http_transport import curl_post


@unittest.skipUnless(shutil.which('curl.exe'), 'Windows curl is not available')
class CurlTransportTests(unittest.TestCase):
    def test_continue_then_streaming_response(self):
        captured = {}

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def do_POST(self):
                captured['authorization'] = self.headers.get('Authorization')
                captured['body'] = self.rfile.read(int(self.headers['Content-Length']))
                body = b'data: {"choices": []}\n\ndata: [DONE]\n\n'
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                pass

        server = HTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.handle_request, daemon=True)
        worker.start()
        try:
            with curl_post(f'http://127.0.0.1:{server.server_port}', b'{"test":true}', 'fixture',
                           {'connect_timeout_seconds': 5, 'request_timeout_seconds': 10}) as response:
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'data: [DONE]', list(response.iter_lines()))
            self.assertEqual(captured['body'], b'{"test":true}')
            self.assertEqual(captured['authorization'], 'Bearer fixture')
        finally:
            server.server_close()
            worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
