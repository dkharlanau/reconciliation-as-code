from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


def generate(rows: int, output: Path) -> Path:
    output.mkdir(parents=True, exist_ok=True)
    source = output / "source.csv"
    target = output / "target.csv"
    query = f"""
        SELECT
            lpad(CAST(i AS VARCHAR), 10, '0') AS ID,
            CASE i % 4 WHEN 0 THEN 'DE' WHEN 1 THEN 'US' WHEN 2 THEN 'GB' ELSE 'CN' END AS COUNTRY,
            'C' || lpad(CAST(i % 20 AS VARCHAR), 2, '0') AS COMPANY_CODE,
            CAST((i % 100000) + 0.25 AS DECIMAL(18,2)) AS AMOUNT,
            'Y' AS ACTIVE,
            DATE '2026-01-01' + CAST(i % 200 AS INTEGER) AS LAST_CHANGED
        FROM range({rows}) t(i)
    """
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(
            f"COPY ({query}) TO '{source.as_posix()}' (FORMAT CSV, HEADER, DELIMITER ',')"
        )
        connection.execute(
            f"COPY ({query}) TO '{target.as_posix()}' (FORMAT CSV, HEADER, DELIMITER ',')"
        )
    finally:
        connection.close()

    spec = output / "reconciliation.yaml"
    spec.write_text(
        f"""version: 1

reconciliation:
  name: DuckDB {rows}-row benchmark
  description: Deterministic large-file benchmark generated from DuckDB range().

source:
  file: source.csv
  key: ID

target:
  file: target.csv
  key: ID

scopes:
  active:
    source:
      field: ACTIVE
      op: eq
      value: Y
    target:
      field: ACTIVE
      op: eq
      value: Y

checks:
  - id: coverage
    type: record_coverage

  - id: country
    type: field_match
    source: COUNTRY
    target: COUNTRY

  - id: amount-total
    type: control_total
    source: AMOUNT
    target: AMOUNT
    tolerance: 0

  - id: count-by-country
    type: aggregate_match
    operation: count
    scope: active
    group_by:
      source: COUNTRY
      target: COUNTRY
    tolerance: 0

  - id: amount-by-company
    type: aggregate_match
    operation: sum
    source: AMOUNT
    target: AMOUNT
    group_by:
      source: COMPANY_CODE
      target: COMPANY_CODE
    tolerance: 0

  - id: last-change
    type: field_match
    source: LAST_CHANGED
    target: LAST_CHANGED
    date_tolerance_days: 0

evidence:
  detail_limit: 10
""",
        encoding="utf-8",
    )
    return spec


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Reconciliation as Code scale fixtures.")
    parser.add_argument("--rows", type=int, default=1_000_000)
    parser.add_argument("--output", type=Path, default=Path("build/benchmark"))
    args = parser.parse_args()
    if args.rows < 1:
        parser.error("--rows must be >= 1")
    spec = generate(args.rows, args.output)
    print(f"rows={args.rows} spec={spec}")


if __name__ == "__main__":
    main()
