from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine

from reconciliation_as_code.runtime import run_reconciliation_runtime


POSTGRES_URL = os.environ.get("RAC_TEST_POSTGRES_URL")


def endpoint(reference: str, query: str, *, timeout: float = 5) -> dict:
    return {
        "key": "id",
        "sql": {
            "connection": reference,
            "query": query,
            "max_rows": 1000,
            "timeout_seconds": timeout,
            "chunk_size": 2,
        },
    }


@unittest.skipUnless(POSTGRES_URL, "RAC_TEST_POSTGRES_URL is not configured")
class PostgreSqlAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine(POSTGRES_URL)
        with cls.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS rac_source")
            connection.exec_driver_sql("DROP TABLE IF EXISTS rac_target")
            connection.exec_driver_sql(
                "CREATE TABLE rac_source (id text primary key, country text, amount numeric)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE rac_target (id text primary key, country text, amount numeric)"
            )
            connection.exec_driver_sql(
                "INSERT INTO rac_source VALUES ('1','DE',10),('2','US',20)"
            )
            connection.exec_driver_sql(
                "INSERT INTO rac_target VALUES ('1','DE',10),('2','US',20)"
            )

    @classmethod
    def tearDownClass(cls) -> None:
        with cls.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE IF EXISTS rac_source")
            connection.exec_driver_sql("DROP TABLE IF EXISTS rac_target")
        cls.engine.dispose()

    def _environment(self) -> dict[str, str]:
        assert POSTGRES_URL is not None
        return {
            "RAC_CONNECTION_PG_SOURCE": POSTGRES_URL,
            "RAC_CONNECTION_PG_TARGET": POSTGRES_URL,
        }

    def test_postgresql_sql_to_sql_reconciliation_and_evidence(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "postgres-sql-to-sql"},
            "source": endpoint(
                "pg-source", "SELECT id, country, amount FROM rac_source ORDER BY id"
            ),
            "target": endpoint(
                "pg-target", "SELECT id, country, amount FROM rac_target ORDER BY id"
            ),
            "checks": [
                {"id": "coverage", "type": "record_coverage"},
                {
                    "id": "country",
                    "type": "field_match",
                    "source": "country",
                    "target": "country",
                },
                {
                    "id": "total",
                    "type": "control_total",
                    "source": "amount",
                    "target": "amount",
                    "tolerance": 0,
                },
            ],
        }
        with patch.dict(os.environ, self._environment(), clear=False):
            result = run_reconciliation_runtime(spec, backend="duckdb")

        self.assertEqual("passed", result["status"])
        self.assertEqual("postgresql", result["inputs"]["source"]["dialect"])
        self.assertEqual("duckdb", result["run"]["backend"])
        self.assertEqual(2, result["inputs"]["source"]["rows"])
        serialized = json.dumps(result)
        self.assertNotIn("postgresql+psycopg://", serialized)
        self.assertNotIn("postgres:postgres", serialized)

    def test_postgresql_statement_timeout_is_enforced(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "postgres-timeout"},
            "source": endpoint(
                "pg-source",
                "SELECT '1'::text AS id FROM (SELECT pg_sleep(1)) wait",
                timeout=0.01,
            ),
            "target": endpoint("pg-target", "SELECT '1'::text AS id"),
            "checks": [{"id": "coverage", "type": "record_coverage"}],
        }
        with patch.dict(os.environ, self._environment(), clear=False):
            with self.assertRaisesRegex(Exception, "SQL extraction failed"):
                run_reconciliation_runtime(spec)

    def test_postgresql_transaction_is_read_only_even_for_with_query(self) -> None:
        spec = {
            "version": 1,
            "reconciliation": {"name": "postgres-readonly"},
            "source": endpoint(
                "pg-source",
                "WITH deleted AS (DELETE FROM rac_source WHERE id='1' RETURNING id) SELECT id FROM deleted",
            ),
            "target": endpoint("pg-target", "SELECT id FROM rac_target"),
            "checks": [{"id": "coverage", "type": "record_coverage"}],
        }
        with patch.dict(os.environ, self._environment(), clear=False):
            with self.assertRaisesRegex(Exception, "SQL extraction failed"):
                run_reconciliation_runtime(spec)

        with self.engine.connect() as connection:
            remaining = connection.exec_driver_sql("SELECT count(*) FROM rac_source").scalar_one()
        self.assertEqual(2, remaining)


if __name__ == "__main__":
    unittest.main()
