from copy import deepcopy
import unittest
from badminton_alignment import validate_alignment

class AlignmentValidationTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {'shots': [{'shot': 'S01', 'start': 0, 'end': 2}]}
        self.combined = {'shots': [{'shot': 'S01', 'actors': [{'id': 'S01-P01'}]}],
                         'actions': [{'id': 'A01', 'shot': 'S01', 'start': 0.5, 'end': 1.5}],
                         'audio': {'speakers': [{'id': 'V01'}], 'utterances': [{}]}}
        self.example = {'shot': 'S01', 'speech_segments': [], 'action_sounds': [
            {'action_id': 'A01', 'status': 'supported', 'sound_time': 1.05, 'visual_time': 1.0,
             'confidence': 'high', 'description': 'brief tap', 'evidence': 'audible tap with visible contact'}], 'unmatched_sounds': []}

    def check(self, value):
        return validate_alignment(value, self.manifest, self.combined)

    def test_supported_match_retains_independent_timing(self):
        value = self.check(self.example)
        self.assertEqual(value['action_sounds'][0]['status'], 'supported')
        self.assertEqual(value['action_sounds'][0]['audio_minus_visual_seconds'], 0.05)

    def test_large_timing_difference_is_not_supported(self):
        self.example['action_sounds'][0]['sound_time'] = 1.4
        self.assertEqual(self.check(self.example)['action_sounds'][0]['status'], 'uncertain')

    def test_low_confidence_does_not_create_a_positive_match(self):
        self.example['action_sounds'][0]['confidence'] = 'low'
        self.assertEqual(self.check(self.example)['action_sounds'][0]['status'], 'uncertain')

    def test_nonexistent_or_unassessed_actions_are_rejected(self):
        self.example['action_sounds'][0]['action_id'] = 'A99'
        with self.assertRaises(ValueError):
            self.check(self.example)
        self.example['action_sounds'] = []
        with self.assertRaises(ValueError):
            self.check(self.example)

    def test_speech_coincidence_alone_cannot_create_actor_identity(self):
        self.example['speech_segments'] = [{'source_utterance_id': 'U01', 'start': 0.5, 'end': 1.0, 'speaker': 'V01',
            'actor': 'S01-P01', 'speaker_status': 'uncertain', 'confidence': 'medium', 'evidence': 'mouth unclear', 'related_actions': []}]
        self.assertIsNone(self.check(self.example)['speech_segments'][0]['actor'])

    def test_false_temporal_overlap_is_rejected(self):
        self.example['speech_segments'] = [{'source_utterance_id': 'U01', 'start': 1.7, 'end': 1.9, 'speaker': 'V01',
            'actor': None, 'speaker_status': 'off_screen', 'confidence': 'high', 'evidence': 'voice heard',
            'related_actions': [{'action_id': 'A01', 'relationship': 'temporal overlap only'}]}]
        with self.assertRaises(ValueError):
            self.check(self.example)

if __name__ == '__main__':
    unittest.main()
