from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .governance import run_reconciliation_with_governance
from .mapping_artifacts import resolve_mapping_artifacts
from .sql_adapter import apply_sql_input_metadata, prepare_sql_inputs



def _sha256_object(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _apply_mapping_artifact_metadata(
    result: dict[str, Any], metadata: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not metadata:
        return result
    for alias, record in sorted(metadata.items()):
        result.setdefault("inputs", {})[f"mapping:{alias}"] = record
    result["configuration_sha256"] = _sha256_object(
        {
            "resolved_configuration_sha256": result["configuration_sha256"],
            "mapping_artifacts": {alias: record["sha256"] for alias, record in sorted(metadata.items())},
        }
    )
    return result

def run_reconciliation_runtime(
    spec: dict[str, Any],
    *,
    base_dir: str | Path = ".",
    spec_path: str | Path | None = None,
    backend: str = "python",
) -> dict[str, Any]:
    """Run a reconciliation after resolving local mapping artifacts and bounded SQL inputs."""
    mapping_spec, mapping_metadata = resolve_mapping_artifacts(spec, base_dir)
    with prepare_sql_inputs(mapping_spec, base_dir=base_dir) as (execution_spec, sql_metadata):
        result = run_reconciliation_with_governance(
            execution_spec,
            base_dir=base_dir,
            spec_path=spec_path,
            backend=backend,
        )
        result = apply_sql_input_metadata(result, spec, sql_metadata)
        return _apply_mapping_artifact_metadata(result, mapping_metadata)
