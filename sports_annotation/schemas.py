"""The same strict schemas are supplied in prompts and used locally."""
from copy import deepcopy


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


TEXT = {"type": "string"}
IDENT = {"type": "string", "minLength": 1, "pattern": "^[A-Za-z0-9_-]+$"}
NUMBER = {"type": "number", "minimum": 0}
RANGE = {"type": "array", "items": NUMBER, "minItems": 2, "maxItems": 2}
CONFIDENCE = {"enum": ["high", "medium", "low"]}
EVIDENCE = arr(obj({"time": NUMBER, "observation": {"type": "string", "minLength": 1}}))
TIME_FIELDS = {"start": NUMBER, "end": NUMBER, "start_range": RANGE, "end_range": RANGE}
ACTOR = obj({"id": IDENT, "shot_id": IDENT, "description": TEXT})
EXECUTION = obj({"id": IDENT, "actor_id": IDENT, "shot_id": IDENT,
                 "start": NUMBER, "end": NUMBER, "description": TEXT})
ACTION = obj({
    "id": IDENT, "actor_id": IDENT, "shot_id": IDENT,
    "execution_id": {"type": ["string", "null"]},
    "kind": {"enum": ["motion", "held_pose", "gesture"]}, "label": TEXT,
    **TIME_FIELDS, "detail": {"type": "string", "minLength": 1}, "evidence": EVIDENCE,
    "key_moments": arr(obj({"name": TEXT, "time": {"type": ["number", "null"], "minimum": 0},
                            "time_range": {"anyOf": [RANGE, {"type": "null"}]}})),
    "boundary_clipped": obj({"start": {"type": "boolean"}, "end": {"type": "boolean"}}),
    "confidence": CONFIDENCE,
})
VISUAL = obj({"schema_version": {"const": "1.0"}, "in_scope": {"type": "boolean"},
              "scope_note": TEXT, "actors": arr(ACTOR), "executions": arr(EXECUTION),
              "actions": arr(ACTION), "uncertainties": arr(TEXT)})
AUDIO_EVENT = obj({
    "id": IDENT, "kind": {"enum": ["speech", "transient", "friction", "background", "music", "other"]},
    "layer": {"enum": ["foreground", "background"]}, **TIME_FIELDS,
    "speaker_id": {"type": ["string", "null"]}, "description": TEXT,
    "evidence": EVIDENCE, "confidence": CONFIDENCE,
    "transcript": {"type": ["string", "null"]},
})
AUDIO = obj({"schema_version": {"const": "1.0"}, "events": arr(AUDIO_EVENT), "uncertainties": arr(TEXT)})
REVIEW = obj({"schema_version": {"const": "1.0"}, "visual": VISUAL, "audio": AUDIO,
              "change_log": arr(obj({"target": TEXT, "change": TEXT, "evidence": EVIDENCE})),
              "unresolved": arr(TEXT)})


def schema_for(stage):
    return deepcopy({"visual": VISUAL, "audio": AUDIO, "review": REVIEW}[stage])
