# Architecture and extension model

## Boundary

Reconciliation as Code does not own extraction, transport, or source-system credentials. It starts from explicit runtime datasets and a versioned control specification.

This boundary keeps the engine portable and makes it usable in restricted enterprise environments: extraction can remain inside SAP, middleware, a database, or an approved ETL tool, while the same reconciliation definition runs against the produced evidence files.

## Execution flow

1. Parse and validate the YAML specification.
2. Resolve source and target data paths relative to the spec.
3. Load tabular data.
4. Normalize business keys.
5. Detect duplicate keys before comparisons.
6. Build matched / missing / unexpected key sets.
7. Execute ordered reconciliation checks.
8. Calculate overall status using check severity.
9. Fingerprint the inputs.
10. Emit JSON and Markdown evidence.

## Why business keys are first-class

Reconciliation is not just “compare row 42 with row 42.” Enterprise data frequently changes ordering, identifiers, formatting, or record counts between systems. A declared business key makes matching semantics explicit and reviewable.

Composite keys are supported by declaring lists on both endpoints:

```yaml
source:
  key: [SALES_ORG, CUSTOMER]
target:
  key: [VKORG, KUNNR]
```

The two lists must have equal length; each position maps source key component to target key component.

## Deterministic-first rule

Core controls should be deterministic. The same inputs and same spec must produce the same findings. AI can later help propose rules, classify exceptions, explain patterns, or draft remediation, but it should not silently change reconciliation truth.

## Evidence as a product

A reconciliation result is not only a console message. It is evidence that can be stored, diffed, attached, signed off, indexed, or consumed by agents. That is why the MVP outputs:

- normalized check statuses;
- structured metrics;
- bounded detail samples;
- file/spec fingerprints;
- a human-readable companion report.

## Adapter direction

Future adapters should implement the same conceptual interface:

```text
load(endpoint) -> rows + input identity
```

Likely adapters:

- SQL query / database;
- Parquet;
- JSON / JSONL;
- SAP OData/API extraction wrappers;
- object storage;
- HTTP endpoints.

Credentials and secrets should remain outside reconciliation specs.

## Rule direction

Checks should remain composable and small. Candidates include:

- set equality / subset controls;
- aggregates by dimension;
- date/time tolerances;
- conditional checks (`when`);
- referential integrity;
- cardinality constraints;
- mapped-code coverage;
- regex / domain constraints;
- transformation-aware expectations.

## Interoperability direction

A future spec should be able to reference artifacts rather than duplicating them. Examples:

- consume value mappings from `mapping-as-code`;
- identify expected transformation stages from `transformation-graph`;
- bind a reconciliation to an `interface-as-code` contract;
- publish evidence nodes into `project-evidence-graph`.

The goal is a connected enterprise change system where mapping, transformation, interface, cutover, reconciliation, and evidence definitions can be independently versioned but machine-linked.
