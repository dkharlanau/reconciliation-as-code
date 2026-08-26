from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.identity import run_reconciliation_with_identity


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def identity_spec() -> dict:
    return {
        "version": 1,
        "reconciliation": {"name": "changed identities"},
        "source": {"file": "source.csv", "key": "LEGACY_ID"},
        "target": {"file": "target.csv", "key": "BP_ID"},
        "identity": {
            "crosswalk": {
                "file": "crosswalk.csv",
                "source_key": "SOURCE_ID",
                "target_key": "TARGET_ID",
            },
            "aggregation": {
                "source": {"AMOUNT": "sum", "COUNTRY": "require_equal"},
                "target": {"AMOUNT": "sum", "COUNTRY": "require_equal"},
            },
        },
        "checks": [
            {"id": "coverage", "type": "record_coverage"},
            {"id": "amount", "type": "field_match", "source": "AMOUNT", "target": "AMOUNT", "numeric_tolerance": 0},
            {"id": "country", "type": "field_match", "source": "COUNTRY", "target": "COUNTRY"},
        ],
    }


class IdentityTests(unittest.TestCase):
    def test_changed_id_split_and_merge_can_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [
                {"LEGACY_ID": "1001", "COUNTRY": "DE", "AMOUNT": "50"},
                {"LEGACY_ID": "1002", "COUNTRY": "US", "AMOUNT": "100"},
                {"LEGACY_ID": "1003", "COUNTRY": "FR", "AMOUNT": "30"},
                {"LEGACY_ID": "1004", "COUNTRY": "FR", "AMOUNT": "70"},
            ])
            write_csv(base / "target.csv", [
                {"BP_ID": "9001", "COUNTRY": "DE", "AMOUNT": "50"},
                {"BP_ID": "9002", "COUNTRY": "US", "AMOUNT": "60"},
                {"BP_ID": "9003", "COUNTRY": "US", "AMOUNT": "40"},
                {"BP_ID": "9004", "COUNTRY": "FR", "AMOUNT": "100"},
            ])
            write_csv(base / "crosswalk.csv", [
                {"SOURCE_ID": "1001", "TARGET_ID": "9001"},
                {"SOURCE_ID": "1002", "TARGET_ID": "9002"},
                {"SOURCE_ID": "1002", "TARGET_ID": "9003"},
                {"SOURCE_ID": "1003", "TARGET_ID": "9004"},
                {"SOURCE_ID": "1004", "TARGET_ID": "9004"},
            ])
            result = run_reconciliation_with_identity(identity_spec(), base_dir=base)
            self.assertEqual("passed", result["status"])
            modes = sorted(item["mode"] for item in result["identity"]["components"])
            self.assertEqual(["1:1", "1:N", "N:1"], modes)
            self.assertEqual(3, result["summary"]["identity_components"])
            self.assertEqual(4, result["summary"]["source_raw_records"])
            self.assertEqual(4, result["summary"]["target_raw_records"])
            integrity = next(item for item in result["checks"] if item["id"] == "identity-crosswalk-integrity")
            self.assertEqual("passed", integrity["status"])
            self.assertEqual(1, integrity["metrics"]["one_to_many"])
            self.assertEqual(1, integrity["metrics"]["many_to_one"])
            self.assertIn("identity_crosswalk", result["inputs"])

    def test_unmapped_source_identity_fails_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [
                {"LEGACY_ID": "1001", "COUNTRY": "DE", "AMOUNT": "50"},
                {"LEGACY_ID": "9999", "COUNTRY": "DE", "AMOUNT": "10"},
            ])
            write_csv(base / "target.csv", [{"BP_ID": "9001", "COUNTRY": "DE", "AMOUNT": "50"}])
            write_csv(base / "crosswalk.csv", [{"SOURCE_ID": "1001", "TARGET_ID": "9001"}])
            result = run_reconciliation_with_identity(identity_spec(), base_dir=base)
            self.assertEqual("failed", result["status"])
            integrity = next(item for item in result["checks"] if item["id"] == "identity-crosswalk-integrity")
            self.assertEqual(1, integrity["metrics"]["unmapped_source"])
            self.assertTrue(any(item["difference"] == "unmapped_source_identity" for item in integrity["details"]))

    def test_n_to_n_component_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [
                {"LEGACY_ID": "1", "COUNTRY": "DE", "AMOUNT": "1"},
                {"LEGACY_ID": "2", "COUNTRY": "DE", "AMOUNT": "1"},
            ])
            write_csv(base / "target.csv", [
                {"BP_ID": "A", "COUNTRY": "DE", "AMOUNT": "1"},
                {"BP_ID": "B", "COUNTRY": "DE", "AMOUNT": "1"},
            ])
            write_csv(base / "crosswalk.csv", [
                {"SOURCE_ID": "1", "TARGET_ID": "A"},
                {"SOURCE_ID": "1", "TARGET_ID": "B"},
                {"SOURCE_ID": "2", "TARGET_ID": "A"},
            ])
            with self.assertRaisesRegex(Exception, "N:N identity component"):
                run_reconciliation_with_identity(identity_spec(), base_dir=base)

    def test_changed_parent_ids_flow_into_child_hierarchy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"LEGACY_ID": "1001", "COUNTRY": "DE", "AMOUNT": "50"}])
            write_csv(base / "target.csv", [{"BP_ID": "9001", "COUNTRY": "DE", "AMOUNT": "50"}])
            write_csv(base / "crosswalk.csv", [{"SOURCE_ID": "1001", "TARGET_ID": "9001"}])
            write_csv(base / "source_addresses.csv", [{"LEGACY_ID": "1001", "TYPE": "BILL", "CITY": "Berlin"}])
            write_csv(base / "target_addresses.csv", [{"BP_ID": "9001", "TYPE": "BILL", "CITY": "Berlin"}])
            spec = identity_spec()
            spec["object"] = {"type": "CustomerBP"}
            spec["children"] = {
                "addresses": {
                    "source": {"file": "source_addresses.csv", "key": ["LEGACY_ID", "TYPE"], "parent_key": "LEGACY_ID"},
                    "target": {"file": "target_addresses.csv", "key": ["BP_ID", "TYPE"], "parent_key": "BP_ID"},
                    "checks": [
                        {"id": "coverage", "type": "record_coverage"},
                        {"id": "city", "type": "field_match", "source": "CITY", "target": "CITY"},
                    ],
                }
            }
            result = run_reconciliation_with_identity(spec, base_dir=base)
            self.assertEqual("passed", result["status"])
            self.assertEqual(1, result["summary"]["child_collections"])
            self.assertEqual(0, result["summary"]["objects_failed"])


if __name__ == "__main__":
    unittest.main()
