from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .errors import ReconciliationError
from .governance import run_reconciliation_with_governance
from .hierarchy import validate_hierarchy_spec
from .profiling import generate_spec, inspect_dataset, render_generated_spec
from .report import prepare_evidence, write_bundle, write_json, write_markdown
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
        "--bundle",
        help="Create a self-contained evidence directory with JSON, Markdown, HTML, XLSX, CSV details and manifest.",
    )
    run.add_argument(
        "--no-fail-on-diff",
        action="store_true",
        help="Return exit code 0 even when reconciliation error checks fail.",
    )

    inspect = subparsers.add_parser("inspect", help="Profile a CSV/Excel file before authoring a control.")
    inspect.add_argument("file", help="Dataset to inspect.")
    inspect.add_argument("--sheet", help="Excel sheet name.")
    inspect.add_argument("--delimiter", default=",", help="CSV delimiter.")
    inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON profile.")

    init = subparsers.add_parser("init", help="Generate a conservative first reconciliation spec from two files.")
    init.add_argument("source", help="Source CSV/Excel file.")
    init.add_argument("target", help="Target CSV/Excel file.")
    init.add_argument("--output", "-o", default="reconciliation.yaml", help="Generated YAML path.")
    init.add_argument("--source-key", help="Explicit source business key column.")
    init.add_argument("--target-key", help="Explicit target business key column.")
    init.add_argument("--source-sheet", help="Source Excel sheet name.")
    init.add_argument("--target-sheet", help="Target Excel sheet name.")
    init.add_argument("--delimiter", default=",", help="CSV delimiter.")
    init.add_argument("--interactive", action="store_true", help="Prompt to select candidate keys when needed.")
    init.add_argument("--force", action="store_true", help="Overwrite the output file if it exists.")

    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")
    schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Schema to export: spec or evidence.")
    schema.add_argument("--output", "-o", default="-", help="Output file, or '-' for stdout.")
    return parser


def _print_profile(profile: dict) -> None:
    print(f"file={profile['file']} rows={profile['rows']} format={profile['format']}")
    print("column\ttype\tnulls\tnull_rate\tdistinct\tuniqueness")
    for item in profile["columns"]:
        print(
            f"{item['name']}\t{item['type']}\t{item['null_count']}\t{item['null_rate']:.3f}\t"
            f"{item['distinct_count']}\t{item['uniqueness']:.3f}"
        )
    candidates = profile["candidate_keys"]
    if candidates:
        print("candidate_keys=" + ",".join(item["field"] for item in candidates))
    else:
        print("candidate_keys=none")


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

        if args.command == "inspect":
            profile = inspect_dataset(args.file, sheet=args.sheet, delimiter=args.delimiter)
            if args.json:
                print(json.dumps(profile, indent=2, ensure_ascii=False))
            else:
                _print_profile(profile)
            return 0

        if args.command == "init":
            output = Path(args.output).expanduser().resolve()
            if output.exists() and not args.force:
                raise ReconciliationError(f"Output already exists: {output}. Use --force to overwrite it.")
            spec, todos, source_profile, target_profile = generate_spec(
                args.source,
                args.target,
                source_key=args.source_key,
                target_key=args.target_key,
                interactive=args.interactive,
                source_sheet=args.source_sheet,
                target_sheet=args.target_sheet,
                delimiter=args.delimiter,
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            spec["source"]["file"] = os.path.relpath(Path(args.source).expanduser().resolve(), output.parent)
            spec["target"]["file"] = os.path.relpath(Path(args.target).expanduser().resolve(), output.parent)
            output.write_text(render_generated_spec(spec, todos), encoding="utf-8")
            print(
                f"created={output} source_key={spec['source']['key']} target_key={spec['target']['key']} "
                f"checks={len(spec['checks'])} todos={len(todos)}"
            )
            print(
                f"profile: source_rows={source_profile['rows']} target_rows={target_profile['rows']} "
                f"source_columns={len(source_profile['columns'])} target_columns={len(target_profile['columns'])}"
            )
            if todos:
                print("Review TODO comments in the generated YAML before treating inferred mappings as complete.")
            return 0

        spec_path = Path(args.spec).resolve()
        spec = load_spec(spec_path)
        validate_hierarchy_spec(spec)
        if args.command == "validate":
            print(f"valid: {spec_path} version={spec.get('version', 1)}")
            return 0

        raw_result = run_reconciliation_with_governance(spec, base_dir=spec_path.parent, spec_path=spec_path)
        result = prepare_evidence(raw_result, spec)
        write_json(result, args.evidence)
        write_markdown(result, args.report)
        if args.bundle:
            manifest = write_bundle(result, args.bundle)
            print(f"bundle={Path(args.bundle).resolve()} files={len(manifest['files'])}")
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
