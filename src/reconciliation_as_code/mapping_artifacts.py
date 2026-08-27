from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .errors import DataError


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_mapping_artifact(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Mapping artifact not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise DataError(f"Invalid Mapping as Code YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DataError(f"Mapping artifact root must be an object: {path}")
    mapping = raw.get("mapping")
    if not isinstance(mapping, dict) or not isinstance(mapping.get("id"), str) or not mapping.get("id"):
        raise DataError(f"Mapping artifact requires mapping.id: {path}")
    fields = mapping.get("fields")
    if not isinstance(fields, list):
        raise DataError(f"Mapping artifact requires mapping.fields list: {path}")
    value_maps = raw.get("value_maps", {})
    if not isinstance(value_maps, dict):
        raise DataError(f"Mapping artifact value_maps must be an object: {path}")
    return raw


def resolve_mapping_artifacts(
    spec: dict[str, Any], base_dir: str | Path
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Resolve local Mapping as Code value maps into an effective RAC spec.

    The source reconciliation spec remains unchanged. Returned evidence records preserve
    the exact artifact hash and Mapping as Code identity used to derive effective maps.
    """
    refs = spec.get("mapping_artifacts") or {}
    if not refs:
        return copy.deepcopy(spec), {}

    base = Path(base_dir).resolve()
    loaded: dict[str, tuple[dict[str, Any], Path, str]] = {}
    evidence: dict[str, dict[str, Any]] = {}
    for alias, config in refs.items():
        path = Path(config["file"])
        if not path.is_absolute():
            path = base / path
        path = path.resolve()
        artifact = _load_mapping_artifact(path)
        sha256 = _sha256(path)
        expected_sha = config.get("sha256")
        if expected_sha is not None and expected_sha != sha256:
            raise DataError(
                f"Mapping artifact {alias!r} SHA-256 mismatch: expected {expected_sha}, got {sha256}."
            )
        loaded[alias] = (artifact, path, sha256)
        evidence[alias] = {
            "path": config["file"],
            "sha256": sha256,
            "mapping_id": artifact["mapping"]["id"],
            "schema_version": artifact.get("schema_version"),
        }

    effective = copy.deepcopy(spec)
    for index, check in enumerate(effective.get("checks", []), start=1):
        map_ref = check.get("map_ref")
        if not map_ref:
            continue
        check_id = check.get("id", f"check-{index}")
        alias = map_ref["artifact"]
        field_id = map_ref["field"]
        artifact, _, _ = loaded[alias]
        field = next(
            (
                item
                for item in artifact["mapping"]["fields"]
                if isinstance(item, dict) and item.get("id") == field_id
            ),
            None,
        )
        if field is None:
            raise DataError(
                f"field_match check {check_id!r} references unknown Mapping as Code field {field_id!r} "
                f"in artifact {alias!r}."
            )
        source_field = (field.get("source") or {}).get("field")
        target_field = (field.get("target") or {}).get("field")
        if source_field and source_field != check.get("source"):
            raise DataError(
                f"field_match check {check_id!r} source {check.get('source')!r} does not match "
                f"Mapping as Code field source {source_field!r}."
            )
        if target_field and target_field != check.get("target"):
            raise DataError(
                f"field_match check {check_id!r} target {check.get('target')!r} does not match "
                f"Mapping as Code field target {target_field!r}."
            )
        transform = field.get("transform") or {}
        if transform.get("type") != "lookup" or not isinstance(transform.get("reference"), str):
            raise DataError(
                f"field_match check {check_id!r} map_ref currently requires a Mapping as Code lookup transform."
            )
        reference = transform["reference"]
        value_map = artifact.get("value_maps", {}).get(reference)
        if not isinstance(value_map, dict):
            raise DataError(
                f"Mapping as Code lookup {reference!r} referenced by field {field_id!r} is missing or ambiguous."
            )
        # The public contract uses map_ref; the deterministic engine already knows how
        # to evaluate an inline map. Materialize the effective map and remove map_ref
        # from the execution copy so ordinary validation cannot mistake derived state
        # for a user-authored duplicate mapping definition.
        check["map"] = copy.deepcopy(value_map)
        check.pop("map_ref", None)
        evidence[alias].setdefault("fields", []).append(field_id)

    for record in evidence.values():
        if "fields" in record:
            record["fields"] = sorted(set(record["fields"]))
    return effective, evidence
