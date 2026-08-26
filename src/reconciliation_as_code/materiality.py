from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import DataError

_ALLOWED_POLICY_KEYS = {
    "severity",
    "critical",
    "max_failures",
    "max_failure_percentage",
    "max_absolute_difference",
    "max_percentage_difference",
}


def validate_materiality_spec(spec: dict[str, Any]) -> None:
    config = spec.get("materiality")
    if config is None:
        return
    if not isinstance(config, dict):
        raise DataError("materiality must be an object.")
    unknown = set(config) - {"default", "fields", "checks"}
    if unknown:
        raise DataError(f"materiality contains unsupported keys: {sorted(unknown)}.")
    if "default" in config:
        _validate_policy(config["default"], "materiality.default")
    for section in ("fields", "checks"):
        values = config.get(section, {})
        if not isinstance(values, dict):
            raise DataError(f"materiality.{section} must be an object.")
        for name, policy in values.items():
            if not isinstance(name, str) or not name:
                raise DataError(f"materiality.{section} keys must be non-empty strings.")
            _validate_policy(policy, f"materiality.{section}.{name}")
    for check, label in _all_spec_checks(spec):
        if "materiality" in check:
            _validate_policy(check["materiality"], f"{label}.materiality")


def _validate_policy(policy: Any, label: str) -> None:
    if not isinstance(policy, dict) or not policy:
        raise DataError(f"{label} must be a non-empty object.")
    unknown = set(policy) - _ALLOWED_POLICY_KEYS
    if unknown:
        raise DataError(f"{label} contains unsupported keys: {sorted(unknown)}.")
    if "severity" in policy and policy["severity"] not in {"error", "warning"}:
        raise DataError(f"{label}.severity must be error or warning.")
    if "critical" in policy and not isinstance(policy["critical"], bool):
        raise DataError(f"{label}.critical must be boolean.")
    if "max_failures" in policy and (
        not isinstance(policy["max_failures"], int) or policy["max_failures"] < 0
    ):
        raise DataError(f"{label}.max_failures must be a non-negative integer.")
    for name in (
        "max_failure_percentage",
        "max_absolute_difference",
        "max_percentage_difference",
    ):
        if name not in policy:
            continue
        try:
            value = Decimal(str(policy[name]))
        except (InvalidOperation, ValueError) as exc:
            raise DataError(f"{label}.{name} must be numeric.") from exc
        if value < 0:
            raise DataError(f"{label}.{name} must be non-negative.")


def _all_spec_checks(spec: dict[str, Any]):
    for index, check in enumerate(spec.get("checks", []), start=1):
        yield check, f"checks[{index}]"
    for child_name, child in (spec.get("children") or {}).items():
        for index, check in enumerate(child.get("checks", []), start=1):
            yield check, f"children.{child_name}.checks[{index}]"


def _spec_check_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, check in enumerate(spec.get("checks", []), start=1):
        result[check.get("id", f"check-{index}")] = check
    for child_name, child in (spec.get("children") or {}).items():
        for index, check in enumerate(child.get("checks", []), start=1):
            result[f"child:{child_name}:{check.get('id', f'check-{index}')}"] = check
    return result


def _resolve_policy(
    check_result: dict[str, Any], check_spec: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    explicit_check_policy = config.get("checks", {}).get(check_result["id"])
    # Automatic integrity/governance checks are never relaxed by a default policy.
    if not check_spec and not isinstance(explicit_check_policy, dict):
        return {}

    policy: dict[str, Any] = dict(config.get("default", {}))
    fields = config.get("fields", {})
    source_field = check_result.get("metrics", {}).get("source_field") or check_spec.get("source")
    target_field = check_result.get("metrics", {}).get("target_field") or check_spec.get("target")
    if source_field in fields:
        policy.update(fields[source_field])
    if target_field in fields and target_field != source_field:
        policy.update(fields[target_field])
    if isinstance(explicit_check_policy, dict):
        policy.update(explicit_check_policy)
    if isinstance(check_spec.get("materiality"), dict):
        policy.update(check_spec["materiality"])
    return policy


def _failure_count(check: dict[str, Any]) -> int:
    metrics = check.get("metrics", {})
    if "unaccepted_failures" in metrics:
        return int(metrics["unaccepted_failures"])
    if check["type"] == "field_match":
        return int(metrics.get("mismatches", 0))
    if check["type"] == "aggregate_match":
        return int(metrics.get("groups_failed", 0))
    if check["type"] == "record_coverage":
        missing = int(metrics.get("missing_in_target", 0))
        unexpected = 0 if metrics.get("allow_unexpected") else int(
            metrics.get("unexpected_in_target", 0)
        )
        return missing + unexpected
    return 0 if check.get("status") == "passed" else 1


def _denominator(check: dict[str, Any]) -> int:
    metrics = check.get("metrics", {})
    if check["type"] == "field_match":
        return int(metrics.get("compared", 0))
    if check["type"] == "aggregate_match":
        return int(metrics.get("groups_compared", 0))
    if check["type"] == "record_coverage":
        if "source_scope_records" in metrics:
            return int(metrics["source_scope_records"])
        return max(int(metrics.get("matched", 0)) + int(metrics.get("missing_in_target", 0)), 0)
    return 1


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _numeric_pair(detail: dict[str, Any]) -> tuple[Decimal, Decimal] | None:
    for left_name, right_name in (
        ("normalized_source", "normalized_target"),
        ("source_value", "target_value"),
        ("source", "target"),
    ):
        left = _decimal_or_none(detail.get(left_name))
        right = _decimal_or_none(detail.get(right_name))
        if left is not None and right is not None:
            return left, right
    return None


def _max_absolute_difference(check: dict[str, Any]) -> Decimal | None:
    metrics = check.get("metrics", {})
    direct = _decimal_or_none(metrics.get("absolute_difference"))
    values = [direct] if direct is not None else []
    for detail in check.get("details", []):
        value = _decimal_or_none(detail.get("absolute_difference"))
        if value is None:
            pair = _numeric_pair(detail)
            if pair is not None:
                value = abs(pair[0] - pair[1])
        if value is not None:
            values.append(value)
    return max(values) if values else None


def _max_percentage_difference(check: dict[str, Any]) -> Decimal | None:
    values: list[Decimal] = []
    for detail in check.get("details", []):
        value = _decimal_or_none(detail.get("percentage_difference"))
        if value is None:
            pair = _numeric_pair(detail)
            if pair is not None:
                difference = abs(pair[0] - pair[1])
                value = Decimal("0") if pair[0] == 0 and difference == 0 else (
                    None if pair[0] == 0 else difference / abs(pair[0]) * Decimal("100")
                )
        if value is not None:
            values.append(value)
    return max(values) if values else None


def _evaluate(check: dict[str, Any], policy: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    failures = _failure_count(check)
    denominator = _denominator(check)
    failure_percentage = (
        Decimal(failures) * Decimal("100") / Decimal(denominator)
        if denominator
        else Decimal("0")
    )
    max_absolute = _max_absolute_difference(check)
    max_percentage = _max_percentage_difference(check)

    observed: dict[str, Any] = {
        "failures": failures,
        "denominator": denominator,
        "failure_percentage": str(failure_percentage),
        "max_observed_absolute_difference": str(max_absolute) if max_absolute is not None else None,
        "max_observed_percentage_difference": str(max_percentage) if max_percentage is not None else None,
    }
    if policy.get("critical") and failures > 0:
        observed["critical_failure"] = True
        return False, observed

    applied = False
    passed = True
    if "max_failures" in policy:
        applied = True
        passed = passed and failures <= int(policy["max_failures"])
    if "max_failure_percentage" in policy:
        applied = True
        passed = passed and failure_percentage <= Decimal(str(policy["max_failure_percentage"]))
    if "max_absolute_difference" in policy:
        applied = True
        if failures > 0 and max_absolute is None:
            observed["absolute_difference_not_evaluable"] = True
            passed = False
        elif max_absolute is not None:
            passed = passed and max_absolute <= Decimal(str(policy["max_absolute_difference"]))
    if "max_percentage_difference" in policy:
        applied = True
        if failures > 0 and max_percentage is None:
            observed["percentage_difference_not_evaluable"] = True
            passed = False
        elif max_percentage is not None:
            passed = passed and max_percentage <= Decimal(str(policy["max_percentage_difference"]))
    if not applied:
        passed = check.get("status") == "passed"
    return passed, observed


def _recompute_hierarchy(result: dict[str, Any], failed_error_ids: set[str]) -> None:
    hierarchy = result.get("hierarchy")
    if not hierarchy:
        return
    remaining = []
    for obj in hierarchy.get("failed_objects", []):
        obj["failed_checks"] = [
            check_id for check_id in obj.get("failed_checks", []) if check_id in failed_error_ids
        ]
        if obj["failed_checks"]:
            remaining.append(obj)
    hierarchy["failed_objects"] = remaining
    result["summary"]["objects_failed"] = len(remaining)
    evaluated = int(result["summary"].get("objects_evaluated", 0))
    result["summary"]["objects_passed"] = max(evaluated - len(remaining), 0)


def apply_materiality(result: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    validate_materiality_spec(spec)
    config = spec.get("materiality")
    if not config:
        return result
    spec_checks = _spec_check_map(spec)
    applied_checks = 0
    critical_failures = 0

    for check in result.get("checks", []):
        check_spec = spec_checks.get(check["id"], {})
        policy = _resolve_policy(check, check_spec, config)
        if not policy:
            continue
        applied_checks += 1
        raw_status = check.get("status")
        raw_severity = check.get("severity")
        if policy.get("severity"):
            check["severity"] = policy["severity"]
        if policy.get("critical"):
            check["severity"] = "error"
        passed, observed = _evaluate(check, policy)
        check["status"] = "passed" if passed else "failed"
        check.setdefault("metrics", {})["materiality"] = {
            "policy": policy,
            "observed": observed,
            "raw_status": raw_status,
            "raw_severity": raw_severity,
            "status": check["status"],
        }
        if policy.get("critical") and not passed:
            critical_failures += 1

    failed_errors = [
        item for item in result["checks"]
        if item["severity"] == "error" and item["status"] == "failed"
    ]
    failed_warnings = [
        item for item in result["checks"]
        if item["severity"] == "warning" and item["status"] == "failed"
    ]
    result["status"] = "failed" if failed_errors else "passed"
    result["summary"]["checks_failed"] = len(failed_errors)
    result["summary"]["warnings_failed"] = len(failed_warnings)
    result["summary"]["materiality_checks"] = applied_checks
    result["summary"]["critical_failures"] = critical_failures
    result["materiality"] = {
        "policy": config,
        "checks_evaluated": applied_checks,
        "critical_failures": critical_failures,
        "error_failures": len(failed_errors),
        "warning_failures": len(failed_warnings),
    }
    _recompute_hierarchy(result, {item["id"] for item in failed_errors})
    return result
