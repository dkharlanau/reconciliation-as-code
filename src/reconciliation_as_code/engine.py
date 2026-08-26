from __future__ import annotations

import hashlib
import json
import platform
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

from .errors import DataError
from .filtering import filter_rows, predicate_matches
from .io import load_table
from .normalize import comparable_key, normalize_value
from .spec import validate_spec

EVIDENCE_SCHEMA_VERSION = "1.0"


def _listify(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_object(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _engine_version() -> str:
    try:
        return package_version("reconciliation-as-code")
    except PackageNotFoundError:
        return "0+unknown"


def _index_rows(
    rows: list[dict[str, Any]], fields: list[str], operations: list[str]
) -> tuple[dict[tuple[str, ...], dict[str, Any]], list[tuple[str, ...]]]:
    index: dict[tuple[str, ...], dict[str, Any]] = {}
    duplicates: list[tuple[str, ...]] = []
    for row in rows:
        key = comparable_key(row, fields, operations)
        if key in index:
            duplicates.append(key)
        else:
            index[key] = row
    return index, duplicates


def _key_label(key: tuple[str, ...]) -> str | list[str]:
    return key[0] if len(key) == 1 else list(key)


def _limited(details: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], bool]:
    return details[:limit], len(details) > limit


def _result(
    check_id: str,
    check_type: str,
    severity: str,
    passed: bool,
    metrics: dict[str, Any],
    details: list[dict[str, Any]] | None = None,
    detail_limit: int = 100,
) -> dict[str, Any]:
    details = details or []
    limited, truncated = _limited(details, detail_limit)
    return {
        "id": check_id,
        "type": check_type,
        "severity": severity,
        "status": "passed" if passed else "failed",
        "metrics": metrics,
        "details": limited,
        "details_truncated": truncated,
    }


def _decimal(value: Any, field: str, key: tuple[str, ...] | None = None) -> Decimal:
    if value is None or str(value).strip() == "":
        return Decimal("0")
    text = str(value).strip().replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        location = f" for key {_key_label(key)}" if key else ""
        raise DataError(f"Value {value!r} in field {field!r}{location} is not numeric.") from exc


def _is_null(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def _parse_datetime(value: Any) -> datetime | None:
    if _is_null(value):
        return None
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _field_equal(source_value: Any, target_value: Any, check: dict[str, Any]) -> tuple[bool, Any, Any]:
    operations = check.get("normalize", ["trim"])
    left = normalize_value(source_value, operations)
    right = normalize_value(target_value, operations)

    null_semantics = check.get("null_semantics", "equal")
    if null_semantics == "empty_is_null":
        left = None if _is_null(left) else left
        right = None if _is_null(right) else right
    elif null_semantics == "never_equal" and (_is_null(left) or _is_null(right)):
        return False, left, right

    mapping = check.get("map") or {}
    if left in mapping:
        left = mapping[left]
    elif str(left) in mapping:
        left = mapping[str(left)]

    date_tolerance_days = check.get("date_tolerance_days")
    if date_tolerance_days is not None:
        left_date = _parse_datetime(left)
        right_date = _parse_datetime(right)
        if left_date is None or right_date is None:
            return left_date is right_date and null_semantics != "never_equal", left, right
        difference_days = abs((left_date - right_date).total_seconds()) / 86400
        return difference_days <= float(date_tolerance_days), left, right

    absolute_tolerance = check.get("numeric_tolerance")
    percentage_tolerance = check.get("percentage_tolerance")
    if absolute_tolerance is not None or percentage_tolerance is not None:
        try:
            left_decimal = _decimal(left, check["source"])
            right_decimal = _decimal(right, check["target"])
        except DataError:
            return False, left, right
        difference = abs(left_decimal - right_decimal)
        absolute_pass = (
            absolute_tolerance is not None and difference <= Decimal(str(absolute_tolerance))
        )
        percentage_pass = False
        if percentage_tolerance is not None:
            if left_decimal == 0:
                percentage_pass = difference == 0
            else:
                percentage = difference / abs(left_decimal) * Decimal("100")
                percentage_pass = percentage <= Decimal(str(percentage_tolerance))
        return bool(absolute_pass or percentage_pass), left, right

    return left == right, left, right


def _scope_predicates(spec: dict[str, Any], check: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_predicate: dict[str, Any] | None = None
    target_predicate: dict[str, Any] | None = None
    scope_name = check.get("scope")
    if scope_name:
        scope = spec.get("scopes", {}).get(scope_name, {})
        source_predicate = scope.get("source")
        target_predicate = scope.get("target")
    return source_predicate, target_predicate


def _eligible_pair(
    source_row: dict[str, Any],
    target_row: dict[str, Any],
    spec: dict[str, Any],
    check: dict[str, Any],
) -> bool:
    source_scope, target_scope = _scope_predicates(spec, check)
    when = check.get("when") or {}
    predicates = (
        (source_row, source_scope),
        (target_row, target_scope),
        (source_row, when.get("source")),
        (target_row, when.get("target")),
    )
    return all(predicate is None or predicate_matches(row, predicate) for row, predicate in predicates)


def _rows_for_check(
    source_rows: list[dict[str, Any]],
    target_rows: list[dict[str, Any]],
    spec: dict[str, Any],
    check: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    source_scope, target_scope = _scope_predicates(spec, check)
    source_selected = filter_rows(source_rows, source_scope)
    target_selected = filter_rows(target_rows, target_scope)
    when = check.get("when") or {}
    source_selected = filter_rows(source_selected, when.get("source"))
    target_selected = filter_rows(target_selected, when.get("target"))
    return source_selected, target_selected


def _group_key(row: dict[str, Any], fields: list[str]) -> tuple[str, ...]:
    return tuple(str(normalize_value(row.get(field), ["trim"]) or "") for field in fields)


def _aggregate_rows(rows: list[dict[str, Any]], fields: list[str], operation: str, value_field: str | None) -> dict[tuple[str, ...], Decimal]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[_group_key(row, fields)].append(row)

    result: dict[tuple[str, ...], Decimal] = {}
    for key, group_rows in grouped.items():
        if operation == "count":
            result[key] = Decimal(len(group_rows))
        elif operation == "distinct_count":
            assert value_field is not None
            values = {
                str(normalize_value(row.get(value_field), ["trim"]) or "")
                for row in group_rows
            }
            result[key] = Decimal(len(values))
        elif operation == "sum":
            assert value_field is not None
            result[key] = sum(
                (_decimal(row.get(value_field), value_field) for row in group_rows),
                Decimal("0"),
            )
    return result


def _difference_metrics(source_value: Decimal, target_value: Decimal) -> tuple[Decimal, Decimal | None]:
    difference = abs(source_value - target_value)
    if source_value == 0:
        percentage = Decimal("0") if difference == 0 else None
    else:
        percentage = difference / abs(source_value) * Decimal("100")
    return difference, percentage


def _within_tolerance(
    source_value: Decimal,
    target_value: Decimal,
    absolute_tolerance: Decimal,
    percentage_tolerance: Decimal | None,
) -> tuple[bool, Decimal, Decimal | None]:
    difference, percentage = _difference_metrics(source_value, target_value)
    absolute_pass = difference <= absolute_tolerance
    percentage_pass = (
        percentage_tolerance is not None
        and percentage is not None
        and percentage <= percentage_tolerance
    )
    return absolute_pass or percentage_pass, difference, percentage


def run_reconciliation(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    timer_started = time.perf_counter()
    validate_spec(spec)
    base = Path(base_dir).resolve()
    source_path, raw_source_rows = load_table(spec["source"], base)
    target_path, raw_target_rows = load_table(spec["target"], base)
    source_rows = filter_rows(raw_source_rows, spec["source"].get("filter"))
    target_rows = filter_rows(raw_target_rows, spec["target"].get("filter"))

    source_keys = _listify(spec["source"]["key"])
    target_keys = _listify(spec["target"]["key"])
    source_key_normalize = spec["source"].get("key_normalize", ["trim"])
    target_key_normalize = spec["target"].get("key_normalize", ["trim"])
    source_index, source_duplicates = _index_rows(source_rows, source_keys, source_key_normalize)
    target_index, target_duplicates = _index_rows(target_rows, target_keys, target_key_normalize)

    source_key_set = set(source_index)
    target_key_set = set(target_index)
    matched_keys = sorted(source_key_set & target_key_set)
    missing_keys = sorted(source_key_set - target_key_set)
    unexpected_keys = sorted(target_key_set - source_key_set)
    detail_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))

    checks: list[dict[str, Any]] = []
    checks.append(
        _result(
            "source-key-integrity",
            "key_integrity",
            "error",
            not source_duplicates,
            {"duplicate_keys": len(source_duplicates)},
            [{"key": _key_label(key)} for key in source_duplicates],
            detail_limit,
        )
    )
    checks.append(
        _result(
            "target-key-integrity",
            "key_integrity",
            "error",
            not target_duplicates,
            {"duplicate_keys": len(target_duplicates)},
            [{"key": _key_label(key)} for key in target_duplicates],
            detail_limit,
        )
    )

    for position, check in enumerate(spec["checks"], start=1):
        check_id = check.get("id", f"check-{position}")
        check_type = check["type"]
        severity = check.get("severity", "error")

        if check_type == "record_coverage":
            scoped_source_rows, scoped_target_rows = _rows_for_check(source_rows, target_rows, spec, check)
            scoped_source_index, _ = _index_rows(scoped_source_rows, source_keys, source_key_normalize)
            scoped_target_index, _ = _index_rows(scoped_target_rows, target_keys, target_key_normalize)
            scoped_source_keys = set(scoped_source_index)
            scoped_target_keys = set(scoped_target_index)
            scoped_matched = sorted(scoped_source_keys & scoped_target_keys)
            scoped_missing = sorted(scoped_source_keys - scoped_target_keys)
            scoped_unexpected = sorted(scoped_target_keys - scoped_source_keys)
            allow_unexpected = bool(check.get("allow_unexpected", False))
            failures = len(scoped_missing) + (0 if allow_unexpected else len(scoped_unexpected))
            details = [
                {"key": _key_label(key), "difference": "missing_in_target"} for key in scoped_missing
            ]
            details.extend(
                {"key": _key_label(key), "difference": "unexpected_in_target"}
                for key in scoped_unexpected
            )
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    failures == 0,
                    {
                        "matched": len(scoped_matched),
                        "missing_in_target": len(scoped_missing),
                        "unexpected_in_target": len(scoped_unexpected),
                        "allow_unexpected": allow_unexpected,
                        "source_scope_records": len(scoped_source_rows),
                        "target_scope_records": len(scoped_target_rows),
                    },
                    details,
                    detail_limit,
                )
            )

        elif check_type == "field_match":
            mismatches: list[dict[str, Any]] = []
            compared = 0
            skipped = 0
            for key in matched_keys:
                source_row = source_index[key]
                target_row = target_index[key]
                if not _eligible_pair(source_row, target_row, spec, check):
                    skipped += 1
                    continue
                compared += 1
                source_value = source_row.get(check["source"])
                target_value = target_row.get(check["target"])
                equal, normalized_source, normalized_target = _field_equal(source_value, target_value, check)
                if not equal:
                    mismatches.append(
                        {
                            "key": _key_label(key),
                            "source": source_value,
                            "target": target_value,
                            "normalized_source": normalized_source,
                            "normalized_target": normalized_target,
                        }
                    )
            max_mismatches = int(check.get("max_mismatches", 0))
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    len(mismatches) <= max_mismatches,
                    {
                        "compared": compared,
                        "skipped_by_scope_or_when": skipped,
                        "mismatches": len(mismatches),
                        "max_mismatches": max_mismatches,
                        "source_field": check["source"],
                        "target_field": check["target"],
                    },
                    mismatches,
                    detail_limit,
                )
            )

        elif check_type == "control_total":
            scoped_source_rows, scoped_target_rows = _rows_for_check(source_rows, target_rows, spec, check)
            source_total = sum(
                (_decimal(row.get(check["source"]), check["source"]) for row in scoped_source_rows),
                Decimal("0"),
            )
            target_total = sum(
                (_decimal(row.get(check["target"]), check["target"]) for row in scoped_target_rows),
                Decimal("0"),
            )
            difference = abs(source_total - target_total)
            tolerance = Decimal(str(check.get("tolerance", 0)))
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    difference <= tolerance,
                    {
                        "source_total": str(source_total),
                        "target_total": str(target_total),
                        "absolute_difference": str(difference),
                        "tolerance": str(tolerance),
                        "source_field": check["source"],
                        "target_field": check["target"],
                        "source_scope_records": len(scoped_source_rows),
                        "target_scope_records": len(scoped_target_rows),
                    },
                    detail_limit=detail_limit,
                )
            )

        elif check_type == "row_count":
            scoped_source_rows, scoped_target_rows = _rows_for_check(source_rows, target_rows, spec, check)
            difference = abs(len(scoped_source_rows) - len(scoped_target_rows))
            tolerance = int(check.get("tolerance", 0))
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    difference <= tolerance,
                    {
                        "source_rows": len(scoped_source_rows),
                        "target_rows": len(scoped_target_rows),
                        "absolute_difference": difference,
                        "tolerance": tolerance,
                    },
                    detail_limit=detail_limit,
                )
            )

        elif check_type == "aggregate_match":
            scoped_source_rows, scoped_target_rows = _rows_for_check(source_rows, target_rows, spec, check)
            source_groups = _listify(check["group_by"]["source"])
            target_groups = _listify(check["group_by"]["target"])
            operation = check.get("operation", "count")
            source_values = _aggregate_rows(scoped_source_rows, source_groups, operation, check.get("source"))
            target_values = _aggregate_rows(scoped_target_rows, target_groups, operation, check.get("target"))
            all_groups = sorted(set(source_values) | set(target_values))
            tolerance = Decimal(str(check.get("tolerance", 0)))
            percentage_tolerance = (
                Decimal(str(check["percentage_tolerance"]))
                if "percentage_tolerance" in check
                else None
            )
            failures: list[dict[str, Any]] = []
            for group in all_groups:
                source_value = source_values.get(group, Decimal("0"))
                target_value = target_values.get(group, Decimal("0"))
                passed, difference, percentage = _within_tolerance(
                    source_value, target_value, tolerance, percentage_tolerance
                )
                if not passed:
                    failures.append(
                        {
                            "group": _key_label(group),
                            "source_value": str(source_value),
                            "target_value": str(target_value),
                            "absolute_difference": str(difference),
                            "percentage_difference": str(percentage) if percentage is not None else None,
                        }
                    )
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    not failures,
                    {
                        "operation": operation,
                        "groups_compared": len(all_groups),
                        "groups_failed": len(failures),
                        "tolerance": str(tolerance),
                        "percentage_tolerance": str(percentage_tolerance) if percentage_tolerance is not None else None,
                        "source_group_by": source_groups,
                        "target_group_by": target_groups,
                        "source_field": check.get("source"),
                        "target_field": check.get("target"),
                        "source_scope_records": len(scoped_source_rows),
                        "target_scope_records": len(scoped_target_rows),
                    },
                    failures,
                    detail_limit,
                )
            )

    failed_errors = [item for item in checks if item["severity"] == "error" and item["status"] == "failed"]
    failed_warnings = [item for item in checks if item["severity"] == "warning" and item["status"] == "failed"]

    inputs: dict[str, Any] = {
        "source": {"path": spec["source"]["file"], "sha256": _sha256(source_path)},
        "target": {"path": spec["target"]["file"], "sha256": _sha256(target_path)},
    }
    if spec_path:
        resolved_spec_path = Path(spec_path).resolve()
        if resolved_spec_path.exists():
            inputs["specification"] = {
                "path": resolved_spec_path.name,
                "sha256": _sha256(resolved_spec_path),
            }

    finished_at = datetime.now(timezone.utc)
    duration_ms = round((time.perf_counter() - timer_started) * 1000, 3)
    engine_version = _engine_version()

    return {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "spec_version": int(spec.get("version", 1)),
        "engine_version": engine_version,
        "configuration_sha256": _sha256_object(spec),
        "run": {
            "id": str(uuid.uuid4()),
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_ms": duration_ms,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
        },
        "reconciliation": spec["reconciliation"]["name"],
        "description": spec["reconciliation"].get("description"),
        "status": "failed" if failed_errors else "passed",
        "generated_at": finished_at.isoformat(),
        "inputs": inputs,
        "selection": {
            "source": {
                "raw_records": len(raw_source_rows),
                "selected_records": len(source_rows),
                "filter": spec["source"].get("filter"),
            },
            "target": {
                "raw_records": len(raw_target_rows),
                "selected_records": len(target_rows),
                "filter": spec["target"].get("filter"),
            },
        },
        "summary": {
            "source_records": len(source_rows),
            "target_records": len(target_rows),
            "matched_records": len(matched_keys),
            "missing_in_target": len(missing_keys),
            "unexpected_in_target": len(unexpected_keys),
            "checks_total": len(checks),
            "checks_failed": len(failed_errors),
            "warnings_failed": len(failed_warnings),
        },
        "checks": checks,
    }
