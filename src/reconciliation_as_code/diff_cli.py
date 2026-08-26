from __future__ import annotations

import json
from argparse import Namespace

from .evidence_diff import (
    compare_evidence_files,
    write_diff_html,
    write_diff_json,
    write_diff_markdown,
)


def add_diff_arguments(parser) -> None:
    parser.add_argument("baseline", help="Baseline evidence JSON from an earlier rehearsal/run.")
    parser.add_argument("current", help="Current evidence JSON to compare against the baseline.")
    parser.add_argument("--output", "-o", default="build/rehearsal-diff.json", help="Diff JSON output path.")
    parser.add_argument("--report", default="build/rehearsal-diff.md", help="Markdown report output path.")
    parser.add_argument("--html", default="build/rehearsal-diff.html", help="Offline HTML report output path.")
    parser.add_argument(
        "--no-fail-on-regression",
        action="store_true",
        help="Return exit code 0 even when new discrepancies or regressed checks are detected.",
    )


def run_diff_command(args: Namespace) -> int:
    result = compare_evidence_files(args.baseline, args.current)
    write_diff_json(result, args.output)
    write_diff_markdown(result, args.report)
    write_diff_html(result, args.html)
    print(json.dumps(result["summary"], ensure_ascii=False))
    print(
        f"reconciliation={result['reconciliation']} "
        f"baseline={result['baseline'].get('run_id')} current={result['current'].get('run_id')} "
        f"diff={args.output} report={args.report} html={args.html}"
    )
    if result["summary"]["regression"] and not args.no_fail_on_regression:
        return 1
    return 0
