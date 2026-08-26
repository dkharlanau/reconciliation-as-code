from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from .errors import DataError, SpecError
from .io import load_table
from .spec import validate_spec


def _is_null(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _value_type(value: Any) -> str:
    if _is_null(value):
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    text = str(value).strip()
    if text.lower() in {"true", "false"}:
        return "boolean"
    try:
        int(text)
        return "integer"
    except ValueError:
        pass
    try:
        Decimal(text.replace(",", ""))
        return "number"
    except InvalidOperation:
        pass
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
        return "datetime"
    except ValueError:
        return "string"


def _column_type(values: list[Any]) -> str:
    types = {_value_type(value) for value in values if not _is_null(value)}
    if not types:
        return "empty"
    if types <= {"integer"}:
        return "integer"
    if types <= {"integer", "number"}:
        return "number"
    if len(types) == 1:
        return next(iter(types))
    return "mixed"


def _normalized_name(name: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def _key_name_score(name: str) -> float:
    normalized = _normalized_name(name)
    if normalized == "ID":
        return 1.0
    if normalized.endswith("ID") or "KEY" in normalized:
        return 0.9
    if normalized.endswith("CODE") or normalized.endswith("NUMBER") or normalized.endswith("NO"):
        return 0.7
    return 0.2


def inspect_dataset(
    path: str | Path, *, sheet: str | None = None, delimiter: str = ","
) -> dict[str, Any]:
    input_path = Path(path).expanduser().resolve()
    endpoint: dict[str, Any] = {"file": input_path.name, "key": "__profile__"}
    if sheet:
        endpoint["sheet"] = sheet
    if input_path.suffix.lower() == ".csv":
        endpoint["delimiter"] = delimiter
    resolved, rows = load_table(endpoint, input_path.parent)
    if not rows:
        raise DataError(f"Cannot inspect an empty dataset: {resolved}")

    columns = list(rows[0].keys())
    profile_columns: list[dict[str, Any]] = []
    candidate_keys: list[dict[str, Any]] = []
    row_count = len(rows)

    for name in columns:
        values = [row.get(name) for row in rows]
        non_null = [value for value in values if not _is_null(value)]
        distinct = len({str(value) for value in non_null})
        null_count = row_count - len(non_null)
        uniqueness = distinct / len(non_null) if non_null else 0.0
        item = {
            "name": name,
            "type": _column_type(values),
            "null_count": null_count,
            "null_rate": round(null_count / row_count, 6),
            "distinct_count": distinct,
            "uniqueness": round(uniqueness, 6),
        }
        profile_columns.append(item)
        if null_count == 0 and distinct == row_count:
            candidate_keys.append(
                {
                    "field": name,
                    "uniqueness": 1.0,
                    "null_rate": 0.0,
                    "key_name_score": _key_name_score(name),
                    "reason": "single-column values are unique and non-null",
                }
            )

    candidate_keys.sort(key=lambda item: (-item["key_name_score"], item["field"]))
    return {
        "file": str(resolved),
        "format": resolved.suffix.lower().lstrip("."),
        "rows": row_count,
        "columns": profile_columns,
        "candidate_keys": candidate_keys,
    }


def suggest_field_mappings(source_profile: dict[str, Any], target_profile: dict[str, Any]) -> list[dict[str, Any]]:
    source_names = [item["name"] for item in source_profile["columns"]]
    target_names = [item["name"] for item in target_profile["columns"]]
    target_by_normalized: dict[str, list[str]] = defaultdict(list)
    for name in target_names:
        target_by_normalized[_normalized_name(name)].append(name)

    suggestions: list[dict[str, Any]] = []
    for source_name in source_names:
        if source_name in target_names:
            suggestions.append(
                {"source": source_name, "target": source_name, "confidence": "exact", "status": "suggested"}
            )
            continue
        candidates = target_by_normalized.get(_normalized_name(source_name), [])
        if len(candidates) == 1:
            suggestions.append(
                {
                    "source": source_name,
                    "target": candidates[0],
                    "confidence": "normalized-name",
                    "status": "suggested",
                }
            )
        elif len(candidates) > 1:
            suggestions.append(
                {
                    "source": source_name,
                    "target": None,
                    "confidence": "ambiguous",
                    "status": "review",
                    "candidates": candidates,
                }
            )
        else:
            suggestions.append(
                {"source": source_name, "target": None, "confidence": "none", "status": "review", "candidates": []}
            )
    return suggestions


def _candidate_fields(profile: dict[str, Any]) -> list[str]:
    return [item["field"] for item in profile["candidate_keys"]]


def suggest_key_pair(source_profile: dict[str, Any], target_profile: dict[str, Any]) -> tuple[str, str] | None:
    source_candidates = [item for item in source_profile["candidate_keys"] if item.get("key_name_score", 0) >= 0.7]
    target_candidates = [item for item in target_profile["candidate_keys"] if item.get("key_name_score", 0) >= 0.7]
    matches: list[tuple[str, str]] = []
    for source in source_candidates:
        for target in target_candidates:
            if _normalized_name(source["field"]) == _normalized_name(target["field"]):
                matches.append((source["field"], target["field"]))
    return matches[0] if len(matches) == 1 else None


def _choose_interactive(label: str, candidates: list[str]) -> str:
    if not candidates:
        raise SpecError(f"No unique non-null candidate keys found for {label} dataset.")
    print(f"Select {label} key:")
    for index, candidate in enumerate(candidates, start=1):
        print(f"  {index}. {candidate}")
    while True:
        raw = input(f"{label} key [1-{len(candidates)}]: ").strip()
        try:
            selected = int(raw)
        except ValueError:
            continue
        if 1 <= selected <= len(candidates):
            return candidates[selected - 1]


def generate_spec(
    source_path: str | Path,
    target_path: str | Path,
    *,
    source_key: str | None = None,
    target_key: str | None = None,
    interactive: bool = False,
    source_sheet: str | None = None,
    target_sheet: str | None = None,
    delimiter: str = ",",
) -> tuple[dict[str, Any], list[str], dict[str, Any], dict[str, Any]]:
    source_profile = inspect_dataset(source_path, sheet=source_sheet, delimiter=delimiter)
    target_profile = inspect_dataset(target_path, sheet=target_sheet, delimiter=delimiter)
    source_fields = {item["name"] for item in source_profile["columns"]}
    target_fields = {item["name"] for item in target_profile["columns"]}

    if source_key and source_key not in source_fields:
        raise SpecError(f"Source key {source_key!r} is not a source column.")
    if target_key and target_key not in target_fields:
        raise SpecError(f"Target key {target_key!r} is not a target column.")

    if not source_key or not target_key:
        suggested_pair = suggest_key_pair(source_profile, target_profile)
        if suggested_pair:
            source_key = source_key or suggested_pair[0]
            target_key = target_key or suggested_pair[1]
        elif interactive:
            source_key = source_key or _choose_interactive("source", _candidate_fields(source_profile))
            target_key = target_key or _choose_interactive("target", _candidate_fields(target_profile))
        else:
            source_candidates = ", ".join(_candidate_fields(source_profile)) or "none"
            target_candidates = ", ".join(_candidate_fields(target_profile)) or "none"
            raise SpecError(
                "Could not safely infer equivalent business keys. "
                f"Source candidates: {source_candidates}. Target candidates: {target_candidates}. "
                "Rerun with --source-key FIELD --target-key FIELD or --interactive."
            )

    mappings = suggest_field_mappings(source_profile, target_profile)
    checks: list[dict[str, Any]] = [{"id": "coverage", "type": "record_coverage"}]
    todos: list[str] = []
    check_ids: set[str] = {"coverage"}
    for item in mappings:
        if item["status"] != "suggested" or not item.get("target"):
            candidates = item.get("candidates") or []
            suffix = f" candidates={','.join(candidates)}" if candidates else ""
            todos.append(f"review mapping for source field {item['source']!r}{suffix}")
            continue
        if item["source"] == source_key and item["target"] == target_key:
            continue
        base_id = "field-" + re.sub(r"[^a-z0-9]+", "-", item["source"].lower()).strip("-")
        check_id = base_id or "field"
        counter = 2
        while check_id in check_ids:
            check_id = f"{base_id}-{counter}"
            counter += 1
        check_ids.add(check_id)
        checks.append(
            {
                "id": check_id,
                "type": "field_match",
                "source": item["source"],
                "target": item["target"],
            }
        )

    source = {"file": Path(source_path).name, "key": source_key}
    target = {"file": Path(target_path).name, "key": target_key}
    if source_sheet:
        source["sheet"] = source_sheet
    if target_sheet:
        target["sheet"] = target_sheet
    if Path(source_path).suffix.lower() == ".csv" and delimiter != ",":
        source["delimiter"] = delimiter
    if Path(target_path).suffix.lower() == ".csv" and delimiter != ",":
        target["delimiter"] = delimiter

    spec: dict[str, Any] = {
        "version": 1,
        "reconciliation": {"name": f"{Path(source_path).stem} to {Path(target_path).stem}"},
        "source": source,
        "target": target,
        "checks": checks,
        "evidence": {"detail_limit": 100},
    }
    validate_spec(spec)
    return spec, todos, source_profile, target_profile


def render_generated_spec(spec: dict[str, Any], todos: list[str]) -> str:
    text = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True)
    if todos:
        text += "\n# TODO: review unresolved mappings before treating this control as complete.\n"
        for todo in todos:
            text += f"# - {todo}\n"
    return text
