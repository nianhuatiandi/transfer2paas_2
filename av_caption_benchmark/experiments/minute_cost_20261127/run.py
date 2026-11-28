"""Measure the current three-pass pipeline on the first minute of the badminton source."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
import getpass
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "three_pass_20261127"))
import run_trial as trial
import finalize_trial as finalize

CASE = HERE / "badminton_60s"

def prepare():
    CASE.mkdir(parents=True, exist_ok=True)
    clip = CASE / "clip.mp4"
    source, = HERE.parents[3].glob("*.31679122798.mp4")
    if not clip.exists():
        subprocess.run([trial.FF, "-v", "error", "-i", str(source), "-t", "60", "-map", "0:v:0",
                        "-map", "0:a:0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(clip)], check=True)
    with trial.av.open(str(clip)) as container:
        duration = container.duration / 1_000_000
        assert len(container.streams.audio) == 1 and abs(duration - 60) < .1
    selection = dict(id="sport01", title="羽毛球挑球教学", source=source.name, source_window=[0,60],
                     duration=duration, sha256=trial.file_hash(clip))
    trial.write_json(CASE / "selection.json", selection)
    return selection

def recover_repeated_ids(dest, name, prompt, refs, provenance, validator, cfg):
    # The one-minute trial exhausted the standard retries. Preserve every charged call.
    last = dest / 'retry2' / 'metadata.json'
    def exhausted():
        return name == 'align_instances' and last.exists() and trial.read_json(last).get('error') == 'Invalid grouping'
    if not exhausted():
        try:
            return trial.request(dest, name, prompt, refs, provenance, validator, cfg)
        except RuntimeError:
            if not exhausted():
                raise
    raw = json.loads((dest / 'response.txt').read_text('utf8'))
    counts = Counter(token for group in raw['groups'] for token in group)
    unique = [[token for token in group if counts[token] == 1] for group in raw['groups']]
    invalid = [group for group in unique if len({i.split('.')[0] for i in group}) != len(group)]
    recovered = {'groups':[group for group in unique if 2 <= len(group) <= 3 and group not in invalid]}
    validator(recovered)
    trial.write_json(dest / 'local_recovery.json', {'source':'response.txt', 'withheld_repeated_ids':
                     sorted(k for k,v in counts.items() if v>1), 'withheld_same_round_groups':invalid, 'result':recovered})
    return recovered

def run():
    selection = prepare()
    refs = trial.media(CASE)
    print("duration", selection["duration"], "stills", len(refs["visual"])-1, flush=True)
    if not os.getenv("QWEN_API_KEY"):
        os.environ["QWEN_API_KEY"] = getpass.getpass("Qwen credential: ")
    with ThreadPoolExecutor(4) as pool:
        jobs = {pool.submit(trial.annotate, CASE, selection, refs[mode], mode, n): (mode, n)
                for n in (1,2,3) for mode in ("visual", "audio")
                if not (CASE / f"round{n}" / (mode + ".json")).exists()}
        for job in as_completed(jobs):
            job.result()
            print("done", jobs[job], flush=True)
    if not (CASE / "consensus.json").exists():
        finalize.request = recover_repeated_ids
        finalize.one(CASE)
    # Replicate the optional joint-media replay on three reproducible disputed facts.
    consensus = trial.read_json(CASE / "consensus.json")
    claims = []
    for mode, field in (("visual", "brief"), ("audio", "text")):
        singles = [g for g in consensus["groups"][mode] if g["votes"] == 1]
        if singles:
            g = singles[len(singles) // 2]
            claims.append({"id":str(len(claims)+1), "claim":f"{g['start']:.2f}–{g['end']:.2f} s，{g['example'][field]}"})
    candidates = [row for row in consensus["edges"] if not row["keep"] and row["median_intersection"]]
    if candidates:
        edge = max(candidates, key=lambda e:e["median_intersection"][1]-e["median_intersection"][0])
        lookup = {g["id"]:g["example"] for groups in consensus["groups"].values() for g in groups}
        v, a = lookup[edge["visual"]], lookup[edge["audio"]]
        lo, hi = edge["median_intersection"]
        claims.append({"id":str(len(claims)+1), "claim":f"{lo:.2f}–{hi:.2f} s，同时可见、可听：{v['brief']} / {a['text']}"})
    if claims and not (CASE / "replay.json").exists():
        prompt = (trial.HERE / "prompts/verify.txt").read_text("utf8") + "\n" + json.dumps(claims, ensure_ascii=False)
        def check(out):
            assert [str(i["id"]) for i in out["checks"]] == [c["id"] for c in claims]
            for i in out["checks"]:
                assert i["verdict"] in ("supported","contradicted","unclear") and i["evidence"]
                assert i.get("time_s") is None or 0 <= i["time_s"] <= selection["duration"] + .05
        cfg = {**trial.CFG,"extra_body":{**trial.CFG["extra_body"],"temperature":.1}}
        out = trial.request(CASE / "verification/replay", "replay", prompt, refs["visual"]+refs["audio"],
                            {"source":selection["sha256"]}, check, cfg)
        trial.write_json(CASE / "replay.json", {"claims":claims, "checks":out["checks"]})
    print("complete", flush=True)

if __name__ == "__main__":
    run()
