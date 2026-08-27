# SAP S/4HANA Customer to Business Partner migration reconciliation

This synthetic starter pack shows how to validate a Customer → Business Partner migration when the target BP receives a new technical ID and the business object contains repeating child data.

## What it proves

- every in-scope legacy Customer maps to a target BP through an explicit crosswalk;
- root name and country survived migration;
- legacy account groups were transformed to the expected BP grouping;
- address collections reconcile under the changed BP identity;
- sales-area collections reconcile under the changed BP identity;
- child failures roll up to the affected business object.

## Run

```bash
rac run examples/sap-s4hana/customer-to-bp/reconciliation.yaml \
  --evidence build/customer-bp.json \
  --report build/customer-bp.md \
  --bundle build/customer-bp-bundle \
  --no-fail-on-diff
```

## Intentional failures

The target fixture is intentionally not perfect:

1. BP `900002` has postal code `98109` while source Customer `000010002` has `98101`;
2. the source sales-area view `2000/20/00` for Customer `000010002` is absent in the target.

The expected result is therefore `failed`, with the problems attributed to child checks rather than reported as an unexplained root-level mismatch.

## Why this is different from a flat file diff

A Customer/BP is not one row. The comparison has to preserve root identity while validating collections such as addresses and sales areas. The explicit crosswalk also makes the target BP number part of evidence instead of assuming that legacy and target technical keys are identical.

## Adapt this to a project

Replace the synthetic exports and explicitly review:

- Customer/BP crosswalk logic;
- account group → BP grouping rules;
- BP roles and customer/supplier role expectations;
- address identity rules;
- sales-area scope and organizational keys;
- tax numbers, partner functions, company-code data, credit data, texts and classifications required by the project.

Do not reuse the example mappings as SAP standard truth. They are deliberately synthetic placeholders showing the control pattern.
