from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .errors import SpecError

SUPPORTED_CHECKS = {"record_coverage", "field_match", "control_total", "row_count"}
SUPPORTED_SEVERITIES = {"error", "warning"}
SUPPORTED_NORMALIZERS = {
    "trim",
    "uppercase",
    "lowercase",
    "empty_to_null",
    "strip_leading_zeros",
}


def load_spec(path: str | Path) -> dict[str, Any]:
    spec_path = Path(path)
    try:
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"Specification not found: {spec_path}") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"Invalid YAML in {spec_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise SpecError("Specification root must be a mapping/object.")
    validate_spec(raw)
    return raw


def _as_list(value: Any, field: str) -> list[str]:
    if isinstance(value, str) and value:
        return [value]
    if isinstance(value, list) and value and all(isinstance(item, str) and item for item in value):
        return value
    raise SpecError(f"{field} must be a non-empty string or list of strings.")


def _validate_endpoint(name: str, endpoint: Any) -> None:
    if not isinstance(endpoint, dict):
        raise SpecError(f"{name} must be an object.")
    if not endpoint.get("file") or not isinstance(endpoint.get("file"), str):
        raise SpecError(f"{name}.file must be a non-empty string.")
    _as_list(endpoint.get("key"), f"{name}.key")

    normalizers = endpoint.get("key_normalize", ["trim"])
    if not isinstance(normalizers, list):
        raise SpecError(f"{name}.key_normalize must be a list.")
    unknown = set(normalizers) - SUPPORTED_NORMALIZERS
    if unknown:
        raise SpecError(f"Unsupported {name}.key_normalize values: {sorted(unknown)}")


def validate_spec(spec: dict[str, Any]) -> None:
    version = spec.get("version", 1)
    if version != 1:
        raise SpecError(f"Unsupported specification version: {version!r}. Expected 1.")

    reconciliation = spec.get("reconciliation")
    if not isinstance(reconciliation, dict) or not reconciliation.get("name"):
        raise SpecError("reconciliation.name is required.")

    _validate_endpoint("source", spec.get("source"))
    _validate_endpoint("target", spec.get("target"))

    source_keys = _as_list(spec["source"]["key"], "source.key")
    target_keys = _as_list(spec["target"]["key"], "target.key")
    if len(source_keys) != len(target_keys):
        raise SpecError("source.key and target.key must contain the same number of fields.")

    checks = spec.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SpecError("checks must be a non-empty list.")

    ids: set[str] = set()
    for index, check in enumerate(checks, start=1):
        if not isinstance(check, dict):
            raise SpecError(f"checks[{index}] must be an object.")
        check_type = check.get("type")
        if check_type not in SUPPORTED_CHECKS:
            raise SpecError(
                f"checks[{index}].type must be one of {sorted(SUPPORTED_CHECKS)}; got {check_type!r}."
            )
        check_id = check.get("id", f"check-{index}")
        if not isinstance(check_id, str) or not check_id:
            raise SpecError(f"checks[{index}].id must be a non-empty string when supplied.")
        if check_id in ids:
            raise SpecError(f"Duplicate check id: {check_id}")
        ids.add(check_id)

        severity = check.get("severity", "error")
        if severity not in SUPPORTED_SEVERITIES:
            raise SpecError(f"checks[{index}].severity must be error or warning.")

        if check_type == "field_match":
            if not isinstance(check.get("source"), str) or not isinstance(check.get("target"), str):
                raise SpecError(f"field_match check {check_id!r} requires source and target fields.")
            normalizers = check.get("normalize", ["trim"])
            if not isinstance(normalizers, list):
                raise SpecError(f"field_match check {check_id!r}.normalize must be a list.")
            unknown = set(normalizers) - SUPPORTED_NORMALIZERS
            if unknown:
                raise SpecError(f"Unsupported normalizers in {check_id!r}: {sorted(unknown)}")
            mapping = check.get("map")
            if mapping is not None and not isinstance(mapping, dict):
                raise SpecError(f"field_match check {check_id!r}.map must be an object.")
            numeric_tolerance = check.get("numeric_tolerance")
            if numeric_tolerance is not None and (
                not isinstance(numeric_tolerance, (int, float)) or numeric_tolerance < 0
            ):
                raise SpecError(f"field_match check {check_id!r}.numeric_tolerance must be >= 0.")
            max_mismatches = check.get("max_mismatches", 0)
            if not isinstance(max_mismatches, int) or max_mismatches < 0:
                raise SpecError(f"field_match check {check_id!r}.max_mismatches must be an integer >= 0.")

        if check_type == "control_total":
            if not isinstance(check.get("source"), str) or not isinstance(check.get("target"), str):
                raise SpecError(f"control_total check {check_id!r} requires source and target fields.")
            tolerance = check.get("tolerance", 0)
            if not isinstance(tolerance, (int, float)) or tolerance < 0:
                raise SpecError(f"control_total check {check_id!r}.tolerance must be >= 0.")

        if check_type == "row_count":
            tolerance = check.get("tolerance", 0)
            if not isinstance(tolerance, int) or tolerance < 0:
                raise SpecError(f"row_count check {check_id!r}.tolerance must be an integer >= 0.")

    evidence = spec.get("evidence", {})
    if evidence is not None:
        if not isinstance(evidence, dict):
            raise SpecError("evidence must be an object.")
        detail_limit = evidence.get("detail_limit", 100)
        if not isinstance(detail_limit, int) or detail_limit < 0:
            raise SpecError("evidence.detail_limit must be an integer >= 0.")
