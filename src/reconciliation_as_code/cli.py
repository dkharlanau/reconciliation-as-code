from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .errors import ReconciliationError
from .pipeline_cli import add_pipeline_arguments, run_pipeline_command
from .diff_cli import add_diff_arguments, run_diff_command
from .identity import validate_identity_spec
from .mapping_artifacts import resolve_mapping_artifacts
from .profiling import generate_spec, inspect_dataset, render_generated_spec
from .report import prepare_evidence, write_bundle, write_json, write_markdown
from .runtime import run_reconciliation_runtime
from .schema import SCHEMA_FILES, schema_text
from .spec import load_spec


def _add_pair_authoring_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("source", help="Source CSV/Excel file.")
    parser.add_argument("target", help="Target CSV/Excel file.")
    parser.add_argument("--source-key", help="Explicit source business key column.")
    parser.add_argument("--target-key", help="Explicit target business key column.")
    parser.add_argument("--source-sheet", help="Source Excel sheet name.")
    parser.add_argument("--target-sheet", help="Target Excel sheet name.")
    parser.add_argument("--delimiter", default=",", help="CSV delimiter.")
    parser.add_argument("--interactive", action="store_true", help="Prompt to select candidate keys when needed.")
    parser.add_argument("--force", action="store_true", help="Overwrite generated preflight/spec artifacts if they already exist.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rac", description="Run versioned data reconciliations from YAML specifications.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate", help="Validate a reconciliation specification.")
    validate.add_argument("spec", help="Path to reconciliation YAML.")
    run = subparsers.add_parser("run", help="Run a reconciliation.")
    run.add_argument("spec", help="Path to reconciliation YAML.")
    run.add_argument(
        "--engine",
        choices=["python", "duckdb"],
        default="python",
        help="Execution backend. DuckDB scales flat CSV/Parquet and extracted SQL reconciliations without materializing all rows in Python.",
    )
    run.add_argument("--evidence", default="build/evidence.json", help="Evidence JSON output path.")
    run.add_argument("--report", default="build/evidence.md", help="Markdown report output path.")
    run.add_argument("--bundle", help="Create a self-contained evidence directory with JSON, Markdown, HTML, XLSX, CSV details and manifest.")
    run.add_argument("--no-fail-on-diff", action="store_true", help="Return exit code 0 even when reconciliation error checks fail.")
    inspect = subparsers.add_parser("inspect", help="Profile a CSV/Excel file before authoring a control.")
    inspect.add_argument("file", help="Dataset to inspect.")
    inspect.add_argument("--sheet", help="Excel sheet name.")
    inspect.add_argument("--delimiter", default=",", help="CSV delimiter.")
    inspect.add_argument("--json", action="store_true", help="Print machine-readable JSON profile.")
    init = subparsers.add_parser("init", help="Generate a conservative first reconciliation spec from two files.")
    _add_pair_authoring_arguments(init)
    init.add_argument("--output", "-o", default="reconciliation.yaml", help="Generated YAML path.")
    preflight = subparsers.add_parser(
        "preflight",
        help="Generate a conservative first spec from two files and run it only when no mapping review is still required.",
    )
    _add_pair_authoring_arguments(preflight)
    preflight.add_argument(
        "--output-dir",
        default="build/preflight",
        help="Directory for generated reconciliation.yaml, evidence.json and evidence.md.",
    )
    preflight.add_argument(
        "--engine",
        choices=["python", "duckdb"],
        default="python",
        help="Execution backend used after the generated spec is review-complete.",
    )
    preflight.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="Return exit code 1 when the executed preflight finds reconciliation differences. Default preflight mode reports differences without failing.",
    )
    pipeline = subparsers.add_parser("pipeline", help="Run reconciliation across an ordered migration pipeline.")
    add_pipeline_arguments(pipeline)

    diff = subparsers.add_parser("diff", help="Compare two retained reconciliation evidence runs.")
    add_diff_arguments(diff)

    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")
    schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Published schema to export.")
    schema.add_argument("--output", "-o", default="-", help="Output file, or '-' for stdout.")
    return parser


def _print_profile(profile: dict) -> None:
    print(f"file={profile['file']} rows={profile['rows']} format={profile['format']}")
    print("column\ttype\tnulls\tnull_rate\tdistinct\tuniqueness")
    for item in profile["columns"]:
        print(f"{item['name']}\t{item['type']}\t{item['null_count']}\t{item['null_rate']:.3f}\t{item['distinct_count']}\t{item['uniqueness']:.3f}")
    candidates = profile["candidate_keys"]
    print("candidate_keys=" + (",".join(item["field"] for item in candidates) if candidates else "none"))


def _generate_spec_file(args: argparse.Namespace, output: Path) -> tuple[dict, list[str], dict, dict]:
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
    return spec, todos, source_profile, target_profile


def _run_generated_preflight(args: argparse.Namespace, spec_path: Path) -> int:
    output_dir = spec_path.parent
    evidence_path = output_dir / "evidence.json"
    report_path = output_dir / "evidence.md"
    if not args.force:
        existing = [path for path in (evidence_path, report_path) if path.exists()]
        if existing:
            joined = ", ".join(str(path) for path in existing)
            raise ReconciliationError(f"Preflight output already exists: {joined}. Use --force to overwrite it.")

    spec = load_spec(spec_path)
    validate_identity_spec(spec)
    resolve_mapping_artifacts(spec, spec_path.parent)
    raw_result = run_reconciliation_runtime(
        spec,
        base_dir=spec_path.parent,
        spec_path=spec_path,
        backend=args.engine,
    )
    result = prepare_evidence(raw_result, spec)
    write_json(result, evidence_path)
    write_markdown(result, report_path)
    print(json.dumps(result["summary"], ensure_ascii=False))
    backend = result.get("run", {}).get("backend", args.engine)
    print(
        f"status={result['status']} mode=preflight run_id={result['run']['id']} backend={backend} "
        f"spec={spec_path} evidence={evidence_path} report={report_path}"
    )
    if result["status"] == "failed" and args.fail_on_diff:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "pipeline":
            return run_pipeline_command(args)

        if args.command == "diff":
            return run_diff_command(args)

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
            print(json.dumps(profile, indent=2, ensure_ascii=False) if args.json else "", end="" if args.json else "")
            if not args.json:
                _print_profile(profile)
            return 0
        if args.command in {"init", "preflight"}:
            if args.command == "init":
                output = Path(args.output).expanduser().resolve()
            else:
                output_dir = Path(args.output_dir).expanduser().resolve()
                output = output_dir / "reconciliation.yaml"

            spec, todos, source_profile, target_profile = _generate_spec_file(args, output)
            print(f"created={output} source_key={spec['source']['key']} target_key={spec['target']['key']} checks={len(spec['checks'])} todos={len(todos)}")
            print(f"profile: source_rows={source_profile['rows']} target_rows={target_profile['rows']} source_columns={len(source_profile['columns'])} target_columns={len(target_profile['columns'])}")
            if todos:
                print("Review TODO comments in the generated YAML before treating inferred mappings as complete.")
            if args.command == "init":
                return 0

            if todos:
                print(f"status=needs_review mode=preflight spec={output} todos={len(todos)}")
                print("Preflight did not execute because unresolved field mappings still require review.")
                return 0
            return _run_generated_preflight(args, output)

        spec_path = Path(args.spec).resolve()
        spec = load_spec(spec_path)
        validate_identity_spec(spec)
        if args.command == "validate":
            resolve_mapping_artifacts(spec, spec_path.parent)
            print(f"valid: {spec_path} version={spec.get('version', 1)}")
            return 0
        raw_result = run_reconciliation_runtime(
            spec,
            base_dir=spec_path.parent,
            spec_path=spec_path,
            backend=args.engine,
        )
        result = prepare_evidence(raw_result, spec)
        write_json(result, args.evidence)
        write_markdown(result, args.report)
        if args.bundle:
            manifest = write_bundle(result, args.bundle)
            print(f"bundle={Path(args.bundle).resolve()} files={len(manifest['files'])}")
        print(json.dumps(result["summary"], ensure_ascii=False))
        backend = result.get("run", {}).get("backend", args.engine)
        print(
            f"status={result['status']} run_id={result['run']['id']} backend={backend} "
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
