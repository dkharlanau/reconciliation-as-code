# SQL source and target adapters

Reconciliation specs can read source or target data directly from SQLite or PostgreSQL without storing database credentials in Git.

The control contains a **connection reference** and a read query. The actual SQLAlchemy URL is supplied at runtime through an environment variable.

## Example

```yaml
source:
  key: CUSTOMER_ID
  sql:
    connection: legacy-erp
    query: |
      SELECT CUSTOMER_ID, COUNTRY, CREDIT_LIMIT
      FROM migration_customers
      WHERE LOAD_WAVE = :wave
    params:
      wave: W3
    max_rows: 1000000
    timeout_seconds: 60
    chunk_size: 10000

target:
  key: LEGACY_ID
  sql:
    connection: s4-target
    query: |
      SELECT LEGACY_ID, COUNTRY, CREDIT_LIMIT
      FROM bp_migration_view
      WHERE LOAD_WAVE = :wave
    params:
      wave: W3
```

No URL, password, token, or certificate path is stored in the YAML.

## Connection environment variables

A connection reference is converted to an environment variable:

```text
legacy-erp  → RAC_CONNECTION_LEGACY_ERP
s4-target   → RAC_CONNECTION_S4_TARGET
```

SQLite:

```bash
export RAC_CONNECTION_LEGACY_ERP='sqlite:////data/legacy.db'
```

PostgreSQL:

```bash
export RAC_CONNECTION_S4_TARGET='postgresql+psycopg://user:password@db.example.internal:5432/migration'
```

Install dependencies with:

```bash
pip install -e '.[sql]'
```

For PostgreSQL:

```bash
pip install -e '.[postgres]'
```

## Run

```bash
rac run reconciliation.yaml --evidence build/evidence.json
```

The extracted rows can also be handed to the DuckDB backend:

```bash
rac run reconciliation.yaml --engine duckdb
```

This is useful when a database query returns a large flat extract: SQLAlchemy streams query results in chunks to a bounded temporary CSV, and DuckDB performs the reconciliation joins/aggregates without building a full Python row dictionary.

## Safety controls

SQL inputs are not arbitrary database scripts.

### Read-only execution

The adapter accepts queries beginning with `SELECT` or `WITH` and additionally enforces database read-only mode:

- PostgreSQL: `SET TRANSACTION READ ONLY`;
- SQLite: `PRAGMA query_only = ON`.

The second control is important because a `WITH` query can otherwise contain data-modifying statements on databases that support them.

Use a database account that is already read-only as the primary security boundary. The runtime restrictions are defense in depth.

### Row limit

Every query has an explicit safety ceiling:

```yaml
max_rows: 1000000
```

The default is 1,000,000 rows. If the streamed result exceeds the limit, execution stops with an execution error rather than silently truncating data.

### Timeout

```yaml
timeout_seconds: 60
```

The default is 60 seconds per endpoint query.

- PostgreSQL uses `statement_timeout` inside the read-only transaction;
- SQLite uses a progress handler that interrupts long-running queries.

### Chunking

```yaml
chunk_size: 10000
```

Rows are fetched with streaming result semantics and written to the temporary extract in chunks. The default chunk size is 10,000.

## Evidence and provenance

The database URL is never copied into evidence. A SQL input is represented with metadata such as:

```json
{
  "path": "sql:legacy-erp",
  "input_type": "sql",
  "connection_ref": "legacy-erp",
  "dialect": "postgresql",
  "query_sha256": "...",
  "sha256": "...",
  "rows": 248000,
  "max_rows": 1000000,
  "timeout_seconds": 60.0,
  "chunk_size": 10000
}
```

`query_sha256` fingerprints the query plus bound parameter values without exposing those values. `sha256` fingerprints the actual temporary extract consumed by reconciliation.

Only parameter **names** are exposed in evidence.

## Supported combinations

- CSV → SQL
- SQL → CSV
- SQL → SQL
- SQL extraction → Python reference engine
- SQL extraction → DuckDB flat-data engine

SQLite and PostgreSQL are the first explicitly supported/tested dialects. Other SQLAlchemy dialects are rejected until their read-only and timeout semantics are implemented and tested.

## Runnable SQLite example

```bash
python examples/sql-sqlite/setup.py

export RAC_CONNECTION_LEGACY_SQLITE="sqlite:///$PWD/examples/sql-sqlite/legacy.db"
export RAC_CONNECTION_TARGET_SQLITE="sqlite:///$PWD/examples/sql-sqlite/target.db"

rac run examples/sql-sqlite/reconciliation.yaml --engine duckdb
```

CI also starts a real PostgreSQL service and verifies SQL→SQL reconciliation, statement timeout, and read-only transaction enforcement.
