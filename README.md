# Reconciliation as Code

Define repeatable cross-system reconciliations with business keys, control totals, coverage rules, and evidence outputs.

## Problem

Enterprise reconciliations are repeatedly rebuilt as one-off Excel files or scripts during migration, cutover, integration, and operations.

## Core idea

Define reconciliations as repeatable, versionable specifications with configurable keys, checks, tolerances, and evidence outputs.

## Example

```yaml
reconciliation:
  name: Customer Legacy to S4

source:
  file: legacy.xlsx
  key: CUSTOMER_ID

target:
  file: s4.xlsx
  key: LEGACY_ID

checks:
  - type: record_coverage

  - type: field_match
    source: COUNTRY
    target: COUNTRY

  - type: control_total
    field: CREDIT_LIMIT
    tolerance: 0
```

## Initial scope

- source/target file comparison
- configurable keys
- matched/missing/unexpected records
- field comparisons
- control totals
- tolerance rules
- mapping-aware reconciliation
- repeatable reports
- evidence JSON/HTML

## Long-term direction

A versionable reconciliation specification for migrations, cutovers, integrations, and operational controls.

## Design principles

- versionable
- portable
- machine-readable
- deterministic-first
- visual where useful
- Git-friendly
- vendor-neutral where practical
- interoperable with enterprise tools

## Status

Planning.
