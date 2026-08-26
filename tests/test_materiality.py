from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.governance import run_reconciliation_with_governance
from reconciliation_as_code.spec import validate_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def base_spec() -> dict:
    return {
        "version": 1,
        "reconciliation": {"name": "materiality-test"},
        "source": {"file": "source.csv", "key": "ID"},
        "target": {"file": "target.csv", "key": "ID"},
        "checks": [
            {"id": "coverage", "type": "record_coverage"},
            {"id": "name", "type": "field_match", "source": "NAME", "target": "NAME"},
        ],
    }


class MaterialityTests(unittest.TestCase):
    def test_cosmetic_difference_can_be_materiality_pass_without_hiding_raw_diff(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "NAME": "Acme"}])
            write_csv(base / "target.csv", [{"ID": "1", "NAME": "Acme GmbH"}])
            spec = base_spec()
            spec["materiality"] = {
                "fields": {"NAME": {"severity": "warning", "max_failures": 1}}
            }

            result = run_reconciliation_with_governance(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "name")

            self.assertEqual("passed", result["status"])
            self.assertEqual("passed", check["status"])
            self.assertEqual("warning", check["severity"])
            self.assertEqual(1, check["metrics"]["mismatches"])
            self.assertEqual("failed", check["metrics"]["materiality"]["raw_status"])
            self.assertEqual(1, len(check["details"]))

    def test_critical_field_fails_even_when_failure_rate_policy_would_allow_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "CREDIT_LIMIT": "100"}])
            write_csv(base / "target.csv", [{"ID": "1", "CREDIT_LIMIT": "101"}])
            spec = {
                "version": 1,
                "reconciliation": {"name": "critical-field"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [
                    {
                        "id": "credit",
                        "type": "field_match",
                        "source": "CREDIT_LIMIT",
                        "target": "CREDIT_LIMIT",
                    }
                ],
                "materiality": {
                    "fields": {
                        "CREDIT_LIMIT": {
                            "critical": True,
                            "max_failure_percentage": 100,
                        }
                    }
                },
            }

            result = run_reconciliation_with_governance(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "credit")

            self.assertEqual("failed", result["status"])
            self.assertEqual("failed", check["status"])
            self.assertEqual("error", check["severity"])
            self.assertEqual(1, result["summary"]["critical_failures"])
            self.assertTrue(
                check["metrics"]["materiality"]["observed"]["critical_failure"]
            )

    def test_percentage_materiality_uses_real_compared_denominator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_rows = [
                {"ID": str(index), "VALUE": "A"} for index in range(1, 11)
            ]
            target_rows = [dict(row) for row in source_rows]
            target_rows[-1]["VALUE"] = "B"
            write_csv(base / "source.csv", source_rows)
            write_csv(base / "target.csv", target_rows)
            spec = {
                "version": 1,
                "reconciliation": {"name": "percentage"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [
                    {"id": "value", "type": "field_match", "source": "VALUE", "target": "VALUE"}
                ],
                "materiality": {"checks": {"value": {"max_failure_percentage": 10}}},
            }

            result = run_reconciliation_with_governance(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "value")
            observed = check["metrics"]["materiality"]["observed"]

            self.assertEqual("passed", result["status"])
            self.assertEqual(10, observed["denominator"])
            self.assertEqual("10", observed["failure_percentage"])

    def test_default_materiality_cannot_waive_automatic_key_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(
                base / "source.csv",
                [{"ID": "1", "NAME": "A"}, {"ID": "1", "NAME": "A"}],
            )
            write_csv(base / "target.csv", [{"ID": "1", "NAME": "A"}])
            spec = base_spec()
            spec["materiality"] = {"default": {"max_failures": 999}}

            result = run_reconciliation_with_governance(spec, base_dir=base)
            integrity = next(
                item for item in result["checks"] if item["id"] == "source-key-integrity"
            )

            self.assertEqual("failed", result["status"])
            self.assertEqual("failed", integrity["status"])
            self.assertNotIn("materiality", integrity["metrics"])

    def test_accepted_exception_is_applied_before_critical_materiality(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "NAME": "Acme"}])
            write_csv(base / "target.csv", [{"ID": "1", "NAME": "Acme GmbH"}])
            (base / "exceptions.yaml").write_text(
                """version: 1
exceptions:
  - check: name
    key: '1'
    field: NAME
    reason_code: APPROVED
    reason: Approved cutover exception
    owner: Migration Lead
    reference: TEST-1
    expires: 2099-12-31
""",
                encoding="utf-8",
            )
            spec = base_spec()
            spec["exceptions"] = {"file": "exceptions.yaml", "expiry_policy": "error"}
            spec["materiality"] = {"fields": {"NAME": {"critical": True}}}

            result = run_reconciliation_with_governance(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "name")

            self.assertEqual("passed", result["status"])
            self.assertEqual(1, check["metrics"]["gross_failures"])
            self.assertEqual(1, check["metrics"]["accepted_exceptions"])
            self.assertEqual(0, check["metrics"]["unaccepted_failures"])
            self.assertEqual("accepted-exception", check["details"][0]["disposition"])

    def test_invalid_materiality_policy_is_rejected_by_spec_validation(self) -> None:
        spec = base_spec()
        spec["materiality"] = {"fields": {"NAME": {"severity": "maybe"}}}
        with self.assertRaisesRegex(Exception, "severity must be error or warning"):
            validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
