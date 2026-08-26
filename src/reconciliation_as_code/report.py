from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        f"# Reconciliation evidence: {result['reconciliation']}",
        "",
        f"**Status:** `{result['status'].upper()}`  ",
        f"**Generated:** {result['generated_at']}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Source records | {summary['source_records']} |",
        f"| Target records | {summary['target_records']} |",
        f"| Matched records | {summary['matched_records']} |",
        f"| Missing in target | {summary['missing_in_target']} |",
        f"| Unexpected in target | {summary['unexpected_in_target']} |",
        f"| Failed error checks | {summary['checks_failed']} |",
        f"| Failed warning checks | {summary['warnings_failed']} |",
        "",
        "## Checks",
        "",
        "| Check | Type | Severity | Status |",
        "| --- | --- | --- | --- |",
    ]
    for check in result["checks"]:
        lines.append(
            f"| `{check['id']}` | {check['type']} | {check['severity']} | **{check['status']}** |"
        )

    for check in result["checks"]:
        if check["status"] == "passed" and not check["details"]:
            continue
        lines.extend(["", f"### {check['id']}", "", "Metrics:", "", "```json"])
        lines.append(json.dumps(check["metrics"], indent=2, ensure_ascii=False))
        lines.append("```")
        if check["details"]:
            lines.extend(["", "Evidence sample:", "", "```json"])
            lines.append(json.dumps(check["details"], indent=2, ensure_ascii=False))
            lines.append("```")
            if check.get("details_truncated"):
                lines.append("\n_Detail output was truncated by `evidence.detail_limit`._")

    lines.extend(["", "## Input fingerprints", ""])
    for name, info in result.get("inputs", {}).items():
        lines.append(f"- **{name}** — `{info['sha256']}` — `{info['path']}`")
    lines.append("")
    return "\n".join(lines)


def write_markdown(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(result), encoding="utf-8")
