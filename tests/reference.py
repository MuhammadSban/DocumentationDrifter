# talks to the reference service and compares its answers and schemas with ours

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REFERENCE_URL = os.environ.get("DRIFTER_REFERENCE_URL", "https://doc-tracker-5t4s.onrender.com/system").rstrip("/")
CAPTURED_OPENAPI = Path(__file__).parent / "data" / "reference-openapi.json"

# names every model the two services must agree on
SHARED_MODELS = ["AnalysisRequest", "AnalysisResult", "Change", "Finding", "Skipped", "ErrorBody", "TestSetupRequest"]

# lists the only differences allowed between the services, in one place (ticket 09)
# removes these fields before comparing, they differ every run or name the build
VOLATILE_FIELDS = ("analysis_id", "created_at", "tool_version")
# allows these fields to differ, our rules file is not theirs
KNOWN_DIFFERENT_FIELDS = ("config_version",)
# allows these category swaps, they have no DOCUMENTATION yet
KNOWN_CATEGORY_SWAPS = {("DOCUMENTATION", "OTHER")}
# allows enum values only our schema has
KNOWN_SCHEMA_EXTRAS = {"DOCUMENTATION"}
# allows a named difference in one case, each agreed by Kaan
KNOWN_CASE_DIFFERENCES = {
    "unfetchable-short-sha": ("body.message", "decision Q6: ours asks for the full 40-character SHA, 2026-10-17"),
    "course-setup-no-body": ("body.message", "decision T12-Q4: theirs says ' is required' with no field name, a fault, 2026-10-17"),
}


def warm(base_url: str = REFERENCE_URL, tries: int = 12, wait: float = 10) -> bool:
    # wakes a sleeping service through its health route, True once it answers
    for _ in range(tries):
        try:
            if httpx.get(f"{base_url}/health", timeout=20).status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(wait)
    return False


def reachable(base_url: str = REFERENCE_URL) -> bool:
    # checks once, quickly, whether the service answers at all
    try:
        httpx.get(f"{base_url}/health", timeout=10)
        return True
    except httpx.HTTPError:
        return False


# --- answers ---------------------------------------------------------


def normalise(body: Any) -> Any:
    # drops the volatile fields, so the rest can be compared exactly
    if isinstance(body, dict):
        return {k: v for k, v in body.items() if k not in VOLATILE_FIELDS}
    return body


def _hidden(path: str | None) -> bool:
    # tells a hidden path, any segment starting with a dot
    return path is not None and any(part.startswith(".") for part in path.split("/"))


def _without_hidden(change: dict) -> dict | None:
    # rewrites one of their changes the way ours reports it with hidden paths ignored (decision T12-Q9)
    new, old = _hidden(change["path"]), _hidden(change.get("old_path"))
    if change["change_type"] != "RENAMED":
        return None if new else change
    if new and old:
        return None
    if old:
        return {**change, "change_type": "ADDED", "old_path": None}
    if new:
        return {**change, "path": change["old_path"], "change_type": "DELETED", "old_path": None}
    return change


def comparable(ours: Any, theirs: Any) -> tuple[Any, Any]:
    # removes the known difference by choice: their hidden paths
    if not (isinstance(ours, dict) and isinstance(theirs, dict) and "changes" in theirs):
        return ours, theirs
    changes = [c for c in map(_without_hidden, theirs["changes"]) if c is not None]
    skipped = [s for s in theirs.get("skipped", []) if not _hidden(s["path"])]
    return ours, {**theirs, "changes": sorted(changes, key=lambda c: c["path"]), "skipped": skipped}


def differences(ours: Any, theirs: Any, where: str = "body") -> list[str]:
    # lists every difference that is not a known one, each naming the field
    if isinstance(ours, dict) and isinstance(theirs, dict):
        found = []
        for key in sorted(set(ours) | set(theirs)):
            path = f"{where}.{key}"
            if key in KNOWN_DIFFERENT_FIELDS and where == "body":
                continue
            if key not in ours or key not in theirs:
                found.append(f"{path}: only in {'ours' if key in ours else 'theirs'}")
                continue
            if key == "category" and (ours[key], theirs[key]) in KNOWN_CATEGORY_SWAPS:
                continue
            found += differences(ours[key], theirs[key], path)
        return found
    if isinstance(ours, list) and isinstance(theirs, list):
        if len(ours) != len(theirs):
            return [f"{where}: {len(ours)} items in ours, {len(theirs)} in theirs"]
        return [d for i, (a, b) in enumerate(zip(ours, theirs)) for d in differences(a, b, f"{where}[{i}]")]
    return [] if ours == theirs else [f"{where}: ours {ours!r}, theirs {theirs!r}"]


def key_shape(body: Any) -> Any:
    # reduces a body to its keys and value types, for answers whose values differ by design
    if isinstance(body, dict):
        return {k: key_shape(v) for k, v in body.items()}
    if isinstance(body, list):
        return [key_shape(v) for v in body]
    return type(body).__name__


# --- schemas ---------------------------------------------------------


def shape(doc: dict, schema: dict) -> Any:
    # reduces a JSON schema to what callers depend on: types, enums, nesting, nullability
    if "$ref" in schema:
        name = schema["$ref"].rsplit("/", 1)[-1]
        target = doc["components"]["schemas"][name]
        return shape(doc, target) if "enum" in target else ("model", name)
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [shape(doc, s) for s in schema[key]]
            nullable = ("null",) in options
            rest = [o for o in options if o != ("null",)]
            inner = rest[0] if len(rest) == 1 else ("union", tuple(sorted(map(repr, rest))))
            return ("nullable", inner) if nullable else inner
    if "allOf" in schema and len(schema["allOf"]) == 1:
        return shape(doc, schema["allOf"][0])
    if "enum" in schema:
        return ("enum", frozenset(schema["enum"]))
    if schema.get("type") == "array":
        return ("array", shape(doc, schema.get("items", {})))
    if schema.get("nullable"):
        return ("nullable", (schema.get("type"),))
    return (schema.get("type"),)


def model_shape(doc: dict, name: str) -> dict:
    # describes one model as {field: (required, shape)}
    model = doc["components"]["schemas"][name]
    required = set(model.get("required", []))
    return {f: (f in required, shape(doc, s)) for f, s in model.get("properties", {}).items()}


def schema_differences(ours: dict, theirs: dict) -> list[str]:
    # lists differences in the shared models, allowing only our known enum extras
    found = []
    for name in SHARED_MODELS:
        if name not in theirs["components"]["schemas"]:
            found.append(f"{name}: missing from the reference document")
            continue
        a, b = model_shape(ours, name), model_shape(theirs, name)
        for field in sorted(set(a) | set(b)):
            if field not in a or field not in b:
                found.append(f"{name}.{field}: only in {'ours' if field in a else 'theirs'}")
            elif _strip_extras(a[field]) != _strip_extras(b[field]):
                found.append(f"{name}.{field}: ours {a[field]!r}, theirs {b[field]!r}")
    return found


def _strip_extras(value: Any) -> Any:
    # removes our known enum extras, wherever they sit in a shape
    if isinstance(value, frozenset):
        return value - KNOWN_SCHEMA_EXTRAS
    if isinstance(value, tuple):
        return tuple(_strip_extras(v) for v in value)
    return value


def capture() -> None:
    # saves the live reference OpenAPI document as test data for the offline schema test
    doc = httpx.get(f"{REFERENCE_URL}/openapi.json", timeout=90).json()
    CAPTURED_OPENAPI.parent.mkdir(exist_ok=True)
    CAPTURED_OPENAPI.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    print(f"saved {CAPTURED_OPENAPI}")


if __name__ == "__main__":
    # runs the capture, as python tests/reference.py capture
    if sys.argv[1:] == ["capture"]:
        capture()
    else:
        sys.exit("usage: python tests/reference.py capture")
