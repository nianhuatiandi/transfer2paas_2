import copy
import unittest
from sports_annotation.bench import visual_events
from sports_annotation.bench_adjudicate import adjudicate, validate
from sports_annotation.bench_export import bound_adjacent_turns, package
from sports_annotation.long_timeline import stitch

class EventReferenceTests(unittest.TestCase):
    def setUp(self):
        self.header=dict(schema="av-events/1.0",duration_seconds=6,actors=[dict(id="P1",appearance="coach")])
        self.v=dict(id="V1",modality="visual",kind="visible_speech",actor_id="P1",actor="coach",activity="instruction",
                    label="speak",brief="The coach speaks.",detail="His lips open and close as he faces forward.",
                    posture="unclear",visual_evidence="Repeated lip movement",phases=[],start=0,end=2,review_flags=[])
        self.a=dict(id="A1",modality="audio",kind="speech",actor="voice",label="Speech",detail="Start the jump.",
                    transcript_original="开始跳。",start=1,end=3,review_flags=[])

    def test_same_utterance_can_overlap_speech_and_motion(self):
        jump={**self.v,"id":"V2","kind":"motion","start":2.2,"end":4}
        table=package(self.header,[self.v,jump,self.a],status="machine_reviewed_silver",scored_only=True)
        validate(table)
        self.assertEqual([r["visual_id"] for r in table["relations"]],["V1","V2"])

    def test_consistent_removal_and_retiming(self):
        original=package(self.header,[self.v,self.a],status="model")
        decisions={"reviewer":"fixture","events":{"V1":{"decision":"accept"},"A1":{"decision":"edit","changes":{"start":2.3}}}}
        self.assertEqual(adjudicate(original,decisions)["relations"],[])
        decisions["events"]["A1"]={"decision":"drop"}
        self.assertEqual([e["id"] for e in adjudicate(original,decisions)["events"]],["V1"])
        del decisions["events"]["A1"]
        with self.assertRaises(ValueError): adjudicate(original,decisions)

    def test_small_handoff_uncertainty_retains_only_robust_overlap(self):
        marker="Possible overlapping turns from the same voice"
        a={**self.a,"review_flags":[marker]}
        b={**self.a,"id":"A2","start":2.7,"end":5,"transcript_original":"第二步。","review_flags":[marker]}
        bound_adjacent_turns([a,b])
        self.assertEqual(a["boundary_ranges"]["end"],[2.7,3])
        v={**self.v,"start":2.6,"end":3.2}
        table=package(self.header,[v,a,b],status="silver",scored_only=True)
        self.assertFalse(any(r["audio_id"]=="A1" for r in table["relations"]))

    def test_context_only_observer_cannot_truncate_end(self):
        scopes=[{"core":[0,5],"span":[0,5.7]},{"core":[5,10],"span":[4.3,10]}]
        l={**self.v,"origin":"l","start":4.8,"end":5.4}
        r={**self.v,"origin":"r","start":4.8,"end":9.6}
        table,_=stitch(scopes,[{"visual":[l]},{"visual":[r]}],[[{"left":"l","right":"r","verdict":"same","quote":""}]],10,prefer_core_bounds=True)
        self.assertEqual(table["visual"][0]["end"],9.6)

    def test_no_actor_from_a_voice_alone(self):
        self.assertEqual(visual_events({"events":[]},5,self.header["actors"]),[])
        table=package(self.header,[self.a],status="silver",scored_only=True)
        self.assertEqual(table["relations"],[])
