from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "reconciliation_as_code" / "cli.py"
SCHEMA = ROOT / "src" / "reconciliation_as_code" / "schema.py"
WORKFLOW = ROOT / ".github" / "workflows" / "wire-diff-cli.yml"
SELF = Path(__file__).resolve()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} anchor, found {count}.")
    return text.replace(old, new, 1)


def patch_cli() -> None:
    text = CLI.read_text(encoding="utf-8")
    if "from .diff_cli import add_diff_arguments, run_diff_command" not in text:
        text = replace_once(
            text,
            "from .errors import ReconciliationError\n",
            "from .errors import ReconciliationError\nfrom .diff_cli import add_diff_arguments, run_diff_command\n",
            "CLI import",
        )
    if 'subparsers.add_parser("diff"' not in text:
        anchor = '    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")\n'
        insertion = (
            '    diff = subparsers.add_parser("diff", help="Compare two retained reconciliation evidence runs.")\n'
            '    add_diff_arguments(diff)\n'
            '\n'
            + anchor
        )
        text = replace_once(text, anchor, insertion, "CLI parser")
    text = text.replace(
        'schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Schema to export: spec or evidence.")',
        'schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Published schema to export.")',
    )
    if 'if args.command == "diff":' not in text:
        anchor = '    try:\n        if args.command == "schema":\n'
        insertion = (
            '    try:\n'
            '        if args.command == "diff":\n'
            '            return run_diff_command(args)\n'
            '\n'
            '        if args.command == "schema":\n'
        )
        text = replace_once(text, anchor, insertion, "CLI dispatch")
    CLI.write_text(text, encoding="utf-8")


def patch_schema() -> None:
    text = SCHEMA.read_text(encoding="utf-8")
    if '"diff": "evidence-diff.schema.json"' not in text:
        if '"evidence": "evidence.schema.json"' in text:
            text = text.replace(
                '"evidence": "evidence.schema.json"',
                '"evidence": "evidence.schema.json",\n    "diff": "evidence-diff.schema.json"',
                1,
            )
        elif "SCHEMA_FILES" in text:
            raise RuntimeError("SCHEMA_FILES layout changed; refusing an unsafe patch.")
        else:
            raise RuntimeError("Could not locate SCHEMA_FILES in schema.py.")
    SCHEMA.write_text(text, encoding="utf-8")


def main() -> None:
    patch_cli()
    patch_schema()
    if WORKFLOW.exists():
        WORKFLOW.unlink()
    if SELF.exists():
        SELF.unlink()


if __name__ == "__main__":
    main()
