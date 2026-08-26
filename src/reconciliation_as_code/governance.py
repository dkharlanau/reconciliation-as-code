from __future__ import annotations

import copy
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .errors import DataError
from .hierarchy import run_reconciliation_with_hierarchy


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_expiry(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DataError(f"Invalid accepted-exception expiry date: {value!r}. Use YYYY-MM-DD.") from exc


def _load_policy(spec: dict[str, Any], base_dir: Path) -> tuple[dict[str, Any] | None, Path | None]:
    config = spec.get("exceptions")
    if config is None:
        return None, None
    if not isinstance(config, dict):
        raise DataError("exceptions must be an object with a file property.")
    filename = config.get("file")
    if not isinstance(filename, str) or not filename:
        raise DataError("exceptions.file must be a non-empty string.")
    expiry_policy = config.get("expiry_policy", "error")
    if expiry_policy not in {"error", "warning"}:
        raise DataError("exceptions.expiry_policy must be error or warning.")

    path = Path(filename).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Accepted-exception file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise DataError(f"Invalid YAML in accepted-exception file {path}: {exc}") from exc

    if not isinstance(raw, dict) or raw.get("version", 1) != 1:
        raise DataError("Accepted-exception artifact must be an object with version: 1.")
    entries = raw.get("exceptions", [])
    if not isinstance(entries, list):
        raise DataError("Accepted-exception artifact exceptions must be a list.")

    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str | None]] = set()
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            raise DataError(f"Accepted exception #{index} must be an object.")
        check_id = item.get("check")
        if not isinstance(check_id, str) or not check_id:
            raise DataError(f"Accepted exception #{index} requires check.")
        has_key = "key" in item
        has_group = "group" in item
        if has_key == has_group:
            raise DataError(f"Accepted exception #{index} must define exactly one of key or group.")
        for required in ("reason_code", "reason"):
            if not isinstance(item.get(required), str) or not item.get(required):
                raise DataError(f"Accepted exception #{index} requires {required}.")
        field = item.get("field")
        if field is not None and (not isinstance(field, str) or not field):
            raise DataError(f"Accepted exception #{index}.field must be a non-empty string.")
        reference_value = item["key"] if has_key else item["group"]
        identity = (check_id, _canonical(reference_value), field)
        if identity in identities:
            raise DataError(f"Duplicate accepted exception for check {check_id!r}, reference {reference_value!r}, field {field!r}.")
        identities.add(identity)
        normalized_item = copy.deepcopy(item)
        normalized_item["_index"] = index
        normalized_item["_reference_kind"] = "key" if has_key else "group"
        normalized_item["_expires"] = _parse_expiry(item.get("expires"))
        normalized.append(normalized_item)

    return {"version": 1, "expiry_policy": expiry_policy, "entries": normalized}, path


def _entry_public(entry: dict[str, Any], status: str) -> dict[str, Any]:
    expires = entry.get("expires")
    if isinstance(expires, datetime):
        expires = expires.date().isoformat()
    elif isinstance(expires, date):
        expires = expires.isoformat()
    return {
        "index": entry["_index"],
        "check": entry["check"],
        entry["_reference_kind"]: entry[entry["_reference_kind"]],
        "field": entry.get("field"),
        "reason_code": entry["reason_code"],
        "reason": entry["reason"],
        "owner": entry.get("owner"),
        "reference": entry.get("reference"),
        "expires": expires,
        "status": status,
    }


def _entry_matches(entry: dict[str, Any], check: dict[str, Any], detail: dict[str, Any], check_spec: dict[str, Any]) -> bool:
    if entry["check"] != check["id"]:
        return False
    reference_kind = entry["_reference_kind"]
    if reference_kind not in detail:
        return False
    if _canonical(entry[reference_kind]) != _canonical(detail[reference_kind]):
        return False
    field = entry.get("field")
    if field is None:
        return True
    candidates = {
        check_spec.get("source"), check_spec.get("target"),
        check.get("metrics", {}).get("source_field"), check.get("metrics", {}).get("target_field"),
    }
    return field in candidates


def _gross_failures(check: dict[str, Any]) -> int | None:
    metrics = check.get("metrics", {})
    if check["type"] == "field_match":
        return int(metrics.get("mismatches", 0))
    if check["type"] == "aggregate_match":
        return int(metrics.get("groups_failed", 0))
    if check["type"] == "record_coverage":
        missing = int(metrics.get("missing_in_target", 0))
        unexpected = 0 if metrics.get("allow_unexpected") else int(metrics.get("unexpected_in_target", 0))
        return missing + unexpected
    return None


def _detail_counts_as_failure(check: dict[str, Any], detail: dict[str, Any]) -> bool:
    if check["type"] == "record_coverage":
        if detail.get("difference") == "missing_in_target":
            return True
        if detail.get("difference") == "unexpected_in_target":
            return not bool(check.get("metrics", {}).get("allow_unexpected"))
        return False
    return check["type"] in {"field_match", "aggregate_match"}


def apply_exception_governance(result: dict[str, Any], spec: dict[str, Any], policy: dict[str, Any], policy_path: Path) -> dict[str, Any]:
    now = datetime.now(timezone.utc).date()
    entries = policy["entries"]
    used: set[int] = set()
    expired: set[int] = set()
    spec_checks = {check.get("id", f"check-{index}"): check for index, check in enumerate(spec.get("checks", []), start=1)}
    for child_name, child in (spec.get("children") or {}).items():
        for index, check in enumerate(child.get("checks", []), start=1):
            spec_checks[f"child:{child_name}:{check.get('id', f'check-{index}')}"] = check

    for entry in entries:
        expiry = entry.get("_expires")
        if expiry is not None and expiry < now:
            expired.add(entry["_index"])

    for check in result.get("checks", []):
        gross = _gross_failures(check)
        if gross is None or gross == 0:
            continue
        accepted_count = 0
        check_spec = spec_checks.get(check["id"], {})
        for detail in check.get("details", []):
            if not _detail_counts_as_failure(check, detail):
                continue
            matches = [entry for entry in entries if entry["_index"] not in expired and _entry_matches(entry, check, detail, check_spec)]
            if len(matches) > 1:
                raise DataError(f"Ambiguous accepted exceptions for check {check['id']!r} and detail reference {detail.get('key', detail.get('group'))!r}.")
            if not matches:
                detail.setdefault("disposition", "unaccepted")
                continue
            entry = matches[0]
            accepted_count += 1
            used.add(entry["_index"])
            detail["disposition"] = "accepted-exception"
            detail["exception"] = _entry_public(entry, "used")

        unaccepted = max(gross - accepted_count, 0)
        check["metrics"]["gross_failures"] = gross
        check["metrics"]["accepted_exceptions"] = accepted_count
        check["metrics"]["unaccepted_failures"] = unaccepted
        if check["type"] == "field_match":
            threshold = int(check["metrics"].get("max_mismatches", 0))
            check["status"] = "passed" if unaccepted <= threshold else "failed"
        else:
            check["status"] = "passed" if unaccepted == 0 else "failed"

    unused = [entry for entry in entries if entry["_index"] not in used and entry["_index"] not in expired]
    expired_entries = [entry for entry in entries if entry["_index"] in expired]
    result["checks"].append({
        "id": "accepted-exceptions-policy", "type": "exception_governance", "severity": policy["expiry_policy"],
        "status": "failed" if expired_entries else "passed",
        "metrics": {"entries_total": len(entries), "entries_used": len(used), "entries_unused": len(unused), "entries_expired": len(expired_entries), "expiry_policy": policy["expiry_policy"]},
        "details": [*[_entry_public(entry, "expired") for entry in expired_entries], *[_entry_public(entry, "unused") for entry in unused]],
        "details_truncated": False,
    })

    failed_errors = [item for item in result["checks"] if item["severity"] == "error" and item["status"] == "failed"]
    failed_warnings = [item for item in result["checks"] if item["severity"] == "warning" and item["status"] == "failed"]
    result["status"] = "failed" if failed_errors else "passed"
    result["summary"].update({
        "checks_total": len(result["checks"]), "checks_failed": len(failed_errors), "warnings_failed": len(failed_warnings),
        "accepted_exceptions": len(used), "unused_exceptions": len(unused), "expired_exceptions": len(expired_entries),
    })
    result["inputs"]["exceptions"] = {"path": str(policy_path.name), "sha256": _sha256(policy_path)}
    result["exception_governance"] = {
        "version": policy["version"], "expiry_policy": policy["expiry_policy"], "entries_total": len(entries),
        "used": [_entry_public(entry, "used") for entry in entries if entry["_index"] in used],
        "unused": [_entry_public(entry, "unused") for entry in unused],
        "expired": [_entry_public(entry, "expired") for entry in expired_entries],
    }
    if "hierarchy" in result:
        # Recompute object roll-up after accepted child discrepancies changed check status.
        failed_check_ids = {item["id"] for item in failed_errors}
        remaining = []
        for obj in result["hierarchy"].get("failed_objects", []):
            obj["failed_checks"] = [check_id for check_id in obj.get("failed_checks", []) if check_id in failed_check_ids]
            if obj["failed_checks"]:
                remaining.append(obj)
        result["hierarchy"]["failed_objects"] = remaining
        result["summary"]["objects_failed"] = len(remaining)
        evaluated = int(result["summary"].get("objects_evaluated", 0))
        result["summary"]["objects_passed"] = max(evaluated - len(remaining), 0)
    return result


def _truncate_details(result: dict[str, Any], limit: int) -> None:
    for check in result.get("checks", []):
        details = check.get("details", [])
        check["details_truncated"] = len(details) > limit
        check["details"] = details[:limit]


def run_reconciliation_with_governance(spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None) -> dict[str, Any]:
    base = Path(base_dir).resolve()
    policy, policy_path = _load_policy(spec, base)
    if policy is None or policy_path is None:
        return run_reconciliation_with_hierarchy(spec, base_dir=base, spec_path=spec_path)

    original_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))
    execution_spec = copy.deepcopy(spec)
    execution_spec.setdefault("evidence", {})["detail_limit"] = 1_000_000_000
    result = run_reconciliation_with_hierarchy(execution_spec, base_dir=base, spec_path=spec_path)
    result["configuration_sha256"] = hashlib.sha256(_canonical(spec).encode("utf-8")).hexdigest()
    apply_exception_governance(result, spec, policy, policy_path)
    _truncate_details(result, original_limit)
    return result
