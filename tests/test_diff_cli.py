from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import validate as validate_json_schema

from reconciliation_as_code.cli import main as cli_main
from reconciliation_as_code.schema import load_schema


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "rehearsal-diff"


class DiffCliTests(unittest.TestCase):
    def test_rac_diff_writes_json_markdown_and_html_without_original_data(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            baseline = EXAMPLE / "rehearsal-1.json"
            current = EXAMPLE / "rehearsal-2.json"
            diff_json = output / "diff.json"
            diff_md = output / "diff.md"
            diff_html = output / "diff.html"

            code = cli_main(
                [
                    "diff",
                    str(baseline),
                    str(current),
                    "--output",
                    str(diff_json),
                    "--report",
                    str(diff_md),
                    "--html",
                    str(diff_html),
                ]
            )

            self.assertEqual(0, code)
            self.assertTrue(diff_json.exists())
            self.assertTrue(diff_md.exists())
            self.assertTrue(diff_html.exists())
            payload = json.loads(diff_json.read_text(encoding="utf-8"))
            validate_json_schema(payload, load_schema("diff"))
            self.assertEqual(1, payload["summary"]["resolved_discrepancies"])
            self.assertEqual(1, payload["summary"]["persistent_discrepancies"])
            self.assertEqual(1, payload["summary"]["changed_discrepancies"])
            self.assertEqual(0, payload["summary"]["new_discrepancies"])
            self.assertTrue(payload["summary"]["improvement"])
            self.assertFalse(payload["summary"]["regression"])
            self.assertFalse((EXAMPLE / "legacy-export.csv").exists())
            self.assertFalse((EXAMPLE / "s4-export.csv").exists())

    def test_rac_diff_returns_one_on_regression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            code = cli_main(
                [
                    "diff",
                    str(EXAMPLE / "rehearsal-2.json"),
                    str(EXAMPLE / "rehearsal-1.json"),
                    "--output",
                    str(output / "diff.json"),
                    "--report",
                    str(output / "diff.md"),
                    "--html",
                    str(output / "diff.html"),
                ]
            )
            self.assertEqual(1, code)

    def test_no_fail_on_regression_is_reporting_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            code = cli_main(
                [
                    "diff",
                    str(EXAMPLE / "rehearsal-2.json"),
                    str(EXAMPLE / "rehearsal-1.json"),
                    "--output",
                    str(output / "diff.json"),
                    "--report",
                    str(output / "diff.md"),
                    "--html",
                    str(output / "diff.html"),
                    "--no-fail-on-regression",
                ]
            )
            self.assertEqual(0, code)

    def test_diff_schema_is_exportable_from_public_schema_command(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "diff.schema.json"
            code = cli_main(["schema", "diff", "--output", str(output)])
            self.assertEqual(0, code)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("Reconciliation as Code rehearsal evidence diff", payload["title"])


if __name__ == "__main__":
    unittest.main()
