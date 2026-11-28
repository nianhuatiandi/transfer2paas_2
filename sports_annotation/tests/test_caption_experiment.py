import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import requests

from sports_annotation.caption_experiment import execute_text
from sports_annotation.client import describe_request
from sports_annotation.io_utils import read_json


class Response:
    status_code=200
    def __init__(self,fail=False): self.fail=fail
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def iter_lines(self):
        yield b'data: {"id":"mock-only","choices":[{"delta":{"content":"## Storyline\\nMock fixture"}}]}'
        if self.fail: raise requests.exceptions.ChunkedEncodingError('Synthetic dropped stream')
        yield b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}'


class TextClientTests(unittest.TestCase):
    def test_dropped_attempt_preserved_and_completed_response_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            provider={'base_url':'https://example.invalid','model':'mock','max_tokens':100}
            descriptor=describe_request('test','fixture',[],provider,{})
            spec=(descriptor,'fixture',[])
            with patch('sports_annotation.caption_experiment.requests.post',side_effect=[Response(True),Response()]) as http:
                result=execute_text(root,spec,provider,lambda:'fake-test-key',['## Storyline'])
            self.assertEqual(http.call_count,2)
            self.assertEqual(read_json(root/'attempts/01/metadata.json')['status'],'failed')
            self.assertTrue((root/'attempts/01/response.partial.txt').exists())
            self.assertEqual(read_json(root/'metadata.json')['accepted_attempt'],2)
            with patch('sports_annotation.caption_experiment.requests.post',side_effect=AssertionError('Must reuse')):
                self.assertEqual(execute_text(root,spec,provider,lambda:None,['## Storyline']),result)

    def test_missing_section_is_review_warning_not_extra_api_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            provider={'base_url':'https://example.invalid','model':'mock','max_tokens':100}
            spec=(describe_request('test','fixture',[],provider,{}),'fixture',[])
            with patch('sports_annotation.caption_experiment.requests.post',return_value=Response()) as http:
                execute_text(root,spec,provider,lambda:'fake-test-key',['## Atomic Actions'])
            self.assertEqual(http.call_count,1)
            self.assertEqual(read_json(root/'metadata.json')['missing_sections'],['## Atomic Actions'])


if __name__=='__main__': unittest.main()
