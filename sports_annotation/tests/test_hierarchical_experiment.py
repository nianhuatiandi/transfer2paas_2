"""Synthetic protocol checks, not tests of real video accuracy."""
import copy
import unittest

from jsonschema import Draft202012Validator, ValidationError

from sports_annotation.hierarchical_experiment import nominal_relations, output_schema, runtime_lexicon, validate_draft
from sports_annotation.io_utils import read_json
from sports_annotation.pipeline import PACKAGE
from sports_annotation.tests.test_core import action, audio, manifest, visual


def hierarchical_visual():
    data = visual()
    data['schema_version'] = 'hierarchical-0.1'
    data['actions'][0].update(label='chasse', movement_roles=['recover'], body_parts=['legs'], subphases=[])
    return data


class HierarchicalProtocolTests(unittest.TestCase):
    def setUp(self):
        self.lexicon = runtime_lexicon(read_json(PACKAGE / 'lexicons/badminton_bwf_v01.json'))

    def test_roles_cannot_be_counted_as_technique_labels(self):
        data = hierarchical_visual()
        data['actions'][0]['label'] = 'recover'
        with self.assertRaises(ValidationError):
            Draft202012Validator(output_schema('visual', self.lexicon)).validate(data)

    def test_concurrent_footwork_stroke_and_state_without_subphase_double_count(self):
        data = hierarchical_visual()
        stroke = copy.deepcopy(data['actions'][0])
        stroke.update(id='A002', label='forehand_net_lift', body_parts=['racket_arm'], movement_roles=['hit'],
                      subphases=[{'label': 'forward_swing', 'start': .3, 'end': .6, 'detail': 'Synthetic only.',
                                  'evidence': [{'time': .5, 'observation': 'Synthetic only.'}]}])
        pose = copy.deepcopy(data['actions'][0])
        pose.update(id='A003', label='held_pose', kind='held_pose', movement_roles=[])
        data['actions'] += [stroke, pose]
        notes = validate_draft('visual', data, manifest(), self.lexicon, manifest()['frames'])
        self.assertEqual(notes, [])
        graph = nominal_relations(data, audio(), manifest())
        self.assertEqual({p['action_id'] for p in graph['primary_edges']}, {'A001', 'A002'})
        self.assertEqual(len(graph['context_edges']), 1)
        self.assertEqual(len(graph['pairs']), 3)

    def test_subphase_boundary_problem_is_preserved_for_review(self):
        data = hierarchical_visual()
        data['actions'][0].update(label='forehand_net_lift', subphases=[
            {'label': 'backswing', 'start': 0., 'end': .3, 'detail': 'Synthetic only.', 'evidence': []}])
        before = copy.deepcopy(data)
        notes = validate_draft('visual', data, manifest(), self.lexicon, manifest()['frames'])
        self.assertTrue(any('outside' in n for n in notes))
        self.assertEqual(data, before)

    def test_invalid_interval_excluded_with_explicit_reason_and_negatives_kept(self):
        data = hierarchical_visual()
        invalid = copy.deepcopy(data['actions'][0])
        invalid.update(id='A002', end=1.5)
        data['actions'].append(invalid)
        sounds = audio()
        sounds['events'][0].update(start=.8, end=.95)
        graph = nominal_relations(data, sounds, manifest())
        self.assertEqual(len(graph['skipped_invalid_events']), 1)
        self.assertEqual(len(graph['pairs']), 1)
        self.assertFalse(graph['pairs'][0]['nominal_overlap'])
        self.assertEqual(graph['primary_edges'], [])


if __name__ == '__main__':
    unittest.main()
