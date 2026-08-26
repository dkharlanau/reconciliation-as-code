# Specification reference

A reconciliation specification is a versioned YAML document describing source and target state, business identity, scope, and the controls that must hold between them.

## Minimal structure

```yaml
version: 1
reconciliation:
  name: Customer migration
source:
  file: legacy.csv
  key: CUSTOMER_ID
target:
  file: s4.csv
  key: LEGACY_ID
checks:
  - id: coverage
    type: record_coverage
```

File paths are resolved relative to the YAML file. CSV is supported without optional dependencies. `.xlsx` and `.xlsm` require `openpyxl`. Parquet is a published file format for the DuckDB backend.

## Source and target endpoints

A top-level `source` or `target` defines **exactly one** of `file` or `sql`, plus its business key.

### File endpoint

```yaml
source:
  file: legacy.csv
  key: CUSTOMER_ID
  key_normalize: [trim, strip_leading_zeros]
```

Supported properties:

| Property | Meaning |
| --- | --- |
| `file` | Relative or absolute input path. |
| `key` | One business-key field or a list for composite keys. |
| `format` | Optional override: `csv`, `xlsx`, `xlsm`, or `parquet`. |
| `delimiter` | CSV delimiter, default `,`. |
| `sheet` | Excel sheet name; first sheet is used when omitted. |
| `key_normalize` | Normalizers applied before key matching. Default: `[trim]`. |
| `filter` | Optional predicate selecting the dataset that is globally in scope. |

Parquet is executed through `--engine duckdb`. Excel is executed through the Python reference backend.

### SQL endpoint

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
```

SQL endpoint properties:

| Property | Meaning |
| --- | --- |
| `connection` | Logical connection reference. Runtime URL comes from `RAC_CONNECTION_<REF>`. |
| `query` | Read query beginning with `SELECT` or `WITH`. |
| `params` | Optional bound parameters. |
| `max_rows` | Hard safety ceiling, default `1,000,000`. |
| `timeout_seconds` | Per-query timeout, default `60`. |
| `chunk_size` | Streaming fetch size, default `10,000`. |

Only SQLite and PostgreSQL are currently accepted. Runtime URLs/credentials are not stored in YAML or evidence. See [SQL source and target adapters](sql-adapters.md).

SQL query results are streamed to bounded temporary CSV extracts before reconciliation. Those extracts can feed either the Python backend or `--engine duckdb` for large flat controls.

### Normalizers

Supported key and field normalizers are:

- `trim`
- `uppercase`
- `lowercase`
- `empty_to_null`
- `strip_leading_zeros`

Endpoint filters are applied before key integrity, global coverage, summary counts and all checks. Evidence records both raw and selected row counts plus the filter definition.

## Predicate language

Filters, named scopes and conditional checks use the same deterministic predicate structure.

```yaml
field: COUNTRY
op: in
value: [DE, AT, CH]
normalize: [trim, uppercase]
```

Operators: `eq`, `ne`, `in`, `not_in`, `contains`, `starts_with`, `is_null`, `not_null`, `gt`, `gte`, `lt`, `lte`.

Predicates can be composed without executing arbitrary expressions:

```yaml
all:
  - field: ACTIVE
    op: eq
    value: Y
  - any:
      - field: COUNTRY
        op: eq
        value: DE
      - field: COUNTRY
        op: eq
        value: AT
```

Logical forms are `all`, `any`, and `not`.

## Reusable scopes

Use `scopes` when multiple controls apply to the same business population.

```yaml
scopes:
  active-customers:
    source:
      field: ACTIVE
      op: eq
      value: Y
    target:
      field: ACTIVE
      op: eq
      value: Y

checks:
  - id: active-count
    type: row_count
    scope: active-customers
```

Source and target predicates are intentionally separate because field names or encodings may differ.

## Conditional checks

`when` narrows one check without defining a reusable scope.

```yaml
- id: tax-number
  type: field_match
  source: TAX_NUMBER
  target: TAX_NO
  when:
    source:
      field: COUNTRY
      op: eq
      value: DE
    target:
      field: COUNTRY_CODE
      op: eq
      value: DE
```

For matched-record field checks, a pair is compared only when all supplied source/target scope and `when` predicates are satisfied. Evidence reports compared and skipped counts.

## Checks

### `record_coverage`

Compares source and target business-key sets. It reports matched keys, source keys missing from target, and unexpected target keys. Set `allow_unexpected: true` when target-only rows are valid. A named `scope` or `when` can restrict the population.

### `field_match`

Compares a source field and target field for matched business identities.

```yaml
- id: country
  type: field_match
  source: COUNTRY
  target: COUNTRY_CODE
  normalize: [trim, uppercase]
  map:
    DE: DEU
    US: USA
```

Optional controls:

- `map`: translate normalized source values before comparison;
- `numeric_tolerance`: absolute numeric tolerance;
- `percentage_tolerance`: percentage difference relative to source;
- `date_tolerance_days`: ISO date/datetime difference allowed in days;
- `null_semantics`: `equal`, `empty_is_null`, or `never_equal`;
- `max_mismatches`: permit a bounded number of raw mismatches;
- `scope`: apply a named reusable population;
- `when`: apply check-specific source/target predicates;
- `severity: warning`: record the failure without failing the run;
- `materiality`: optional check-local business materiality override.

If absolute and percentage numeric tolerances are both supplied, satisfying either passes the value comparison.

### `control_total`

Sums numeric source and target fields and compares the absolute difference against `tolerance`.

```yaml
- id: credit-total
  type: control_total
  source: CREDIT_LIMIT
  target: CREDIT_LIMIT
  scope: active-customers
  tolerance: 0.01
```

Blank numeric cells count as zero. Non-numeric values cause a data error.

### `row_count`

Compares source and target row counts with integer `tolerance`. Named scopes and `when` predicates are supported.

### `aggregate_match`

Compares business controls by one or more dimensions. Supported operations: `count`, `distinct_count`, `sum`.

```yaml
- id: credit-by-company
  type: aggregate_match
  operation: sum
  source: CREDIT_LIMIT
  target: CREDIT_LIMIT
  group_by:
    source: COMPANY_CODE
    target: COMPANY_CODE
  tolerance: 0.01
  percentage_tolerance: 0.1
```

`group_by.source` and `group_by.target` may be lists for composite dimensions. Failed evidence identifies the exact group and values.

## Hierarchical child collections

`children` turns a root comparison into an enterprise-object reconciliation.

```yaml
object:
  type: CustomerBP

children:
  addresses:
    source:
      file: legacy_addresses.csv
      key: [CUSTOMER_ID, ADDRESS_TYPE]
      parent_key: CUSTOMER_ID
    target:
      file: bp_addresses.csv
      key: [LEGACY_ID, ADDRESS_TYPE]
      parent_key: LEGACY_ID
    checks:
      - id: coverage
        type: record_coverage
```

Child endpoints are currently file-based. They have their own keys and a `parent_key` that links discrepancies back to the root object. See [Hierarchical enterprise objects](hierarchical-objects.md).

## Identity crosswalks

Use `identity` when target IDs or cardinality change.

```yaml
identity:
  crosswalk:
    file: crosswalk.csv
    source_key: LEGACY_ID
    target_key: BP_ID
```

The engine supports explicit `1:1`, `1:N`, and `N:1` components. Ambiguous `N:N` components are rejected. Aggregation policies must be explicit when multiple records must be reduced before field comparison. See [Identity crosswalks](identity-crosswalks.md).

## Governed accepted exceptions

```yaml
exceptions:
  file: accepted-exceptions.yaml
  expiry_policy: error
```

The separate artifact identifies exact check/key or check/group discrepancies with reason, optional owner/reference, and expiry. Exceptions never delete raw evidence. See [Governed accepted exceptions](accepted-exceptions.md).

## Materiality

```yaml
materiality:
  fields:
    NAME:
      severity: warning
      max_failures: 10
    CREDIT_LIMIT:
      critical: true
```

Materiality is applied after accepted exceptions. It changes the gate result while preserving raw status, counts and details. See [Materiality and business criticality](materiality.md).

## Automatic key-integrity controls

Every run adds source and target key-integrity checks after global endpoint filters. Duplicate business keys are errors because row-level comparison would otherwise be ambiguous. Broad default materiality does not silently waive automatic integrity controls.

## Execution backends

`rac run` defaults to:

```bash
rac run reconciliation.yaml --engine python
```

For large flat CSV/Parquet or SQL-extracted datasets:

```bash
rac run reconciliation.yaml --engine duckdb
```

The DuckDB backend currently rejects hierarchy/identity specs until those stages have a full query/stream-based implementation. See [DuckDB execution backend](duckdb-backend.md).

## Evidence

Canonical evidence contains:

- selected row counts and coverage totals;
- raw vs selected endpoint counts and filters;
- pass/fail status for every check;
- bounded mismatch/failing-group samples;
- scope-specific record counts;
- SHA-256 fingerprints of specs and file inputs;
- crosswalk and accepted-exception fingerprints;
- SQL query fingerprints and actual extracted-data fingerprints;
- SQL dialect/connection reference without runtime DSN/password;
- hierarchy/identity provenance where applicable;
- materiality raw-vs-final status;
- JSON for machines plus Markdown/HTML/XLSX/CSV for review.

Use `evidence.detail_limit` to cap detailed mismatch rows.

Expose published contracts with:

```bash
rac schema spec
rac schema evidence
```

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Reconciliation passed, or `--no-fail-on-diff` was used. |
| `1` | One or more effective error-severity controls failed. |
| `2` | Invalid specification, input, connection, or execution error. |
