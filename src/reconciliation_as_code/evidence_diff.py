from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from .errors import DataError

DIFF_SCHEMA_VERSION = "1.0"
SUPPORTED_EVIDENCE_SCHEMA_MAJOR = 1


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256_object(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _load(path: str | Path) -> tuple[Path, dict[str, Any]]:
    resolved = Path(path).expanduser().resolve()
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DataError(f"Evidence file not found: {resolved}") from exc
    except json.JSONDecodeError as exc:
        raise DataError(f"Invalid JSON evidence in {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise DataError(f"Evidence root must be an object: {resolved}")
    return resolved, payload


def _schema_major(value: Any) -> int:
    try:
        return int(str(value).split(".", 1)[0])
    except (TypeError, ValueError) as exc:
        raise DataError(f"Invalid evidence schema_version: {value!r}") from exc


def validate_comparable_evidence(baseline: dict[str, Any], current: dict[str, Any]) -> None:
    for label, payload in (("baseline", baseline), ("current", current)):
        required = {"schema_version", "reconciliation", "run", "summary", "checks"}
        missing = required - set(payload)
        if missing:
            raise DataError(f"{label} evidence is missing required fields: {sorted(missing)}")
        major = _schema_major(payload.get("schema_version"))
        if major != SUPPORTED_EVIDENCE_SCHEMA_MAJOR:
            raise DataError(
                f"Unsupported {label} evidence schema major version {major}; "
                f"this diff engine supports major version {SUPPORTED_EVIDENCE_SCHEMA_MAJOR}."
            )
        if not isinstance(payload.get("checks"), list):
            raise DataError(f"{label}.checks must be a list.")
    if baseline["reconciliation"] != current["reconciliation"]:
        raise DataError(
            "Cannot diff evidence from different reconciliations: "
            f"{baseline['reconciliation']!r} vs {current['reconciliation']!r}."
        )


def _check_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        check_id = check.get("id")
        if isinstance(check_id, str) and check_id:
            result[check_id] = check
    return result


def _locator(detail: dict[str, Any]) -> dict[str, Any]:
    locator: dict[str, Any] = {}
    for name in ("object_path", "key", "group", "difference"):
        if name in detail:
            locator[name] = detail[name]
    if not locator:
        # Policy/governance details may be identified by their own stable fields.
        for name in ("index", "check", "field", "status", "reason_code"):
            if name in detail:
                locator[name] = detail[name]
    return locator


def _detail_identity(check: dict[str, Any], detail: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    identity = {
        "check_id": check.get("id"),
        "check_type": check.get("type"),
        "locator": _locator(detail),
    }
    return _sha256_object(identity), identity


def _semantic_detail(detail: dict[str, Any]) -> dict[str, Any]:
    # Exception metadata such as owner/reference/expiry is important when it changes,
    # but ephemeral presentation fields should not create false rehearsal churn.
    copied = dict(detail)
    copied.pop("sensitive_values_redacted", None)
    return copied


def _defects(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for check in payload.get("checks", []):
        if not isinstance(check, dict):
            continue
        for detail in check.get("details", []) or []:
            if not isinstance(detail, dict):
                continue
            identity_hash, identity = _detail_identity(check, detail)
            semantic = _semantic_detail(detail)
            item = {
                "identity": identity_hash,
                "check_id": check.get("id"),
                "check_type": check.get("type"),
                "severity": check.get("severity"),
                "check_status": check.get("status"),
                "locator": identity["locator"],
                "detail": semantic,
                "content_sha256": _sha256_object(semantic),
                "disposition": detail.get("disposition"),
            }
            # A duplicated identity is ambiguous evidence. Preserve both rather than silently overwrite.
            candidate = identity_hash
            sequence = 2
            while candidate in result:
                candidate = _sha256_object({"identity": identity_hash, "sequence": sequence})
                sequence += 1
            item["identity"] = candidate
            result[candidate] = item
    return result


def _metrics_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    keys = set(before) | set(after)
    for key in sorted(keys):
        left = before.get(key)
        right = after.get(key)
        if left == right:
            continue
        delta = None
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            delta = right - left
        result[key] = {"baseline": left, "current": right, "delta": delta}
    return result


def _check_transition(before: dict[str, Any] | None, after: dict[str, Any] | None) -> str:
    if before is None:
        return "added"
    if after is None:
        return "removed"
    left = before.get("status")
    right = after.get("status")
    if left == "passed" and right == "failed":
        return "regressed"
    if left == "failed" and right == "passed":
        return "improved"
    if left == right:
        return "unchanged"
    return "changed"


def _run_ref(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    run = payload.get("run") or {}
    return {
        "path": path.name,
        "run_id": run.get("id"),
        "generated_at": payload.get("generated_at") or run.get("finished_at"),
        "status": payload.get("status"),
        "schema_version": payload.get("schema_version"),
        "spec_version": payload.get("spec_version"),
        "engine_version": payload.get("engine_version"),
        "configuration_sha256": payload.get("configuration_sha256"),
        "summary": payload.get("summary") or {},
        "evidence_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def compare_evidence(
    baseline: dict[str, Any],
    current: dict[str, Any],
    *,
    baseline_path: str | Path | None = None,
    current_path: str | Path | None = None,
) -> dict[str, Any]:
    validate_comparable_evidence(baseline, current)
    baseline_checks = _check_map(baseline)
    current_checks = _check_map(current)
    all_check_ids = sorted(set(baseline_checks) | set(current_checks))

    check_changes: list[dict[str, Any]] = []
    for check_id in all_check_ids:
        before = baseline_checks.get(check_id)
        after = current_checks.get(check_id)
        check_changes.append(
            {
                "id": check_id,
                "type": (after or before or {}).get("type"),
                "baseline_status": before.get("status") if before else None,
                "current_status": after.get("status") if after else None,
                "baseline_severity": before.get("severity") if before else None,
                "current_severity": after.get("severity") if after else None,
                "transition": _check_transition(before, after),
                "metric_changes": _metrics_delta(
                    (before or {}).get("metrics") or {},
                    (after or {}).get("metrics") or {},
                ),
            }
        )

    before_defects = _defects(baseline)
    after_defects = _defects(current)
    before_ids = set(before_defects)
    after_ids = set(after_defects)
    shared = before_ids & after_ids

    new_items = [after_defects[key] for key in sorted(after_ids - before_ids)]
    resolved_items = [before_defects[key] for key in sorted(before_ids - after_ids)]
    persistent_items: list[dict[str, Any]] = []
    changed_items: list[dict[str, Any]] = []
    for key in sorted(shared):
        before = before_defects[key]
        after = after_defects[key]
        if before["content_sha256"] == after["content_sha256"] and before.get("check_status") == after.get("check_status"):
            persistent_items.append(after)
        else:
            changed_items.append(
                {
                    "identity": key,
                    "check_id": after.get("check_id") or before.get("check_id"),
                    "check_type": after.get("check_type") or before.get("check_type"),
                    "locator": after.get("locator") or before.get("locator"),
                    "baseline": before,
                    "current": after,
                }
            )

    transitions = {name: 0 for name in ("regressed", "improved", "unchanged", "changed", "added", "removed")}
    for item in check_changes:
        transitions[item["transition"]] = transitions.get(item["transition"], 0) + 1

    baseline_summary = baseline.get("summary") or {}
    current_summary = current.get("summary") or {}
    regression = bool(new_items or transitions.get("regressed"))
    improvement = bool(resolved_items or transitions.get("improved"))

    if baseline_path is None:
        baseline_path = Path("baseline-evidence.json")
    else:
        baseline_path = Path(baseline_path)
    if current_path is None:
        current_path = Path("current-evidence.json")
    else:
        current_path = Path(current_path)

    # When called from in-memory tests, evidence hashes are stable hashes of the payload.
    def ref(path: Path, payload: dict[str, Any]) -> dict[str, Any]:
        if path.exists():
            return _run_ref(path, payload)
        run = payload.get("run") or {}
        return {
            "path": path.name,
            "run_id": run.get("id"),
            "generated_at": payload.get("generated_at") or run.get("finished_at"),
            "status": payload.get("status"),
            "schema_version": payload.get("schema_version"),
            "spec_version": payload.get("spec_version"),
            "engine_version": payload.get("engine_version"),
            "configuration_sha256": payload.get("configuration_sha256"),
            "summary": payload.get("summary") or {},
            "evidence_sha256": _sha256_object(payload),
        }

    return {
        "schema_version": DIFF_SCHEMA_VERSION,
        "reconciliation": baseline["reconciliation"],
        "baseline": ref(baseline_path, baseline),
        "current": ref(current_path, current),
        "compatibility": {
            "evidence_schema_changed": baseline.get("schema_version") != current.get("schema_version"),
            "spec_version_changed": baseline.get("spec_version") != current.get("spec_version"),
            "engine_version_changed": baseline.get("engine_version") != current.get("engine_version"),
            "configuration_changed": baseline.get("configuration_sha256") != current.get("configuration_sha256"),
        },
        "summary": {
            "baseline_status": baseline.get("status"),
            "current_status": current.get("status"),
            "baseline_checks_failed": baseline_summary.get("checks_failed"),
            "current_checks_failed": current_summary.get("checks_failed"),
            "new_discrepancies": len(new_items),
            "resolved_discrepancies": len(resolved_items),
            "persistent_discrepancies": len(persistent_items),
            "changed_discrepancies": len(changed_items),
            "checks_regressed": transitions.get("regressed", 0),
            "checks_improved": transitions.get("improved", 0),
            "regression": regression,
            "improvement": improvement,
        },
        "check_transitions": check_changes,
        "discrepancies": {
            "new": new_items,
            "resolved": resolved_items,
            "persistent": persistent_items,
            "changed": changed_items,
        },
    }


def compare_evidence_files(baseline_path: str | Path, current_path: str | Path) -> dict[str, Any]:
    baseline_file, baseline = _load(baseline_path)
    current_file, current = _load(current_path)
    return compare_evidence(
        baseline,
        current,
        baseline_path=baseline_file,
        current_path=current_file,
    )


def write_diff_json(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_diff_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        f"# Reconciliation rehearsal diff: {result['reconciliation']}",
        "",
        f"**Baseline:** `{result['baseline'].get('run_id')}` — `{summary.get('baseline_status')}`  ",
        f"**Current:** `{result['current'].get('run_id')}` — `{summary.get('current_status')}`",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| New discrepancies | {summary['new_discrepancies']} |",
        f"| Resolved discrepancies | {summary['resolved_discrepancies']} |",
        f"| Persistent discrepancies | {summary['persistent_discrepancies']} |",
        f"| Changed discrepancies | {summary['changed_discrepancies']} |",
        f"| Checks regressed | {summary['checks_regressed']} |",
        f"| Checks improved | {summary['checks_improved']} |",
        "",
        "## Check transitions",
        "",
        "| Check | Type | Baseline | Current | Transition |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in result["check_transitions"]:
        lines.append(
            f"| `{item['id']}` | {item.get('type') or ''} | {item.get('baseline_status') or '—'} | "
            f"{item.get('current_status') or '—'} | **{item['transition']}** |"
        )

    for category in ("new", "resolved", "persistent", "changed"):
        items = result["discrepancies"][category]
        lines.extend(["", f"## {category.title()} discrepancies", ""])
        if not items:
            lines.append("None.")
            continue
        for item in items:
            locator = item.get("locator") or {}
            lines.append(
                f"- `{item.get('check_id')}` — `{json.dumps(locator, ensure_ascii=False, sort_keys=True)}`"
            )
            if category == "changed":
                before = (item.get("baseline") or {}).get("detail")
                after = (item.get("current") or {}).get("detail")
                lines.append(
                    f"  - before: `{json.dumps(before, ensure_ascii=False, sort_keys=True)}`"
                )
                lines.append(
                    f"  - after: `{json.dumps(after, ensure_ascii=False, sort_keys=True)}`"
                )
    lines.extend(["", "## Compatibility", "", "```json"])
    lines.append(json.dumps(result["compatibility"], indent=2, ensure_ascii=False))
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_diff_markdown(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_diff_markdown(result), encoding="utf-8")


def render_diff_html(result: dict[str, Any]) -> str:
    markdown_like = render_diff_markdown(result)
    summary = result["summary"]
    rows = "".join(
        f"<tr><td>{html.escape(label)}</td><td>{value}</td></tr>"
        for label, value in (
            ("New discrepancies", summary["new_discrepancies"]),
            ("Resolved discrepancies", summary["resolved_discrepancies"]),
            ("Persistent discrepancies", summary["persistent_discrepancies"]),
            ("Changed discrepancies", summary["changed_discrepancies"]),
            ("Checks regressed", summary["checks_regressed"]),
            ("Checks improved", summary["checks_improved"]),
        )
    )
    transitions = "".join(
        "<tr>"
        f"<td>{html.escape(str(item['id']))}</td>"
        f"<td>{html.escape(str(item.get('type') or ''))}</td>"
        f"<td>{html.escape(str(item.get('baseline_status') or '—'))}</td>"
        f"<td>{html.escape(str(item.get('current_status') or '—'))}</td>"
        f"<td>{html.escape(str(item['transition']))}</td>"
        "</tr>"
        for item in result["check_transitions"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rehearsal diff — {html.escape(result['reconciliation'])}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1180px;margin:40px auto;padding:0 24px;color:#111}}table{{border-collapse:collapse;width:100%;margin:16px 0 28px}}th,td{{border:1px solid #ccc;padding:7px 9px;text-align:left}}pre{{background:#f6f6f6;padding:14px;white-space:pre-wrap;border-radius:6px}}</style>
</head><body>
<h1>Reconciliation rehearsal diff</h1><h2>{html.escape(result['reconciliation'])}</h2>
<p>Baseline <code>{html.escape(str(result['baseline'].get('run_id')))}</code> → current <code>{html.escape(str(result['current'].get('run_id')))}</code></p>
<h2>Summary</h2><table><tbody>{rows}</tbody></table>
<h2>Check transitions</h2><table><thead><tr><th>Check</th><th>Type</th><th>Baseline</th><th>Current</th><th>Transition</th></tr></thead><tbody>{transitions}</tbody></table>
<h2>Full diff detail</h2><pre>{html.escape(markdown_like)}</pre>
</body></html>"""


def write_diff_html(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_diff_html(result), encoding="utf-8")
