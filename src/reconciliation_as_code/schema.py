from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from .errors import SpecError

SCHEMA_FILES = {
    "spec": "reconciliation.schema.json",
    "evidence": "evidence.schema.json",
}


def schema_text(kind: str) -> str:
    try:
        filename = SCHEMA_FILES[kind]
    except KeyError as exc:
        raise SpecError(f"Unknown schema {kind!r}. Expected one of: {', '.join(sorted(SCHEMA_FILES))}.") from exc
    resource = files("reconciliation_as_code").joinpath("_schemas", filename)
    return resource.read_text(encoding="utf-8")


def load_schema(kind: str) -> dict[str, Any]:
    return json.loads(schema_text(kind))
