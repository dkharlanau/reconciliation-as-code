# Reconciliation as Code

**Version reconciliation controls instead of rebuilding them in spreadsheets for every migration, cutover, interface, and audit.**

`reconciliation-as-code` is a Python CLI and YAML specification for deterministic cross-system reconciliation. You define business keys, scope, field rules, mappings, tolerances, grouped controls, object structure, and evidence policy in Git. The runner produces machine-readable proof and reviewer-friendly evidence, and can fail CI when reconciliation controls fail.

## Why

Enterprise reconciliation is usually treated as disposable work:

- an Excel workbook for one cutover;
- a Python script owned by one consultant;
- a SQL query copied into a ticket;
- a manual comparison that cannot be reproduced later.

The control logic is valuable engineering knowledge. It should be versioned, reviewed, repeatable, and executable.

## What works today

- CSV reconciliation with no data-frame dependency;
- optional Excel (`.xlsx` / `.xlsm`) input;
- `rac inspect` dataset profiling and candidate-key quality;
- `rac init` conservative first-spec generation;
- single or composite business keys;
- key normalization, including leading-zero handling;
- duplicate-key detection;
- endpoint filters, reusable named scopes and conditional checks;
- matched / missing / unexpected record coverage;
- field comparison with normalization and explicit value mappings;
- absolute, percentage and date tolerances;
- explicit null semantics;
- control totals and row-count controls;
- grouped `count`, `distinct_count`, and `sum` reconciliation by business dimension;
- hierarchical enterprise objects with unordered child collections;
- child coverage, field checks, duplicate policy and object-level status roll-up;
- warning vs error severity;
- bounded evidence samples for large runs without changing object roll-up truth;
- SHA-256 fingerprints for root/child inputs, specification and canonical configuration;
- versioned evidence schema and run provenance;
- JSON + Markdown evidence;
- offline HTML, XLSX and discrepancy CSV evidence bundles;
- masking/hash-only/omit controls for configured sensitive evidence fields and hierarchical identities;
- CI-friendly exit codes.

## Quick start

```bash
python -m pip install -e '.[excel]'

rac inspect examples/customer-migration/legacy.csv
rac validate examples/customer-migration/reconciliation.yaml
rac run examples/customer-migration/reconciliation.yaml \
  --bundle build/customer-evidence \
  --no-fail-on-diff
```

To see a root Customer/BP-style object with address and sales-area child collections:

```bash
rac run examples/customer-object/reconciliation.yaml \
  --bundle build/customer-object-evidence \
  --no-fail-on-diff
```

To generate a conservative first YAML from two real exports:

```bash
rac init source.csv target.csv -o reconciliation.yaml
```

If business keys differ, make the relationship explicit rather than relying on inference:

```bash
rac init legacy.csv s4.csv \
  --source-key CUSTOMER_ID \
  --target-key LEGACY_ID \
  -o reconciliation.yaml
```

The included examples intentionally contain differences so generated evidence shows what failed controls look like.

## Reconciliation spec

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

scopes:
  active:
    source: {field: ACTIVE, op: eq, value: Y}
    target: {field: ACTIVE, op: eq, value: Y}

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

  - id: credit-by-company
    type: aggregate_match
    operation: sum
    source: CREDIT_LIMIT
    target: CREDIT_LIMIT
    scope: active
    group_by:
      source: COMPANY_CODE
      target: COMPANY_CODE
    tolerance: 0.01
```

The YAML is the control definition. Source data and target data are runtime inputs. That separation makes the control reusable across DEV, QA, rehearsals, production cutover, and recurring operations.

## Enterprise-object hierarchy

The top-level source/target/checks remain the root business object. Optional `object.children` collections add repeating structures such as addresses, sales areas, roles, tax numbers, order items or schedules.

```yaml
object:
  name: customer
  children:
    - name: addresses
      source:
        file: source-addresses.csv
        parent_key: CUSTOMER_ID
        key: ADDRESS_ID
      target:
        file: target-addresses.csv
        parent_key: LEGACY_ID
        key: ADDRESS_ID
      checks:
        - id: city
          type: field_match
          source: CITY
          target: CITY
```

Child identity is `(parent business key, local child key)`, so row order does not matter. Evidence distinguishes missing, unexpected and changed child records and rolls attributable failures up to the root object.

## Evidence model

A run creates a versioned result with summary metrics, check results, bounded discrepancy samples, run metadata, input/spec hashes, and a canonical configuration fingerprint.

```json
{
  "schema_version": "1.0",
  "reconciliation": "Customer legacy to S/4HANA",
  "status": "failed",
  "summary": {
    "source_records": 3,
    "target_records": 3,
    "matched_records": 2,
    "missing_in_target": 1,
    "unexpected_in_target": 1,
    "checks_failed": 3
  }
}
```

For cutover hand-off, `--bundle DIR` creates canonical JSON plus Markdown, offline HTML, filterable XLSX, discrepancy CSVs, and a manifest containing hashes for generated evidence files. Sensitive evidence fields can be masked, hashed, or omitted without changing deterministic reconciliation logic.

## CI / cutover gate

By default, `rac run` returns:

- `0` when all error-severity controls pass;
- `1` when reconciliation differences violate an error-severity control;
- `2` when the specification or input is invalid.

This makes a reconciliation spec usable as a migration gate, deployment control, scheduled integration check, or audit evidence step.

Use `--no-fail-on-diff` when you only want to generate evidence during exploration or rehearsal.

## Design

```text
YAML control spec
      │
      ├── root source / target
      ├── optional child collections
      └── explicit scope / rules
              │
              ▼
        reconciliation engine
        ├── root key integrity / coverage
        ├── child identity / coverage
        ├── field mappings / tolerances
        ├── grouped business controls
        └── object-level status roll-up
              │
              ▼
       canonical evidence.json
              │
              ├── offline HTML / Markdown
              ├── XLSX / discrepancy CSV
              ├── manifest + file hashes
              └── CI / agent / automation
```

The core is deliberately vendor-neutral. SAP is an important use case, not a runtime dependency: extracts can come from SAP, Salesforce, a data lake, APIs, databases, middleware, or flat files.

## Use cases

- SAP ECC / AFS → SAP S/4HANA migration reconciliation;
- Customer / Supplier → Business Partner object validation;
- MDG → downstream system replication controls;
- interface source vs receiver reconciliation;
- cutover load verification;
- master-data synchronization checks;
- finance or inventory control totals by organizational dimension;
- pre/post transformation verification;
- repeatable evidence attached to Jira, ServiceNow, audit, or sign-off workflows.

## Documentation

- [Product strategy](PRODUCT_STRATEGY.md)
- [Prioritized product backlog](BACKLOG.md)
- [Five-minute real-data quickstart](docs/quickstart-real-data.md)
- [Specification reference](docs/specification.md)
- [Hierarchical enterprise objects](docs/hierarchical-objects.md)
- [Evidence bundles and privacy controls](docs/evidence-bundle.md)
- [Compatibility policy](docs/compatibility.md)
- [Architecture and extension model](docs/architecture.md)
- [JSON Schema](schema/reconciliation.schema.json)
- [Roadmap](ROADMAP.md)

## Relationship to the wider toolkit

`reconciliation-as-code` answers **“did the intended state arrive correctly?”**. It is designed to compose with other versioned enterprise artifacts:

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code) — how values/fields map;
- [Transformation Graph](https://github.com/dkharlanau/transformation-graph) — how data changes across stages;
- [Interface as Code](https://github.com/dkharlanau/interface-as-code) — how systems exchange data;
- [Process as Code](https://github.com/dkharlanau/process-as-code) — how business execution is defined;
- [Cutover Graph](https://github.com/dkharlanau/cutover-graph) — how migration/cutover activities depend on one another;
- [Project Evidence Graph](https://github.com/dkharlanau/project-evidence-graph) — how delivery evidence is linked.

## Status

**Working MVP / alpha.** Flat and hierarchical deterministic reconciliation, guided setup, scoped/grouped controls, evidence contracts and reviewer bundles are implemented. The next migration-specific focus is changed identities/cardinality, governed exceptions, scale, SQL access and SAP starter packs.

MIT licensed.
