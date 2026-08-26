from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from .engine import run_reconciliation
from .errors import DataError
from .io import load_table
from .normalize import comparable_key


def _listify(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _label(values: tuple[str, ...]) -> str | list[str]:
    return values[0] if len(values) == 1 else list(values)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def validate_hierarchy_spec(spec: dict[str, Any]) -> None:
    children = spec.get("children")
    if children is None:
        return
    if not isinstance(children, dict) or not children:
        raise DataError("children must be a non-empty object keyed by collection name.")

    root_source_keys = _listify(spec["source"]["key"])
    root_target_keys = _listify(spec["target"]["key"])
    for name, child in children.items():
        if not isinstance(name, str) or not name:
            raise DataError("child collection names must be non-empty strings.")
        if not isinstance(child, dict):
            raise DataError(f"child collection {name!r} must be an object.")
        for side, root_keys in (("source", root_source_keys), ("target", root_target_keys)):
            endpoint = child.get(side)
            if not isinstance(endpoint, dict):
                raise DataError(f"children.{name}.{side} must be an endpoint object.")
            if not isinstance(endpoint.get("file"), str) or not endpoint.get("file"):
                raise DataError(f"children.{name}.{side}.file is required.")
            key = endpoint.get("key")
            if not isinstance(key, (str, list)):
                raise DataError(f"children.{name}.{side}.key is required.")
            parent_key = endpoint.get("parent_key")
            if not isinstance(parent_key, (str, list)):
                raise DataError(f"children.{name}.{side}.parent_key is required.")
            child_keys = _listify(key)
            parent_keys = _listify(parent_key)
            if len(parent_keys) != len(root_keys):
                raise DataError(
                    f"children.{name}.{side}.parent_key must contain {len(root_keys)} field(s) to match the root identity."
                )
            missing = [field for field in parent_keys if field not in child_keys]
            if missing:
                raise DataError(
                    f"children.{name}.{side}.parent_key fields must also be part of child key; missing {missing}."
                )
        checks = child.get("checks")
        if not isinstance(checks, list) or not checks:
            raise DataError(f"children.{name}.checks must be a non-empty list.")
        duplicate_policy = child.get("duplicate_policy", "error")
        if duplicate_policy not in {"error", "warning"}:
            raise DataError(f"children.{name}.duplicate_policy must be error or warning.")


def _root_key_sets(spec: dict[str, Any], base: Path) -> tuple[set[tuple[str, ...]], set[tuple[str, ...]]]:
    _, source_rows = load_table(spec["source"], base)
    _, target_rows = load_table(spec["target"], base)
    source_keys = _listify(spec["source"]["key"])
    target_keys = _listify(spec["target"]["key"])
    source_ops = spec["source"].get("key_normalize", ["trim"])
    target_ops = spec["target"].get("key_normalize", ["trim"])
    return (
        {comparable_key(row, source_keys, source_ops) for row in source_rows},
        {comparable_key(row, target_keys, target_ops) for row in target_rows},
    )


def _parent_from_detail(detail: dict[str, Any], endpoint: dict[str, Any]) -> str | list[str] | None:
    if "key" not in detail:
        return None
    child_fields = _listify(endpoint["key"])
    parent_fields = _listify(endpoint["parent_key"])
    raw_key = detail["key"]
    values = [raw_key] if not isinstance(raw_key, list) else raw_key
    if len(values) != len(child_fields):
        return None
    positions = [child_fields.index(field) for field in parent_fields]
    parent = tuple(str(values[position]) for position in positions)
    return _label(parent)


def _path(root_name: str, parent: Any, collection: str, child_key: Any) -> str:
    parent_text = "/".join(str(value) for value in parent) if isinstance(parent, list) else str(parent)
    child_text = "/".join(str(value) for value in child_key) if isinstance(child_key, list) else str(child_key)
    return f"{root_name}/{parent_text}/{collection}/{child_text}"


def _orphan_check(
    name: str,
    side: str,
    endpoint: dict[str, Any],
    root_keys: set[tuple[str, ...]],
    rows: list[dict[str, Any]],
    root_name: str,
    detail_limit: int,
) -> dict[str, Any]:
    parent_fields = _listify(endpoint["parent_key"])
    parent_ops = endpoint.get("parent_key_normalize", endpoint.get("key_normalize", ["trim"]))
    child_fields = _listify(endpoint["key"])
    child_ops = endpoint.get("key_normalize", ["trim"])
    details: list[dict[str, Any]] = []
    for row in rows:
        parent = comparable_key(row, parent_fields, parent_ops)
        if parent in root_keys:
            continue
        child_key = comparable_key(row, child_fields, child_ops)
        parent_label = _label(parent)
        child_label = _label(child_key)
        details.append(
            {
                "key": child_label,
                "parent_key": parent_label,
                "difference": f"orphan_{side}_child",
                "collection": name,
                "object_path": _path(root_name, parent_label, name, child_label),
            }
        )
    return {
        "id": f"child:{name}:{side}-parent-integrity",
        "type": "parent_integrity",
        "severity": "error",
        "status": "passed" if not details else "failed",
        "metrics": {"orphan_rows": len(details), "side": side, "collection": name},
        "details": details[:detail_limit],
        "details_truncated": len(details) > detail_limit,
    }


def _annotate_child_check(
    check: dict[str, Any], name: str, source_endpoint: dict[str, Any], target_endpoint: dict[str, Any], root_name: str
) -> None:
    original_id = check["id"]
    check["id"] = f"child:{name}:{original_id}"
    check.setdefault("metrics", {})["collection"] = name
    for detail in check.get("details", []):
        detail["collection"] = name
        parent = _parent_from_detail(detail, source_endpoint)
        if parent is None:
            parent = _parent_from_detail(detail, target_endpoint)
        if parent is not None:
            detail["parent_key"] = parent
            detail["object_path"] = _path(root_name, parent, name, detail.get("key", "group"))


def _collect_object_failures(result: dict[str, Any], root_name: str) -> list[dict[str, Any]]:
    failures: dict[str, dict[str, Any]] = {}
    for check in result.get("checks", []):
        if check.get("severity") != "error" or check.get("status") != "failed":
            continue
        for detail in check.get("details", []):
            parent = detail.get("parent_key")
            if parent is None and not check["id"].startswith("child:"):
                parent = detail.get("key")
            if parent is None:
                continue
            identity = _canonical(parent)
            item = failures.setdefault(
                identity,
                {"key": parent, "status": "failed", "failed_checks": [], "paths": []},
            )
            if check["id"] not in item["failed_checks"]:
                item["failed_checks"].append(check["id"])
            path = detail.get("object_path") or f"{root_name}/{parent}"
            if path not in item["paths"]:
                item["paths"].append(path)
    return list(failures.values())


def run_reconciliation_with_hierarchy(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    validate_hierarchy_spec(spec)
    base = Path(base_dir).resolve()
    root_result = run_reconciliation(spec, base_dir=base, spec_path=spec_path)
    children = spec.get("children")
    if not children:
        return root_result

    root_source_set, root_target_set = _root_key_sets(spec, base)
    root_name = spec.get("object", {}).get("type") or spec["reconciliation"]["name"].replace(" ", "_")
    detail_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))
    collection_summaries: dict[str, Any] = {}

    for name, child in children.items():
        child_spec = {
            "version": spec.get("version", 1),
            "reconciliation": {
                "name": f"{spec['reconciliation']['name']} / {name}",
                "description": child.get("description"),
            },
            "source": {key: value for key, value in child["source"].items() if key not in {"parent_key", "parent_key_normalize"}},
            "target": {key: value for key, value in child["target"].items() if key not in {"parent_key", "parent_key_normalize"}},
            "checks": copy.deepcopy(child["checks"]),
            "evidence": {"detail_limit": detail_limit},
        }
        if child.get("scopes"):
            child_spec["scopes"] = copy.deepcopy(child["scopes"])
        child_result = run_reconciliation(child_spec, base_dir=base)

        duplicate_policy = child.get("duplicate_policy", "error")
        for check in child_result["checks"]:
            _annotate_child_check(check, name, child["source"], child["target"], root_name)
            if duplicate_policy == "warning" and check["type"] == "key_integrity":
                check["severity"] = "warning"

        _, source_rows = load_table(child["source"], base)
        _, target_rows = load_table(child["target"], base)
        orphan_source = _orphan_check(
            name, "source", child["source"], root_source_set, source_rows, root_name, detail_limit
        )
        orphan_target = _orphan_check(
            name, "target", child["target"], root_target_set, target_rows, root_name, detail_limit
        )
        child_checks = [*child_result["checks"], orphan_source, orphan_target]
        root_result["checks"].extend(child_checks)

        for side in ("source", "target"):
            info = child_result.get("inputs", {}).get(side)
            if info:
                root_result["inputs"][f"child:{name}:{side}"] = info

        collection_failed = any(
            item["severity"] == "error" and item["status"] == "failed" for item in child_checks
        )
        collection_summaries[name] = {
            "status": "failed" if collection_failed else "passed",
            "source_records": child_result["summary"]["source_records"],
            "target_records": child_result["summary"]["target_records"],
            "matched_records": child_result["summary"]["matched_records"],
            "missing_in_target": child_result["summary"]["missing_in_target"],
            "unexpected_in_target": child_result["summary"]["unexpected_in_target"],
            "duplicate_policy": duplicate_policy,
        }

    failed_errors = [
        item for item in root_result["checks"] if item["severity"] == "error" and item["status"] == "failed"
    ]
    failed_warnings = [
        item for item in root_result["checks"] if item["severity"] == "warning" and item["status"] == "failed"
    ]
    object_failures = _collect_object_failures(root_result, root_name)
    objects_evaluated = root_result["summary"]["source_records"]
    root_result["status"] = "failed" if failed_errors else "passed"
    root_result["summary"]["checks_total"] = len(root_result["checks"])
    root_result["summary"]["checks_failed"] = len(failed_errors)
    root_result["summary"]["warnings_failed"] = len(failed_warnings)
    root_result["summary"]["child_collections"] = len(collection_summaries)
    root_result["summary"]["child_collections_failed"] = sum(
        1 for item in collection_summaries.values() if item["status"] == "failed"
    )
    root_result["summary"]["objects_evaluated"] = objects_evaluated
    root_result["summary"]["objects_failed"] = len(object_failures)
    root_result["summary"]["objects_passed"] = max(objects_evaluated - len(object_failures), 0)
    root_result["hierarchy"] = {
        "object_type": root_name,
        "collections": collection_summaries,
        "failed_objects": object_failures,
    }
    return root_result
