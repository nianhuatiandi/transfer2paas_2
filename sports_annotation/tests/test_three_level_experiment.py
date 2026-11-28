import unittest

from sports_annotation.three_level_experiment import align_levels, audit_events, link_notes


def event(eid, start, end, actor='S01-P01'):
    return {'id': eid, 'start': start, 'end': end,
            'start_range': [start, start], 'end_range': [end, end],
            'shot_id': 'S01', 'actor_id': actor, 'evidence': []}


class ThreeLevelSemantics(unittest.TestCase):
    def setUp(self):
        self.manifest = {'duration': 4, 'shots': [{'id': 'S01', 'start': 0, 'end': 4}]}

    def test_parent_audio_overlap_is_not_inherited_by_children(self):
        parent = {'episodes': [event('E1', 0, 4)], 'actions': [event('A1', 0, 3)]}
        motion = [event('M1', 2, 3)]
        sound = {**event('U1', .5, 1), 'layer': 'foreground'}
        result = align_levels(parent, motion, {'events': [sound]}, self.manifest)
        self.assertEqual(len(result['levels']['L1']['foreground_overlap']), 1)
        self.assertEqual(len(result['levels']['L2']['foreground_overlap']), 1)
        self.assertEqual(result['levels']['L3']['foreground_overlap'], [])

    def test_touching_endpoints_are_disjoint_and_uncertainty_is_retained(self):
        sound = {**event('U1', 1, 2), 'layer': 'foreground'}
        action = event('A1', 0, 1)
        parent = {'episodes': [], 'actions': [action]}
        result = align_levels(parent, [], {'events': [sound]}, self.manifest)
        self.assertEqual(result['levels']['L2']['pairs'][0]['status'], 'disjoint')
        action['end_range'] = [.9, 1.1]
        result = align_levels(parent, [], {'events': [sound]}, self.manifest)
        self.assertEqual(result['levels']['L2']['pairs'][0]['status'], 'uncertain')

    def test_shared_motion_links_do_not_require_duplicate_primitives(self):
        parents = {'A1': event('A1', 0, 2), 'A2': event('A2', 1, 3)}
        children = {'M1': event('M1', .5, 2.5)}
        links = [{'action_id': 'A1', 'primitive_id': 'M1', 'start': .5, 'end': 2},
                 {'action_id': 'A2', 'primitive_id': 'M1', 'start': 1, 'end': 2.5}]
        self.assertEqual(link_notes(links, parents, children, 'action_id', 'primitive_id'), [])
        children['M1']['actor_id'] = 'S01-P02'
        with self.assertRaises(ValueError):
            link_notes(links, parents, children, 'action_id', 'primitive_id')

    def test_audit_checks_every_event_and_invalid_times_are_not_aligned(self):
        a, b = event('A1', 0, 1), event('A2', 2, 3)
        a['start_range'] = [.1, .2]
        b['end_range'] = [1, 2]
        notes = audit_events([a, b], self.manifest, [])
        self.assertEqual(len(notes), 2)
        graph = align_levels({'episodes': [], 'actions': [a, b]}, [], {'events': []}, self.manifest)
        self.assertEqual(graph['skipped'], ['A1', 'A2'])


if __name__ == '__main__':
    unittest.main()
