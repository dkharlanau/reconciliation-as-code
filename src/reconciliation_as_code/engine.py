from __future__ import annotations

import hashlib
import json
import platform
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

from .errors import DataError
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


def _field_equal(source_value: Any, target_value: Any, check: dict[str, Any]) -> tuple[bool, Any, Any]:
    operations = check.get("normalize", ["trim"])
    left = normalize_value(source_value, operations)
    mapping = check.get("map") or {}
    if left in mapping:
        left = mapping[left]
    elif str(left) in mapping:
        left = mapping[str(left)]
    right = normalize_value(target_value, operations)

    tolerance = check.get("numeric_tolerance")
    if tolerance is not None:
        try:
            left_decimal = _decimal(left, check["source"])
            right_decimal = _decimal(right, check["target"])
        except DataError:
            return False, left, right
        return abs(left_decimal - right_decimal) <= Decimal(str(tolerance)), left, right

    return left == right, left, right


def run_reconciliation(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    started_at = datetime.now(timezone.utc)
    timer_started = time.perf_counter()
    validate_spec(spec)
    base = Path(base_dir).resolve()
    source_path, source_rows = load_table(spec["source"], base)
    target_path, target_rows = load_table(spec["target"], base)

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
            allow_unexpected = bool(check.get("allow_unexpected", False))
            failures = len(missing_keys) + (0 if allow_unexpected else len(unexpected_keys))
            details = [
                {"key": _key_label(key), "difference": "missing_in_target"} for key in missing_keys
            ]
            details.extend(
                {"key": _key_label(key), "difference": "unexpected_in_target"}
                for key in unexpected_keys
            )
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    failures == 0,
                    {
                        "matched": len(matched_keys),
                        "missing_in_target": len(missing_keys),
                        "unexpected_in_target": len(unexpected_keys),
                        "allow_unexpected": allow_unexpected,
                    },
                    details,
                    detail_limit,
                )
            )

        elif check_type == "field_match":
            mismatches: list[dict[str, Any]] = []
            for key in matched_keys:
                source_value = source_index[key].get(check["source"])
                target_value = target_index[key].get(check["target"])
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
                        "compared": len(matched_keys),
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
            source_total = sum(
                (_decimal(row.get(check["source"]), check["source"]) for row in source_rows), Decimal("0")
            )
            target_total = sum(
                (_decimal(row.get(check["target"]), check["target"]) for row in target_rows), Decimal("0")
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
                    },
                    detail_limit=detail_limit,
                )
            )

        elif check_type == "row_count":
            difference = abs(len(source_rows) - len(target_rows))
            tolerance = int(check.get("tolerance", 0))
            checks.append(
                _result(
                    check_id,
                    check_type,
                    severity,
                    difference <= tolerance,
                    {
                        "source_rows": len(source_rows),
                        "target_rows": len(target_rows),
                        "absolute_difference": difference,
                        "tolerance": tolerance,
                    },
                    detail_limit=detail_limit,
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
