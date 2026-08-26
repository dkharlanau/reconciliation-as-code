from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.engine import run_reconciliation
from reconciliation_as_code.spec import validate_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def base_spec() -> dict:
    return {
        "version": 1,
        "reconciliation": {"name": "scoped-controls"},
        "source": {"file": "source.csv", "key": "ID"},
        "target": {"file": "target.csv", "key": "ID"},
        "checks": [{"id": "coverage", "type": "record_coverage"}],
    }


class ScopeAndAggregateTests(unittest.TestCase):
    def test_endpoint_filter_is_visible_in_selection_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rows = [
                {"ID": "1", "ACTIVE": "Y"},
                {"ID": "2", "ACTIVE": "Y"},
                {"ID": "3", "ACTIVE": "N"},
            ]
            write_csv(base / "source.csv", rows)
            write_csv(base / "target.csv", rows)
            spec = base_spec()
            spec["source"]["filter"] = {"field": "ACTIVE", "op": "eq", "value": "Y"}
            spec["target"]["filter"] = {"field": "ACTIVE", "op": "eq", "value": "Y"}

            result = run_reconciliation(spec, base_dir=base)
            self.assertEqual(2, result["summary"]["source_records"])
            self.assertEqual(3, result["selection"]["source"]["raw_records"])
            self.assertEqual(2, result["selection"]["source"]["selected_records"])
            self.assertEqual("passed", result["status"])

    def test_named_scope_and_when_limit_field_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(
                base / "source.csv",
                [
                    {"ID": "1", "ACTIVE": "Y", "DATE": "2026-01-01"},
                    {"ID": "2", "ACTIVE": "Y", "DATE": "2026-01-02"},
                    {"ID": "3", "ACTIVE": "N", "DATE": "2026-01-01"},
                ],
            )
            write_csv(
                base / "target.csv",
                [
                    {"ID": "1", "ACTIVE": "Y", "DATE": "2026-01-02"},
                    {"ID": "2", "ACTIVE": "Y", "DATE": "2026-01-02"},
                    {"ID": "3", "ACTIVE": "N", "DATE": "2026-03-01"},
                ],
            )
            spec = base_spec()
            spec["scopes"] = {
                "active": {
                    "source": {"field": "ACTIVE", "op": "eq", "value": "Y"},
                    "target": {"field": "ACTIVE", "op": "eq", "value": "Y"},
                }
            }
            spec["checks"].append(
                {
                    "id": "active-date",
                    "type": "field_match",
                    "source": "DATE",
                    "target": "DATE",
                    "scope": "active",
                    "when": {
                        "source": {"field": "DATE", "op": "not_null"},
                        "target": {"field": "DATE", "op": "not_null"},
                    },
                    "date_tolerance_days": 1,
                }
            )

            result = run_reconciliation(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "active-date")
            self.assertEqual("passed", check["status"])
            self.assertEqual(2, check["metrics"]["compared"])
            self.assertEqual(1, check["metrics"]["skipped_by_scope_or_when"])

    def test_aggregate_sum_reports_failing_business_group(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(
                base / "source.csv",
                [
                    {"ID": "1", "COMPANY": "1000", "AMOUNT": "100"},
                    {"ID": "2", "COMPANY": "1000", "AMOUNT": "200"},
                    {"ID": "3", "COMPANY": "2000", "AMOUNT": "300"},
                ],
            )
            write_csv(
                base / "target.csv",
                [
                    {"ID": "1", "COMPANY": "1000", "AMOUNT": "100"},
                    {"ID": "2", "COMPANY": "1000", "AMOUNT": "195"},
                    {"ID": "3", "COMPANY": "2000", "AMOUNT": "300"},
                ],
            )
            spec = base_spec()
            spec["checks"].append(
                {
                    "id": "amount-by-company",
                    "type": "aggregate_match",
                    "operation": "sum",
                    "source": "AMOUNT",
                    "target": "AMOUNT",
                    "group_by": {"source": "COMPANY", "target": "COMPANY"},
                    "tolerance": 0,
                }
            )

            result = run_reconciliation(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "amount-by-company")
            self.assertEqual("failed", check["status"])
            self.assertEqual(2, check["metrics"]["groups_compared"])
            self.assertEqual(1, check["metrics"]["groups_failed"])
            self.assertEqual("1000", check["details"][0]["group"])
            self.assertEqual("5", check["details"][0]["absolute_difference"])

    def test_percentage_tolerance_can_pass_field_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "AMOUNT": "100"}])
            write_csv(base / "target.csv", [{"ID": "1", "AMOUNT": "101"}])
            spec = base_spec()
            spec["checks"].append(
                {
                    "id": "amount",
                    "type": "field_match",
                    "source": "AMOUNT",
                    "target": "AMOUNT",
                    "percentage_tolerance": 1,
                }
            )
            result = run_reconciliation(spec, base_dir=base)
            check = next(item for item in result["checks"] if item["id"] == "amount")
            self.assertEqual("passed", check["status"])

    def test_null_semantics_are_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": ""}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": ""}])
            spec = base_spec()
            spec["checks"].extend(
                [
                    {
                        "id": "nulls-equal",
                        "type": "field_match",
                        "source": "VALUE",
                        "target": "VALUE",
                        "null_semantics": "empty_is_null",
                    },
                    {
                        "id": "nulls-never",
                        "type": "field_match",
                        "source": "VALUE",
                        "target": "VALUE",
                        "null_semantics": "never_equal",
                    },
                ]
            )
            result = run_reconciliation(spec, base_dir=base)
            equal = next(item for item in result["checks"] if item["id"] == "nulls-equal")
            never = next(item for item in result["checks"] if item["id"] == "nulls-never")
            self.assertEqual("passed", equal["status"])
            self.assertEqual("failed", never["status"])

    def test_unknown_scope_is_rejected(self) -> None:
        spec = base_spec()
        spec["checks"].append(
            {
                "id": "x",
                "type": "field_match",
                "source": "A",
                "target": "A",
                "scope": "missing",
            }
        )
        with self.assertRaisesRegex(Exception, "must reference a declared scope"):
            validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
