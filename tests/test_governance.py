from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from reconciliation_as_code.governance import run_reconciliation_with_governance


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


class ExceptionGovernanceTests(unittest.TestCase):
    def test_accepted_field_difference_can_make_net_result_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": "A"}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": "B"}])
            (base / "exceptions.yaml").write_text(
                """version: 1
exceptions:
  - check: value
    key: '1'
    field: VALUE
    reason_code: approved-conversion
    reason: Accepted project conversion difference
    owner: migration-lead
    reference: CUT-123
""",
                encoding="utf-8",
            )
            spec = {
                "version": 1,
                "reconciliation": {"name": "accepted"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [
                    {"id": "coverage", "type": "record_coverage"},
                    {"id": "value", "type": "field_match", "source": "VALUE", "target": "VALUE"},
                ],
                "exceptions": {"file": "exceptions.yaml", "expiry_policy": "error"},
            }
            result = run_reconciliation_with_governance(spec, base_dir=base)
            self.assertEqual("passed", result["status"])
            self.assertEqual(1, result["summary"]["accepted_exceptions"])
            value = next(item for item in result["checks"] if item["id"] == "value")
            self.assertEqual(1, value["metrics"]["gross_failures"])
            self.assertEqual(0, value["metrics"]["unaccepted_failures"])
            self.assertEqual("accepted-exception", value["details"][0]["disposition"])
            self.assertIn("exceptions", result["inputs"])

    def test_unlisted_difference_still_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": "A"}, {"ID": "2", "VALUE": "C"}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": "B"}, {"ID": "2", "VALUE": "D"}])
            (base / "exceptions.yaml").write_text(
                """version: 1
exceptions:
  - check: value
    key: '1'
    reason_code: known
    reason: Known difference
""",
                encoding="utf-8",
            )
            spec = {
                "version": 1,
                "reconciliation": {"name": "partial"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [{"id": "value", "type": "field_match", "source": "VALUE", "target": "VALUE"}],
                "exceptions": {"file": "exceptions.yaml"},
            }
            result = run_reconciliation_with_governance(spec, base_dir=base)
            self.assertEqual("failed", result["status"])
            value = next(item for item in result["checks"] if item["id"] == "value")
            self.assertEqual(2, value["metrics"]["gross_failures"])
            self.assertEqual(1, value["metrics"]["accepted_exceptions"])
            self.assertEqual(1, value["metrics"]["unaccepted_failures"])

    def test_expired_exception_is_visible_and_can_fail_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": "A"}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": "B"}])
            (base / "exceptions.yaml").write_text(
                """version: 1
exceptions:
  - check: value
    key: '1'
    reason_code: temporary
    reason: Temporary exception
    expires: 2000-01-01
""",
                encoding="utf-8",
            )
            spec = {
                "version": 1,
                "reconciliation": {"name": "expired"},
                "source": {"file": "source.csv", "key": "ID"},
                "target": {"file": "target.csv", "key": "ID"},
                "checks": [{"id": "value", "type": "field_match", "source": "VALUE", "target": "VALUE"}],
                "exceptions": {"file": "exceptions.yaml", "expiry_policy": "error"},
            }
            result = run_reconciliation_with_governance(spec, base_dir=base)
            self.assertEqual("failed", result["status"])
            self.assertEqual(1, result["summary"]["expired_exceptions"])
            policy = next(item for item in result["checks"] if item["id"] == "accepted-exceptions-policy")
            self.assertEqual("failed", policy["status"])
            self.assertEqual(1, policy["metrics"]["entries_expired"])


if __name__ == "__main__":
    unittest.main()
