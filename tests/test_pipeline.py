from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.pipeline import (
    load_pipeline_spec,
    render_pipeline_html,
    render_pipeline_markdown,
    run_pipeline,
    validate_pipeline_spec,
    write_pipeline_html,
    write_pipeline_json,
    write_pipeline_markdown,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "multi-stage"
SPEC_PATH = EXAMPLE / "pipeline.yaml"


class PipelineTests(unittest.TestCase):
    def test_four_stage_pipeline_identifies_first_divergence(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        result = run_pipeline(spec, base_dir=EXAMPLE, spec_path=SPEC_PATH)

        self.assertEqual("failed", result["status"])
        self.assertEqual(4, result["summary"]["stages_total"])
        self.assertEqual(3, result["summary"]["transitions_total"])
        self.assertEqual(2, result["summary"]["transitions_failed"])
        self.assertEqual("failed", result["summary"]["end_to_end_status"])

        transitions = {item["id"]: item for item in result["transitions"]}
        self.assertEqual("passed", transitions["source-to-extract"]["status"])
        self.assertEqual("failed", transitions["extract-to-transformed"]["status"])
        self.assertEqual("failed", transitions["transformed-to-target"]["status"])

        divergences = {
            (item["check_id"], json.dumps(item["locator"], sort_keys=True)): item
            for item in result["first_divergence"]
        }
        amount = divergences[("amount", json.dumps({"key": "1002"}, sort_keys=True))]
        self.assertEqual("extract-to-transformed", amount["first_transition"])
        self.assertEqual("extract", amount["from_stage"])
        self.assertEqual("transformed", amount["to_stage"])

        coverage = divergences[
            ("coverage", json.dumps({"difference": "missing_in_target", "key": "1002"}, sort_keys=True))
        ]
        self.assertEqual("transformed-to-target", coverage["first_transition"])

    def test_expected_country_transformation_does_not_create_false_drift(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        result = run_pipeline(spec, base_dir=EXAMPLE)
        middle = next(item for item in result["transitions"] if item["id"] == "extract-to-transformed")
        country = next(item for item in middle["evidence"]["checks"] if item["id"] == "country")
        self.assertEqual("passed", country["status"])
        self.assertEqual(0, country["metrics"]["mismatches"])

    def test_stage_fingerprints_are_captured(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        result = run_pipeline(spec, base_dir=EXAMPLE)
        self.assertEqual(4, len(result["stages"]))
        for stage in result["stages"]:
            self.assertEqual(64, len(stage["sha256"]))
            self.assertEqual("file", stage["input_type"])
        self.assertEqual("baseline", result["stages"][0]["status"])
        self.assertEqual("passed", result["stages"][1]["status"])
        self.assertEqual("failed", result["stages"][2]["status"])

    def test_subset_of_stages_runs_only_selected_transition(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        result = run_pipeline(
            spec,
            base_dir=EXAMPLE,
            from_stage="source",
            to_stage="extract",
        )
        self.assertEqual("passed", result["status"])
        self.assertEqual(2, result["summary"]["stages_total"])
        self.assertEqual(1, result["summary"]["transitions_total"])
        self.assertEqual(0, result["summary"]["first_divergences"])
        self.assertFalse(result["summary"]["end_to_end_executed"])
        self.assertEqual(["source-to-extract"], [item["id"] for item in result["transitions"]])

    def test_invalid_reverse_or_single_stage_subset_is_rejected(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        with self.assertRaisesRegex(Exception, "at least one forward transition"):
            run_pipeline(spec, base_dir=EXAMPLE, from_stage="target", to_stage="source")
        with self.assertRaisesRegex(Exception, "at least one forward transition"):
            run_pipeline(spec, base_dir=EXAMPLE, from_stage="extract", to_stage="extract")

    def test_missing_adjacent_transition_is_invalid(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        spec["transitions"] = [
            item for item in spec["transitions"] if item["id"] != "extract-to-transformed"
        ]
        with self.assertRaisesRegex(Exception, "Missing adjacent transition"):
            validate_pipeline_spec(spec)

    def test_reports_visualize_stage_path_and_first_divergence(self) -> None:
        spec = load_pipeline_spec(SPEC_PATH)
        result = run_pipeline(spec, base_dir=EXAMPLE)
        markdown = render_pipeline_markdown(result)
        html = render_pipeline_html(result)
        self.assertIn("First divergence", markdown)
        self.assertIn("extract → transformed", markdown)
        self.assertIn("Stage path", html)
        self.assertIn("extract-to-transformed", html)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_pipeline_json(result, root / "pipeline.json")
            write_pipeline_markdown(result, root / "pipeline.md")
            write_pipeline_html(result, root / "pipeline.html")
            self.assertTrue((root / "pipeline.json").exists())
            self.assertTrue((root / "pipeline.md").exists())
            self.assertTrue((root / "pipeline.html").exists())


if __name__ == "__main__":
    unittest.main()
