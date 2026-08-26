from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "reconciliation_as_code" / "cli.py"
SCHEMA = ROOT / "src" / "reconciliation_as_code" / "schema.py"
SELF = Path(__file__).resolve()
WORKFLOW = ROOT / ".github" / "workflows" / "wire-diff-cli-v2.yml"
OLD_SELF = ROOT / "scripts" / "wire_diff_cli.py"
OLD_WORKFLOW = ROOT / ".github" / "workflows" / "wire-diff-cli.yml"


def patch_cli(text: str) -> str:
    if "from .diff_cli import add_diff_arguments, run_diff_command" not in text:
        anchor = "from .errors import ReconciliationError\n"
        if anchor not in text:
            raise RuntimeError("CLI import anchor not found")
        text = text.replace(anchor, anchor + "from .diff_cli import add_diff_arguments, run_diff_command\n", 1)

    if 'subparsers.add_parser("diff"' not in text:
        anchor = '    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")\n'
        if anchor not in text:
            raise RuntimeError("CLI parser anchor not found")
        text = text.replace(
            anchor,
            '    diff = subparsers.add_parser("diff", help="Compare two retained reconciliation evidence runs.")\n'
            '    add_diff_arguments(diff)\n\n'
            + anchor,
            1,
        )

    text = text.replace(
        'schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Schema to export: spec or evidence.")',
        'schema.add_argument("kind", choices=sorted(SCHEMA_FILES), help="Published schema to export.")',
    )

    if 'if args.command == "diff":' not in text:
        anchor = '    try:\n        if args.command == "schema":\n'
        if anchor not in text:
            raise RuntimeError("CLI dispatch anchor not found")
        text = text.replace(
            anchor,
            '    try:\n'
            '        if args.command == "diff":\n'
            '            return run_diff_command(args)\n\n'
            '        if args.command == "schema":\n',
            1,
        )
    return text


def patch_schema(text: str) -> str:
    if '"diff": "evidence-diff.schema.json"' in text:
        return text
    anchor = '"evidence": "evidence.schema.json"'
    if anchor not in text:
        raise RuntimeError("schema registry anchor not found")
    return text.replace(anchor, anchor + ',\n    "diff": "evidence-diff.schema.json"', 1)


def main() -> None:
    CLI.write_text(patch_cli(CLI.read_text(encoding="utf-8")), encoding="utf-8")
    SCHEMA.write_text(patch_schema(SCHEMA.read_text(encoding="utf-8")), encoding="utf-8")
    for path in (SELF, WORKFLOW, OLD_SELF, OLD_WORKFLOW):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
