"""Rebuild a scored reference after explicit annotation edits and human adjudication."""
import argparse
import math
from pathlib import Path
from .bench import POSTURES, english
from .bench_export import package
from .io_utils import file_hash, read_json, write_json

def validate(table):
    ids=set()
    event_ids=set()
    audio_ids=set()
    phase_ids=set()
    people={p["id"] for p in table["actors"]}
    d=table["duration_seconds"]
    for e in table["events"]:
        k=e["id"]
        if not isinstance(k,str) or k in ids or not 0<=e["start"]<e["end"]<=d+.001 or not english(e["detail"]):
            raise ValueError("Invalid event "+str(k))
        ids.add(k)
        if not english(e["actor"]) or not english(e["label"]):
            raise ValueError("Expected an English actor and event label")
        if e["modality"]=="visual":
            event_ids.add(k)
            if (e["kind"] not in ("motion","gesture","state","visible_speech") or not english(e["brief"]) or not english(e["activity"])
                    or e["actor_id"] not in people|{"unknown"} and e["actor_id"]!="local_"+k):
                raise ValueError("Invalid visual fields or actor: "+k)
            if e["kind"]=="visible_speech" and (e.get("posture") not in POSTURES or not english(e.get("visual_evidence"))):
                raise ValueError("Missing communication evidence: "+k)
            for p in e["phases"]:
                if p["id"] in ids or not english(p["label"]) or not e["start"]<=p["start"]<p["end"]<=e["end"]:
                    raise ValueError("Invalid phase in "+k)
                ids.add(p["id"])
                phase_ids.add(p["id"])
        elif e["modality"]=="audio":
            audio_ids.add(k)
            if e["kind"] not in ("music","speech","ambience","sound") or (e["kind"]=="speech" and not e.get("transcript_original")):
                raise ValueError("Invalid audio: "+k)
        else:
            raise ValueError("Unknown modality")
        if "boundary_ranges" in e:
            lo,hi=e["boundary_ranges"]["start"],e["boundary_ranges"]["end"]
            if not 0<=lo[0]<=e["start"]<=lo[1]<hi[0]<=e["end"]<=hi[1]<=d+.001:
                raise ValueError("Invalid uncertainty ranges in "+k)
    for key,valid in (("relations",event_ids),("phase_relations",phase_ids)):
        links=set()
        for rel in table[key]:
            pair=(rel["visual_id"],rel["audio_id"])
            if pair in links or pair[0] not in valid or pair[1] not in audio_ids or not 0<=rel["start"]<rel["end"]<=d+.001:
                raise ValueError("Invalid temporal edge "+str(pair))
            links.add(pair)

def adjudicate(annotation, decisions):
    # Complete decisions are necessary to describe this particular exported file as human-reviewed.
    grouped={e["id"]:e for e in annotation["events"]}
    if set(decisions["events"])!=set(grouped) or not decisions.get("reviewer"):
        raise ValueError("Provide a reviewer and an accept/edit/drop decision for every existing event.")
    accepted=[]
    for k,e in grouped.items():
        item=decisions["events"][k]
        action=item["decision"]
        if action=="drop": continue
        if action not in ("accept","edit"):
            raise ValueError("Unknown decision")
        row={**e,"review_flags":[]}
        if action=="edit":
            changes=item["changes"]
            if set(changes).intersection(("id","sources","modality","kind","review_flags")):
                raise ValueError("Drop and add to change an event's ID, kind or modality")
            row.update(changes)
            if ("start" in changes or "end" in changes) and "boundary_ranges" not in changes:
                row.pop("boundary_ranges",None)
        accepted.append(row)
    for e in decisions.get("add",[]):
        if e["id"] in grouped:
            raise ValueError("Added ID already in use")
        accepted.append({**e,"review_flags":[]})
    accepted.sort(key=lambda e:(e["start"],e["end"],e["id"]))
    header={k:v for k,v in annotation.items() if k not in ("events","relations","phase_relations","reference_status")}
    header["reviewer"]=decisions["reviewer"]
    result=package(header,accepted,status="human_adjudicated",scored_only=True)
    validate(result)
    return result

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("annotations",type=Path)
    p.add_argument("decisions",type=Path)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args(argv)
    if a.out.resolve() in (a.annotations.resolve(),a.decisions.resolve()):
        p.error("Choose an output separate from the inputs.")
    d=read_json(a.decisions)
    if d.get("annotations_sha256")!=file_hash(a.annotations):
        raise ValueError("Review decisions belong to a different annotation revision.")
    result=adjudicate(read_json(a.annotations),d)
    write_json(a.out,result)
