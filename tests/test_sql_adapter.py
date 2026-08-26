from __future__ import annotations

import csv
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reconciliation_as_code.cli import main as cli_main
from reconciliation_as_code.runtime import run_reconciliation_runtime
from reconciliation_as_code.spec import validate_spec


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def create_sqlite(path: Path, rows: list[tuple[str, str, str]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE TABLE customers (id TEXT PRIMARY KEY, country TEXT, amount TEXT)")
        connection.executemany("INSERT INTO customers VALUES (?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()


def sql_endpoint(reference: str, query: str = "SELECT id, country, amount FROM customers") -> dict:
    return {
        "key": "id",
        "sql": {
            "connection": reference,
            "query": query,
            "max_rows": 1000,
            "timeout_seconds": 5,
            "chunk_size": 2,
        },
    }


def base_checks() -> list[dict]:
    return [
        {"id": "coverage", "type": "record_coverage"},
        {"id": "country", "type": "field_match", "source": "country", "target": "country"},
        {"id": "amount", "type": "field_match", "source": "amount", "target": "amount", "numeric_tolerance": 0},
        {"id": "total", "type": "control_total", "source": "amount", "target": "amount", "tolerance": 0},
    ]


class SqlAdapterTests(unittest.TestCase):
    def test_sql_to_sql_reconciliation_uses_env_refs_and_safe_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_db = base / "source.db"
            target_db = base / "target.db"
            rows = [("1", "DE", "10"), ("2", "US", "20")]
            create_sqlite(source_db, rows)
            create_sqlite(target_db, rows)
            spec = {
                "version": 1,
                "reconciliation": {"name": "sqlite-sql-to-sql"},
                "source": sql_endpoint("legacy-db"),
                "target": sql_endpoint("target-db"),
                "checks": base_checks(),
            }
            validate_spec(spec)
            env = {
                "RAC_CONNECTION_LEGACY_DB": f"sqlite:///{source_db.as_posix()}",
                "RAC_CONNECTION_TARGET_DB": f"sqlite:///{target_db.as_posix()}",
            }
            with patch.dict(os.environ, env, clear=False):
                result = run_reconciliation_runtime(spec, base_dir=base, backend="python")

            self.assertEqual("passed", result["status"])
            self.assertEqual(2, result["summary"]["matched_records"])
            self.assertEqual("sql", result["inputs"]["source"]["input_type"])
            self.assertEqual("legacy-db", result["inputs"]["source"]["connection_ref"])
            self.assertEqual("sqlite", result["inputs"]["source"]["dialect"])
            self.assertEqual(64, len(result["inputs"]["source"]["query_sha256"]))
            self.assertEqual(2, result["inputs"]["source"]["rows"])
            serialized = json.dumps(result)
            self.assertNotIn("sqlite:///", serialized)
            self.assertNotIn(source_db.as_posix(), serialized)

    def test_csv_to_sql_can_use_duckdb_after_chunked_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source_csv = base / "source.csv"
            target_db = base / "target.db"
            write_csv(
                source_csv,
                [
                    {"id": "1", "country": "DE", "amount": "10"},
                    {"id": "2", "country": "US", "amount": "20"},
                ],
            )
            create_sqlite(target_db, [("1", "DE", "10"), ("2", "US", "20")])
            spec = {
                "version": 1,
                "reconciliation": {"name": "csv-to-sql"},
                "source": {"file": "source.csv", "key": "id"},
                "target": sql_endpoint("target-db"),
                "checks": base_checks(),
            }
            with patch.dict(
                os.environ,
                {"RAC_CONNECTION_TARGET_DB": f"sqlite:///{target_db.as_posix()}"},
                clear=False,
            ):
                result = run_reconciliation_runtime(spec, base_dir=base, backend="duckdb")

            self.assertEqual("passed", result["status"])
            self.assertEqual("duckdb", result["run"]["backend"])
            self.assertEqual("sql", result["inputs"]["target"]["input_type"])
            self.assertEqual(2, result["sql_inputs"]["target"]["rows"])

    def test_row_limit_is_a_hard_safety_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            database = base / "data.db"
            create_sqlite(database, [("1", "DE", "10"), ("2", "US", "20"), ("3", "GB", "30")])
            source = sql_endpoint("limited-db")
            source["sql"]["max_rows"] = 2
            spec = {
                "version": 1,
                "reconciliation": {"name": "row-limit"},
                "source": source,
                "target": sql_endpoint("limited-db"),
                "checks": [{"id": "coverage", "type": "record_coverage"}],
            }
            with patch.dict(
                os.environ,
                {"RAC_CONNECTION_LIMITED_DB": f"sqlite:///{database.as_posix()}"},
                clear=False,
            ):
                with self.assertRaisesRegex(Exception, "exceeded max_rows=2"):
                    run_reconciliation_runtime(spec, base_dir=base)

    def test_sqlite_query_timeout_interrupts_long_query(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            database = base / "timeout.db"
            create_sqlite(database, [("1", "DE", "10")])
            long_query = """WITH RECURSIVE cnt(x) AS (
  SELECT 1
  UNION ALL
  SELECT x + 1 FROM cnt WHERE x < 100000000
)
SELECT CAST(x AS TEXT) AS id, 'DE' AS country, '1' AS amount FROM cnt
"""
            endpoint = sql_endpoint("timeout-db", long_query)
            endpoint["sql"]["timeout_seconds"] = 0.001
            endpoint["sql"]["max_rows"] = 100000000
            spec = {
                "version": 1,
                "reconciliation": {"name": "timeout"},
                "source": endpoint,
                "target": {"file": "unused.csv", "key": "id"},
                "checks": [{"id": "coverage", "type": "record_coverage"}],
            }
            write_csv(base / "unused.csv", [{"id": "1", "country": "DE", "amount": "1"}])
            with patch.dict(
                os.environ,
                {"RAC_CONNECTION_TIMEOUT_DB": f"sqlite:///{database.as_posix()}"},
                clear=False,
            ):
                with self.assertRaisesRegex(Exception, "SQL extraction failed"):
                    run_reconciliation_runtime(spec, base_dir=base)

    def test_missing_connection_env_is_execution_error_without_credentials(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "missing-connection"},
            "source": sql_endpoint("definitely-missing"),
            "target": {"file": "target.csv", "key": "id"},
            "checks": [{"id": "coverage", "type": "record_coverage"}],
        }
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(Exception, "RAC_CONNECTION_DEFINITELY_MISSING"):
                run_reconciliation_runtime(spec)

    def test_write_statement_is_rejected_at_spec_validation(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "write-rejected"},
            "source": sql_endpoint("db", "DELETE FROM customers"),
            "target": {"file": "target.csv", "key": "id"},
            "checks": [{"id": "coverage", "type": "record_coverage"}],
        }
        with self.assertRaisesRegex(Exception, "beginning with SELECT or WITH"):
            validate_spec(spec)

    def test_cli_sql_run_does_not_need_connection_url_in_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            database = base / "cli.db"
            create_sqlite(database, [("1", "DE", "10")])
            spec_path = base / "reconciliation.yaml"
            spec_path.write_text(
                """version: 1
reconciliation:
  name: cli-sql
source:
  key: id
  sql:
    connection: cli-db
    query: SELECT id, country, amount FROM customers
    max_rows: 100
    timeout_seconds: 5
target:
  key: id
  sql:
    connection: cli-db
    query: SELECT id, country, amount FROM customers
    max_rows: 100
    timeout_seconds: 5
checks:
  - id: coverage
    type: record_coverage
""",
                encoding="utf-8",
            )
            evidence = base / "evidence.json"
            report = base / "evidence.md"
            with patch.dict(
                os.environ,
                {"RAC_CONNECTION_CLI_DB": f"sqlite:///{database.as_posix()}"},
                clear=False,
            ):
                code = cli_main(
                    [
                        "run",
                        str(spec_path),
                        "--evidence",
                        str(evidence),
                        "--report",
                        str(report),
                    ]
                )
            self.assertEqual(0, code)
            payload = json.loads(evidence.read_text(encoding="utf-8"))
            self.assertEqual("sqlite", payload["inputs"]["source"]["dialect"])
            self.assertNotIn("sqlite:///", evidence.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
