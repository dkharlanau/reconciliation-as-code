from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from .pipeline import (
    load_pipeline_spec,
    run_pipeline,
    write_pipeline_html,
    write_pipeline_json,
    write_pipeline_markdown,
)


def add_pipeline_arguments(parser) -> None:
    parser.add_argument("spec", help="Path to multi-stage pipeline YAML.")
    parser.add_argument(
        "--engine",
        choices=["python", "duckdb"],
        default="python",
        help="Execution backend used for each selected stage transition.",
    )
    parser.add_argument("--from-stage", help="Start at this stage instead of the first stage.")
    parser.add_argument("--to-stage", help="Stop at this stage instead of the final stage.")
    parser.add_argument("--evidence", default="build/pipeline-evidence.json", help="Pipeline evidence JSON output path.")
    parser.add_argument("--report", default="build/pipeline-evidence.md", help="Markdown report output path.")
    parser.add_argument("--html", default="build/pipeline-evidence.html", help="Offline HTML stage report output path.")
    parser.add_argument(
        "--no-fail-on-diff",
        action="store_true",
        help="Return exit code 0 even when a selected transition or end-to-end control fails.",
    )


def run_pipeline_command(args: Namespace) -> int:
    spec_path = Path(args.spec).expanduser().resolve()
    spec = load_pipeline_spec(spec_path)
    result = run_pipeline(
        spec,
        base_dir=spec_path.parent,
        spec_path=spec_path,
        backend=args.engine,
        from_stage=args.from_stage,
        to_stage=args.to_stage,
    )
    write_pipeline_json(result, args.evidence)
    write_pipeline_markdown(result, args.report)
    write_pipeline_html(result, args.html)
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(
        f"pipeline={result['pipeline']} status={result['status']} run_id={result['run']['id']} "
        f"from={result['run']['from_stage']} to={result['run']['to_stage']} "
        f"evidence={args.evidence} report={args.report} html={args.html}"
    )
    if result["status"] == "failed" and not args.no_fail_on_diff:
        return 1
    return 0
