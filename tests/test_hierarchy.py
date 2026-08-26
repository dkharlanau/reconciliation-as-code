from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.engine import run_reconciliation
from reconciliation_as_code.spec import load_spec, validate_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class HierarchyTests(unittest.TestCase):
    def test_customer_example_distinguishes_child_difference_categories_and_rolls_up(self) -> None:
        root = Path(__file__).resolve().parents[1]
        example = root / "examples" / "customer-object" / "reconciliation.yaml"
        spec = load_spec(example)
        result = run_reconciliation(spec, base_dir=example.parent, spec_path=example)

        self.assertEqual("failed", result["status"])
        addresses_coverage = next(
            item for item in result["checks"] if item["id"] == "children.addresses.coverage"
        )
        differences = {item["difference"] for item in addresses_coverage["details"]}
        self.assertEqual(
            {"missing_child_in_target", "unexpected_child_in_target"}, differences
        )

        city = next(item for item in result["checks"] if item["id"] == "children.addresses.city")
        self.assertEqual(3, city["metrics"]["compared"])
        self.assertEqual(1, city["metrics"]["mismatches"])
        self.assertEqual("changed_child_field", city["details"][0]["difference"])
        self.assertEqual("customer/C1/addresses/A2", city["details"][0]["path"])

        sales_coverage = next(
            item for item in result["checks"] if item["id"] == "children.sales_areas.coverage"
        )
        self.assertEqual(1, sales_coverage["metrics"]["missing_in_target"])

        self.assertEqual(3, result["object"]["summary"]["objects_total"])
        self.assertEqual(2, result["object"]["summary"]["objects_failed"])
        by_key = {item["key"]: item for item in result["object"]["details"]}
        self.assertEqual("failed", by_key["C1"]["status"])
        self.assertEqual("passed", by_key["C2"]["status"])
        self.assertEqual("failed", by_key["C3"]["status"])
        self.assertTrue(any("addresses" in path for path in by_key["C1"]["failure_paths"]))

        self.assertIn("child.addresses.source", result["inputs"])
        self.assertIn("child.sales_areas.target", result["inputs"])

    def test_identical_duplicate_child_rows_can_be_explicitly_collapsed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source-root.csv", [{"ID": "1"}])
            write_csv(base / "target-root.csv", [{"ID": "1"}])
            write_csv(
                base / "source-child.csv",
                [
                    {"ID": "1", "ITEM": "A", "VALUE": "x"},
                    {"ID": "1", "ITEM": "A", "VALUE": "x"},
                ],
            )
            write_csv(
                base / "target-child.csv",
                [{"ID": "1", "ITEM": "A", "VALUE": "x"}],
            )
            spec = {
                "version": 1,
                "reconciliation": {"name": "duplicate-policy"},
                "source": {"file": "source-root.csv", "key": "ID"},
                "target": {"file": "target-root.csv", "key": "ID"},
                "checks": [{"id": "coverage", "type": "record_coverage"}],
                "object": {
                    "name": "order",
                    "children": [
                        {
                            "name": "items",
                            "duplicate_policy": "allow_identical",
                            "source": {
                                "file": "source-child.csv",
                                "parent_key": "ID",
                                "key": "ITEM",
                            },
                            "target": {
                                "file": "target-child.csv",
                                "parent_key": "ID",
                                "key": "ITEM",
                            },
                            "checks": [
                                {
                                    "id": "value",
                                    "type": "field_match",
                                    "source": "VALUE",
                                    "target": "VALUE",
                                }
                            ],
                        }
                    ],
                },
            }
            result = run_reconciliation(spec, base_dir=base)
            integrity = next(
                item
                for item in result["checks"]
                if item["id"] == "children.items.source-key-integrity"
            )
            self.assertEqual("passed", integrity["status"])
            self.assertEqual(1, integrity["metrics"]["identical_duplicates_ignored"])
            self.assertEqual("passed", result["status"])

    def test_conflicting_duplicate_child_rows_still_fail_allow_identical_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source-root.csv", [{"ID": "1"}])
            write_csv(base / "target-root.csv", [{"ID": "1"}])
            write_csv(
                base / "source-child.csv",
                [
                    {"ID": "1", "ITEM": "A", "VALUE": "x"},
                    {"ID": "1", "ITEM": "A", "VALUE": "y"},
                ],
            )
            write_csv(base / "target-child.csv", [{"ID": "1", "ITEM": "A", "VALUE": "x"}])
            spec = {
                "version": 1,
                "reconciliation": {"name": "conflicting-duplicate"},
                "source": {"file": "source-root.csv", "key": "ID"},
                "target": {"file": "target-root.csv", "key": "ID"},
                "checks": [{"type": "record_coverage"}],
                "object": {
                    "name": "order",
                    "children": [
                        {
                            "name": "items",
                            "duplicate_policy": "allow_identical",
                            "source": {"file": "source-child.csv", "parent_key": "ID", "key": "ITEM"},
                            "target": {"file": "target-child.csv", "parent_key": "ID", "key": "ITEM"},
                        }
                    ],
                },
            }
            result = run_reconciliation(spec, base_dir=base)
            integrity = next(
                item
                for item in result["checks"]
                if item["id"] == "children.items.source-key-integrity"
            )
            self.assertEqual("failed", integrity["status"])
            self.assertEqual(1, integrity["metrics"]["duplicate_keys"])
            self.assertEqual("failed", result["status"])

    def test_child_parent_key_must_match_root_identity_width(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "composite-root"},
            "source": {"file": "a.csv", "key": ["CLIENT", "ID"]},
            "target": {"file": "b.csv", "key": ["CLIENT", "ID"]},
            "checks": [{"type": "record_coverage"}],
            "object": {
                "name": "customer",
                "children": [
                    {
                        "name": "addresses",
                        "source": {"file": "c.csv", "parent_key": "ID", "key": "ADDR"},
                        "target": {"file": "d.csv", "parent_key": "ID", "key": "ADDR"},
                    }
                ],
            },
        }
        with self.assertRaisesRegex(Exception, "parent_key must contain 2 field"):
            validate_spec(spec)


if __name__ == "__main__":
    unittest.main()
