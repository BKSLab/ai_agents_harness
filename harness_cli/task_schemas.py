"""Versioned task contracts. Structural validation never substitutes for human authorization."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

_DEVICES = ("con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
            *(f"lpt{i}" for i in range(1, 10)))
_RESERVED = "|".join("".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else c for c in word)
                     for word in _DEVICES)
ID = {"type": "string", "pattern": rf"^(?!(?:{_RESERVED})(?:\.|$))[A-Za-z0-9](?:[A-Za-z0-9_.-]{{0,78}}[A-Za-z0-9_-])?$"}
TEXT = {"type": "string", "minLength": 1, "maxLength": 12000}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}


def record(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


def array(items, minimum=0, maximum=100):
    return {"type": "array", "items": items, "minItems": minimum, "maxItems": maximum, "uniqueItems": True}


PLAN = record({
    "schema_version": {"const": 1},
    "scope": array(TEXT, 1),
    "acceptance": array(record({"id": ID, "description": TEXT, "checks": array(ID, 1)}), 1),
    "risks": array(record({"id": ID, "description": TEXT, "checks": array(ID, 1),
                           "severity": {"enum": ["low", "medium", "high"]}})),
    "checks": array(record({"id": ID, "argv": array(TEXT, 1, 100),
                            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 600}},
                           ["id", "argv"]), 1),
    "rollback": TEXT,
    "compatibility": TEXT,
}, ["schema_version", "scope", "acceptance", "risks", "checks"])
# Repeated command arguments are valid (e.g. multiple -k/-c flags).
PLAN["properties"]["checks"]["items"]["properties"]["argv"]["uniqueItems"] = False

REVIEW = record({
    "schema_version": {"const": 1},
    "snapshot_id": ID,
    "fingerprint": HASH,
    "plan_hash": HASH,
    "verification_id": ID,
    "reviewer": TEXT,
    "status": {"enum": ["approved", "changes_requested", "blocked"]},
    "summary": TEXT,
    "findings": array(record({"id": ID, "severity": {"enum": ["blocker", "major", "minor"]},
                              "location": TEXT, "problem": TEXT, "evidence": TEXT, "suggestion": TEXT})),
    "limitations": array(TEXT),
})


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in mapping:
            raise ValueError("YAML keys must be unique strings.")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def read_input(path):
    path = Path(path)
    if path.stat().st_size > 1_000_000:
        raise ValueError("Structured task input exceeds 1 MB.")
    try:
        return yaml.load(path.read_text(encoding="utf-8-sig"), Loader=UniqueLoader)
    except (yaml.YAMLError, UnicodeError, RecursionError) as exc:
        raise ValueError("Task input is not valid UTF-8 JSON/YAML.") from exc


def validate(value, schema):
    try:
        errors = list(Draft202012Validator(schema).iter_errors(value))
    except (RecursionError, TypeError) as exc:
        raise ValueError("Invalid structured input.") from exc
    if errors:
        path = "/".join(str(part) for part in errors[0].absolute_path) or "root"
        # jsonschema error.message embeds input values, which may be private.
        raise ValueError(f"Invalid structured input at {path}; violated {errors[0].validator}.")
    json.dumps(value, allow_nan=False)
    return value
