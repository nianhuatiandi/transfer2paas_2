import math
from collections import Counter

from jsonschema import Draft202012Validator

from .schemas import schema_for

# Models commonly serialize a frame-boundary time to three decimals. This is
# numeric tolerance only; it does not establish millisecond annotation accuracy.
EPS = 0.001
EVIDENCE_ROUNDING_TOLERANCE = 0.051


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), "Non-finite number")
    elif isinstance(value, dict):
        for item in value.values():
            check_finite(item)
    elif isinstance(value, list):
        for item in value:
            check_finite(item)


def index_unique(items, what):
    result = {v["id"]: v for v in items}
    require(len(result) == len(items), f"Duplicate {what} IDs")
    return result


def interval(item, low, high, uncertain=True):
    start, end = item["start"], item["end"]
    require(low - EPS <= start < end <= high + EPS, f"Invalid interval: {item.get('id')}")
    if uncertain:
        for key in ("start", "end"):
            lo, hi = item[key + "_range"]
            require(low - EPS <= lo <= item[key] <= hi <= high + EPS,
                    f"Invalid {key} uncertainty bracket: {item.get('id')}")


def evidence(items, low, high, frame_times=None):
    for e in items:
        require(low - EPS <= e["time"] <= high + EPS, "Evidence outside supplied time span")
        if frame_times is not None:
            require(any(abs(e["time"] - t) <= EVIDENCE_ROUNDING_TOLERANCE for t in frame_times),
                    f"Evidence references an unsupplied frame: {e['time']}")


def validate_visual(data, manifest, lexicon, frame_times=None):
    shots = {s["id"]: s for s in manifest["shots"]}
    actors = index_unique(data["actors"], "actor")
    executions = index_unique(data["executions"], "execution")
    index_unique(data["actions"], "action")
    for actor in actors.values():
        require(actor["shot_id"] in shots, "Unknown actor shot")
        require(actor["id"].startswith(actor["shot_id"] + "-P"), "Use shot-local actor IDs, e.g. S01-P01")
    if data["in_scope"]:
        require(all(n <= 2 for n in Counter(a["shot_id"] for a in actors.values()).values()),
                "More than two main actors in a shot; flag out of scope")
    for item in list(executions.values()) + data["actions"]:
        require(item["shot_id"] in shots, "Unknown event shot")
        require(item["actor_id"] in actors, "Unknown event actor")
        require(actors[item["actor_id"]]["shot_id"] == item["shot_id"], "Actor crosses shot identity boundary")
        shot = shots[item["shot_id"]]
        interval(item, shot["start"], shot["end"], uncertain="start_range" in item)
    labels = {x["label"]: x for x in lexicon["terms"]}
    labels.update({"other_motion": {"kind": "motion"}, "held_pose": {"kind": "held_pose"},
                   "explanatory_gesture": {"kind": "gesture"}})
    for action in data["actions"]:
        require(action["label"] in labels, f"Unknown technique: {action['label']}")
        require(action["kind"] == labels[action["label"]].get("kind", "motion"), "Label/kind mismatch")
        parent = action["execution_id"]
        if parent is not None:
            require(parent in executions, "Unknown execution parent")
            ex = executions[parent]
            require(ex["actor_id"] == action["actor_id"] and ex["shot_id"] == action["shot_id"], "Wrong execution parent")
            interval(action, ex["start"], ex["end"], uncertain=False)
        shot = shots[action["shot_id"]]
        require(bool(action["evidence"]), "Action requires visible evidence")
        evidence(action["evidence"], shot["start"], shot["end"], frame_times)
        for anchor in action["key_moments"]:
            if anchor["time"] is None:
                require(anchor["time_range"] is None, "Unobserved anchor must have null range")
            else:
                require(anchor["time_range"] is not None, "Observed anchor requires a bracket")
                lo, hi = anchor["time_range"]
                require(action["start"] - EPS <= anchor["time"] <= action["end"] + EPS and
                        action["start_range"][0] - EPS <= lo <= anchor["time"] <= hi <= action["end_range"][1] + EPS,
                        "Anchor outside action")


def validate_audio(data, manifest):
    index_unique(data["events"], "audio")
    for event in data["events"]:
        interval(event, 0, manifest["duration"])
        require(bool(event["evidence"]), "Audio event requires audible evidence")
        evidence(event["evidence"], 0, manifest["duration"])
        require(event["kind"] == "speech" or event["speaker_id"] is None, "Non-speech event has a speaker")
        require(event["kind"] == "speech" or event["transcript"] is None, "Non-speech event has a transcript")
        spans = manifest.get("audio", {}).get("valid_span")
        if spans:
            require(max(event["start"], spans[0]) < min(event["end"], spans[1]),
                    "Audio event lies entirely in padded silence")
    if not manifest.get("audio", {}).get("present", True):
        require(not data["events"], "Events in a source without an audio track")


def validate(stage, data, manifest, lexicon, frame_times=None, locked_speech=None):
    check_finite(data)
    Draft202012Validator(schema_for(stage)).validate(data)
    if stage == "visual":
        validate_visual(data, manifest, lexicon, frame_times)
    elif stage == "audio":
        validate_audio(data, manifest)
    else:
        validate_visual(data["visual"], manifest, lexicon, frame_times)
        validate_audio(data["audio"], manifest)
        if locked_speech is not None:
            actual = [e for e in data["audio"]["events"] if e["kind"] == "speech"]
            require(sorted(actual, key=lambda e: e["id"]) == sorted(locked_speech, key=lambda e: e["id"]),
                    "Review changed externally supplied speech")
    return data
