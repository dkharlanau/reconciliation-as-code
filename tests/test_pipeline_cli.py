from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import validate as validate_json_schema

from reconciliation_as_code.cli import main as cli_main
from reconciliation_as_code.pipeline import load_pipeline_spec
from reconciliation_as_code.schema import load_schema


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "multi-stage"
SPEC = EXAMPLE / "pipeline.yaml"


class PipelineCliTests(unittest.TestCase):
    def test_pipeline_spec_validates_against_published_schema(self) -> None:
        spec = load_pipeline_spec(SPEC)
        validate_json_schema(spec, load_schema("pipeline"))

    def test_rac_pipeline_writes_versioned_evidence_and_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "pipeline.json"
            report = root / "pipeline.md"
            html = root / "pipeline.html"
            code = cli_main(
                [
                    "pipeline",
                    str(SPEC),
                    "--evidence",
                    str(evidence),
                    "--report",
                    str(report),
                    "--html",
                    str(html),
                    "--no-fail-on-diff",
                ]
            )
            self.assertEqual(0, code)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            validate_json_schema(payload, load_schema("pipeline-evidence"))
            self.assertEqual("failed", payload["status"])
            self.assertEqual(2, payload["summary"]["transitions_failed"])
            self.assertTrue(report.exists())
            self.assertTrue(html.exists())

    def test_pipeline_failure_is_ci_gate_without_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            code = cli_main(
                [
                    "pipeline",
                    str(SPEC),
                    "--evidence",
                    str(root / "pipeline.json"),
                    "--report",
                    str(root / "pipeline.md"),
                    "--html",
                    str(root / "pipeline.html"),
                ]
            )
            self.assertEqual(1, code)

    def test_public_schema_command_exports_pipeline_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec_schema = root / "pipeline.schema.json"
            evidence_schema = root / "pipeline-evidence.schema.json"
            self.assertEqual(0, cli_main(["schema", "pipeline", "--output", str(spec_schema)]))
            self.assertEqual(
                0,
                cli_main(["schema", "pipeline-evidence", "--output", str(evidence_schema)]),
            )
            self.assertEqual(
                "Reconciliation as Code multi-stage pipeline specification",
                json.loads(spec_schema.read_text(encoding="utf-8"))["title"],
            )
            self.assertEqual(
                "Reconciliation as Code multi-stage pipeline evidence",
                json.loads(evidence_schema.read_text(encoding="utf-8"))["title"],
            )

    def test_cli_can_run_only_source_to_extract_subset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            evidence = root / "subset.json"
            code = cli_main(
                [
                    "pipeline",
                    str(SPEC),
                    "--from-stage",
                    "source",
                    "--to-stage",
                    "extract",
                    "--evidence",
                    str(evidence),
                    "--report",
                    str(root / "subset.md"),
                    "--html",
                    str(root / "subset.html"),
                ]
            )
            self.assertEqual(0, code)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("passed", payload["status"])
            self.assertEqual(1, payload["summary"]["transitions_total"])
            self.assertFalse(payload["summary"]["end_to_end_executed"])


if __name__ == "__main__":
    unittest.main()
