# Reconciliation as Code

**Version migration controls instead of rebuilding reconciliation spreadsheets and one-off scripts for every rehearsal, cutover, interface, and audit.**

`reconciliation-as-code` is a Python CLI and YAML control language for deterministic cross-system reconciliation. It is aimed at migrations where business state must be proved even when scope, technical IDs, structure, mappings, tolerances, or record cardinality change.

You define the control in Git. The runner produces canonical machine-readable evidence, business-reviewable HTML/XLSX/CSV output, and CI-friendly pass/fail results.

## Why

Enterprise reconciliation is usually treated as disposable work:

- an Excel workbook for one cutover;
- a Python script owned by one consultant;
- a SQL query copied into a ticket;
- a manual comparison that cannot be reproduced later.

The control logic is valuable delivery knowledge. It should be versioned, reviewed, repeatable, executable, and tied to exact inputs.

## Product direction

The product is a **portable migration assurance layer**: prove that intended business state survived migration or replication even when source and target are not structurally identical.

The first strong use case is SAP S/4HANA migration, while the runtime stays vendor-neutral.

See the [documentation hub](docs/index.md), [Product Strategy](PRODUCT_STRATEGY.md), [Product Backlog](BACKLOG.md), and [Roadmap](ROADMAP.md).

## What works today

### Reconciliation controls

- CSV and optional Excel input on the reference Python backend;
- CSV and Parquet input on the scalable DuckDB backend;
- direct top-level SQLite and PostgreSQL query inputs through credential-free connection references;
- `rac inspect` dataset profiling;
- `rac init` conservative first-spec generation;
- single or composite business keys;
- key normalization, including leading-zero handling;
- duplicate-key integrity checks;
- matched / missing / unexpected coverage;
- source/target filters, reusable scopes, and conditional `when` checks;
- field comparison with normalization and explicit value maps;
- numeric, percentage, and date tolerances;
- configurable null semantics;
- control totals and aggregate-by-dimension checks;
- warning/error severity.

### Enterprise migration semantics

- hierarchical business objects with repeating child collections;
- object-level failure roll-up and nested evidence paths;
- explicit identity crosswalks when source/target IDs change;
- deterministic `1:1`, `1:N` split, and `N:1` merge reconciliation;
- explicit rejection of ambiguous `N:N` identity components;
- governed accepted exceptions with reason, owner/reference, expiry, and fingerprints;
- materiality and critical-field policies without hiding raw differences.

### Evidence and automation

- versioned specification and canonical evidence schemas;
- SHA-256 fingerprints for inputs, spec, crosswalks, exception artifacts, SQL queries and SQL extracts;
- JSON + Markdown output;
- offline HTML, filterable XLSX, and CSV discrepancy bundle;
- value masking/hash/omit policies for sensitive evidence;
- SQL evidence that records connection refs/dialect/query hashes but never copies the runtime DSN or password;
- CI-friendly exit codes;
- Python 3.10/3.12 CI coverage.

### Scale

- selectable `--engine duckdb` execution path for flat CSV/Parquet reconciliations;
- joins, filters, aggregates, and mismatch classification executed in DuckDB;
- bounded evidence returned to Python instead of materializing the full dataset as dictionaries;
- SQL query results streamed in chunks to bounded temporary extracts and optionally handed to DuckDB;
- required CI benchmark using two generated 1,000,000-row migration extracts;
- reproducible 100k / 1M / 5M benchmark tooling.

## Quick start

```bash
python -m pip install -e .

rac inspect examples/customer-migration/legacy.csv
rac validate examples/customer-migration/reconciliation.yaml

rac run examples/customer-migration/reconciliation.yaml \
  --evidence build/evidence.json \
  --report build/evidence.md \
  --bundle build/evidence-bundle \
  --no-fail-on-diff
```

Generate a first control from your own exports:

```bash
rac init legacy.csv target.csv -o reconciliation.yaml
```

For Excel:

```bash
pip install -e '.[excel]'
```

For large flat CSV/Parquet reconciliation:

```bash
pip install -e '.[duckdb]'

rac run reconciliation.yaml \
  --engine duckdb \
  --evidence build/evidence.json \
  --report build/evidence.md
```

For SQLite/PostgreSQL source or target queries:

```bash
pip install -e '.[sql]'
# PostgreSQL driver:
pip install -e '.[postgres]'
```

A SQL endpoint stores only a connection reference:

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
```

The actual database URL is supplied at runtime:

```bash
export RAC_CONNECTION_LEGACY_ERP='postgresql+psycopg://user:password@db.internal:5432/migration'
rac run reconciliation.yaml --engine duckdb
```

The connection URL is not stored in the YAML or evidence. See [SQL source and target adapters](docs/sql-adapters.md).

The included examples intentionally contain both passing and failing controls so evidence behavior can be reviewed rather than only described.

## A basic reconciliation spec

```yaml
version: 1

reconciliation:
  name: Customer legacy to S/4HANA

source:
  file: legacy.csv
  key: CUSTOMER_ID
  key_normalize: [trim, strip_leading_zeros]

target:
  file: s4.csv
  key: LEGACY_ID
  key_normalize: [trim, strip_leading_zeros]

checks:
  - id: coverage
    type: record_coverage

  - id: country
    type: field_match
    source: COUNTRY
    target: COUNTRY_CODE
    normalize: [trim, uppercase]
    map:
      DE: DEU
      US: USA

  - id: credit-limit
    type: field_match
    source: CREDIT_LIMIT
    target: CREDIT_LIMIT
    numeric_tolerance: 0.01

  - id: credit-total
    type: control_total
    source: CREDIT_LIMIT
    target: CREDIT_LIMIT
    tolerance: 0.01
```

The YAML is the control definition. Source and target data are runtime inputs. The same control can therefore be reviewed and replayed across DEV, QA, migration rehearsals, production cutover, and recurring operations.

## Beyond row-to-row comparison

A migration often cannot be represented as `source.key == target.key`.

For example:

```text
Legacy Customer 100003
  ├── address HOME
  └── sales area 1000/10/00

             ↓ migration

Business Partner 900017
  ├── address HOME
  └── sales area 1000/10/00
```

The hierarchy model reconciles the root plus child collections and records paths such as:

```text
CustomerBP/100003/addresses/HOME
CustomerBP/100003/sales_areas/1000|10|00
```

When IDs or cardinality change, an explicit crosswalk can describe:

```text
1001        → 9001        1:1
1002        → 9002,9003   1:N split
1003,1004   → 9004        N:1 merge
```

The engine preserves source/target identity provenance and requires explicit aggregation semantics where a merge or split changes comparison cardinality.

See:

- [Hierarchical enterprise objects](docs/hierarchical-objects.md)
- [Changed IDs, merges and splits](docs/identity-crosswalks.md)
- [Governed accepted exceptions](docs/accepted-exceptions.md)
- [Materiality and business criticality](docs/materiality.md)

## Evidence model

A run creates canonical evidence containing:

- spec/evidence version;
- engine version and run ID;
- exact input/spec fingerprints;
- source/target selection counts;
- check-level status and metrics;
- bounded discrepancy samples;
- identity/hierarchy provenance where applicable;
- SQL query/extract provenance where applicable;
- accepted-exception disposition;
- materiality policy and raw-vs-final status;
- privacy-safe values according to evidence policy.

Use:

```bash
rac schema spec
rac schema evidence
```

to expose the published contracts.

## CI / cutover gate

By default, `rac run` returns:

- `0` when all error-severity controls pass;
- `1` when reconciliation differences violate the effective control policy;
- `2` when specification/input/execution is invalid.

Use `--no-fail-on-diff` when generating evidence during exploration or rehearsal without using the run as a gate.

## Scalable execution

The same flat reconciliation YAML can be executed through DuckDB:

```bash
rac run reconciliation.yaml --engine duckdb
```

This backend supports CSV/Parquet flat controls and can consume bounded SQL extracts produced by the SQL adapter. A separate CI job generates and reconciles **1,000,000 source rows against 1,000,000 target rows**. A manual benchmark workflow defaults to 5,000,000 rows.

Hierarchy and identity crosswalks deliberately remain on `--engine python` until those stages have a true query/stream-based implementation. The CLI rejects them on DuckDB rather than making an unsupported scale claim.

See [DuckDB execution backend](docs/duckdb-backend.md), [SQL adapters](docs/sql-adapters.md), and [scale benchmarks](benchmarks/README.md).

## Design

```text
versioned YAML control spec
          │
          ├── source state (file or SQL query)
          ├── target state (file or SQL query)
          ├── optional identity crosswalk
          ├── optional child collections
          └── optional exception/materiality policy
                  │
        SQL inputs│stream to bounded extracts
                  ▼
          deterministic reconciliation
          ├── identity / key integrity
          ├── scope / coverage
          ├── hierarchy
          ├── field rules / mappings
          ├── totals / grouped controls
          └── governance / materiality
                  │
                  ▼
          canonical evidence JSON
                  │
          ┌───────┼────────┐
          ▼       ▼        ▼
        HTML     XLSX     CSV
          │
          ├── business review / sign-off
          └── CI / agent / automation
```

## Use cases

- SAP ECC / AFS → SAP S/4HANA migration reconciliation;
- Customer → Business Partner migration validation;
- Supplier/Vendor → Business Partner validation;
- MDG → downstream replication controls;
- database-to-database source/target reconciliation;
- CSV extract → target database validation;
- cutover load verification;
- master-data synchronization checks;
- finance or inventory grouped control totals;
- pre/post transformation verification;
- heterogeneous source-to-target migrations with changed IDs;
- repeatable evidence attached to Jira, ServiceNow, audit, or sign-off workflows.

## Documentation

- [Documentation hub](docs/index.md)
- [Runnable use-case gallery](https://dkharlanau.github.io/reconciliation-as-code/use-cases/)
- [5-minute real-data quickstart](docs/quickstart-real-data.md)
- [Specification reference](docs/specification.md)
- [SQL source and target adapters](docs/sql-adapters.md)
- [Hierarchical enterprise objects](docs/hierarchical-objects.md)
- [Identity crosswalks](docs/identity-crosswalks.md)
- [Governed accepted exceptions](docs/accepted-exceptions.md)
- [Materiality](docs/materiality.md)
- [DuckDB execution backend](docs/duckdb-backend.md)
- [Scale benchmarks](benchmarks/README.md)
- [Compatibility policy](docs/compatibility.md)
- [Evidence bundle and privacy controls](docs/evidence-bundle.md)
- [Architecture and extension model](docs/architecture.md)
- [As-code suite handoffs](docs/as-code-suite.md)
- [Contributing guide](CONTRIBUTING.md)
- [JSON Schemas](schema/)
- [Product Strategy](PRODUCT_STRATEGY.md)
- [Product Backlog](BACKLOG.md)

## Related projects

`reconciliation-as-code` answers **“did the intended business state arrive correctly?”**. It is designed to compose with other versioned enterprise artifacts:

See [Reconciliation as Code in the as-code suite](docs/as-code-suite.md) for the executable handoff and its limits.

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code) — consume a pinned lookup mapping directly or review a generated starting reconciliation contract.
- [Interface as Code](https://github.com/dkharlanau/interface-as-code) — retain a typed reference to the reconciliation control without implying that interface validation executes it.
- [Process as Code](https://github.com/dkharlanau/process-as-code) — link a process or cutover gate to RAC controls and evidence through generic artifact traceability.
- [Decision Tables as Code](https://github.com/dkharlanau/decision-tables-as-code) — govern bounded decisions independently; RAC does not infer controls from decision outputs.

## Status

**Migration-controls alpha.** The product supports guided onboarding, enterprise-object hierarchy, changed identities/merge/split, scoped and grouped controls, governed exceptions, materiality, audit-grade evidence, a scalable flat-data DuckDB backend, safe SQLite/PostgreSQL source/target adapters, and tested SAP S/4HANA starter packs. JSON/JSONL adapters, a plugin boundary, and first immutable public package/container releases remain future work.

MIT licensed.

## About the author

Created and maintained by **Dzmitryi Kharlanau**, an SAP consultant and system analyst working across enterprise architecture, data, integration, operations, and practical AI.

- [Website and knowledge base](https://dkharlanau.github.io/)
- [LinkedIn](https://www.linkedin.com/in/dkharlanau/)
