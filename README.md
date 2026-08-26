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

See [Product Strategy](PRODUCT_STRATEGY.md), [Product Backlog](BACKLOG.md), and [Roadmap](ROADMAP.md).

## What works today

### Reconciliation controls

- CSV and optional Excel input on the reference Python backend;
- CSV and Parquet input on the scalable DuckDB backend;
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
- SHA-256 fingerprints for inputs, spec, crosswalks, and exception artifacts;
- JSON + Markdown output;
- offline HTML, filterable XLSX, and CSV discrepancy bundle;
- value masking/hash/omit policies for sensitive evidence;
- CI-friendly exit codes;
- Python 3.10/3.12 CI coverage.

### Scale

- selectable `--engine duckdb` execution path for flat CSV/Parquet reconciliations;
- joins, filters, aggregates, and mismatch classification executed in DuckDB;
- bounded evidence returned to Python instead of materializing the full dataset as dictionaries;
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

This backend currently supports CSV/Parquet flat controls and is continuously tested against the Python reference semantics. A separate CI job generates and reconciles **1,000,000 source rows against 1,000,000 target rows**. A manual benchmark workflow defaults to 5,000,000 rows.

Hierarchy and identity crosswalks deliberately remain on `--engine python` until those stages have a true query/stream-based implementation. The CLI rejects them on DuckDB rather than making an unsupported scale claim.

See [DuckDB execution backend](docs/duckdb-backend.md) and [scale benchmarks](benchmarks/README.md).

## Design

```text
versioned YAML control spec
          │
          ├── source state
          ├── target state
          ├── optional identity crosswalk
          ├── optional child collections
          └── optional exception/materiality policy
                  │
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
- cutover load verification;
- master-data synchronization checks;
- finance or inventory grouped control totals;
- pre/post transformation verification;
- heterogeneous source-to-target migrations with changed IDs;
- repeatable evidence attached to Jira, ServiceNow, audit, or sign-off workflows.

## Documentation

- [5-minute real-data quickstart](docs/quickstart-real-data.md)
- [Specification reference](docs/specification.md)
- [Hierarchical enterprise objects](docs/hierarchical-objects.md)
- [Identity crosswalks](docs/identity-crosswalks.md)
- [Governed accepted exceptions](docs/accepted-exceptions.md)
- [Materiality](docs/materiality.md)
- [DuckDB execution backend](docs/duckdb-backend.md)
- [Scale benchmarks](benchmarks/README.md)
- [Compatibility policy](docs/compatibility.md)
- [Evidence bundle and privacy controls](docs/evidence-bundle.md)
- [Architecture and extension model](docs/architecture.md)
- [JSON Schemas](schema/)
- [Product Strategy](PRODUCT_STRATEGY.md)
- [Product Backlog](BACKLOG.md)

## Relationship to the wider toolkit

`reconciliation-as-code` answers **“did the intended business state arrive correctly?”**. It is designed to compose with other versioned enterprise artifacts:

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code) — how values and fields map;
- [Transformation Graph](https://github.com/dkharlanau/transformation-graph) — how data changes across stages;
- [Interface as Code](https://github.com/dkharlanau/interface-as-code) — how systems exchange data;
- [Process as Code](https://github.com/dkharlanau/process-as-code) — how business execution is defined;
- [Cutover Graph](https://github.com/dkharlanau/cutover-graph) — how migration/cutover activities depend on one another;
- [Project Evidence Graph](https://github.com/dkharlanau/project-evidence-graph) — how delivery evidence is linked.

## Status

**Migration-controls alpha.** The product now supports guided onboarding, enterprise-object hierarchy, changed identities/merge/split, scoped and grouped controls, governed exceptions, materiality, audit-grade evidence, and a scalable flat-data DuckDB execution path. The next P0 work is database adapters and deeper SAP S/4HANA starter packs.

MIT licensed.
