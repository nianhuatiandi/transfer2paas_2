"""Independently verify the pilot files, positive intersections and the preselected presence probes."""
import json
from collections import Counter
from html import escape
from html.parser import HTMLParser
from urllib.parse import unquote
from pathlib import Path
import sys
from statistics import median

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from sports_annotation.bench_adjudicate import validate
from sports_annotation.io_utils import file_hash, object_hash, read_json, write_json

def verify_edges(record):
    audio=[e for e in record["events"] if e["modality"]=="audio"]
    visual=[e for e in record["events"] if e["modality"]=="visual"]
    phases=[p for e in visual for p in e["phases"]]
    for kind,items in (("relations",visual),("phase_relations",phases)):
        expected={}
        for e in items:
            for a in audio:
                lo=max(e["start"],a["start"]); hi=min(e["end"],a["end"])
                if hi<=lo:continue
                bounds=a.get("boundary_ranges",{"start":[a["start"]]*2,"end":[a["end"]]*2})
                core=(max(lo,bounds["start"][1]),min(hi,bounds["end"][0]))
                if record["reference_status"]=="machine_reviewed_silver" and core[1]-core[0]<.2-1e-8:continue
                expected[e["id"],a["id"]]=(lo,hi,core if core[1]>core[0] else ())
        actual={(x["visual_id"],x["audio_id"]):(x["start"],x["end"],tuple(x["robust_interval"] or [])) for x in record[kind]}
        assert expected==actual,(kind,len(expected),len(actual))

def main():
    sampled=read_json(HERE/"probes.json")
    sets={k:sampled[k] for k in ("development","transfer")}
    sets["final_checks"]=read_json(HERE/"sealed_checks.json")["cases"]
    name_to_set={name:(group,points) for group,clips in sets.items() for name,points in clips.items()}
    out={}
    rows=[]
    for folder in sorted((HERE/"cases").iterdir()):
        ref,raw=(read_json(folder/f) for f in ("reference.json","annotations.json"))
        validate(ref);validate(raw)
        verify_edges(ref);verify_edges(raw)
        assert object_hash(read_json(folder/"release_protocol.json"))==ref["protocol_sha256"]
        assert all(not e["review_flags"] for e in ref["events"])
        class Playback(HTMLParser):
            def __init__(self):
                super().__init__()
                self.sources=[]
                self.buttons=[]
            def handle_starttag(self,tag,attrs):
                a=dict(attrs)
                if tag=="video": self.sources.append(a["src"])
                if tag=="button": self.buttons.append((float(a["data-a"]),float(a["data-b"])))
        page=Playback()
        page.feed((folder/"review.html").read_text("utf8"))
        assert len(page.sources)==1 and file_hash((folder/unquote(page.sources[0])).resolve())==ref["source_sha256"]
        assert len(page.buttons)>=len(raw["events"]) and all(0<=a<b<=ref["duration_seconds"]+.001 for a,b in page.buttons)
        assert (folder/"events.txt").is_file()
        name=folder.name
        group,probes=name_to_set.get(name,("exploratory",{}))
        final_speakers=[e for e in ref["events"] if e["kind"]=="visible_speech"]
        draft=[e for f in folder.glob("w*/draft.json") for e in read_json(f)["visual"] if e["kind"]=="visible_speech"]
        checks=[]
        for label,points in probes.items():
            for t in points:
                def hits(events):
                    return any(e["start"]<=t<e["end"] and (name!="badminton" or label=="no" or e.get("actor_id")=="P1") for e in events)
                checks.append({"second":t,"expected":label=="yes","draft":hits(draft),"reference":hits(final_speakers)})
        counts=Counter(e["kind"] for e in ref["events"])
        out[name]={"set":group,"events":len(ref["events"]),"counts":dict(counts),"scored_temporal_relations":len(ref["relations"]),
                   "phases":sum(len(e.get("phases",[])) for e in ref["events"]),"scored_phase_relations":len(ref["phase_relations"]),
                   "withheld_event_count":len(raw["events"])-len(ref["events"]),"checks":checks}
        f=sum(c["reference"]==c["expected"] for c in checks)
        rows.append(f'<tr><td><a href="cases/{name}/review.html">{escape(name)}</a></td><td>{escape(group)}</td><td>{len(ref["events"])}</td><td>{len(final_speakers)}</td><td>{len(ref["relations"])}</td><td>{str(f)+"/"+str(len(checks)) if checks else "—"}</td><td><a href="cases/{name}/reference.json">Reference JSON</a></td></tr>')
    stats={}
    for group in [*sets,"all"]:
        c=[v for entry in out.values() if group=="all" or entry["set"]==group for v in entry["checks"]]
        stats[group]={stage:{k:sum(x["expected"]==yes and x[stage]==pred for x in c) for k,yes,pred in (("tp",True,True),("fn",True,False),("tn",False,False),("fp",False,True))} for stage in ("draft","reference")}
    write_json(HERE/"validation.json",{"cases":out,"presence_probes":stats,"definition":sampled["definition"]})
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>English event references</title><style>body{font:16px/1.55 system-ui;max-width:1040px;margin:2rem auto;color:#182d3b;padding:0 1rem}table{border-collapse:collapse}td,th{border-bottom:1px solid #ccd5d9;padding:.6rem;text-align:left}a{color:#165c78}</style><h1>English event references</h1><p>Open a clip to replay event intervals and inspect descriptions, evidence and temporal relations. The JSON contains the machine-reviewed scoring subset.</p><table><tr><th>Clip and review</th><th>Evaluation group</th><th>Events</th><th>Visible speaking bouts</th><th>Temporal overlaps</th><th>Speaking presence probes correct</th><th>Data</th></tr>'''
    html+="".join(rows)+"</table><p>Presence probes check a small set of selected instants. They do not measure transcription accuracy, exact boundaries or the correctness of every physical event.</p></html>"
    (HERE/"index.html").write_text(html,"utf8")
    print(json.dumps(stats))

if __name__=="__main__":main()
