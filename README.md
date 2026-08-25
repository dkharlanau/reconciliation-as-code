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

## Related projects

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code)
- [Transformation Graph](https://github.com/dkharlanau/transformation-graph)
- [Interface as Code](https://github.com/dkharlanau/interface-as-code)
- [Process as Code](https://github.com/dkharlanau/process-as-code)
- [Enterprise Change Graph](https://github.com/dkharlanau/enterprise-change-graph)
- [Decision Tables as Code](https://github.com/dkharlanau/decision-tables-as-code)
- [Data Relationship Map](https://github.com/dkharlanau/data-relationship-map)
- [Cutover Graph](https://github.com/dkharlanau/cutover-graph)
- [Project Evidence Graph](https://github.com/dkharlanau/project-evidence-graph)

## Status

Planning.
