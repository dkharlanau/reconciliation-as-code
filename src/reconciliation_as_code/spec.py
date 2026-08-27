from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

from .errors import SpecError
from .filtering import validate_predicate
from .materiality import validate_materiality_spec
from .sql_adapter import validate_sql_config

SUPPORTED_CHECKS = {"record_coverage", "field_match", "control_total", "row_count", "aggregate_match"}
SUPPORTED_SEVERITIES = {"error", "warning"}
SUPPORTED_NORMALIZERS = {
    "trim",
    "uppercase",
    "lowercase",
    "empty_to_null",
    "strip_leading_zeros",
}
SUPPORTED_NULL_SEMANTICS = {"equal", "empty_is_null", "never_equal"}
SUPPORTED_AGGREGATES = {"count", "distinct_count", "sum"}
SUPPORTED_SENSITIVE_VALUE_MODES = {"mask", "hash", "omit"}
SUPPORTED_KEY_MODES = {"plain", "hash"}


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
    has_file = endpoint.get("file") is not None
    has_sql = endpoint.get("sql") is not None
    if has_file == has_sql:
        raise SpecError(f"{name} must define exactly one of file or sql.")
    if has_file and (not isinstance(endpoint.get("file"), str) or not endpoint.get("file")):
        raise SpecError(f"{name}.file must be a non-empty string.")
    if has_sql:
        try:
            validate_sql_config(endpoint["sql"], f"{name}.sql")
        except Exception as exc:
            if isinstance(exc, SpecError):
                raise
            raise SpecError(str(exc)) from exc
    _as_list(endpoint.get("key"), f"{name}.key")

    normalizers = endpoint.get("key_normalize", ["trim"])
    if not isinstance(normalizers, list):
        raise SpecError(f"{name}.key_normalize must be a list.")
    unknown = set(normalizers) - SUPPORTED_NORMALIZERS
    if unknown:
        raise SpecError(f"Unsupported {name}.key_normalize values: {sorted(unknown)}")
    if endpoint.get("filter") is not None:
        validate_predicate(endpoint["filter"], f"{name}.filter")


def _validate_scopes(spec: dict[str, Any]) -> set[str]:
    scopes = spec.get("scopes", {})
    if scopes is None:
        return set()
    if not isinstance(scopes, dict):
        raise SpecError("scopes must be an object keyed by scope name.")
    names: set[str] = set()
    for name, scope in scopes.items():
        if not isinstance(name, str) or not name:
            raise SpecError("scope names must be non-empty strings.")
        if not isinstance(scope, dict) or not scope:
            raise SpecError(f"scope {name!r} must be a non-empty object.")
        unknown = set(scope) - {"source", "target"}
        if unknown:
            raise SpecError(f"scope {name!r} has unsupported keys: {sorted(unknown)}")
        if "source" in scope:
            validate_predicate(scope["source"], f"scopes.{name}.source")
        if "target" in scope:
            validate_predicate(scope["target"], f"scopes.{name}.target")
        names.add(name)
    return names


def _validate_when(check: dict[str, Any], check_id: str) -> None:
    when = check.get("when")
    if when is None:
        return
    if not isinstance(when, dict) or not when:
        raise SpecError(f"check {check_id!r}.when must be a non-empty object.")
    unknown = set(when) - {"source", "target"}
    if unknown:
        raise SpecError(f"check {check_id!r}.when has unsupported keys: {sorted(unknown)}")
    if "source" in when:
        validate_predicate(when["source"], f"checks.{check_id}.when.source")
    if "target" in when:
        validate_predicate(when["target"], f"checks.{check_id}.when.target")



def _validate_mapping_artifacts(spec: dict[str, Any]) -> set[str]:
    artifacts = spec.get("mapping_artifacts", {})
    if artifacts is None:
        return set()
    if not isinstance(artifacts, dict):
        raise SpecError("mapping_artifacts must be an object keyed by local artifact alias.")
    aliases: set[str] = set()
    for alias, config in artifacts.items():
        if not isinstance(alias, str) or not alias:
            raise SpecError("mapping_artifacts aliases must be non-empty strings.")
        if not isinstance(config, dict):
            raise SpecError(f"mapping_artifacts.{alias} must be an object.")
        if not isinstance(config.get("file"), str) or not config.get("file"):
            raise SpecError(f"mapping_artifacts.{alias}.file must be a non-empty string.")
        sha256 = config.get("sha256")
        if sha256 is not None and (not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None):
            raise SpecError(f"mapping_artifacts.{alias}.sha256 must be a lowercase SHA-256 hex digest.")
        aliases.add(alias)
    return aliases

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

    scope_names = _validate_scopes(spec)
    mapping_artifact_ids = _validate_mapping_artifacts(spec)
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
        scope = check.get("scope")
        if scope is not None and (not isinstance(scope, str) or scope not in scope_names):
            raise SpecError(f"check {check_id!r}.scope must reference a declared scope.")
        _validate_when(check, check_id)
        if check.get("map_ref") is not None and check_type != "field_match":
            raise SpecError(f"check {check_id!r}.map_ref is supported only for field_match checks.")

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
            map_ref = check.get("map_ref")
            if map_ref is not None:
                if mapping is not None:
                    raise SpecError(f"field_match check {check_id!r} cannot define both map and map_ref.")
                if not isinstance(map_ref, dict):
                    raise SpecError(f"field_match check {check_id!r}.map_ref must be an object.")
                artifact = map_ref.get("artifact")
                field = map_ref.get("field")
                if not isinstance(artifact, str) or artifact not in mapping_artifact_ids:
                    raise SpecError(
                        f"field_match check {check_id!r}.map_ref.artifact must reference a declared mapping_artifact."
                    )
                if not isinstance(field, str) or not field:
                    raise SpecError(f"field_match check {check_id!r}.map_ref.field must be a non-empty string.")
            numeric_tolerance = check.get("numeric_tolerance")
            if numeric_tolerance is not None and (
                not isinstance(numeric_tolerance, (int, float)) or numeric_tolerance < 0
            ):
                raise SpecError(f"field_match check {check_id!r}.numeric_tolerance must be >= 0.")
            percentage_tolerance = check.get("percentage_tolerance")
            if percentage_tolerance is not None and (
                not isinstance(percentage_tolerance, (int, float)) or percentage_tolerance < 0
            ):
                raise SpecError(f"field_match check {check_id!r}.percentage_tolerance must be >= 0.")
            date_tolerance_days = check.get("date_tolerance_days")
            if date_tolerance_days is not None and (
                not isinstance(date_tolerance_days, (int, float)) or date_tolerance_days < 0
            ):
                raise SpecError(f"field_match check {check_id!r}.date_tolerance_days must be >= 0.")
            null_semantics = check.get("null_semantics", "equal")
            if null_semantics not in SUPPORTED_NULL_SEMANTICS:
                raise SpecError(
                    f"field_match check {check_id!r}.null_semantics must be one of {sorted(SUPPORTED_NULL_SEMANTICS)}."
                )
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

        if check_type == "aggregate_match":
            operation = check.get("operation", "count")
            if operation not in SUPPORTED_AGGREGATES:
                raise SpecError(
                    f"aggregate_match check {check_id!r}.operation must be one of {sorted(SUPPORTED_AGGREGATES)}."
                )
            group_by = check.get("group_by")
            if not isinstance(group_by, dict) or "source" not in group_by or "target" not in group_by:
                raise SpecError(
                    f"aggregate_match check {check_id!r} requires group_by.source and group_by.target."
                )
            source_groups = _as_list(group_by["source"], f"checks.{check_id}.group_by.source")
            target_groups = _as_list(group_by["target"], f"checks.{check_id}.group_by.target")
            if len(source_groups) != len(target_groups):
                raise SpecError(
                    f"aggregate_match check {check_id!r} source/target group_by field counts must match."
                )
            if operation in {"sum", "distinct_count"}:
                if not isinstance(check.get("source"), str) or not isinstance(check.get("target"), str):
                    raise SpecError(
                        f"aggregate_match {operation} check {check_id!r} requires source and target fields."
                    )
            for tolerance_name in ("tolerance", "percentage_tolerance"):
                tolerance = check.get(tolerance_name, 0)
                if not isinstance(tolerance, (int, float)) or tolerance < 0:
                    raise SpecError(
                        f"aggregate_match check {check_id!r}.{tolerance_name} must be >= 0."
                    )

    evidence = spec.get("evidence", {})
    if evidence is not None:
        if not isinstance(evidence, dict):
            raise SpecError("evidence must be an object.")
        detail_limit = evidence.get("detail_limit", 100)
        if not isinstance(detail_limit, int) or detail_limit < 0:
            raise SpecError("evidence.detail_limit must be an integer >= 0.")
        sensitive_fields = evidence.get("sensitive_fields", [])
        if not isinstance(sensitive_fields, list) or not all(
            isinstance(field, str) and field for field in sensitive_fields
        ):
            raise SpecError("evidence.sensitive_fields must be a list of non-empty field names.")
        sensitive_value_mode = evidence.get("sensitive_value_mode", "mask")
        if sensitive_value_mode not in SUPPORTED_SENSITIVE_VALUE_MODES:
            raise SpecError(
                "evidence.sensitive_value_mode must be one of "
                f"{sorted(SUPPORTED_SENSITIVE_VALUE_MODES)}."
            )
        key_mode = evidence.get("key_mode", "plain")
        if key_mode not in SUPPORTED_KEY_MODES:
            raise SpecError(f"evidence.key_mode must be one of {sorted(SUPPORTED_KEY_MODES)}.")

    validate_materiality_spec(spec)
