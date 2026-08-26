from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from .filtering import filter_rows
from .io import load_table
from .normalize import normalize_value

FieldComparator = Callable[[Any, Any, dict[str, Any]], tuple[bool, Any, Any]]
ResultFactory = Callable[..., dict[str, Any]]


def _listify(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _normalized_tuple(row: dict[str, Any], fields: list[str], operations: list[str]) -> tuple[str, ...]:
    return tuple(str(normalize_value(row.get(field), operations) or "") for field in fields)


def _label(key: tuple[str, ...]) -> str | list[str]:
    return key[0] if len(key) == 1 else list(key)


def _path_part(key: tuple[str, ...]) -> str:
    return "+".join(key)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _child_identity(row: dict[str, Any], endpoint: dict[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    parent_fields = _listify(endpoint["parent_key"])
    local_fields = _listify(endpoint["key"])
    parent_ops = endpoint.get("parent_key_normalize", ["trim"])
    local_ops = endpoint.get("key_normalize", ["trim"])
    return (
        _normalized_tuple(row, parent_fields, parent_ops),
        _normalized_tuple(row, local_fields, local_ops),
    )


def _index_child_rows(
    rows: list[dict[str, Any]], endpoint: dict[str, Any], duplicate_policy: str
) -> tuple[
    dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]],
    list[tuple[tuple[str, ...], tuple[str, ...]]],
    int,
]:
    index: dict[tuple[tuple[str, ...], tuple[str, ...]], dict[str, Any]] = {}
    conflicts: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    identical_ignored = 0
    for row in rows:
        identity = _child_identity(row, endpoint)
        if identity not in index:
            index[identity] = row
            continue
        if duplicate_policy == "allow_identical" and index[identity] == row:
            identical_ignored += 1
            continue
        conflicts.append(identity)
    return index, conflicts, identical_ignored


def _detail(
    object_name: str,
    child_name: str,
    identity: tuple[tuple[str, ...], tuple[str, ...]],
    **values: Any,
) -> dict[str, Any]:
    parent, local = identity
    return {
        "path": f"{object_name}/{_path_part(parent)}/{child_name}/{_path_part(local)}",
        "parent_key": _label(parent),
        "child_key": _label(local),
        **values,
    }


def _event(check_id: str, severity: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "parent_key": detail["parent_key"],
        "check_id": check_id,
        "severity": severity,
        "path": detail.get("path"),
    }


def run_child_collections(
    spec: dict[str, Any],
    *,
    base_dir: str | Path,
    detail_limit: int,
    compare_field: FieldComparator,
    make_result: ResultFactory,
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, Any],
    list[dict[str, Any]],
]:
    object_spec = spec.get("object") or {}
    children = object_spec.get("children") or []
    if not children:
        return [], {}, {}, []

    base = Path(base_dir).resolve()
    object_name = object_spec.get("name", "object")
    checks: list[dict[str, Any]] = []
    inputs: dict[str, dict[str, Any]] = {}
    child_summary: dict[str, Any] = {}
    failure_events: list[dict[str, Any]] = []

    for child in children:
        child_name = child["name"]
        source_path, raw_source_rows = load_table(child["source"], base)
        target_path, raw_target_rows = load_table(child["target"], base)
        source_rows = filter_rows(raw_source_rows, child["source"].get("filter"))
        target_rows = filter_rows(raw_target_rows, child["target"].get("filter"))
        duplicate_policy = child.get("duplicate_policy", "error")
        source_index, source_duplicates, source_identical = _index_child_rows(
            source_rows, child["source"], duplicate_policy
        )
        target_index, target_duplicates, target_identical = _index_child_rows(
            target_rows, child["target"], duplicate_policy
        )

        inputs[f"child.{child_name}.source"] = {
            "path": child["source"]["file"],
            "sha256": _sha256(source_path),
        }
        inputs[f"child.{child_name}.target"] = {
            "path": child["target"]["file"],
            "sha256": _sha256(target_path),
        }

        source_check_id = f"children.{child_name}.source-key-integrity"
        target_check_id = f"children.{child_name}.target-key-integrity"
        source_duplicate_details = [
            _detail(object_name, child_name, identity, difference="duplicate_child_key")
            for identity in source_duplicates
        ]
        target_duplicate_details = [
            _detail(object_name, child_name, identity, difference="duplicate_child_key")
            for identity in target_duplicates
        ]
        failure_events.extend(
            _event(source_check_id, "error", detail) for detail in source_duplicate_details
        )
        failure_events.extend(
            _event(target_check_id, "error", detail) for detail in target_duplicate_details
        )
        checks.append(
            make_result(
                source_check_id,
                "child_key_integrity",
                "error",
                not source_duplicates,
                {
                    "child": child_name,
                    "duplicate_keys": len(source_duplicates),
                    "identical_duplicates_ignored": source_identical,
                    "duplicate_policy": duplicate_policy,
                },
                source_duplicate_details,
                detail_limit,
            )
        )
        checks.append(
            make_result(
                target_check_id,
                "child_key_integrity",
                "error",
                not target_duplicates,
                {
                    "child": child_name,
                    "duplicate_keys": len(target_duplicates),
                    "identical_duplicates_ignored": target_identical,
                    "duplicate_policy": duplicate_policy,
                },
                target_duplicate_details,
                detail_limit,
            )
        )

        source_keys = set(source_index)
        target_keys = set(target_index)
        matched = sorted(source_keys & target_keys)
        missing = sorted(source_keys - target_keys)
        unexpected = sorted(target_keys - source_keys)
        coverage = child.get("coverage") or {}
        allow_unexpected = bool(coverage.get("allow_unexpected", False))
        coverage_severity = coverage.get("severity", "error")
        coverage_check_id = f"children.{child_name}.coverage"
        missing_details = [
            _detail(object_name, child_name, identity, difference="missing_child_in_target")
            for identity in missing
        ]
        unexpected_details = [
            _detail(object_name, child_name, identity, difference="unexpected_child_in_target")
            for identity in unexpected
        ]
        coverage_details = missing_details + unexpected_details
        failure_events.extend(
            _event(coverage_check_id, coverage_severity, detail) for detail in missing_details
        )
        if not allow_unexpected:
            failure_events.extend(
                _event(coverage_check_id, coverage_severity, detail) for detail in unexpected_details
            )
        coverage_failures = len(missing) + (0 if allow_unexpected else len(unexpected))
        checks.append(
            make_result(
                coverage_check_id,
                "child_record_coverage",
                coverage_severity,
                coverage_failures == 0,
                {
                    "child": child_name,
                    "matched": len(matched),
                    "missing_in_target": len(missing),
                    "unexpected_in_target": len(unexpected),
                    "allow_unexpected": allow_unexpected,
                },
                coverage_details,
                detail_limit,
            )
        )

        for position, check in enumerate(child.get("checks", []), start=1):
            check_id = check.get("id", f"field-{position}")
            full_check_id = f"children.{child_name}.{check_id}"
            mismatches: list[dict[str, Any]] = []
            for identity in matched:
                source_row = source_index[identity]
                target_row = target_index[identity]
                source_value = source_row.get(check["source"])
                target_value = target_row.get(check["target"])
                equal, normalized_source, normalized_target = compare_field(
                    source_value, target_value, check
                )
                if not equal:
                    mismatches.append(
                        _detail(
                            object_name,
                            child_name,
                            identity,
                            difference="changed_child_field",
                            field=check_id,
                            source=source_value,
                            target=target_value,
                            normalized_source=normalized_source,
                            normalized_target=normalized_target,
                        )
                    )
            max_mismatches = int(check.get("max_mismatches", 0))
            severity = check.get("severity", "error")
            failed = len(mismatches) > max_mismatches
            if failed:
                failure_events.extend(
                    _event(full_check_id, severity, detail) for detail in mismatches
                )
            checks.append(
                make_result(
                    full_check_id,
                    "child_field_match",
                    severity,
                    not failed,
                    {
                        "child": child_name,
                        "compared": len(matched),
                        "mismatches": len(mismatches),
                        "max_mismatches": max_mismatches,
                        "source_field": check["source"],
                        "target_field": check["target"],
                    },
                    mismatches,
                    detail_limit,
                )
            )

        child_summary[child_name] = {
            "source_raw_records": len(raw_source_rows),
            "target_raw_records": len(raw_target_rows),
            "source_records": len(source_rows),
            "target_records": len(target_rows),
            "matched_records": len(matched),
            "missing_in_target": len(missing),
            "unexpected_in_target": len(unexpected),
            "source_identical_duplicates_ignored": source_identical,
            "target_identical_duplicates_ignored": target_identical,
        }

    return checks, inputs, child_summary, failure_events
