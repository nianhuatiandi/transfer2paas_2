import array
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from sports_annotation.media import ffmpeg_path, inspect_source, prepare, prepare_review, run_ffmpeg, sample_indices
from sports_annotation.pipeline import PACKAGE, assemble, prepare_case, request_spec, review_case, run_candidates
from sports_annotation.io_utils import read_json


class RealMediaTests(unittest.TestCase):
    """Tiny generated AV fixture tests real decoding and audio alignment, no API."""

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        cls.binary = ffmpeg_path()
        cls.source = cls.root / "synthetic_vfr_offset.mkv"
        run_ffmpeg(cls.binary, "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=25:duration=0.4",
                   "-itsoffset", "0.12", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000:duration=0.2",
                   "-map", "0:v:0", "-map", "1:a:0", "-vf", "select=eq(n\\,0)+eq(n\\,1)+eq(n\\,4)+eq(n\\,9)",
                   "-fps_mode", "vfr", "-c:v", "ffv1", "-c:a", "pcm_s16le", "-n", cls.source)
        cls.settings = {"sampling_fps": 10, "scene_threshold": 0.12, "max_clip_seconds": 30, "max_review_frames": 20}

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_actual_pts_and_short_shots_preserved(self):
        info = inspect_source(self.source)
        times = [round(f["time"], 3) for f in info["source_frames"]]
        self.assertEqual(times, [0.0, 0.04, 0.16, 0.36])
        prepared = prepare(self.source, self.root / "short_shots", self.settings, cuts=[0.16])
        self.assertEqual(len(prepared["shots"]), 2)
        self.assertEqual(prepared["shots"][0]["end"], 0.16)
        self.assertLess(prepared["duration"], 1)
        self.assertTrue({f["time"] for f in prepared["frames"]}.issubset(set(times)))
        self.assertIn(0.36, [f["time"] for f in prepared["frames"]])

    def test_audio_offset_survives_resampling(self):
        folder = self.root / "offset"
        prepared = prepare(self.source, folder, self.settings, cuts=[])
        self.assertAlmostEqual(prepared["audio"]["valid_span"][0], 0.12, places=3)
        self.assertAlmostEqual(prepared["audio"]["valid_span"][1], 0.32, places=3)
        with wave.open(str(folder / "audio.wav"), "rb") as wav:
            rate = wav.getframerate()
            samples = array.array("h", wav.readframes(wav.getnframes()))
        self.assertEqual(max(abs(x) for x in samples[:int(0.10 * rate)]), 0)
        self.assertGreater(max(abs(x) for x in samples[int(0.14 * rate):int(0.18 * rate)]), 100)
        self.assertEqual(max(abs(x) for x in samples[int(0.34 * rate):]), 0)

    def test_preparation_cache_rejects_changed_sampling(self):
        folder = self.root / "cache"
        prepare(self.source, folder, self.settings, cuts=[])
        with self.assertRaisesRegex(ValueError, "Preparation changed"):
            prepare(self.source, folder, {**self.settings, "sampling_fps": 5}, cuts=[])

    def test_prepare_cannot_call_network_and_audio_prompt_has_no_visual_context(self):
        config = {"media": self.settings, "provider": {"base_url": "https://example.invalid/v1", "model": "test", "max_tokens": 100}}
        case = {"id": "fixture", "sport": "golf", "source": self.source.name}
        with patch("sports_annotation.client.requests.post", side_effect=AssertionError("Offline prepare must not call API")):
            out, info, lex, locked, ext, summary = prepare_case(config, self.root, case, self.root / "offline", "test")
        self.assertEqual(summary["api_calls_in_prepare"], 0)
        request = read_json(out / "stages/audio/request.json")
        self.assertEqual(request["image_count"], 0)
        prompt = (out / "stages/audio/prompt.txt").read_text()
        self.assertNotIn('"lexicon"', prompt)
        self.assertNotIn('"shots"', prompt)
        self.assertNotIn(self.source.name, prompt)

    def test_dense_review_uses_only_real_frames(self):
        folder = self.root / "review"
        info = prepare(self.source, folder, {**self.settings, "sampling_fps": 2}, cuts=[])
        candidates = {"actions": [{"id": "A1", "start": 0, "end": 0.35, "start_range": [0, 0.04],
                                    "end_range": [0.3, 0.36], "confidence": "low", "key_moments": [{"name": "anchor", "time": 0.16}]}]}
        plan = prepare_review(folder, info, candidates, {"events": []}, self.settings)
        self.assertEqual(len(plan["frames"]), 4)
        self.assertEqual({f["time"] for f in plan["frames"]}, {f["time"] for f in info["source_frames"]})

    def test_full_mock_model_workflow_and_resume(self):
        from sports_annotation.tests.test_core import FakeResponse, action, sound, visual
        config = {"media": self.settings, "provider": {"base_url": "https://example.invalid/v1", "model": "test", "max_tokens": 100}}
        case = {"id": "workflow", "sport": "golf", "source": self.source.name}
        out, info, lex, locked, ext, _ = prepare_case(config, self.root, case, self.root / "workflow", "test")
        v = visual()
        a = action(start=0.04, end=0.36)
        a["evidence"] = [{"time": 0.16, "observation": "Synthetic frame fixture; not a real sports label."}]
        v["actions"] = [a]
        u = {"schema_version": "1.0", "events": [sound(start=0.12, end=0.3)], "uncertainties": []}
        reviewed = {"schema_version": "1.0", "visual": v, "audio": u, "change_log": [], "unresolved": ["Synthetic fixture only."]}
        with patch("sports_annotation.client.requests.post", side_effect=[FakeResponse(v), FakeResponse(u), FakeResponse(reviewed)]) as http:
            run_candidates(config, out, info, lex, locked, ext, "test", lambda: "test-key")
            plan = review_case(config, out, info, lex, locked, ext, "test", lambda: "test-key", dry_run=True)
            self.assertEqual(http.call_count, 2)
            review_case(config, out, info, lex, locked, ext, "test", lambda: "test-key")
            self.assertEqual(http.call_count, 3)
        result = assemble(out, info, lex, locked, ext)
        self.assertEqual(result["status"], "model_reviewed_not_human_gt")
        self.assertEqual(result["primary_edges"], 1)
        with patch("sports_annotation.client.requests.post", side_effect=AssertionError("Resume must not call HTTP")):
            run_candidates(config, out, info, lex, locked, ext, "test", lambda: (_ for _ in ()).throw(AssertionError("No key")))
            review_case(config, out, info, lex, locked, ext, "test", lambda: (_ for _ in ()).throw(AssertionError("No key")))

    def test_review_byte_budget_keeps_base_and_reports_omissions(self):
        folder = self.root / "budget"
        info = prepare(self.source, folder, {**self.settings, "sampling_fps": 2}, cuts=[])
        budget = sum(4 * (((folder / f['file']).stat().st_size + 2) // 3) for f in info['frames'])
        candidates = {"actions": [{"id": "A1", "start": 0, "end": 0.35, "start_range": [0, 0.04],
                                    "end_range": [0.3, 0.36], "confidence": "low", "key_moments": []}]}
        plan = prepare_review(folder, info, candidates, {"events": []}, self.settings, budget)
        self.assertEqual(len(plan['frames']), len(info['frames']))
        self.assertGreater(plan['omitted_dense_frames'], 0)
        self.assertLessEqual(plan['image_base64_bytes'], budget)


if __name__ == "__main__":
    unittest.main()
