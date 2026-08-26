from __future__ import annotations

import copy
import hashlib
import html
import json
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .errors import DataError, SpecError
from .governance import run_reconciliation_with_governance
from .identity import validate_identity_spec
from .sql_adapter import extract_sql_to_csv
from .spec import validate_spec

PIPELINE_SPEC_VERSION = 1
PIPELINE_EVIDENCE_SCHEMA_VERSION = "1.0"


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256_object(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pipeline_spec(path: str | Path) -> dict[str, Any]:
    resolved = Path(path).expanduser().resolve()
    try:
        payload = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SpecError(f"Pipeline specification not found: {resolved}") from exc
    except yaml.YAMLError as exc:
        raise SpecError(f"Invalid YAML in pipeline specification {resolved}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SpecError("Pipeline specification root must be an object.")
    validate_pipeline_spec(payload)
    return payload


def _stage_map(spec: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {stage["id"]: stage for stage in spec["stages"]}


def _comparison_payload(
    pipeline_spec: dict[str, Any],
    transition: dict[str, Any],
    source_endpoint: dict[str, Any],
    target_endpoint: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": 1,
        "reconciliation": {
            "name": f"{pipeline_spec['pipeline']['name']} / {transition['id']}",
            "description": transition.get("description"),
        },
        "source": copy.deepcopy(source_endpoint),
        "target": copy.deepcopy(target_endpoint),
        "checks": copy.deepcopy(transition["checks"]),
    }
    for name in ("scopes", "identity", "children", "exceptions", "materiality"):
        if transition.get(name) is not None:
            payload[name] = copy.deepcopy(transition[name])
    if pipeline_spec.get("evidence") is not None:
        payload["evidence"] = copy.deepcopy(pipeline_spec["evidence"])
    return payload


def _validate_transition(
    pipeline_spec: dict[str, Any], transition: dict[str, Any], stages: dict[str, dict[str, Any]]
) -> None:
    for field in ("id", "from", "to"):
        if not isinstance(transition.get(field), str) or not transition[field]:
            raise SpecError(f"Pipeline transition requires non-empty {field}.")
    if transition["from"] not in stages or transition["to"] not in stages:
        raise SpecError(
            f"Transition {transition['id']!r} references unknown stages "
            f"{transition['from']!r} -> {transition['to']!r}."
        )
    checks = transition.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SpecError(f"Transition {transition['id']!r}.checks must be a non-empty list.")
    mini = _comparison_payload(
        pipeline_spec,
        transition,
        stages[transition["from"]]["endpoint"],
        stages[transition["to"]]["endpoint"],
    )
    validate_spec(mini)
    validate_identity_spec(mini)


def validate_pipeline_spec(spec: dict[str, Any]) -> None:
    if spec.get("version", 1) != PIPELINE_SPEC_VERSION:
        raise SpecError(
            f"Unsupported pipeline specification version: {spec.get('version')!r}. "
            f"Expected {PIPELINE_SPEC_VERSION}."
        )
    pipeline = spec.get("pipeline")
    if not isinstance(pipeline, dict) or not isinstance(pipeline.get("name"), str) or not pipeline["name"]:
        raise SpecError("pipeline.name is required.")
    stages = spec.get("stages")
    if not isinstance(stages, list) or len(stages) < 2:
        raise SpecError("stages must contain at least two ordered stages.")
    ids: list[str] = []
    for index, stage in enumerate(stages, start=1):
        if not isinstance(stage, dict):
            raise SpecError(f"stages[{index}] must be an object.")
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or not stage_id:
            raise SpecError(f"stages[{index}].id must be a non-empty string.")
        if stage_id in ids:
            raise SpecError(f"Duplicate pipeline stage id: {stage_id}")
        ids.append(stage_id)
        endpoint = stage.get("endpoint")
        if not isinstance(endpoint, dict):
            raise SpecError(f"Stage {stage_id!r}.endpoint must be an object.")
        # Validate endpoints by composing a minimal same-endpoint reconciliation.
        probe = {
            "version": 1,
            "reconciliation": {"name": f"pipeline-stage-probe-{stage_id}"},
            "source": copy.deepcopy(endpoint),
            "target": copy.deepcopy(endpoint),
            "checks": [{"id": "probe", "type": "record_coverage"}],
        }
        validate_spec(probe)

    stage_lookup = _stage_map(spec)
    transitions = spec.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        raise SpecError("transitions must be a non-empty list.")
    transition_ids: set[str] = set()
    pair_to_transition: dict[tuple[str, str], str] = {}
    for transition in transitions:
        if not isinstance(transition, dict):
            raise SpecError("Each transition must be an object.")
        _validate_transition(spec, transition, stage_lookup)
        if transition["id"] in transition_ids:
            raise SpecError(f"Duplicate transition id: {transition['id']}")
        transition_ids.add(transition["id"])
        pair = (transition["from"], transition["to"])
        if pair in pair_to_transition:
            raise SpecError(
                f"Multiple transitions declared for {pair[0]!r} -> {pair[1]!r}."
            )
        pair_to_transition[pair] = transition["id"]

    for left, right in zip(ids, ids[1:]):
        if (left, right) not in pair_to_transition:
            raise SpecError(
                f"Missing adjacent transition for ordered stages {left!r} -> {right!r}."
            )

    end_to_end = spec.get("end_to_end")
    if end_to_end is not None:
        if not isinstance(end_to_end, dict):
            raise SpecError("end_to_end must be an object.")
        end_transition = {
            **copy.deepcopy(end_to_end),
            "id": end_to_end.get("id", "end-to-end"),
            "from": ids[0],
            "to": ids[-1],
        }
        _validate_transition(spec, end_transition, stage_lookup)

    evidence = spec.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        raise SpecError("evidence must be an object when supplied.")


def _stage_endpoint_path(endpoint: dict[str, Any], base_dir: Path) -> Path | None:
    filename = endpoint.get("file")
    if not filename:
        return None
    path = Path(filename).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _snapshot_stages(
    spec: dict[str, Any], base_dir: Path, temporary_root: Path
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    execution: dict[str, dict[str, Any]] = {}
    metadata: dict[str, dict[str, Any]] = {}
    for stage in spec["stages"]:
        stage_id = stage["id"]
        endpoint = copy.deepcopy(stage["endpoint"])
        if endpoint.get("sql") is not None:
            output = temporary_root / f"stage-{stage_id}.csv"
            info = extract_sql_to_csv(endpoint["sql"], output, label=f"stages.{stage_id}.sql")
            endpoint.pop("sql", None)
            endpoint["file"] = str(output)
            endpoint["format"] = "csv"
            endpoint["delimiter"] = ","
            metadata[stage_id] = {
                **info,
                "stage_id": stage_id,
                "label": stage.get("label"),
            }
        else:
            path = _stage_endpoint_path(endpoint, base_dir)
            if path is None or not path.exists():
                raise DataError(f"Pipeline stage {stage_id!r} input file not found: {path}")
            metadata[stage_id] = {
                "stage_id": stage_id,
                "label": stage.get("label"),
                "input_type": "file",
                "path": endpoint["file"],
                "sha256": _sha256_file(path),
                "format": endpoint.get("format") or path.suffix.lower().lstrip("."),
            }
        execution[stage_id] = endpoint
    return execution, metadata


def _selected_stage_range(
    spec: dict[str, Any], from_stage: str | None, to_stage: str | None
) -> tuple[list[str], int, int]:
    ids = [stage["id"] for stage in spec["stages"]]
    start = ids.index(from_stage) if from_stage is not None else 0
    end = ids.index(to_stage) if to_stage is not None else len(ids) - 1
    if start >= end:
        raise DataError("Pipeline stage subset must contain at least one forward transition.")
    return ids[start : end + 1], start, end


def _transition_for_pair(spec: dict[str, Any], source_id: str, target_id: str) -> dict[str, Any]:
    for transition in spec["transitions"]:
        if transition["from"] == source_id and transition["to"] == target_id:
            return transition
    raise DataError(f"No transition configured for {source_id!r} -> {target_id!r}.")


def _locator(detail: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in ("object_path", "key", "group", "difference"):
        if name in detail:
            result[name] = detail[name]
    return result


def _divergence_signals(transition_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for transition_index, transition in enumerate(transition_results):
        evidence = transition["evidence"]
        for check in evidence.get("checks", []):
            details = [
                item
                for item in (check.get("details") or [])
                if isinstance(item, dict) and item.get("disposition") != "accepted-exception"
            ]
            if not details and check.get("status") != "failed":
                continue
            if not details:
                details = [{"check_level": True}]
            for detail in details:
                locator = _locator(detail)
                if not locator and detail.get("check_level"):
                    locator = {"check_level": True}
                identity_payload = {
                    "check_id": check.get("id"),
                    "check_type": check.get("type"),
                    "locator": locator,
                }
                identity = _sha256_object(identity_payload)
                if identity in seen:
                    continue
                seen.add(identity)
                output.append(
                    {
                        "identity": identity,
                        "check_id": check.get("id"),
                        "check_type": check.get("type"),
                        "severity": check.get("severity"),
                        "locator": locator,
                        "first_transition": transition["id"],
                        "from_stage": transition["from"],
                        "to_stage": transition["to"],
                        "transition_index": transition_index,
                        "detail": detail,
                    }
                )
    return output


def _safe_transition_result(
    transition: dict[str, Any],
    result: dict[str, Any],
    source_meta: dict[str, Any],
    target_meta: dict[str, Any],
    original_config_sha256: str,
) -> dict[str, Any]:
    copied = copy.deepcopy(result)
    copied["inputs"]["source"] = copy.deepcopy(source_meta)
    copied["inputs"]["target"] = copy.deepcopy(target_meta)
    copied["configuration_sha256"] = original_config_sha256
    return {
        "id": transition["id"],
        "from": transition["from"],
        "to": transition["to"],
        "status": copied["status"],
        "run_id": (copied.get("run") or {}).get("id"),
        "duration_ms": (copied.get("run") or {}).get("duration_ms"),
        "summary": copied.get("summary") or {},
        "checks": [
            {
                "id": item.get("id"),
                "type": item.get("type"),
                "severity": item.get("severity"),
                "status": item.get("status"),
                "metrics": item.get("metrics") or {},
            }
            for item in copied.get("checks", [])
        ],
        "evidence": copied,
    }


def run_pipeline(
    spec: dict[str, Any],
    *,
    base_dir: str | Path = ".",
    spec_path: str | Path | None = None,
    backend: str = "python",
    from_stage: str | None = None,
    to_stage: str | None = None,
) -> dict[str, Any]:
    validate_pipeline_spec(spec)
    base = Path(base_dir).resolve()
    started = datetime.now(timezone.utc)
    timer = time.perf_counter()
    selected_ids, start_index, end_index = _selected_stage_range(spec, from_stage, to_stage)
    full_ids = [stage["id"] for stage in spec["stages"]]
    pipeline_config_hash = _sha256_object(spec)

    with tempfile.TemporaryDirectory(prefix="rac-pipeline-") as tmp:
        stage_endpoints, stage_metadata = _snapshot_stages(spec, base, Path(tmp))
        transition_results: list[dict[str, Any]] = []
        for source_id, target_id in zip(selected_ids, selected_ids[1:]):
            transition = _transition_for_pair(spec, source_id, target_id)
            execution_spec = _comparison_payload(
                spec,
                transition,
                stage_endpoints[source_id],
                stage_endpoints[target_id],
            )
            original_spec = _comparison_payload(
                spec,
                transition,
                _stage_map(spec)[source_id]["endpoint"],
                _stage_map(spec)[target_id]["endpoint"],
            )
            result = run_reconciliation_with_governance(
                execution_spec,
                base_dir=base,
                spec_path=spec_path,
                backend=backend,
            )
            transition_results.append(
                _safe_transition_result(
                    transition,
                    result,
                    stage_metadata[source_id],
                    stage_metadata[target_id],
                    _sha256_object(original_spec),
                )
            )

        end_to_end_result: dict[str, Any] | None = None
        is_full_range = start_index == 0 and end_index == len(full_ids) - 1
        if is_full_range and spec.get("end_to_end") is not None:
            config = {
                **copy.deepcopy(spec["end_to_end"]),
                "id": spec["end_to_end"].get("id", "end-to-end"),
                "from": full_ids[0],
                "to": full_ids[-1],
            }
            execution_spec = _comparison_payload(
                spec,
                config,
                stage_endpoints[full_ids[0]],
                stage_endpoints[full_ids[-1]],
            )
            original_spec = _comparison_payload(
                spec,
                config,
                _stage_map(spec)[full_ids[0]]["endpoint"],
                _stage_map(spec)[full_ids[-1]]["endpoint"],
            )
            result = run_reconciliation_with_governance(
                execution_spec,
                base_dir=base,
                spec_path=spec_path,
                backend=backend,
            )
            end_to_end_result = _safe_transition_result(
                config,
                result,
                stage_metadata[full_ids[0]],
                stage_metadata[full_ids[-1]],
                _sha256_object(original_spec),
            )

        first_divergence = _divergence_signals(transition_results)
        failed_transitions = [item for item in transition_results if item["status"] == "failed"]
        stage_status: list[dict[str, Any]] = []
        for index, stage_id in enumerate(selected_ids):
            incoming = transition_results[index - 1] if index > 0 else None
            stage_status.append(
                {
                    **copy.deepcopy(stage_metadata[stage_id]),
                    "status": "baseline" if incoming is None else incoming["status"],
                    "incoming_transition": incoming["id"] if incoming else None,
                }
            )

        final_failed = bool(failed_transitions) or bool(
            end_to_end_result and end_to_end_result["status"] == "failed"
        )
        finished = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "schema_version": PIPELINE_EVIDENCE_SCHEMA_VERSION,
            "spec_version": int(spec.get("version", 1)),
            "pipeline": spec["pipeline"]["name"],
            "description": spec["pipeline"].get("description"),
            "status": "failed" if final_failed else "passed",
            "configuration_sha256": pipeline_config_hash,
            "run": {
                "id": str(uuid.uuid4()),
                "started_at": started.isoformat(),
                "finished_at": finished.isoformat(),
                "duration_ms": round((time.perf_counter() - timer) * 1000, 3),
                "backend": backend,
                "from_stage": selected_ids[0],
                "to_stage": selected_ids[-1],
            },
            "stages": stage_status,
            "transitions": transition_results,
            "first_divergence": first_divergence,
            "summary": {
                "stages_total": len(selected_ids),
                "transitions_total": len(transition_results),
                "transitions_failed": len(failed_transitions),
                "transitions_passed": len(transition_results) - len(failed_transitions),
                "first_divergences": len(first_divergence),
                "end_to_end_executed": end_to_end_result is not None,
                "end_to_end_status": end_to_end_result["status"] if end_to_end_result else None,
            },
        }
        if end_to_end_result is not None:
            result["end_to_end"] = end_to_end_result
        if spec_path:
            resolved = Path(spec_path).resolve()
            if resolved.exists():
                result["specification"] = {
                    "path": resolved.name,
                    "sha256": _sha256_file(resolved),
                }
        return result


def write_pipeline_json(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def render_pipeline_markdown(result: dict[str, Any]) -> str:
    summary = result["summary"]
    lines = [
        f"# Migration pipeline reconciliation: {result['pipeline']}",
        "",
        f"**Status:** `{result['status'].upper()}`  ",
        f"**Run ID:** `{result['run']['id']}`  ",
        f"**Stage range:** `{result['run']['from_stage']}` → `{result['run']['to_stage']}`",
        "",
        "## Stage path",
        "",
        "| Stage | Incoming transition | Status | Input | SHA-256 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for stage in result["stages"]:
        lines.append(
            f"| `{stage['stage_id']}` | {stage.get('incoming_transition') or '—'} | "
            f"**{stage['status']}** | `{stage.get('path')}` | `{stage.get('sha256')}` |"
        )
    lines.extend(
        [
            "",
            "## Transition status",
            "",
            "| Transition | From | To | Status | Failed checks |",
            "| --- | --- | --- | --- | ---: |",
        ]
    )
    for transition in result["transitions"]:
        lines.append(
            f"| `{transition['id']}` | `{transition['from']}` | `{transition['to']}` | "
            f"**{transition['status']}** | {transition['summary'].get('checks_failed', 0)} |"
        )
    lines.extend(["", "## First divergence", ""])
    if not result["first_divergence"]:
        lines.append("No observed divergence in the selected stage range.")
    else:
        for item in result["first_divergence"]:
            lines.append(
                f"- `{item['check_id']}` — first observed at **{item['from_stage']} → {item['to_stage']}** "
                f"— `{json.dumps(item['locator'], ensure_ascii=False, sort_keys=True)}`"
            )
    if result.get("end_to_end"):
        lines.extend(
            [
                "",
                "## End-to-end",
                "",
                f"**Status:** `{result['end_to_end']['status'].upper()}`",
                "",
            ]
        )
    lines.extend(["", "## Summary", "", "```json"])
    lines.append(json.dumps(summary, indent=2, ensure_ascii=False))
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_pipeline_markdown(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_pipeline_markdown(result), encoding="utf-8")


def render_pipeline_html(result: dict[str, Any]) -> str:
    stage_cards = []
    for stage in result["stages"]:
        stage_cards.append(
            f"<div class='stage'><strong>{html.escape(stage['stage_id'])}</strong>"
            f"<span class='{html.escape(stage['status'])}'>{html.escape(stage['status'])}</span>"
            f"<small>{html.escape(str(stage.get('path') or ''))}</small></div>"
        )
    transition_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['id'])}</td><td>{html.escape(item['from'])}</td>"
        f"<td>{html.escape(item['to'])}</td><td>{html.escape(item['status'])}</td>"
        f"<td>{item['summary'].get('checks_failed', 0)}</td></tr>"
        for item in result["transitions"]
    )
    divergence_rows = "".join(
        "<tr>"
        f"<td>{html.escape(str(item.get('check_id')))}</td>"
        f"<td>{html.escape(item['from_stage'])} → {html.escape(item['to_stage'])}</td>"
        f"<td><code>{html.escape(json.dumps(item['locator'], ensure_ascii=False, sort_keys=True))}</code></td>"
        "</tr>"
        for item in result["first_divergence"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pipeline reconciliation — {html.escape(result['pipeline'])}</title>
<style>body{{font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:1180px;margin:40px auto;padding:0 24px;color:#111}}.path{{display:flex;gap:10px;align-items:stretch;overflow-x:auto}}.stage{{border:1px solid #bbb;border-radius:8px;padding:12px;min-width:170px;display:flex;flex-direction:column;gap:6px}}.stage span{{font-weight:700}}.failed{{color:#9b1c1c}}.passed{{color:#176b2c}}.baseline{{color:#555}}table{{border-collapse:collapse;width:100%;margin:16px 0 28px}}th,td{{border:1px solid #ccc;padding:7px 9px;text-align:left}}</style>
</head><body><h1>Migration pipeline reconciliation</h1><h2>{html.escape(result['pipeline'])}</h2>
<p><strong>Status:</strong> {html.escape(result['status'].upper())}</p>
<h2>Stage path</h2><div class="path">{''.join(stage_cards)}</div>
<h2>Transitions</h2><table><thead><tr><th>Transition</th><th>From</th><th>To</th><th>Status</th><th>Failed checks</th></tr></thead><tbody>{transition_rows}</tbody></table>
<h2>First divergence</h2><table><thead><tr><th>Check</th><th>First transition</th><th>Business locator</th></tr></thead><tbody>{divergence_rows}</tbody></table>
</body></html>"""


def write_pipeline_html(result: dict[str, Any], path: str | Path) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_pipeline_html(result), encoding="utf-8")
