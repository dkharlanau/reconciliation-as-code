from __future__ import annotations

from pathlib import Path
from typing import Any

from .governance import run_reconciliation_with_governance
from .sql_adapter import apply_sql_input_metadata, prepare_sql_inputs


def run_reconciliation_runtime(
    spec: dict[str, Any],
    *,
    base_dir: str | Path = ".",
    spec_path: str | Path | None = None,
    backend: str = "python",
) -> dict[str, Any]:
    """Run a reconciliation after resolving credential-free SQL endpoints to bounded local extracts."""
    with prepare_sql_inputs(spec, base_dir=base_dir) as (execution_spec, sql_metadata):
        result = run_reconciliation_with_governance(
            execution_spec,
            base_dir=base_dir,
            spec_path=spec_path,
            backend=backend,
        )
        return apply_sql_input_metadata(result, spec, sql_metadata)
