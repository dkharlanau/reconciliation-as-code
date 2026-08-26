from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from reconciliation_as_code.cli import main as cli_main
from reconciliation_as_code.profiling import generate_spec, inspect_dataset, render_generated_spec
from reconciliation_as_code.spec import load_spec, validate_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class ProfilingTests(unittest.TestCase):
    def test_inspect_reports_types_quality_and_candidate_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "customers.csv"
            write_csv(
                path,
                [
                    {"ID": "1", "COUNTRY": "DE", "AMOUNT": "10.5", "NOTE": ""},
                    {"ID": "2", "COUNTRY": "US", "AMOUNT": "20", "NOTE": "x"},
                    {"ID": "3", "COUNTRY": "DE", "AMOUNT": "30.25", "NOTE": ""},
                ],
            )
            profile = inspect_dataset(path)
            self.assertEqual(3, profile["rows"])
            candidates = [item["field"] for item in profile["candidate_keys"]]
            self.assertIn("ID", candidates)
            by_name = {item["name"]: item for item in profile["columns"]}
            self.assertEqual("number", by_name["AMOUNT"]["type"])
            self.assertEqual(2, by_name["NOTE"]["null_count"])
            self.assertLess(by_name["COUNTRY"]["uniqueness"], 1.0)

    def test_init_can_safely_auto_select_same_named_unique_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.csv"
            target = base / "target.csv"
            write_csv(source, [{"ID": "1", "NAME": "A"}, {"ID": "2", "NAME": "B"}])
            write_csv(target, [{"ID": "1", "NAME": "A"}, {"ID": "2", "NAME": "B"}])
            spec, todos, _, _ = generate_spec(source, target)
            validate_spec(spec)
            self.assertEqual("ID", spec["source"]["key"])
            self.assertEqual("ID", spec["target"]["key"])
            self.assertFalse(todos)
            self.assertTrue(any(check.get("source") == "NAME" for check in spec["checks"]))

    def test_init_requires_explicit_keys_when_business_identity_is_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "legacy.csv"
            target = base / "s4.csv"
            write_csv(source, [{"CUSTOMER_ID": "1", "NAME": "A"}, {"CUSTOMER_ID": "2", "NAME": "B"}])
            write_csv(target, [{"LEGACY_ID": "1", "NAME": "A"}, {"LEGACY_ID": "2", "NAME": "B"}])
            with self.assertRaisesRegex(Exception, "Could not safely infer equivalent business keys"):
                generate_spec(source, target)

            spec, todos, _, _ = generate_spec(
                source, target, source_key="CUSTOMER_ID", target_key="LEGACY_ID"
            )
            validate_spec(spec)
            self.assertEqual("CUSTOMER_ID", spec["source"]["key"])
            self.assertEqual("LEGACY_ID", spec["target"]["key"])
            self.assertTrue(any("CUSTOMER_ID" in todo for todo in todos))
            rendered = render_generated_spec(spec, todos)
            self.assertIn("# TODO:", rendered)

    def test_cli_init_generates_immediately_valid_runnable_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            data_dir = base / "data"
            config_dir = base / "config"
            data_dir.mkdir()
            source = data_dir / "source.csv"
            target = data_dir / "target.csv"
            output = config_dir / "reconciliation.yaml"
            write_csv(source, [{"ID": "1", "VALUE": "A"}])
            write_csv(target, [{"ID": "1", "VALUE": "A"}])

            code = cli_main(["init", str(source), str(target), "--output", str(output)])
            self.assertEqual(0, code)
            spec = load_spec(output)
            self.assertTrue((output.parent / spec["source"]["file"]).resolve().exists())
            self.assertTrue((output.parent / spec["target"]["file"]).resolve().exists())

    def test_excel_inspection_uses_sheet_and_detects_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "customers.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Customers"
            sheet.append(["ID", "NAME"])
            sheet.append([1, "A"])
            sheet.append([2, "B"])
            workbook.save(path)

            profile = inspect_dataset(path, sheet="Customers")
            self.assertEqual(2, profile["rows"])
            self.assertIn("ID", [item["field"] for item in profile["candidate_keys"]])


if __name__ == "__main__":
    unittest.main()
