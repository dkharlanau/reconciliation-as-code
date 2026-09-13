# SAP Customer to Business Partner migration preflight

This synthetic fixture is the smallest product-facing path for `rac preflight`: start from two ordinary migration exports, generate a conservative first reconciliation contract, and execute it only when the generated field mappings do not require review.

It deliberately stays simpler than the full [`customer-to-bp`](../customer-to-bp/) starter pack.

## Run the preflight

```bash
rac preflight \
  examples/sap-s4hana/customer-bp-preflight/legacy-customers.csv \
  examples/sap-s4hana/customer-bp-preflight/s4-business-partners.csv \
  --source-key LEGACY_ID \
  --target-key LEGACY_ID \
  --output-dir build/sap/customer-bp-preflight
```

The target export has a new `BusinessPartner` technical ID but retains `LEGACY_ID` as the explicit comparison key. `BusinessPartner` is target-only context; the preflight does not infer that it should be compared to another field.

Expected artifacts:

```text
build/sap/customer-bp-preflight/
  reconciliation.yaml
  evidence.json
  evidence.md
```

## Intentional finding

`LEGACY_ID=1000002` has source country `US` and target country `CA`.

The generated preflight therefore executes and reports a failed `field-country` check. The command still returns exit code `0` by default because preflight mode is for diagnosis and review, not a release gate. Add `--fail-on-diff` when a reviewed preflight should fail automation on reconciliation differences.

## Safe-stop behavior

If source and target fields cannot be mapped conservatively, `rac preflight` writes the generated `reconciliation.yaml`, keeps the unresolved mappings as `# TODO:` comments, prints `status=needs_review`, and does **not** execute reconciliation.

It never invents business keys, mappings, tolerances, value maps, crosswalks, or expected counts.

## When this fixture is not enough

Use the full [`customer-to-bp`](../customer-to-bp/) pack when the project needs:

- explicit Customer → BP identity crosswalks;
- different source and target object keys without a preserved comparison key;
- repeating addresses or sales-area collections;
- account-group → BP-grouping rules;
- object-level failure roll-up.

A preflight result proves only the fields and records covered by the generated and reviewed contract. It is not SAP certification, migration acceptance, or proof that omitted business rules are correct.
