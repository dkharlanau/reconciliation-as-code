from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src" / "reconciliation_as_code" / "cli.py"
SCHEMA = ROOT / "src" / "reconciliation_as_code" / "schema.py"
SELF = Path(__file__).resolve()
WORKFLOW = ROOT / ".github" / "workflows" / "wire-pipeline-cli.yml"


def patch_cli(text: str) -> str:
    if "from .pipeline_cli import add_pipeline_arguments, run_pipeline_command" not in text:
        anchor = "from .errors import ReconciliationError\n"
        if anchor not in text:
            raise RuntimeError("CLI import anchor not found")
        text = text.replace(
            anchor,
            anchor + "from .pipeline_cli import add_pipeline_arguments, run_pipeline_command\n",
            1,
        )
    if 'subparsers.add_parser("pipeline"' not in text:
        anchors = [
            '    diff = subparsers.add_parser("diff", help="Compare two retained reconciliation evidence runs.")\n',
            '    schema = subparsers.add_parser("schema", help="Print or export a published JSON Schema.")\n',
        ]
        anchor = next((item for item in anchors if item in text), None)
        if anchor is None:
            raise RuntimeError("CLI parser anchor not found")
        insertion = (
            '    pipeline = subparsers.add_parser("pipeline", help="Run reconciliation across an ordered migration pipeline.")\n'
            '    add_pipeline_arguments(pipeline)\n\n'
        )
        text = text.replace(anchor, insertion + anchor, 1)
    if 'if args.command == "pipeline":' not in text:
        anchor = '    try:\n'
        if anchor not in text:
            raise RuntimeError("CLI dispatch anchor not found")
        text = text.replace(
            anchor,
            anchor
            + '        if args.command == "pipeline":\n'
            + '            return run_pipeline_command(args)\n\n',
            1,
        )
    return text


def patch_schema(text: str) -> str:
    additions = {
        '"pipeline": "pipeline.schema.json"': "pipeline.schema.json",
        '"pipeline-evidence": "pipeline-evidence.schema.json"': "pipeline-evidence.schema.json",
    }
    if all(key in text for key in additions):
        return text
    anchor_candidates = [
        '"diff": "evidence-diff.schema.json"',
        '"evidence": "evidence.schema.json"',
    ]
    anchor = next((item for item in anchor_candidates if item in text), None)
    if anchor is None:
        raise RuntimeError("schema registry anchor not found")
    suffix = ""
    if '"pipeline": "pipeline.schema.json"' not in text:
        suffix += ',\n    "pipeline": "pipeline.schema.json"'
    if '"pipeline-evidence": "pipeline-evidence.schema.json"' not in text:
        suffix += ',\n    "pipeline-evidence": "pipeline-evidence.schema.json"'
    return text.replace(anchor, anchor + suffix, 1)


def main() -> None:
    CLI.write_text(patch_cli(CLI.read_text(encoding="utf-8")), encoding="utf-8")
    SCHEMA.write_text(patch_schema(SCHEMA.read_text(encoding="utf-8")), encoding="utf-8")
    for path in (SELF, WORKFLOW):
        if path.exists():
            path.unlink()


if __name__ == "__main__":
    main()
