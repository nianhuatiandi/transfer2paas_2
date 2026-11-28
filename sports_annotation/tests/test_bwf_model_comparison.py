import json
import tempfile
import unittest
from pathlib import Path

from sports_annotation.bwf_model_comparison import validate_transcript
from sports_annotation.client import make_payload
from sports_annotation.io_utils import file_hash


class ComparisonTests(unittest.TestCase):
    def test_openai_visual_transport_and_audio_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'frame.jpg'
            path.write_bytes(b'image-fixture')
            image = {'kind': 'image', 'path': str(path), 'sha256': file_hash(path),
                     'index': 3, 'time': .1, 'shot_id': 'S01'}
            provider = {'model': 'gpt-6.2-sol', 'max_tokens': 1000, 'api_style': 'openai_chat',
                        'image_detail': 'high', 'extra_body': {'reasoning_effort': 'medium', 'store': False}}
            payload = json.loads(make_payload('Return JSON.', [image], provider))
            self.assertNotIn('max_tokens', payload)
            self.assertNotIn('modalities', payload)
            self.assertEqual(payload['max_completion_tokens'], 1000)
            self.assertEqual(payload['messages'][0]['content'][1]['image_url']['detail'], 'high')
            self.assertIn('0.100000 s', payload['messages'][0]['content'][0]['text'])
            with self.assertRaisesRegex(ValueError, 'visual-only'):
                make_payload('Return JSON.', [{**image, 'kind': 'audio'}], provider)
            qwen = json.loads(make_payload('Return JSON.', [image], {'model': 'qwen', 'max_tokens': 1000}))
            self.assertEqual(qwen['modalities'], ['text'])
            self.assertEqual(qwen['max_tokens'], 1000)
            self.assertNotIn('max_completion_tokens', qwen)

    def test_transcription_requires_words_not_only_description(self):
        event = {'id': 'U001', 'kind': 'speech', 'layer': 'foreground', 'start': .1, 'end': .4,
                 'start_range': [0, .2], 'end_range': [.3, .5], 'speaker_id': 'V01',
                 'description': 'A short spoken word.', 'evidence': [{'time': .2, 'observation': 'Voice.'}],
                 'confidence': 'medium', 'transcript': None}
        manifest = {'duration': 1, 'audio': {'present': True, 'valid_span': [0, 1]}}
        data = {'schema_version': '1.0', 'events': [event], 'uncertainties': []}
        with self.assertRaisesRegex(ValueError, 'verbatim'):
            validate_transcript(data, manifest)
        event['transcript'] = 'one'
        validate_transcript(data, manifest)
        validate_transcript({'schema_version': '1.0', 'events': [], 'uncertainties': []}, manifest)


if __name__ == '__main__':
    unittest.main()
