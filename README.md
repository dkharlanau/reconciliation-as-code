# Reconciliation as Code

**Version reconciliation controls instead of rebuilding them in spreadsheets for every migration, cutover, interface, and audit.**

`reconciliation-as-code` is a small Python CLI and YAML specification for deterministic cross-system reconciliation. You define business keys, coverage expectations, field rules, mappings, tolerances, and control totals in Git. The runner produces machine-readable evidence and a reviewable report, and can fail CI when reconciliation controls fail.

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
- single or composite business keys;
- key normalization, including leading-zero handling;
- duplicate-key detection;
- matched / missing / unexpected record coverage;
- field comparison with normalization;
- mapping-aware field comparison;
- numeric tolerances;
- control totals;
- row-count controls;
- warning vs error severity;
- bounded evidence samples for large runs;
- SHA-256 fingerprints for inputs and specification;
- JSON evidence + Markdown report;
- CI-friendly exit codes.

## Quick start

```bash
python -m pip install -e .

rac validate examples/customer-migration/reconciliation.yaml
rac run examples/customer-migration/reconciliation.yaml \
  --evidence build/evidence.json \
  --report build/evidence.md \
  --no-fail-on-diff
```

For Excel files:

```bash
pip install -e '.[excel]'
```

The included customer-migration example intentionally contains differences, so the generated evidence shows what a failed reconciliation looks like.

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

The YAML is the control definition. Source data and target data are runtime inputs. That separation makes the control reusable across DEV, QA, rehearsals, production cutover, and recurring operations.

## Evidence model

A run creates a compact result like:

```json
{
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

Each failed check also carries metrics and a bounded sample of offending business keys/values. Input files and the YAML specification are fingerprinted with SHA-256 so evidence can be tied back to the exact reconciliation inputs.

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
      ├── source extract (CSV / Excel)
      └── target extract (CSV / Excel)
              │
              ▼
        reconciliation engine
        ├── key integrity
        ├── coverage
        ├── field rules
        ├── mappings
        └── totals / tolerances
              │
              ▼
        evidence.json + evidence.md
              │
              ├── human review / sign-off
              └── CI / agent / automation
```

The core is deliberately vendor-neutral. SAP is an important use case, not a runtime dependency: extracts can come from SAP, Salesforce, a data lake, APIs, databases, middleware, or flat files.

## Use cases

- SAP ECC / AFS → SAP S/4HANA migration reconciliation;
- MDG → downstream system replication controls;
- interface source vs receiver reconciliation;
- cutover load verification;
- master-data synchronization checks;
- finance or inventory control totals;
- pre/post transformation verification;
- repeatable evidence attached to Jira, ServiceNow, audit, or sign-off workflows.

## Documentation

- [Product strategy](PRODUCT_STRATEGY.md)
- [Prioritized product backlog](BACKLOG.md)
- [Specification reference](docs/specification.md)
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

**Working MVP / alpha.** The CLI, reconciliation engine, evidence generation, example, tests, JSON Schema, and CI workflow are implemented. The product direction is now focused on migration-aware hierarchy, changed identities/cardinality, governed evidence, scale, SAP starter packs, and discoverability.

MIT licensed.
