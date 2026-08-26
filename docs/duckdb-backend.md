# DuckDB execution backend

`reconciliation-as-code` has two execution paths:

- `python` — the reference backend and the current choice for hierarchical objects and changed-ID merge/split reconciliation;
- `duckdb` — a query-based backend for large flat CSV/Parquet source-to-target reconciliations.

## Why

The reference Python engine deliberately keeps its implementation small and transparent, but its row dictionaries are not the right execution model for million-row migration extracts. The DuckDB backend pushes joins, filters, aggregates and mismatch classification into DuckDB and returns only bounded evidence details to Python.

```bash
pip install -e '.[duckdb]'

rac run reconciliation.yaml \
  --engine duckdb \
  --evidence build/evidence.json \
  --report build/evidence.md
```

The reconciliation YAML does not change when switching between `python` and `duckdb` for supported flat controls.

## Supported controls

The DuckDB backend currently executes:

- CSV and Parquet source/target inputs;
- single and composite business keys;
- key normalization, including leading-zero handling;
- duplicate-key integrity checks;
- endpoint filters, named scopes and `when` predicates;
- record coverage;
- normalized/mapping-aware field comparison;
- numeric, percentage and date tolerances;
- control totals;
- row counts;
- aggregate-by-dimension `count`, `distinct_count` and `sum` checks;
- accepted-exception governance and materiality after deterministic execution.

Evidence retains the same canonical schema. DuckDB runs add:

```json
{
  "run": {
    "backend": "duckdb",
    "duckdb_version": "..."
  }
}
```

## Parquet

Parquet is a published endpoint format for the DuckDB backend:

```yaml
source:
  file: legacy.parquet
  format: parquet
  key: CUSTOMER_ID

target:
  file: s4.parquet
  format: parquet
  key: LEGACY_ID
```

The Python reference backend does not currently read Parquet. Use `--engine duckdb` for Parquet specs.

## Scale evidence

CI contains a separate `duckdb-million-row` gate. It generates two deterministic 1,000,000-row migration extracts and runs coverage, row-level comparisons, dates, totals and grouped controls against them. The resulting evidence must report:

- `source_records = 1,000,000`;
- `target_records = 1,000,000`;
- `matched_records = 1,000,000`;
- `status = passed`;
- `run.backend = duckdb`.

A manual benchmark workflow supports larger runs, with 5,000,000 rows as the default manual size. See [`benchmarks/README.md`](../benchmarks/README.md).

## Deliberate boundary

Hierarchy and identity crosswalk processing are currently rejected by the DuckDB backend:

```text
DuckDB backend currently supports flat reconciliations only.
Use --engine python for hierarchy/identity controls.
```

This is intentional. Those features currently transform child/identity data through the Python execution layer, so claiming million-row DuckDB scale for them would be misleading. They will move to the scalable backend only when their full processing path is query/stream based.

## Choosing an engine

| Scenario | Engine |
| --- | --- |
| Small/medium CSV or Excel comparison | `python` |
| Customer/BP hierarchy | `python` |
| Changed IDs, 1:N split, N:1 merge | `python` |
| Large flat CSV reconciliation | `duckdb` |
| Parquet reconciliation | `duckdb` |
| Million-row grouped controls | `duckdb` |

The engine is an execution choice, not a different control language. The product goal is to keep business reconciliation semantics and evidence stable while allowing execution strategies to evolve independently.
