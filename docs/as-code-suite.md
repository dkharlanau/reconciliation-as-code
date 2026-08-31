# Reconciliation as Code in the as-code suite

Reconciliation as Code owns executable assurance: source/target inputs, business keys, scope, comparison controls, identity changes, tolerances, exceptions, materiality, and retained evidence.

## Direct Mapping as Code consumption

The implemented runtime bridge reads a local Mapping as Code YAML artifact, optionally verifies its SHA-256, resolves a named lookup field, and records the artifact provenance in reconciliation evidence:

```yaml
mapping_artifacts:
  customer-country:
    file: customer.mapping.yaml
    sha256: <64-hex-sha256>

checks:
  - id: country
    type: field_match
    source: country
    target: Country
    map_ref:
      artifact: customer-country
      field: customer-country
```

Run the checked-in bridge:

```bash
rac validate examples/mapping-as-code-bridge/reconciliation.yaml
rac run examples/mapping-as-code-bridge/reconciliation.yaml \
  --evidence build/mapping-evidence.json \
  --report build/mapping-evidence.md
```

Only compatible lookup transforms are consumed. Reconciliation as Code does not execute arbitrary mapping expressions or edit the upstream mapping.

## Related projects

- [Mapping as Code](https://github.com/dkharlanau/mapping-as-code) owns mapping intent and can also generate a reviewed starting RAC contract. This is the suite's direct runtime artifact handoff.
- [Interface as Code](https://github.com/dkharlanau/interface-as-code) can retain a typed `reconciliation.ref` beside its key, frequency, and source-of-truth expectation. Interface validation does not run RAC.
- [Process as Code](https://github.com/dkharlanau/process-as-code) can reference RAC controls or evidence from process/cutover gates through generic artifact traceability.
- [Decision Tables as Code](https://github.com/dkharlanau/decision-tables-as-code) governs bounded decisions. RAC does not consume DTAC tables or infer reconciliation policy from their outputs.

## Handoff rule

A linked artifact or generated starting contract does not prove migrated data is correct. Validate the final reconciliation specification, run it against authorized inputs, and review evidence exposure and business acceptance separately.
