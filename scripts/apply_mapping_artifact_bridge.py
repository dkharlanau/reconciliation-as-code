from __future__ import annotations

import json
from pathlib import Path


# ---- spec.py -------------------------------------------------------------
spec_path = Path("src/reconciliation_as_code/spec.py")
spec = spec_path.read_text(encoding="utf-8")
spec = spec.replace("from pathlib import Path\n", "from pathlib import Path\nimport re\n", 1)

validation_helper = '''\n\ndef _validate_mapping_artifacts(spec: dict[str, Any]) -> set[str]:\n    artifacts = spec.get("mapping_artifacts", {})\n    if artifacts is None:\n        return set()\n    if not isinstance(artifacts, dict):\n        raise SpecError("mapping_artifacts must be an object keyed by local artifact alias.")\n    aliases: set[str] = set()\n    for alias, config in artifacts.items():\n        if not isinstance(alias, str) or not alias:\n            raise SpecError("mapping_artifacts aliases must be non-empty strings.")\n        if not isinstance(config, dict):\n            raise SpecError(f"mapping_artifacts.{alias} must be an object.")\n        if not isinstance(config.get("file"), str) or not config.get("file"):\n            raise SpecError(f"mapping_artifacts.{alias}.file must be a non-empty string.")\n        sha256 = config.get("sha256")\n        if sha256 is not None and (not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None):\n            raise SpecError(f"mapping_artifacts.{alias}.sha256 must be a lowercase SHA-256 hex digest.")\n        aliases.add(alias)\n    return aliases\n'''
anchor = "\ndef validate_spec(spec: dict[str, Any]) -> None:\n"
if validation_helper.strip() not in spec:
    if anchor not in spec:
        raise SystemExit("validate_spec anchor not found")
    spec = spec.replace(anchor, validation_helper + anchor, 1)

old = '''    scope_names = _validate_scopes(spec)\n    checks = spec.get("checks")\n'''
new = '''    scope_names = _validate_scopes(spec)\n    mapping_artifact_ids = _validate_mapping_artifacts(spec)\n    checks = spec.get("checks")\n'''
if old not in spec:
    raise SystemExit("scope/check anchor not found")
spec = spec.replace(old, new, 1)

old = '''        _validate_when(check, check_id)\n\n        if check_type == "field_match":\n'''
new = '''        _validate_when(check, check_id)\n        if check.get("map_ref") is not None and check_type != "field_match":\n            raise SpecError(f"check {check_id!r}.map_ref is supported only for field_match checks.")\n\n        if check_type == "field_match":\n'''
if old not in spec:
    raise SystemExit("check-type anchor not found")
spec = spec.replace(old, new, 1)

old = '''            mapping = check.get("map")\n            if mapping is not None and not isinstance(mapping, dict):\n                raise SpecError(f"field_match check {check_id!r}.map must be an object.")\n            numeric_tolerance = check.get("numeric_tolerance")\n'''
new = '''            mapping = check.get("map")\n            if mapping is not None and not isinstance(mapping, dict):\n                raise SpecError(f"field_match check {check_id!r}.map must be an object.")\n            map_ref = check.get("map_ref")\n            if map_ref is not None:\n                if mapping is not None:\n                    raise SpecError(f"field_match check {check_id!r} cannot define both map and map_ref.")\n                if not isinstance(map_ref, dict):\n                    raise SpecError(f"field_match check {check_id!r}.map_ref must be an object.")\n                artifact = map_ref.get("artifact")\n                field = map_ref.get("field")\n                if not isinstance(artifact, str) or artifact not in mapping_artifact_ids:\n                    raise SpecError(\n                        f"field_match check {check_id!r}.map_ref.artifact must reference a declared mapping_artifact."\n                    )\n                if not isinstance(field, str) or not field:\n                    raise SpecError(f"field_match check {check_id!r}.map_ref.field must be a non-empty string.")\n            numeric_tolerance = check.get("numeric_tolerance")\n'''
if old not in spec:
    raise SystemExit("field map anchor not found")
spec = spec.replace(old, new, 1)
spec_path.write_text(spec, encoding="utf-8")


# ---- runtime.py ----------------------------------------------------------
runtime_path = Path("src/reconciliation_as_code/runtime.py")
runtime = runtime_path.read_text(encoding="utf-8")
runtime = runtime.replace(
    "from pathlib import Path\nfrom typing import Any\n",
    "import hashlib\nimport json\nfrom pathlib import Path\nfrom typing import Any\n",
    1,
)
runtime = runtime.replace(
    "from .governance import run_reconciliation_with_governance\n",
    "from .governance import run_reconciliation_with_governance\nfrom .mapping_artifacts import resolve_mapping_artifacts\n",
    1,
)
helper = '''\n\ndef _sha256_object(value: Any) -> str:\n    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)\n    return hashlib.sha256(payload.encode("utf-8")).hexdigest()\n\n\ndef _apply_mapping_artifact_metadata(\n    result: dict[str, Any], metadata: dict[str, dict[str, Any]]\n) -> dict[str, Any]:\n    if not metadata:\n        return result\n    for alias, record in sorted(metadata.items()):\n        result.setdefault("inputs", {})[f"mapping:{alias}"] = record\n    result["configuration_sha256"] = _sha256_object(\n        {\n            "resolved_configuration_sha256": result["configuration_sha256"],\n            "mapping_artifacts": {alias: record["sha256"] for alias, record in sorted(metadata.items())},\n        }\n    )\n    return result\n'''
anchor = "\ndef run_reconciliation_runtime(\n"
if helper.strip() not in runtime:
    if anchor not in runtime:
        raise SystemExit("runtime function anchor not found")
    runtime = runtime.replace(anchor, helper + anchor, 1)
old = '''    """Run a reconciliation after resolving credential-free SQL endpoints to bounded local extracts."""\n    with prepare_sql_inputs(spec, base_dir=base_dir) as (execution_spec, sql_metadata):\n        result = run_reconciliation_with_governance(\n            execution_spec,\n            base_dir=base_dir,\n            spec_path=spec_path,\n            backend=backend,\n        )\n        return apply_sql_input_metadata(result, spec, sql_metadata)\n'''
new = '''    """Run a reconciliation after resolving local mapping artifacts and bounded SQL inputs."""\n    mapping_spec, mapping_metadata = resolve_mapping_artifacts(spec, base_dir)\n    with prepare_sql_inputs(mapping_spec, base_dir=base_dir) as (execution_spec, sql_metadata):\n        result = run_reconciliation_with_governance(\n            execution_spec,\n            base_dir=base_dir,\n            spec_path=spec_path,\n            backend=backend,\n        )\n        result = apply_sql_input_metadata(result, spec, sql_metadata)\n        return _apply_mapping_artifact_metadata(result, mapping_metadata)\n'''
if old not in runtime:
    raise SystemExit("runtime body anchor not found")
runtime = runtime.replace(old, new, 1)
runtime_path.write_text(runtime, encoding="utf-8")


# ---- cli.py --------------------------------------------------------------
cli_path = Path("src/reconciliation_as_code/cli.py")
cli = cli_path.read_text(encoding="utf-8")
cli = cli.replace(
    "from .identity import validate_identity_spec\n",
    "from .identity import validate_identity_spec\nfrom .mapping_artifacts import resolve_mapping_artifacts\n",
    1,
)
old = '''        if args.command == "validate":\n            print(f"valid: {spec_path} version={spec.get('version', 1)}")\n            return 0\n'''
new = '''        if args.command == "validate":\n            resolve_mapping_artifacts(spec, spec_path.parent)\n            print(f"valid: {spec_path} version={spec.get('version', 1)}")\n            return 0\n'''
if old not in cli:
    raise SystemExit("CLI validate anchor not found")
cli = cli.replace(old, new, 1)
cli_path.write_text(cli, encoding="utf-8")


# ---- published and bundled reconciliation schema ------------------------
def update_schema(path: Path) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    props = schema["properties"]
    props["mapping_artifacts"] = {
        "type": "object",
        "additionalProperties": {"$ref": "#/$defs/mappingArtifact"},
    }
    defs = schema["$defs"]
    defs["mappingArtifact"] = {
        "type": "object",
        "required": ["file"],
        "properties": {
            "file": {"type": "string", "minLength": 1},
            "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
        "additionalProperties": False,
    }
    defs["mappingArtifactRef"] = {
        "type": "object",
        "required": ["artifact", "field"],
        "properties": {
            "artifact": {"type": "string", "minLength": 1},
            "field": {"type": "string", "minLength": 1},
        },
        "additionalProperties": False,
    }
    defs["check"]["properties"]["map_ref"] = {"$ref": "#/$defs/mappingArtifactRef"}
    path.write_text(json.dumps(schema, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


for schema_path in (
    Path("schema/reconciliation.schema.json"),
    Path("src/reconciliation_as_code/_schemas/reconciliation.schema.json"),
):
    update_schema(schema_path)
