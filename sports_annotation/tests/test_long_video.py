import unittest
from sports_annotation.long_video import windows
from sports_annotation.long_timeline import intersections, stitch
from sports_annotation.long_words import anchor
from sports_annotation.long_clauses import same_excerpt

class LongTimelineTests(unittest.TestCase):
    def test_core_windows_cover_tail_and_use_context(self):
        rows=list(windows(301.2,15,3))
        self.assertEqual(rows[0]["span"],[0,18])
        self.assertEqual(rows[-1]["core"],[300,301.2])
        self.assertTrue(all(left["core"][1]==right["core"][0] for left,right in zip(rows,rows[1:])))

    def test_many_to_many_and_touching_boundaries(self):
        v=[dict(id="v1",start=0,end=3),dict(id="v2",start=1,end=2)]
        a=[dict(id="a1",start=.5,end=2),dict(id="a2",start=1,end=3),dict(id="a3",start=3,end=4)]
        self.assertEqual({(e["visual"],e["audio"]) for e in intersections(v,a)},
                         {(x,y) for x in ("v1","v2") for y in ("a1","a2")})
        self.assertEqual(intersections(v,[]),[])

    def test_seam_excerpt_does_not_replace_a_full_utterance(self):
        w=list(windows(30,15,3))
        a=dict(kind="speech",actor="speaker",text="First words and final words",start=10,end=15.8,origin="a")
        b=dict(kind="speech",actor="speaker",text="and final words",start=12,end=15.9,origin="b")
        decisions=[[dict(left="a",right="b",verdict="same",quote=b["text"])]]
        result,_=stitch(w,[{"audio":[a]},{"audio":[b]}],decisions,30)
        self.assertEqual([(e["text"],e["start"]) for e in result["audio"]],[(a["text"],10)])
        self.assertEqual(result["audio"][0]["alternate_quotes"][0]["text"],b["text"])

    def test_word_anchor_declines_repeated_equally_good_matches(self):
        words=[dict(word="两个",start=1,end=1.4),dict(word="两个",start=3,end=3.5)]
        self.assertIsNone(anchor("两个",words,0,4))
        self.assertEqual(anchor("两个",words,2,4)["start"],3)

    def test_extra_excerpt_requires_same_source_or_actor_and_same_time(self):
        e=dict(text="再怎么难受的球你一挑起来",start=40,end=44,sources=["1"],actor="甲")
        short=dict(text="再怎么难受球",start=41,end=42,sources=["1"],actor="甲")
        self.assertTrue(same_excerpt(e,short))
        self.assertFalse(same_excerpt(e,{**short,"start":45,"end":46}))
        self.assertFalse(same_excerpt(e,{**short,"sources":["2"],"actor":"乙"}))
