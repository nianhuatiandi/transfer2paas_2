"""Temporal co-occurrence only: no source causation or language-reference inference."""

EPS = 1e-9


def temporal_relation(action, sound):
    left = max(action["start"], sound["start"])
    right = min(action["end"], sound["end"])
    overlap = max(0.0, right - left)
    # Conservative lower and upper bounds from independently uncertain endpoints.
    lower = max(0.0, min(action["end_range"][0], sound["end_range"][0]) -
                max(action["start_range"][1], sound["start_range"][1]))
    upper = max(0.0, min(action["end_range"][1], sound["end_range"][1]) -
                max(action["start_range"][0], sound["start_range"][0]))
    status = "overlap" if lower > EPS else "disjoint" if upper <= EPS else "uncertain"
    return {"action_id": action["id"], "audio_id": sound["id"],
            "action_kind": action["kind"], "audio_layer": sound["layer"],
            "nominal_overlap": overlap > EPS, "status": status,
            "intersection": [round(left, 6), round(right, 6)] if overlap > EPS else None,
            "overlap_s": round(overlap, 6), "overlap_range_s": [round(lower, 6), round(upper, 6)],
            "action_coverage": overlap / (action["end"] - action["start"]),
            "audio_coverage": overlap / (sound["end"] - sound["start"]),
            "audio_minus_action_start_s": round(sound["start"] - action["start"], 6),
            "audio_minus_action_end_s": round(sound["end"] - action["end"], 6)}


def build_relations(actions, events):
    pairs = [temporal_relation(a, u) for a in actions for u in events]
    return {"definition": "Half-open intervals; any strictly positive intersection. No semantic or causal assertion.",
            "certainty_note": "Status depends on supplied boundary brackets, not measured human certainty.",
            "pairs": pairs,
            "primary_edges": [p for p in pairs if p["action_kind"] == "motion" and p["audio_layer"] == "foreground" and p["status"] == "overlap"],
            "uncertain_pairs": [p for p in pairs if p["status"] == "uncertain"],
            "context_edges": [p for p in pairs if (p["action_kind"] != "motion" or p["audio_layer"] == "background") and p["status"] == "overlap"]}
