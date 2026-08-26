# Reconciliation as Code

**Version reconciliation controls instead of rebuilding them in spreadsheets for every migration, cutover, interface, and audit.**

`reconciliation-as-code` is a Python CLI and YAML specification for deterministic cross-system reconciliation. You define business keys, scope, field rules, mappings, tolerances, grouped controls and evidence policy in Git. The runner produces machine-readable evidence, human-reviewable reports, and CI-friendly pass/fail results.

## Why

Enterprise reconciliation is usually treated as disposable work:

- an Excel workbook for one cutover;
- a Python script owned by one consultant;
- a SQL query copied into a ticket;
- a manual comparison that cannot be reproduced later.

The control logic is valuable engineering knowledge. It should be versioned, reviewed, repeatable, and executable.

## Product direction

The product is evolving from flat source/target comparison into a **portable migration assurance layer**: prove that intended business state survived migration or replication even when scope, mappings, technical IDs and object structures change.

Current focus:

1. hierarchy-aware enterprise objects;
2. changed-ID crosswalks and merge/split reconciliation;
3. governed accepted exceptions;
4. scalable execution;
5. SAP S/4HANA migration starter packs.

See [Product Strategy](PRODUCT_STRATEGY.md), [Product Backlog](BACKLOG.md), and [Roadmap](ROADMAP.md).

## What works today

- CSV reconciliation with no data-frame dependency;
- optional Excel (`.xlsx` / `.xlsm`) input;
- `rac inspect` dataset profiling;
- `rac init` guided first-spec generation;
- single or composite business keys;
- key normalization, including leading-zero handling;
- duplicate-key detection;
- matched / missing / unexpected record coverage;
- source/target filtering and reusable scopes;
- conditional checks;
- field comparison with normalization;
- mapping-aware field comparison;
- numeric, percentage and date tolerances;
- configurable null semantics;
- global and aggregate-by-dimension control totals;
- grouped row and distinct-count controls;
- warning vs error severity;
- bounded evidence samples for large runs;
- SHA-256 fingerprints for inputs and specification;
- versioned canonical evidence schema;
- JSON + Markdown evidence;
- offline HTML, XLSX and CSV evidence bundle;
- evidence masking/hash/omit policies for sensitive values;
- CI-friendly exit codes.

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

Generate a first spec from your own files:

```bash
rac init legacy.csv target.csv -o reconciliation.yaml
```

For Excel files:

```bash
pip install -e '.[excel]'
```

The included examples intentionally contain differences so the generated evidence demonstrates failed controls and handoff output.

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

The YAML is the control definition. Source and target data are runtime inputs. That separation makes the same control reusable across DEV, QA, migration rehearsals, production cutover and recurring operations.

## Evidence model

A run creates a canonical result with:

- spec/evidence version;
- engine version and run ID;
- input/spec fingerprints;
- source/target counts;
- check-level status and metrics;
- bounded discrepancy samples;
- privacy-safe values according to evidence policy.

Use `rac schema spec` and `rac schema evidence` to expose the published schemas.

## CI / cutover gate

By default, `rac run` returns:

- `0` when all error-severity controls pass;
- `1` when reconciliation differences violate an error-severity control;
- `2` when the specification or input is invalid.

This makes a reconciliation spec usable as a migration gate, deployment control, scheduled integration check or audit evidence step.

Use `--no-fail-on-diff` when you only want to generate evidence during exploration or rehearsal.

## Design

```text
versioned YAML control spec
          │
          ├── source extract
          └── target extract
                  │
                  ▼
          reconciliation engine
          ├── identity / key integrity
          ├── scope / coverage
          ├── field rules / mappings
          ├── conditional checks
          └── totals / grouped controls
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

The core is deliberately vendor-neutral. SAP is an important first use case, not a runtime dependency: extracts can come from SAP, Salesforce, a data lake, APIs, databases, middleware or flat files.

## Use cases

- SAP ECC / AFS → SAP S/4HANA migration reconciliation;
- Customer → Business Partner migration validation;
- MDG → downstream replication controls;
- interface source vs receiver reconciliation;
- cutover load verification;
- master-data synchronization checks;
- finance or inventory grouped control totals;
- pre/post transformation verification;
- repeatable evidence attached to Jira, ServiceNow, audit or sign-off workflows.

## Documentation

- [5-minute real-data quickstart](docs/quickstart-real-data.md)
- [Specification reference](docs/specification.md)
- [Compatibility policy](docs/compatibility.md)
- [Evidence bundle and privacy controls](docs/evidence-bundle.md)
- [Architecture and extension model](docs/architecture.md)
- [JSON Schemas](schema/)
- [Product Strategy](PRODUCT_STRATEGY.md)
- [Product Backlog](BACKLOG.md)
- [Roadmap](ROADMAP.md)

## Relationship to the wider toolkit

`reconciliation-as-code` answers **“did the intended business state arrive correctly?”**. It is designed to compose with other versioned enterprise artifacts:

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code) — how values/fields map;
- [Transformation Graph](https://github.com/dkharlanau/transformation-graph) — how data changes across stages;
- [Interface as Code](https://github.com/dkharlanau/interface-as-code) — how systems exchange data;
- [Process as Code](https://github.com/dkharlanau/process-as-code) — how business execution is defined;
- [Cutover Graph](https://github.com/dkharlanau/cutover-graph) — how migration/cutover activities depend on one another;
- [Project Evidence Graph](https://github.com/dkharlanau/project-evidence-graph) — how delivery evidence is linked.

## Status

**Migration-controls alpha.** Slice A is implemented: stable contract, guided onboarding, scoped/grouped controls and audit-grade evidence. The next implementation loop is hierarchy + changed identities/cardinality + accepted-exception governance.

MIT licensed.
