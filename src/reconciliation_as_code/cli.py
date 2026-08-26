from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .engine import run_reconciliation
from .errors import ReconciliationError
from .report import write_json, write_markdown
from .schema import SCHEMA_FILES, schema_text
from .spec import load_spec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rac",
        description="Run versioned data reconciliations from YAML specifications.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate a reconciliation specification.")
    validate.add_argument("spec", help="Path to reconciliation YAML.")

    run = subparsers.add_parser("run", help="Run a reconciliation.")
    run.add_argument("spec", help="Path to reconciliation YAML.")
    run.add_argument("--evidence", default="build/evidence.json", help="Evidence JSON output path.")
    run.add_argument("--report", default="build/evidence.md", help="Markdown report output path.")
    run.add_argument(
        "--no-fail-on-diff",
        action="store_true",
        help="Return exit code 0 even when reconciliation error checks fail.",
    )

    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")
    schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Schema to export: spec or evidence.")
    schema.add_argument("--output", "-o", default="-", help="Output file, or '-' for stdout.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "schema":
            content = schema_text(args.kind)
            if args.output == "-":
                print(content, end="" if content.endswith("\n") else "\n")
            else:
                output = Path(args.output)
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(content, encoding="utf-8")
                print(f"schema={args.kind} output={output}")
            return 0

        spec_path = Path(args.spec).resolve()
        spec = load_spec(spec_path)
        if args.command == "validate":
            print(f"valid: {spec_path} version={spec.get('version', 1)}")
            return 0

        result = run_reconciliation(spec, base_dir=spec_path.parent, spec_path=spec_path)
        write_json(result, args.evidence)
        write_markdown(result, args.report)
        print(json.dumps(result["summary"], ensure_ascii=False))
        print(
            f"status={result['status']} run_id={result['run']['id']} "
            f"evidence={args.evidence} report={args.report}"
        )
        if result["status"] == "failed" and not args.no_fail_on_diff:
            return 1
        return 0
    except ReconciliationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
