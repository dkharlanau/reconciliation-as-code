# Agent instructions

Reconciliation as Code is an assurance tool. Specifications, input datasets, mapping artifacts, exception registers, materiality policies, and evidence are independent inputs; do not collapse them into a single pass/fail assumption.

## Working loop

1. Read `README.md`, the reconciliation specification, and `docs/agent-manifest.json`.
2. Validate the specification before execution.
3. Profile unfamiliar datasets with `rac inspect`; inspect scopes, tolerances, crosswalks, accepted exceptions, and materiality before interpreting results.
4. Run only the requested specification or pipeline range.
5. Preserve structured automation output: JSON on stdout, diagnostics on stderr.
6. When a result is used for a release decision, include evidence provenance and trust/integrity state.

## Guardrails

- Never invent tolerance values, crosswalks, accepted exceptions, or expected counts.
- Do not treat missing evidence as successful evidence.
- Do not modify source datasets as part of reconciliation.
- Keep generated evidence and reports deterministic and reproducible.
- Explain failed checks at the rule level rather than summarizing them away.

## Useful commands

```bash
rac inspect examples/customer-migration/legacy.csv --json
rac validate examples/customer-migration/reconciliation.yaml
rac run examples/customer-migration/reconciliation.yaml --no-fail-on-diff
rac pipeline examples/multi-stage/pipeline.yaml --no-fail-on-diff
```
