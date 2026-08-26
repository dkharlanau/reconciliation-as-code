from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.hierarchy import run_reconciliation_with_hierarchy, validate_hierarchy_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def hierarchy_spec() -> dict:
    return {
        "version": 1,
        "object": {"type": "CustomerBP"},
        "reconciliation": {"name": "Customer to BP hierarchy"},
        "source": {"file": "customers.csv", "key": "CUSTOMER_ID"},
        "target": {"file": "bps.csv", "key": "LEGACY_ID"},
        "checks": [
            {"id": "root-coverage", "type": "record_coverage"},
            {"id": "root-name", "type": "field_match", "source": "NAME", "target": "NAME"},
        ],
        "children": {
            "addresses": {
                "source": {
                    "file": "customer_addresses.csv",
                    "key": ["CUSTOMER_ID", "ADDRESS_TYPE"],
                    "parent_key": "CUSTOMER_ID",
                },
                "target": {
                    "file": "bp_addresses.csv",
                    "key": ["LEGACY_ID", "ADDRESS_TYPE"],
                    "parent_key": "LEGACY_ID",
                },
                "checks": [
                    {"id": "coverage", "type": "record_coverage"},
                    {"id": "city", "type": "field_match", "source": "CITY", "target": "CITY"},
                ],
            }
        },
    }


class HierarchyTests(unittest.TestCase):
    def _root(self, base: Path) -> None:
        write_csv(base / "customers.csv", [{"CUSTOMER_ID": "100", "NAME": "Acme"}, {"CUSTOMER_ID": "200", "NAME": "Beta"}])
        write_csv(base / "bps.csv", [{"LEGACY_ID": "100", "NAME": "Acme"}, {"LEGACY_ID": "200", "NAME": "Beta"}])

    def test_unordered_child_collection_can_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._root(base)
            write_csv(base / "customer_addresses.csv", [
                {"CUSTOMER_ID": "100", "ADDRESS_TYPE": "SHIP", "CITY": "Berlin"},
                {"CUSTOMER_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
                {"CUSTOMER_ID": "200", "ADDRESS_TYPE": "BILL", "CITY": "Paris"},
            ])
            write_csv(base / "bp_addresses.csv", [
                {"LEGACY_ID": "200", "ADDRESS_TYPE": "BILL", "CITY": "Paris"},
                {"LEGACY_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
                {"LEGACY_ID": "100", "ADDRESS_TYPE": "SHIP", "CITY": "Berlin"},
            ])
            result = run_reconciliation_with_hierarchy(hierarchy_spec(), base_dir=base)
            self.assertEqual("passed", result["status"])
            self.assertEqual(1, result["summary"]["child_collections"])
            self.assertEqual(0, result["summary"]["objects_failed"])
            self.assertEqual("passed", result["hierarchy"]["collections"]["addresses"]["status"])

    def test_missing_child_rolls_up_to_parent_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._root(base)
            write_csv(base / "customer_addresses.csv", [
                {"CUSTOMER_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
                {"CUSTOMER_ID": "200", "ADDRESS_TYPE": "BILL", "CITY": "Paris"},
            ])
            write_csv(base / "bp_addresses.csv", [
                {"LEGACY_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
            ])
            result = run_reconciliation_with_hierarchy(hierarchy_spec(), base_dir=base)
            self.assertEqual("failed", result["status"])
            self.assertEqual(1, result["summary"]["objects_failed"])
            coverage = next(item for item in result["checks"] if item["id"] == "child:addresses:coverage")
            self.assertEqual("failed", coverage["status"])
            detail = next(item for item in coverage["details"] if item["difference"] == "missing_in_target")
            self.assertEqual("200", detail["parent_key"])
            self.assertIn("CustomerBP/200/addresses/", detail["object_path"])

    def test_orphan_child_is_parent_integrity_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._root(base)
            write_csv(base / "customer_addresses.csv", [
                {"CUSTOMER_ID": "999", "ADDRESS_TYPE": "BILL", "CITY": "Rome"},
            ])
            write_csv(base / "bp_addresses.csv", [
                {"LEGACY_ID": "999", "ADDRESS_TYPE": "BILL", "CITY": "Rome"},
            ])
            result = run_reconciliation_with_hierarchy(hierarchy_spec(), base_dir=base)
            self.assertEqual("failed", result["status"])
            source_integrity = next(item for item in result["checks"] if item["id"] == "child:addresses:source-parent-integrity")
            target_integrity = next(item for item in result["checks"] if item["id"] == "child:addresses:target-parent-integrity")
            self.assertEqual(1, source_integrity["metrics"]["orphan_rows"])
            self.assertEqual(1, target_integrity["metrics"]["orphan_rows"])

    def test_duplicate_policy_warning_does_not_fail_object_by_itself(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            self._root(base)
            write_csv(base / "customer_addresses.csv", [
                {"CUSTOMER_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
                {"CUSTOMER_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
            ])
            write_csv(base / "bp_addresses.csv", [
                {"LEGACY_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
                {"LEGACY_ID": "100", "ADDRESS_TYPE": "BILL", "CITY": "Berlin"},
            ])
            spec = hierarchy_spec()
            spec["children"]["addresses"]["duplicate_policy"] = "warning"
            result = run_reconciliation_with_hierarchy(spec, base_dir=base)
            source_dup = next(item for item in result["checks"] if item["id"] == "child:addresses:source-key-integrity")
            self.assertEqual("warning", source_dup["severity"])
            self.assertEqual("failed", source_dup["status"])
            self.assertEqual("passed", result["status"])

    def test_parent_key_must_be_part_of_child_key(self) -> None:
        spec = hierarchy_spec()
        spec["children"]["addresses"]["source"]["key"] = "ADDRESS_TYPE"
        with self.assertRaisesRegex(Exception, "must also be part of child key"):
            validate_hierarchy_spec(spec)


if __name__ == "__main__":
    unittest.main()
