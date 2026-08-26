from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.evidence_diff import (
    compare_evidence,
    compare_evidence_files,
    render_diff_html,
    render_diff_markdown,
    write_diff_html,
    write_diff_json,
    write_diff_markdown,
)


def detail_check(check_id: str, details: list[dict], *, status: str = "failed", severity: str = "error") -> dict:
    return {
        "id": check_id,
        "type": "field_match",
        "severity": severity,
        "status": status,
        "metrics": {
            "compared": 3,
            "mismatches": len(details),
            "max_mismatches": 0,
            "source_field": check_id.upper(),
            "target_field": check_id.upper(),
        },
        "details": details,
        "details_truncated": False,
    }


def evidence(run_id: str, checks: list[dict], *, status: str = "failed", config: str = "a" * 64) -> dict:
    failures = sum(1 for item in checks if item["severity"] == "error" and item["status"] == "failed")
    return {
        "schema_version": "1.0",
        "spec_version": 1,
        "engine_version": "0.1.0",
        "configuration_sha256": config,
        "run": {
            "id": run_id,
            "started_at": "2026-08-20T10:00:00+00:00",
            "finished_at": "2026-08-20T10:00:01+00:00",
            "duration_ms": 1000,
            "python_version": "3.12",
            "platform": "test",
        },
        "reconciliation": "Migration rehearsal",
        "status": status,
        "generated_at": "2026-08-20T10:00:01+00:00",
        "inputs": {
            "source": {"path": "source.csv", "sha256": "b" * 64},
            "target": {"path": "target.csv", "sha256": "c" * 64},
        },
        "summary": {
            "source_records": 3,
            "target_records": 3,
            "matched_records": 3,
            "missing_in_target": 0,
            "unexpected_in_target": 0,
            "checks_total": len(checks),
            "checks_failed": failures,
            "warnings_failed": 0,
        },
        "checks": checks,
    }


class EvidenceDiffTests(unittest.TestCase):
    def test_classifies_new_resolved_persistent_and_changed_discrepancies(self) -> None:
        baseline = evidence(
            "r1",
            [
                detail_check("name", [{"key": "1001", "source": "Acme", "target": "Acme GmbH"}]),
                detail_check("country", [{"key": "1002", "source": "DE", "target": "US"}]),
                detail_check("amount", [{"key": "1003", "source": "100", "target": "0"}]),
            ],
        )
        current = evidence(
            "r2",
            [
                detail_check("name", [], status="passed"),
                detail_check("country", [{"key": "1002", "source": "DE", "target": "US"}]),
                detail_check("amount", [{"key": "1003", "source": "100", "target": "80"}]),
                detail_check("tax", [{"key": "1004", "source": "A", "target": "B"}]),
            ],
            config="d" * 64,
        )

        result = compare_evidence(baseline, current)

        self.assertEqual(1, result["summary"]["new_discrepancies"])
        self.assertEqual(1, result["summary"]["resolved_discrepancies"])
        self.assertEqual(1, result["summary"]["persistent_discrepancies"])
        self.assertEqual(1, result["summary"]["changed_discrepancies"])
        self.assertTrue(result["summary"]["regression"])
        self.assertTrue(result["summary"]["improvement"])
        self.assertTrue(result["compatibility"]["configuration_changed"])

        resolved = result["discrepancies"]["resolved"][0]
        self.assertEqual("name", resolved["check_id"])
        persistent = result["discrepancies"]["persistent"][0]
        self.assertEqual("country", persistent["check_id"])
        changed = result["discrepancies"]["changed"][0]
        self.assertEqual("amount", changed["check_id"])
        self.assertEqual("0", changed["baseline"]["detail"]["target"])
        self.assertEqual("80", changed["current"]["detail"]["target"])
        new = result["discrepancies"]["new"][0]
        self.assertEqual("tax", new["check_id"])

    def test_check_transitions_report_improvement_and_regression(self) -> None:
        baseline = evidence(
            "r1",
            [
                detail_check("a", [{"key": "1", "source": "A", "target": "B"}]),
                detail_check("b", [], status="passed"),
            ],
        )
        current = evidence(
            "r2",
            [
                detail_check("a", [], status="passed"),
                detail_check("b", [{"key": "2", "source": "A", "target": "B"}]),
            ],
        )
        result = compare_evidence(baseline, current)
        transitions = {item["id"]: item["transition"] for item in result["check_transitions"]}
        self.assertEqual("improved", transitions["a"])
        self.assertEqual("regressed", transitions["b"])
        self.assertEqual(1, result["summary"]["checks_improved"])
        self.assertEqual(1, result["summary"]["checks_regressed"])

    def test_aggregate_group_locator_is_stable_business_dimension_identity(self) -> None:
        aggregate = {
            "id": "amount-by-country",
            "type": "aggregate_match",
            "severity": "error",
            "status": "failed",
            "metrics": {"groups_compared": 2, "groups_failed": 1},
            "details": [
                {
                    "group": "DE",
                    "source_value": "1000",
                    "target_value": "900",
                    "absolute_difference": "100",
                }
            ],
            "details_truncated": False,
        }
        baseline = evidence("r1", [aggregate])
        current_aggregate = json.loads(json.dumps(aggregate))
        current_aggregate["details"][0]["target_value"] = "980"
        current_aggregate["details"][0]["absolute_difference"] = "20"
        current = evidence("r2", [current_aggregate])

        result = compare_evidence(baseline, current)
        self.assertEqual(1, result["summary"]["changed_discrepancies"])
        item = result["discrepancies"]["changed"][0]
        self.assertEqual({"group": "DE"}, item["locator"])

    def test_incompatible_schema_major_is_explicit_error(self) -> None:
        baseline = evidence("r1", [])
        current = evidence("r2", [])
        current["schema_version"] = "2.0"
        with self.assertRaisesRegex(Exception, "Unsupported current evidence schema major version 2"):
            compare_evidence(baseline, current)

    def test_different_reconciliations_are_rejected(self) -> None:
        baseline = evidence("r1", [])
        current = evidence("r2", [])
        current["reconciliation"] = "Different control"
        with self.assertRaisesRegex(Exception, "different reconciliations"):
            compare_evidence(baseline, current)

    def test_file_diff_needs_no_original_source_or_target_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            baseline = evidence(
                "r1",
                [detail_check("name", [{"key": "1", "source": "A", "target": "B"}])],
            )
            current = evidence("r2", [detail_check("name", [], status="passed")], status="passed")
            baseline_path = root / "rehearsal-1.json"
            current_path = root / "rehearsal-2.json"
            baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
            current_path.write_text(json.dumps(current), encoding="utf-8")

            result = compare_evidence_files(baseline_path, current_path)
            self.assertEqual(1, result["summary"]["resolved_discrepancies"])
            self.assertFalse((root / "source.csv").exists())
            self.assertFalse((root / "target.csv").exists())

            write_diff_json(result, root / "diff.json")
            write_diff_markdown(result, root / "diff.md")
            write_diff_html(result, root / "diff.html")
            self.assertTrue((root / "diff.json").exists())
            self.assertIn("Resolved discrepancies", render_diff_markdown(result))
            self.assertIn("Reconciliation rehearsal diff", render_diff_html(result))


if __name__ == "__main__":
    unittest.main()
