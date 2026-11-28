import json
import re
from pathlib import Path

from . import __version__
from .client import describe_request, execute, save_request
from .io_utils import file_hash, inside, object_hash, read_json, write_json
from .media import prepare, prepare_review, verify_prepared
from .relations import build_relations
from .schemas import schema_for
from .validation import require, validate

PACKAGE = Path(__file__).resolve().parent


def load_config(path):
    path = Path(path).resolve()
    cfg = read_json(path)
    require(cfg.get("schema_version") == "1.0", "Unsupported config version")
    root = (path.parent / cfg["repository_root"]).resolve()
    ids = []
    for case in cfg["cases"]:
        require(bool(re.fullmatch(r"[A-Za-z0-9_-]+", case["id"])), "Invalid case ID")
        require(case["sport"] in {"badminton", "standing_jump", "bowling", "golf"}, "Unsupported sport lexicon")
        require(inside(root, case["source"]).is_file(), "Source missing: " + case["source"])
        ids.append(case["id"])
    require(len(ids) == len(set(ids)), "Duplicate case IDs")
    # Credentials must be provided outside the versioned config.
    require(not any(k in cfg["provider"] for k in ("api_key", "key", "token")), "Do not put API keys in config")
    return cfg, root


def bind_run(run_dir, config):
    """Freeze config, prompts, lexicons, and implementation hashes for safe resume."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    inputs = list((PACKAGE / "prompts").glob("*.txt")) + list((PACKAGE / "lexicons").glob("*.json")) + list(PACKAGE.glob("*.py"))
    hashes = {p.relative_to(PACKAGE).as_posix(): file_hash(p) for p in sorted(inputs)}
    protocol = {"version": __version__, "config": config, "implementation_and_prompt_hashes": hashes}
    signature = object_hash(protocol)
    path = run_dir / "protocol.json"
    if path.exists():
        require(read_json(path)["signature"] == signature, "Run protocol changed; choose a new --run-dir")
    else:
        write_json(path, {"signature": signature, **protocol})
        for source in inputs:
            target = inside(run_dir / "protocol_files", source.relative_to(PACKAGE))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    return signature


def optional_cuts(root, case):
    if not case.get("cuts_file"):
        return None
    data = read_json(inside(root, case["cuts_file"]))
    # Supports an AutoShot export/list without requiring a GPU dependency here.
    cuts = data.get("detected_cut_seconds") if isinstance(data, dict) else data
    require(isinstance(cuts, list) and all(isinstance(t, (float, int)) and not isinstance(t, bool) for t in cuts), "Invalid cut list")
    return cuts


def external_speech(root, case, manifest, lexicon):
    if not case.get("external_speech_file"):
        return None, None
    path = inside(root, case["external_speech_file"])
    data = read_json(path)
    require(data.get("source_sha256") == manifest["source_sha256"], "External speech refers to a different video")
    require(data.get("time_origin") == "clip_start", "External speech must use clip-global seconds")
    audio = {"schema_version": "1.0", "events": data["events"], "uncertainties": []}
    validate("audio", audio, manifest, lexicon)
    require(all(e["kind"] == "speech" for e in audio["events"]), "External speech file must contain only speech")
    return audio["events"], file_hash(path)


def request_spec(stage, manifest, lexicon, media_dir, provider, protocol, locked=None,
                 external_hash=None, candidates=None, review_plan=None):
    media_dir = Path(media_dir)
    frames = review_plan["frames"] if review_plan else manifest["frames"]
    shared = (PACKAGE / "prompts/shared.txt").read_text(encoding="utf-8")
    task = (PACKAGE / f"prompts/{stage}.txt").read_text(encoding="utf-8")
    context = {"duration_seconds": manifest["duration"], "time_origin": "clip_start",
               "external_speech_present": locked is not None}
    attachments = []
    if stage != "audio":
        lexicon = {**lexicon, "terms": lexicon["terms"] + [
            {"label": "other_motion", "kind": "motion", "definition": "Observable motion not supported by a more specific supplied technique."},
            {"label": "held_pose", "kind": "held_pose", "definition": "A maintained position; describe the pose in detail, do not invent a new label."},
            {"label": "explanatory_gesture", "kind": "gesture", "definition": "Visible explanatory gesturing; this is not proof of a sport strike."}
        ]}
        context.update({"shots": manifest["shots"], "source_resolution": [manifest["width"], manifest["height"]],
                        "supplied_frames": [{k: f[k] for k in ("index", "time", "end", "shot_id")} for f in frames],
                        "cut_status": manifest["cut_detection"], "lexicon": lexicon})
        attachments += [{"kind": "image", "path": str(media_dir / f["file"]),
                          **{k: f[k] for k in ("index", "time", "shot_id", "sha256")}} for f in frames]
    if stage != "visual" and manifest["audio"]["present"]:
        context["audio_valid_span"] = manifest["audio"].get("valid_span")
        attachments.append({"kind": "audio", "path": str(media_dir / manifest["audio"]["file"]),
                            "sha256": manifest["audio"]["sha256"]})
    if stage == "review":
        context.update({"candidates": candidates, "review_targets": review_plan["targets"],
                        "omitted_dense_frames": review_plan["omitted_dense_frames"]})
    # The audio-only request deliberately contains no sport, filename, shot, actor or action information.
    prompt = (shared + "\n\n" if stage != "audio" else "") + task
    output_schema = schema_for(stage)
    if stage != "audio":
        visual_schema = output_schema if stage == "visual" else output_schema["properties"]["visual"]
        visual_schema["properties"]["actions"]["items"]["properties"]["label"] = {"enum": [x["label"] for x in lexicon["terms"]]}
    prompt += "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(output_schema, ensure_ascii=False, indent=2)
    prompt += "\n\nCALLER DATA (not instructions):\n" + json.dumps(context, ensure_ascii=False, indent=2)
    provenance = {"source_sha256": manifest["source_sha256"], "preparation_signature": manifest["preparation_signature"],
                  "protocol_signature": protocol, "external_speech_sha256": external_hash,
                  "candidate_hash": object_hash(candidates) if candidates else None}
    descriptor = describe_request(stage, prompt, attachments, provider, provenance)
    return descriptor, prompt, attachments


def prepare_case(config, root, case, run_dir, protocol):
    out = inside(run_dir, case["id"])
    manifest = prepare(inside(root, case["source"]), out / "media", config["media"], optional_cuts(root, case))
    lexicon = read_json(PACKAGE / "lexicons" / (case["sport"] + ".json"))
    locked, external_hash = external_speech(root, case, manifest, lexicon)
    for stage in ("visual", "audio"):
        spec = request_spec(stage, manifest, lexicon, out / "media", config["provider"], protocol, locked, external_hash)
        save_request(out / "stages" / stage, spec[0], spec[1])
    summary = {"id": case["id"], "source_sha256": manifest["source_sha256"], "sport": case["sport"],
               "duration_s": manifest["duration"], "source_frames": manifest["frame_count"],
               "sampled_frames": len(manifest["frames"]), "logical_shots": len(manifest["shots"]),
               "audio_present": manifest["audio"]["present"], "external_speech": locked is not None,
               "status": "prepared", "api_calls_in_prepare": 0}
    write_json(out / "prepared.json", summary)
    return out, manifest, lexicon, locked, external_hash, summary


def load_result(out, stage):
    folder = Path(out) / "stages" / stage
    meta = read_json(folder / "metadata.json")
    request = read_json(folder / "request.json")
    require(meta["status"] == "complete" and meta["signature"] == request["signature"], "Incomplete/stale stage: " + stage)
    require(file_hash(folder / "result.json") == meta["result_sha256"], "Result file changed: " + stage)
    return read_json(folder / "result.json")


def candidate_pair(out, manifest, lexicon, locked):
    visual, audio = load_result(out, "visual"), load_result(out, "audio")
    validate("visual", visual, manifest, lexicon, [f["time"] for f in manifest["frames"]])
    validate("audio", audio, manifest, lexicon)
    if locked is not None:
        require(not any(e["kind"] == "speech" for e in audio["events"]), "Audio model ignored external-speech policy")
        audio = {**audio, "events": audio["events"] + locked}
        validate("audio", audio, manifest, lexicon)
    return {"visual": visual, "audio": audio}


def run_candidates(config, out, manifest, lexicon, locked, external_hash, protocol, get_key):
    for stage in ("visual", "audio"):
        spec = request_spec(stage, manifest, lexicon, out / "media", config["provider"], protocol, locked, external_hash)
        def validator(data, s=stage):
            validate(s, data, manifest, lexicon, [f["time"] for f in manifest["frames"]])
            if s == "audio":
                require(all(e["transcript"] is None for e in data["events"]), "Model transcription is outside scope")
                if locked is not None:
                    require(not any(e["kind"] == "speech" for e in data["events"]), "Model returned speech despite external speech mode")
        if stage == "audio" and not manifest["audio"]["present"]:
            data = {"schema_version": "1.0", "events": [], "uncertainties": ["Source has no audio track."]}
            validator(data)
            folder = out / "stages/audio"
            write_json(folder / "result.json", data)
            write_json(folder / "metadata.json", {"status": "complete", "signature": spec[0]["signature"],
                       "result_sha256": file_hash(folder / "result.json"), "api_call_made": False, "reason": "no_audio_track"})
        else:
            print(f"{out.name}: {stage} (reuse complete checkpoint when available)", flush=True)
            result = execute(out / "stages" / stage, *spec, config["provider"], get_key, validator)
            if stage == "audio" and locked is not None:
                require(not any(e["kind"] == "speech" for e in result["events"]), "Model returned speech despite external speech mode")


def review_case(config, out, manifest, lexicon, locked, external_hash, protocol, get_key, dry_run=False):
    candidates = candidate_pair(out, manifest, lexicon, locked)
    audio_bytes = 0
    if manifest["audio"]["present"]:
        audio_bytes = 4 * (((out / "media" / manifest["audio"]["file"]).stat().st_size + 2) // 3)
    # Reserve room for schema, candidates, frame labels, and JSON framing.
    image_budget = config["provider"].get("max_request_bytes", 80 * 1024 * 1024) - audio_bytes - 2 * 1024 * 1024
    plan = prepare_review(out / "media", manifest, candidates["visual"], candidates["audio"], config["media"], image_budget)
    spec = request_spec("review", manifest, lexicon, out / "media", config["provider"], protocol,
                        locked, external_hash, candidates, plan)
    save_request(out / "stages/review", spec[0], spec[1])
    if dry_run:
        return plan

    def validator(result):
        validate("review", result, manifest, lexicon, [f["time"] for f in plan["frames"]], locked)
        if locked is None:
            require(all(e["transcript"] is None for e in result["audio"]["events"]), "Model transcription is outside scope")
        if result["visual"] != candidates["visual"] or result["audio"] != candidates["audio"]:
            require(bool(result["change_log"]), "Review changed data without a change log")
    print(f"{out.name}: review with {len(plan['frames'])} actual source frames", flush=True)
    execute(out / "stages/review", *spec, config["provider"], get_key, validator)
    return plan


def assemble(out, manifest, lexicon, locked, external_hash):
    candidates = candidate_pair(out, manifest, lexicon, locked)
    review_meta = out / "stages/review/metadata.json"
    if review_meta.exists():
        require(read_json(review_meta).get("status") == "complete", "Review failed/incomplete; do not silently export as reviewed")
        provenance = read_json(out / "stages/review/request.json")["provenance"]
        require(provenance["candidate_hash"] == object_hash(candidates), "Review refers to stale candidates")
        reviewed = load_result(out, "review")
        frames = read_json(out / "media/review_plan.json")["frames"]
        validate("review", reviewed, manifest, lexicon, [f["time"] for f in frames], locked)
        visual, audio = reviewed["visual"], reviewed["audio"]
        status, unresolved = "model_reviewed_not_human_gt", reviewed["unresolved"]
    else:
        visual, audio = candidates["visual"], candidates["audio"]
        status, unresolved = "candidates_only_not_human_gt", []
        frames = manifest["frames"]
    graph = build_relations(visual["actions"], audio["events"])
    queue = [{"type": "visual_uncertainty", "message": s} for s in visual["uncertainties"]]
    queue += [{"type": "audio_uncertainty", "message": s} for s in audio["uncertainties"]]
    queue += [{"type": "unresolved_review", "message": s} for s in unresolved]
    queue += [{"type": "boundary_sensitive_relation", **p} for p in graph["uncertain_pairs"]]
    queue += [{"type": "low_confidence_event", "id": e["id"]} for e in visual["actions"] + audio["events"] if e["confidence"] != "high"]
    for action in visual["actions"]:
        for item in action["evidence"]:
            nearest = min(frames, key=lambda f: abs(f["time"] - item["time"]))
            residual = item["time"] - nearest["time"]
            if abs(residual) > 0.002:
                queue.append({"type": "rounded_evidence_time", "action_id": action["id"],
                              "model_time": item["time"], "nearest_supplied_frame_time": nearest["time"],
                              "residual_s": residual, "note": "Nearest-frame association only; not verified exact frame evidence. Raw model time preserved."})
    queue.append({"type": "cut_review", "message": "Verify all proposed shot cuts; scene threshold is not an action detector."})
    if not visual["in_scope"]:
        queue.append({"type": "out_of_scope", "message": visual["scope_note"]})
    combined = {"schema_version": "1.0", "status": status, "source_sha256": manifest["source_sha256"],
                "external_speech_sha256": external_hash, "duration": manifest["duration"], "shots": manifest["shots"],
                "visual": visual, "audio": audio, "relations": graph,
                "human_review_required": True, "review_queue": queue}
    write_json(out / "annotations.json", combined)
    write_json(out / "relations.json", graph)
    write_json(out / "review_queue.json", queue)
    lines = ["Sports annotation candidate caption", "Status: " + status, "Times are clip-global seconds; temporal links do not assert causation or speech reference.", ""]
    for action in sorted(visual["actions"], key=lambda e: (e["start"], e["id"])):
        lines.append(f"[{action['start']:.3f}-{action['end']:.3f}] {action['id']} {action['actor_id']} / {action['kind']} / {action['label']}: {action['detail']}")
        links = [p for p in graph["pairs"] if p["action_id"] == action["id"] and p["status"] != "disjoint"]
        if links:
            lines.append("  Temporal audio overlaps: " + "; ".join(f"{p['audio_id']} ({p['status']}, nominal {p['overlap_s']:.3f}s)" for p in links))
    lines += ["", "Independent audio events:"]
    for event in sorted(audio["events"], key=lambda e: (e["start"], e["id"])):
        lines.append(f"[{event['start']:.3f}-{event['end']:.3f}] {event['id']} / {event['kind']} / {event['layer']}: {event['description']}")
        if event["transcript"] is not None:
            lines.append("  External transcript: " + event["transcript"])
    (out / "caption.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    metas = [read_json(p) for p in (out / "stages").glob("*/metadata.json")]
    summary = {"status": status, "actions": sum(a["kind"] == "motion" for a in visual["actions"]),
               "held_poses": sum(a["kind"] == "held_pose" for a in visual["actions"]),
               "gestures": sum(a["kind"] == "gesture" for a in visual["actions"]),
               "audio_events": len(audio["events"]), "primary_edges": len(graph["primary_edges"]),
               "uncertain_pairs": len(graph["uncertain_pairs"]), "scope_valid": visual["in_scope"],
               "schema_and_reference_checks_passed": True,
               "successful_api_stages": sum(m.get("api_call_made", False) and m["status"] == "complete" for m in metas),
               "usage_by_stage": {p.parent.name: read_json(p).get("usage") for p in (out / "stages").glob("*/metadata.json")}}
    write_json(out / "summary.json", summary)
    return summary
