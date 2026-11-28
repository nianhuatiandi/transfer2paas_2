"""All model responses here are synthetic test fixtures, never research results."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from sports_annotation.client import JSONStreamGuard, describe_request, execute
from sports_annotation.io_utils import file_hash, parse_model_json, read_json
from sports_annotation.pipeline import PACKAGE, assemble, candidate_pair, request_spec
from sports_annotation.relations import build_relations, temporal_relation
from sports_annotation.validation import validate


def action(identifier="A001", start=0.2, end=0.8, shot="S01"):
    return {"id": identifier, "actor_id": shot + "-P01", "shot_id": shot, "execution_id": None,
            "kind": "motion", "label": "other_motion", "start": start, "end": end,
            "start_range": [start, start], "end_range": [end, end], "detail": "Synthetic fixture motion.",
            "evidence": [{"time": 0.5, "observation": "Synthetic fixture frame."}],
            "key_moments": [], "boundary_clipped": {"start": False, "end": False}, "confidence": "medium"}


def sound(identifier="U001", start=0.4, end=0.9):
    return {"id": identifier, "kind": "speech", "layer": "foreground", "start": start, "end": end,
            "start_range": [start, start], "end_range": [end, end], "speaker_id": None,
            "description": "Synthetic test speech activity.", "evidence": [{"time": (start + end) / 2, "observation": "Synthetic fixture only."}],
            "confidence": "medium", "transcript": None}


def visual():
    return {"schema_version": "1.0", "in_scope": True, "scope_note": "Synthetic test only.",
            "actors": [{"id": "S01-P01", "shot_id": "S01", "description": "Synthetic actor."}],
            "executions": [], "actions": [action()], "uncertainties": []}


def audio():
    return {"schema_version": "1.0", "events": [sound()], "uncertainties": []}


def manifest():
    return {"duration": 2.0, "source_sha256": "synthetic", "preparation_signature": "fixture",
            "shots": [{"id": "S01", "start": 0, "end": 1}, {"id": "S02", "start": 1, "end": 2}],
            "audio": {"present": True, "valid_span": [0, 2]}, "width": 64, "height": 64,
            "frames": [{"index": 0, "time": 0.5, "end": 0.54, "shot_id": "S01"}],
            "cut_detection": {"method": "synthetic"}}


class RelationsTests(unittest.TestCase):
    def test_one_utterance_overlaps_two_actions(self):
        graph = build_relations([action("A1", 0, 0.6), action("A2", 0.6, 1)], [sound(start=0.4, end=0.8)])
        self.assertEqual({e["action_id"] for e in graph["primary_edges"]}, {"A1", "A2"})
        self.assertAlmostEqual(graph["primary_edges"][0]["overlap_s"], 0.2)

    def test_half_open_touch_is_not_overlap(self):
        edge = temporal_relation(action(end=0.8), sound(start=0.8, end=1.1))
        self.assertEqual(edge["status"], "disjoint")
        self.assertFalse(edge["nominal_overlap"])

    def test_borderline_nominal_overlap_is_uncertain(self):
        a, s = action(), sound(start=0.79, end=1.1)
        a["end_range"] = [0.75, 0.85]
        s["start_range"] = [0.74, 0.84]
        edge = temporal_relation(a, s)
        self.assertEqual(edge["status"], "uncertain")
        self.assertTrue(edge["nominal_overlap"])
        self.assertEqual(edge["overlap_range_s"], [0.0, 0.11])

    def test_possible_overlap_without_nominal_overlap_retained(self):
        a, s = action(end=0.7), sound(start=0.8, end=1.1)
        a["end_range"] = [0.65, 0.85]
        self.assertEqual(temporal_relation(a, s)["status"], "uncertain")

    def test_background_and_pose_do_not_inflate_primary_edges(self):
        a, b = action(), sound("N1")
        b.update(kind="background", layer="background", speaker_id=None)
        graph = build_relations([a], [b])
        self.assertEqual(len(graph["primary_edges"]), 0)
        self.assertEqual(len(graph["context_edges"]), 1)
        a.update(kind="held_pose", label="held_pose")
        self.assertEqual(len(build_relations([a], [sound()])["primary_edges"]), 0)

    def test_multiple_sounds_per_action(self):
        graph = build_relations([action()], [sound("U1"), sound("U2", 0.3, 0.5)])
        self.assertEqual(len(graph["primary_edges"]), 2)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.m = manifest()
        self.lex = {"terms": []}

    def test_audio_can_cross_shot_cut(self):
        data = audio()
        data["events"] = [sound(start=0.8, end=1.3)]
        validate("audio", data, self.m, self.lex)

    def test_visual_cannot_cross_shot_cut(self):
        data = visual()
        data["actions"][0] = action(end=1.2)
        with self.assertRaises(ValueError):
            validate("visual", data, self.m, self.lex)

    def test_actor_and_execution_references_are_checked(self):
        for field, value in [("actor_id", "S02-P99"), ("execution_id", "missing")]:
            data = visual()
            data["actions"][0][field] = value
            with self.assertRaises(ValueError):
                validate("visual", data, self.m, self.lex)

    def test_fabricated_evidence_timestamp_rejected(self):
        with self.assertRaises(ValueError):
            validate("visual", visual(), self.m, self.lex, frame_times=[0.0, 0.4, 0.8])

    def test_unknown_technique_rejected(self):
        data = visual()
        data["actions"][0]["label"] = "invented_move"
        with self.assertRaises(ValueError):
            validate("visual", data, self.m, self.lex)

    def test_locked_speech_must_remain_identical(self):
        review = {"schema_version": "1.0", "visual": visual(), "audio": audio(), "change_log": [], "unresolved": []}
        locked = copy.deepcopy(review["audio"]["events"])
        review["audio"]["events"][0]["description"] = "Changed externally supplied item"
        with self.assertRaises(ValueError):
            validate("review", review, self.m, self.lex, [0.5], locked)

    def test_duplicate_audio_ids_rejected(self):
        data = audio()
        data["events"] *= 2
        with self.assertRaises(ValueError):
            validate("audio", data, self.m, self.lex)

    def test_padding_only_sound_rejected(self):
        self.m["audio"]["valid_span"] = [1, 2]
        with self.assertRaises(ValueError):
            validate("audio", audio(), self.m, self.lex)

    def test_no_silent_json_repair(self):
        with self.assertRaises((ValueError, json.JSONDecodeError)):
            parse_model_json('{"x":1')
        with self.assertRaises(ValueError):
            parse_model_json('{"x":NaN}')

    def test_boundary_rounding_and_anchor_uncertainty(self):
        self.m['shots'][0]['start'] = 0.000333
        data = visual()
        a = data['actions'][0]
        a.update(start=0.0, start_range=[0.0,0.1], end_range=[0.7,0.9])
        a['key_moments'] = [{'name':'finish', 'time':0.8, 'time_range':[0.7,0.9]}]
        validate('visual', data, self.m, self.lex, [0.5])
        a['start'] = 0.0
        self.m['shots'][0]['start'] = 0.003
        with self.assertRaises(ValueError):
            validate('visual', data, self.m, self.lex, [0.5])


class FakeResponse:
    status_code = 200

    def __init__(self, result, finish="stop"):
        self.result, self.finish = result, finish

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def iter_lines(self):
        text = json.dumps(self.result)
        for part in (text[:len(text)//2], text[len(text)//2:]):
            yield b"data: " + json.dumps({"id": "synthetic-test", "choices": [{"delta": {"content": part}, "finish_reason": None}]}).encode()
        yield b"data: " + json.dumps({"choices": [{"delta": {}, "finish_reason": self.finish}], "usage": {"total_tokens": 1}}).encode()
        yield b"data: [DONE]"


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.provider = {"base_url": "https://example.invalid/v1", "model": "synthetic-test", "max_tokens": 100}
        self.descriptor = describe_request("audio", "fixture", [], self.provider, {})

    def tearDown(self):
        self.temp.cleanup()

    def test_completed_stage_reuses_without_http_or_key(self):
        with patch("sports_annotation.client.requests.post", return_value=FakeResponse(audio())) as request:
            execute(self.root, self.descriptor, "fixture", [], self.provider, lambda: "test-secret", lambda x: None)
        self.assertEqual(request.call_count, 1)
        with patch("sports_annotation.client.requests.post", side_effect=AssertionError("No HTTP expected")):
            got = execute(self.root, self.descriptor, "fixture", [], self.provider,
                          Mock(side_effect=AssertionError("No key expected")), lambda x: None)
        self.assertEqual(got, audio())
        self.assertNotIn("test-secret", (self.root / "metadata.json").read_text())

    def test_changed_prompt_rejected_before_http(self):
        with patch("sports_annotation.client.requests.post", return_value=FakeResponse(audio())):
            execute(self.root, self.descriptor, "fixture", [], self.provider, lambda: "key", lambda x: None)
        changed = describe_request("audio", "changed", [], self.provider, {})
        with patch("sports_annotation.client.requests.post", side_effect=AssertionError("No HTTP expected")):
            with self.assertRaises(ValueError):
                execute(self.root, changed, "changed", [], self.provider, lambda: "key", lambda x: None)

    def test_truncated_stream_is_not_a_completed_result(self):
        with patch("sports_annotation.client.requests.post", return_value=FakeResponse(audio(), "length")):
            with self.assertRaises(RuntimeError):
                execute(self.root, self.descriptor, "fixture", [], self.provider, lambda: "key", lambda x: None)
        self.assertEqual(read_json(self.root / "metadata.json")["status"], "failed")
        self.assertFalse((self.root / "result.json").exists())

    def test_error_body_redacts_key(self):
        response = FakeResponse({})
        response.status_code = 401
        response.text = "Rejected test-secret"
        with patch("sports_annotation.client.requests.post", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "REDACTED"):
                execute(self.root, self.descriptor, "fixture", [], self.provider, lambda: "test-secret", lambda x: None)
        self.assertNotIn("test-secret", (self.root / "metadata.json").read_text())

    def test_reserved_request_overrides_rejected(self):
        provider = {**self.provider, "extra_body": {"messages": []}}
        with self.assertRaises(ValueError):
            describe_request("audio", "fixture", [], provider, {})

    def test_degenerate_stream_guard_across_chunks(self):
        guard = JSONStreamGuard(8)
        guard.feed('{"x":"abcd')
        with self.assertRaises(ValueError):
            guard.feed('efghijk')
        guard = JSONStreamGuard(8)
        guard.feed('{"x":"abc\\\"d","y":"ok"}')

    def test_invalid_range_repaired_by_model_and_original_preserved(self):
        bad = audio()
        bad['events'][0]['start_range'] = [0.1, 0.2]
        validator = lambda d: validate('audio',d,manifest(),{'terms':[]})
        with patch('sports_annotation.client.requests.post',side_effect=[FakeResponse(bad),FakeResponse(audio())]) as http:
            got = execute(self.root,self.descriptor,'fixture',[],self.provider,lambda:'test-key',validator)
        self.assertEqual(http.call_count,2)
        self.assertEqual(got,audio())
        self.assertEqual(parse_model_json((self.root/'response.txt').read_text()),bad)
        self.assertEqual(read_json(self.root/'metadata.json')['repair_count'],1)
        self.assertEqual(read_json(self.root/'initial_metadata.json')['status'],'failed')


class AssemblyTests(unittest.TestCase):
    def test_mock_candidates_to_deterministic_graph(self):
        # Runs client persistence, validation, candidate merge and export with HTTP mocked.
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            m, lex = manifest(), {"terms": []}
            provider = {"base_url": "https://example.invalid/v1", "model": "test", "max_tokens": 100}
            for stage, data in (("visual", visual()), ("audio", audio())):
                descriptor = describe_request(stage, "fixture", [], provider, {})
                with patch("sports_annotation.client.requests.post", return_value=FakeResponse(data)):
                    execute(out / "stages" / stage, descriptor, "fixture", [], provider, lambda: "key",
                            lambda d, s=stage: validate(s, d, m, lex, [0.5]))
            summary = assemble(out, m, lex, None, None)
            self.assertEqual(summary["primary_edges"], 1)
            self.assertEqual(summary["status"], "candidates_only_not_human_gt")
            self.assertTrue(read_json(out / "annotations.json")["human_review_required"])
            self.assertIn("U001", (out / "caption.txt").read_text())


if __name__ == "__main__":
    unittest.main()
