from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from reconciliation_as_code.cli import main as cli_main
from reconciliation_as_code.duckdb_engine import run_reconciliation_duckdb
from reconciliation_as_code.governance import run_reconciliation_with_governance
from reconciliation_as_code.spec import load_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def check_by_id(result: dict, check_id: str) -> dict:
    return next(item for item in result["checks"] if item["id"] == check_id)


class DuckDBBackendTests(unittest.TestCase):
    def test_python_and_duckdb_match_core_flat_semantics(self) -> None:
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
                "reconciliation": {"name": "backend-equivalence"},
                "source": {
                    "file": "source.csv",
                    "key": "ID",
                    "key_normalize": ["trim", "strip_leading_zeros"],
                },
                "target": {
                    "file": "target.csv",
                    "key": "LEGACY_ID",
                    "key_normalize": ["trim", "strip_leading_zeros"],
                },
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
                    {
                        "id": "amount-total",
                        "type": "control_total",
                        "source": "AMOUNT",
                        "target": "AMOUNT",
                        "tolerance": 0,
                    },
                ],
            }

            python_result = run_reconciliation_with_governance(spec, base_dir=base, backend="python")
            duckdb_result = run_reconciliation_with_governance(spec, base_dir=base, backend="duckdb")

            self.assertEqual(python_result["status"], duckdb_result["status"])
            for metric in (
                "source_records",
                "target_records",
                "matched_records",
                "missing_in_target",
                "unexpected_in_target",
                "checks_failed",
            ):
                self.assertEqual(python_result["summary"][metric], duckdb_result["summary"][metric])
            for check_id in ("coverage", "country", "amount", "amount-total"):
                self.assertEqual(
                    check_by_id(python_result, check_id)["status"],
                    check_by_id(duckdb_result, check_id)["status"],
                    check_id,
                )
            self.assertEqual("duckdb", duckdb_result["run"]["backend"])

    def test_duckdb_runs_scoped_grouped_example(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec_path = root / "examples" / "scoped-controls" / "reconciliation.yaml"
        spec = load_spec(spec_path)
        python_result = run_reconciliation_with_governance(
            spec, base_dir=spec_path.parent, spec_path=spec_path, backend="python"
        )
        duckdb_result = run_reconciliation_with_governance(
            spec, base_dir=spec_path.parent, spec_path=spec_path, backend="duckdb"
        )

        self.assertEqual(python_result["status"], duckdb_result["status"])
        for check_id in (
            "coverage",
            "active-customer-count-by-country",
            "active-credit-by-company",
            "active-last-change-date",
        ):
            left = check_by_id(python_result, check_id)
            right = check_by_id(duckdb_result, check_id)
            self.assertEqual(left["status"], right["status"], check_id)
            self.assertEqual(left["severity"], right["severity"], check_id)

    def test_parquet_is_read_without_conversion_to_python_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_parquet = base / "source.parquet"
            target_parquet = base / "target.parquet"
            connection = duckdb.connect(database=":memory:")
            connection.execute("CREATE TABLE source AS SELECT * FROM (VALUES ('1','DE','10'), ('2','US','20')) t(ID, COUNTRY, AMOUNT)")
            connection.execute("CREATE TABLE target AS SELECT * FROM (VALUES ('1','DE','10'), ('2','US','20')) t(ID, COUNTRY, AMOUNT)")
            connection.execute(f"COPY source TO '{source_parquet.as_posix()}' (FORMAT PARQUET)")
            connection.execute(f"COPY target TO '{target_parquet.as_posix()}' (FORMAT PARQUET)")
            connection.close()

            spec = {
                "version": 1,
                "reconciliation": {"name": "parquet"},
                "source": {"file": "source.parquet", "format": "parquet", "key": "ID"},
                "target": {"file": "target.parquet", "format": "parquet", "key": "ID"},
                "checks": [
                    {"id": "coverage", "type": "record_coverage"},
                    {"id": "country", "type": "field_match", "source": "COUNTRY", "target": "COUNTRY"},
                    {"id": "total", "type": "control_total", "source": "AMOUNT", "target": "AMOUNT", "tolerance": 0},
                ],
            }
            result = run_reconciliation_duckdb(spec, base_dir=base)
            self.assertEqual("passed", result["status"])
            self.assertEqual(2, result["summary"]["matched_records"])
            self.assertEqual("duckdb", result["run"]["backend"])

    def test_duckdb_refuses_hierarchy_until_streaming_semantics_exist(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec_path = root / "examples" / "customer-bp-hierarchy" / "reconciliation.yaml"
        spec = load_spec(spec_path)
        with self.assertRaisesRegex(Exception, "flat reconciliations only"):
            run_reconciliation_with_governance(
                spec, base_dir=spec_path.parent, spec_path=spec_path, backend="duckdb"
            )

    def test_cli_engine_option_writes_backend_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_csv(base / "source.csv", [{"ID": "1", "VALUE": "A"}])
            write_csv(base / "target.csv", [{"ID": "1", "VALUE": "A"}])
            spec = base / "reconciliation.yaml"
            spec.write_text(
                """version: 1
reconciliation:
  name: cli-duckdb
source:
  file: source.csv
  key: ID
target:
  file: target.csv
  key: ID
checks:
  - id: coverage
    type: record_coverage
""",
                encoding="utf-8",
            )
            evidence = base / "evidence.json"
            report = base / "evidence.md"
            exit_code = cli_main(
                [
                    "run",
                    str(spec),
                    "--engine",
                    "duckdb",
                    "--evidence",
                    str(evidence),
                    "--report",
                    str(report),
                ]
            )
            self.assertEqual(0, exit_code)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("duckdb", payload["run"]["backend"])


if __name__ == "__main__":
    unittest.main()
