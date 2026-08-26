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


class EngineTests(unittest.TestCase):
    def test_field_mapping_and_tolerance_can_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(
                base / "source.csv",
                [
                    {"ID": "001", "COUNTRY": "de", "AMOUNT": "10.00"},
                    {"ID": "002", "COUNTRY": "US", "AMOUNT": "20.00"},
                ],
            )
            write_csv(
                base / "target.csv",
                [
                    {"LEGACY_ID": "1", "COUNTRY_CODE": "DEU", "AMOUNT": "10.01"},
                    {"LEGACY_ID": "2", "COUNTRY_CODE": "USA", "AMOUNT": "19.99"},
                ],
            )
            spec = {
                "version": 1,
                "reconciliation": {"name": "test"},
                "source": {"file": "source.csv", "key": "ID", "key_normalize": ["trim", "strip_leading_zeros"]},
                "target": {"file": "target.csv", "key": "LEGACY_ID", "key_normalize": ["trim", "strip_leading_zeros"]},
                "checks": [
                    {"id": "coverage", "type": "record_coverage"},
                    {
                        "id": "country",
                        "type": "field_match",
                        "source": "COUNTRY",
                        "target": "COUNTRY_CODE",
                        "normalize": ["trim", "uppercase"],
                        "map": {"DE": "DEU", "US": "USA"},
                    },
                    {
                        "id": "amount",
                        "type": "field_match",
                        "source": "AMOUNT",
                        "target": "AMOUNT",
                        "numeric_tolerance": 0.02,
                    },
                ],
            }
            result = run_reconciliation(spec, base_dir=base)
            self.assertEqual("passed", result["status"])
            self.assertEqual(2, result["summary"]["matched_records"])

    def test_missing_record_and_mismatch_fail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": "A"}, {"ID": "2", "VALUE": "B"}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": "X"}])
            spec = {
                "version": 1,
                "reconciliation": {"name": "test"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [
                    {"id": "coverage", "type": "record_coverage"},
                    {"id": "value", "type": "field_match", "source": "VALUE", "target": "VALUE"},
                ],
            }
            result = run_reconciliation(spec, base_dir=base)
            self.assertEqual("failed", result["status"])
            self.assertEqual(1, result["summary"]["missing_in_target"])
            value_check = next(item for item in result["checks"] if item["id"] == "value")
            self.assertEqual(1, value_check["metrics"]["mismatches"])

    def test_duplicate_keys_are_automatic_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1"}, {"ID": "1"}])
            write_csv(base / "target.csv", [{"ID": "1"}])
            spec = {
                "version": 1,
                "reconciliation": {"name": "test"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [{"id": "coverage", "type": "record_coverage"}],
            }
            result = run_reconciliation(spec, base_dir=base)
            self.assertEqual("failed", result["status"])
            integrity = next(item for item in result["checks"] if item["id"] == "source-key-integrity")
            self.assertEqual(1, integrity["metrics"]["duplicate_keys"])

    def test_spec_rejects_unknown_check(self) -> None:
        with self.assertRaises(Exception):
            validate_spec(
                {
                    "version": 1,
                    "reconciliation": {"name": "x"},
                    "source": {"file": "a.csv", "key": "ID"},
                    "target": {"file": "b.csv", "key": "ID"},
                    "checks": [{"type": "magic"}],
                }
            )


if __name__ == "__main__":
    unittest.main()
