# Agent instructions

Reconciliation as Code is an assurance tool. Rulepacks, profiles, policies, waivers, and evidence are independent inputs; do not collapse them into a single pass/fail assumption.

## Working loop

1. Read `README.md`, the rulepack, and `docs/agent-manifest.json`.
2. Validate the rulepack before execution.
3. Inspect scopes, tolerances, profiles, and waivers before interpreting results.
4. Run only the requested suite or profile.
5. Preserve structured automation output: JSON on stdout, diagnostics on stderr.
6. When a result is used for a release decision, include evidence provenance and trust/integrity state.

## Guardrails

- Never invent tolerance values, exemptions, waivers, or expected counts.
- Do not treat missing evidence as successful evidence.
- Do not modify source datasets as part of reconciliation.
- Keep generated evidence and reports deterministic and reproducible.
- Explain failed checks at the rule level rather than summarizing them away.

## Useful commands

```bash
rac validate <rulepack.yaml>
rac inspect <rulepack.yaml>
rac run <rulepack.yaml>
```
