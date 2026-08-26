from __future__ import annotations

import copy
import csv
import hashlib
import json
import tempfile
from collections import defaultdict, deque
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .errors import DataError
from .filtering import filter_rows
from .hierarchy import run_reconciliation_with_hierarchy, validate_hierarchy_spec
from .io import load_table
from .normalize import comparable_key


def _listify(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _label(key: tuple[str, ...]) -> str | list[str]:
    return key[0] if len(key) == 1 else list(key)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _component_id(source_keys: set[tuple[str, ...]], target_keys: set[tuple[str, ...]]) -> str:
    payload = {
        "source": sorted([list(key) for key in source_keys]),
        "target": sorted([list(key) for key in target_keys]),
    }
    return "identity-" + hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()[:12]


def validate_identity_spec(spec: dict[str, Any]) -> None:
    identity = spec.get("identity")
    if identity is None:
        return
    if not isinstance(identity, dict):
        raise DataError("identity must be an object.")
    crosswalk = identity.get("crosswalk")
    if not isinstance(crosswalk, dict):
        raise DataError("identity.crosswalk must be an object.")
    for name in ("file", "source_key", "target_key"):
        if name not in crosswalk:
            raise DataError(f"identity.crosswalk.{name} is required.")
    if not isinstance(crosswalk["file"], str) or not crosswalk["file"]:
        raise DataError("identity.crosswalk.file must be a non-empty string.")
    if len(_listify(crosswalk["source_key"])) != len(_listify(spec["source"]["key"])):
        raise DataError("identity.crosswalk.source_key must match source root key cardinality.")
    if len(_listify(crosswalk["target_key"])) != len(_listify(spec["target"]["key"])):
        raise DataError("identity.crosswalk.target_key must match target root key cardinality.")
    aggregation = identity.get("aggregation", {})
    if not isinstance(aggregation, dict):
        raise DataError("identity.aggregation must be an object.")
    allowed = {"sum", "min", "max", "first", "require_equal", "set"}
    for side in ("source", "target"):
        policies = aggregation.get(side, {})
        if not isinstance(policies, dict):
            raise DataError(f"identity.aggregation.{side} must be an object.")
        for field, policy in policies.items():
            if policy not in allowed:
                raise DataError(
                    f"Unsupported identity aggregation policy {policy!r} for {side}.{field}. "
                    f"Allowed: {', '.join(sorted(allowed))}."
                )
    validate_hierarchy_spec(spec)


def _load_crosswalk(spec: dict[str, Any], base: Path) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    config = copy.deepcopy(spec["identity"]["crosswalk"])
    config.setdefault("key", config["source_key"])
    path, rows = load_table(config, base)
    return path, rows, config


def _build_components(
    spec: dict[str, Any], rows: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[dict[tuple[str, ...], str], dict[tuple[str, ...], str], dict[str, dict[str, Any]]]:
    source_fields = _listify(config["source_key"])
    target_fields = _listify(config["target_key"])
    source_ops = config.get("source_normalize", spec["source"].get("key_normalize", ["trim"]))
    target_ops = config.get("target_normalize", spec["target"].get("key_normalize", ["trim"]))

    graph: dict[tuple[str, tuple[str, ...]], set[tuple[str, tuple[str, ...]]]] = defaultdict(set)
    seen_edges: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for index, row in enumerate(rows, start=1):
        source_key = comparable_key(row, source_fields, source_ops)
        target_key = comparable_key(row, target_fields, target_ops)
        if any(value == "" for value in source_key) or any(value == "" for value in target_key):
            raise DataError(f"Identity crosswalk row {index} contains an empty source or target key component.")
        edge = (source_key, target_key)
        if edge in seen_edges:
            raise DataError(f"Duplicate identity crosswalk edge at row {index}: {_label(source_key)!r} -> {_label(target_key)!r}.")
        seen_edges.add(edge)
        source_node = ("source", source_key)
        target_node = ("target", target_key)
        graph[source_node].add(target_node)
        graph[target_node].add(source_node)

    source_map: dict[tuple[str, ...], str] = {}
    target_map: dict[tuple[str, ...], str] = {}
    components: dict[str, dict[str, Any]] = {}
    visited: set[tuple[str, tuple[str, ...]]] = set()
    for start in sorted(graph, key=_canonical):
        if start in visited:
            continue
        queue = deque([start])
        source_keys: set[tuple[str, ...]] = set()
        target_keys: set[tuple[str, ...]] = set()
        while queue:
            node = queue.popleft()
            if node in visited:
                continue
            visited.add(node)
            side, key = node
            (source_keys if side == "source" else target_keys).add(key)
            queue.extend(graph[node] - visited)
        if len(source_keys) > 1 and len(target_keys) > 1:
            raise DataError(
                "N:N identity component is ambiguous and unsupported: "
                f"source={[_label(key) for key in sorted(source_keys)]}, "
                f"target={[_label(key) for key in sorted(target_keys)]}. "
                "Split it into explicit 1:N or N:1 components."
            )
        mode = "1:1"
        if len(source_keys) == 1 and len(target_keys) > 1:
            mode = "1:N"
        elif len(source_keys) > 1 and len(target_keys) == 1:
            mode = "N:1"
        component = _component_id(source_keys, target_keys)
        components[component] = {
            "id": component,
            "mode": mode,
            "source_keys": [_label(key) for key in sorted(source_keys)],
            "target_keys": [_label(key) for key in sorted(target_keys)],
        }
        for key in source_keys:
            source_map[key] = component
        for key in target_keys:
            target_map[key] = component
    return source_map, target_map, components


def _decimal(value: Any, field: str) -> Decimal:
    text = str(value).strip().replace(",", "")
    try:
        return Decimal(text or "0")
    except InvalidOperation as exc:
        raise DataError(f"Identity aggregation policy sum requires numeric field {field!r}; got {value!r}.") from exc


def _aggregate_values(values: list[Any], policy: str, field: str, side: str) -> Any:
    non_null = [value for value in values if value is not None and str(value).strip() != ""]
    if not non_null:
        return ""
    if policy == "first":
        return non_null[0]
    if policy == "sum":
        total = sum((_decimal(value, field) for value in non_null), Decimal("0"))
        return str(total)
    if policy == "min":
        return min(non_null, key=lambda value: str(value))
    if policy == "max":
        return max(non_null, key=lambda value: str(value))
    unique = sorted({_canonical(value): value for value in non_null}.values(), key=lambda value: str(value))
    if policy == "set":
        return "|".join(str(value) for value in unique)
    if len(unique) == 1:
        return unique[0]
    raise DataError(
        f"Identity component has multiple {side} values for field {field!r}: {unique!r}. "
        f"Declare identity.aggregation.{side}.{field} explicitly (for example sum, set, first)."
    )


def _required_fields(spec: dict[str, Any], side: str) -> set[str]:
    result: set[str] = set()
    for check in spec.get("checks", []):
        field = check.get(side)
        if isinstance(field, str):
            result.add(field)
        group = (check.get("group_by") or {}).get(side)
        if isinstance(group, str):
            result.add(group)
        elif isinstance(group, list):
            result.update(group)
    return result


def _aggregate_root_rows(
    rows: list[dict[str, Any]], endpoint: dict[str, Any], mapping: dict[tuple[str, ...], str],
    components: dict[str, dict[str, Any]], side: str, policies: dict[str, str], required_fields: set[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], set[tuple[str, ...]]]:
    key_fields = _listify(endpoint["key"])
    operations = endpoint.get("key_normalize", ["trim"])
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unmapped: list[dict[str, Any]] = []
    observed_keys: set[tuple[str, ...]] = set()

    for row in rows:
        key = comparable_key(row, key_fields, operations)
        observed_keys.add(key)
        component = mapping.get(key)
        if component is None:
            component = "unmapped-" + side + "-" + hashlib.sha256(_canonical(key).encode("utf-8")).hexdigest()[:12]
            components.setdefault(component, {
                "id": component,
                "mode": "unmapped-" + side,
                "source_keys": [_label(key)] if side == "source" else [],
                "target_keys": [_label(key)] if side == "target" else [],
            })
            unmapped.append({"difference": f"unmapped_{side}_identity", "key": _label(key), "identity": component})
        grouped[component].append(row)

    output: list[dict[str, Any]] = []
    for component, group_rows in sorted(grouped.items()):
        fields: list[str] = []
        for row in group_rows:
            for field in row:
                if field not in fields:
                    fields.append(field)
        aggregated: dict[str, Any] = {"__rac_identity": component}
        for field in fields:
            values = [row.get(field) for row in group_rows]
            if field in key_fields:
                aggregated[field] = "|".join(sorted({str(value) for value in values}))
                continue
            if len(group_rows) == 1:
                aggregated[field] = values[0]
                continue
            policy = policies.get(field, "require_equal")
            if field not in required_fields and field not in policies:
                policy = "set"
            aggregated[field] = _aggregate_values(values, policy, field, side)
        output.append(aggregated)
    return output, unmapped, observed_keys


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    if not fields:
        fields = ["__rac_identity"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _transform_child_rows(
    rows: list[dict[str, Any]], endpoint: dict[str, Any], mapping: dict[tuple[str, ...], str], side: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    parent_fields = _listify(endpoint["parent_key"])
    parent_ops = endpoint.get("parent_key_normalize", endpoint.get("key_normalize", ["trim"]))
    output: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    for row in rows:
        parent_key = comparable_key(row, parent_fields, parent_ops)
        component = mapping.get(parent_key)
        if component is None:
            component = "unmapped-" + side + "-" + hashlib.sha256(_canonical(parent_key).encode("utf-8")).hexdigest()[:12]
            unmapped.append({"difference": f"unmapped_{side}_child_parent", "key": _label(parent_key), "identity": component})
        copied = dict(row)
        copied["__rac_parent_identity"] = component
        output.append(copied)
    return output, unmapped


def _rewrite_child_endpoint(endpoint: dict[str, Any], path: Path) -> dict[str, Any]:
    rewritten = copy.deepcopy(endpoint)
    original_key = _listify(endpoint["key"])
    parent_fields = set(_listify(endpoint["parent_key"]))
    local_key = [field for field in original_key if field not in parent_fields]
    rewritten["file"] = str(path)
    rewritten["key"] = ["__rac_parent_identity", *local_key]
    rewritten["parent_key"] = "__rac_parent_identity"
    rewritten["key_normalize"] = ["trim"]
    rewritten["parent_key_normalize"] = ["trim"]
    return rewritten


def _identity_for_detail(detail: dict[str, Any], components: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[Any] = [detail.get("parent_key"), detail.get("key")]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate in components:
            return components[candidate]
        if isinstance(candidate, list) and candidate and candidate[0] in components:
            return components[candidate[0]]
    return None


def run_reconciliation_with_identity(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    validate_identity_spec(spec)
    if "identity" not in spec:
        return run_reconciliation_with_hierarchy(spec, base_dir=base_dir, spec_path=spec_path)

    base = Path(base_dir).resolve()
    crosswalk_path, crosswalk_rows, crosswalk_config = _load_crosswalk(spec, base)
    source_map, target_map, components = _build_components(spec, crosswalk_rows, crosswalk_config)

    source_path, source_raw = load_table(spec["source"], base)
    target_path, target_raw = load_table(spec["target"], base)
    source_selected = filter_rows(source_raw, spec["source"].get("filter"))
    target_selected = filter_rows(target_raw, spec["target"].get("filter"))
    policies = spec["identity"].get("aggregation", {})
    source_rows, source_unmapped, observed_source = _aggregate_root_rows(
        source_selected, spec["source"], source_map, components, "source",
        policies.get("source", {}), _required_fields(spec, "source")
    )
    target_rows, target_unmapped, observed_target = _aggregate_root_rows(
        target_selected, spec["target"], target_map, components, "target",
        policies.get("target", {}), _required_fields(spec, "target")
    )

    unused_source = sorted(set(source_map) - observed_source)
    unused_target = sorted(set(target_map) - observed_target)
    detail_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))

    with tempfile.TemporaryDirectory(prefix="rac-identity-") as tmp:
        temp = Path(tmp)
        source_temp = temp / "source.csv"
        target_temp = temp / "target.csv"
        _write_csv(source_temp, source_rows)
        _write_csv(target_temp, target_rows)

        rewritten = copy.deepcopy(spec)
        rewritten.pop("identity", None)
        rewritten["source"]["file"] = str(source_temp)
        rewritten["source"]["key"] = "__rac_identity"
        rewritten["source"]["key_normalize"] = ["trim"]
        rewritten["source"].pop("filter", None)
        rewritten["target"]["file"] = str(target_temp)
        rewritten["target"]["key"] = "__rac_identity"
        rewritten["target"]["key_normalize"] = ["trim"]
        rewritten["target"].pop("filter", None)

        original_child_inputs: dict[str, tuple[Path, Path]] = {}
        child_unmapped: list[dict[str, Any]] = []
        for name, child in (spec.get("children") or {}).items():
            source_child_path, source_child_rows = load_table(child["source"], base)
            target_child_path, target_child_rows = load_table(child["target"], base)
            source_transformed, source_child_unmapped = _transform_child_rows(source_child_rows, child["source"], source_map, "source")
            target_transformed, target_child_unmapped = _transform_child_rows(target_child_rows, child["target"], target_map, "target")
            child_unmapped.extend({**item, "collection": name} for item in source_child_unmapped)
            child_unmapped.extend({**item, "collection": name} for item in target_child_unmapped)
            source_child_temp = temp / f"child-{name}-source.csv"
            target_child_temp = temp / f"child-{name}-target.csv"
            _write_csv(source_child_temp, source_transformed)
            _write_csv(target_child_temp, target_transformed)
            rewritten["children"][name]["source"] = _rewrite_child_endpoint(child["source"], source_child_temp)
            rewritten["children"][name]["target"] = _rewrite_child_endpoint(child["target"], target_child_temp)
            original_child_inputs[name] = (source_child_path, target_child_path)

        result = run_reconciliation_with_hierarchy(rewritten, base_dir=temp, spec_path=None)

    result["configuration_sha256"] = hashlib.sha256(_canonical(spec).encode("utf-8")).hexdigest()
    result["inputs"]["source"] = {"path": spec["source"]["file"], "sha256": _sha256(source_path)}
    result["inputs"]["target"] = {"path": spec["target"]["file"], "sha256": _sha256(target_path)}
    result["inputs"]["identity_crosswalk"] = {"path": spec["identity"]["crosswalk"]["file"], "sha256": _sha256(crosswalk_path)}
    if spec_path:
        resolved = Path(spec_path).resolve()
        if resolved.exists():
            result["inputs"]["specification"] = {"path": resolved.name, "sha256": _sha256(resolved)}
    for name, paths in original_child_inputs.items():
        result["inputs"][f"child:{name}:source"] = {"path": spec["children"][name]["source"]["file"], "sha256": _sha256(paths[0])}
        result["inputs"][f"child:{name}:target"] = {"path": spec["children"][name]["target"]["file"], "sha256": _sha256(paths[1])}

    identity_details = [*source_unmapped, *target_unmapped, *child_unmapped]
    identity_details.extend({"difference": "unused_crosswalk_source", "key": _label(key), "severity": "warning"} for key in unused_source)
    identity_details.extend({"difference": "unused_crosswalk_target", "key": _label(key), "severity": "warning"} for key in unused_target)
    integrity_failures = len(source_unmapped) + len(target_unmapped) + len(child_unmapped)
    result["checks"].append({
        "id": "identity-crosswalk-integrity",
        "type": "identity_integrity",
        "severity": "error",
        "status": "failed" if integrity_failures else "passed",
        "metrics": {
            "components": len([item for item in components.values() if not item["mode"].startswith("unmapped-")]),
            "one_to_one": sum(item["mode"] == "1:1" for item in components.values()),
            "one_to_many": sum(item["mode"] == "1:N" for item in components.values()),
            "many_to_one": sum(item["mode"] == "N:1" for item in components.values()),
            "unmapped_source": len(source_unmapped),
            "unmapped_target": len(target_unmapped),
            "unmapped_child_parents": len(child_unmapped),
            "unused_crosswalk_source": len(unused_source),
            "unused_crosswalk_target": len(unused_target),
        },
        "details": identity_details[:detail_limit],
        "details_truncated": len(identity_details) > detail_limit,
    })

    for check in result.get("checks", []):
        for detail in check.get("details", []):
            identity_info = _identity_for_detail(detail, components)
            if identity_info is not None:
                detail["identity"] = identity_info
    if "hierarchy" in result:
        for item in result["hierarchy"].get("failed_objects", []):
            identity_info = _identity_for_detail(item, components)
            if identity_info is not None:
                item["identity"] = identity_info

    failed_errors = [item for item in result["checks"] if item["severity"] == "error" and item["status"] == "failed"]
    failed_warnings = [item for item in result["checks"] if item["severity"] == "warning" and item["status"] == "failed"]
    result["status"] = "failed" if failed_errors else "passed"
    result["summary"].update({
        "checks_total": len(result["checks"]),
        "checks_failed": len(failed_errors),
        "warnings_failed": len(failed_warnings),
        "source_raw_records": len(source_selected),
        "target_raw_records": len(target_selected),
        "identity_components": len([item for item in components.values() if not item["mode"].startswith("unmapped-")]),
        "identity_unmapped_source": len(source_unmapped),
        "identity_unmapped_target": len(target_unmapped),
    })
    result["identity"] = {
        "crosswalk": result["inputs"]["identity_crosswalk"],
        "components": [components[key] for key in sorted(components) if not components[key]["mode"].startswith("unmapped-")],
        "aggregation": spec["identity"].get("aggregation", {}),
    }
    return result
