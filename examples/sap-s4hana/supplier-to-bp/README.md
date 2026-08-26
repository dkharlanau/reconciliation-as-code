# SAP S/4HANA Supplier to Business Partner migration reconciliation

This synthetic starter pack validates a Supplier/Vendor → Business Partner migration with changed technical IDs and bank details as a repeating child collection.

## What it proves

- source Supplier IDs map deterministically to target BP IDs;
- name, country and payment terms survived migration;
- synthetic account-group → BP-group transformations are explicit;
- bank-account coverage and IBAN values are reconciled under the new BP identity.

## Run

```bash
rac run examples/sap-s4hana/supplier-to-bp/reconciliation.yaml \
  --evidence build/supplier-bp.json \
  --report build/supplier-bp.md \
  --bundle build/supplier-bp-bundle \
  --no-fail-on-diff
```

## Intentional failure

The second target BP contains an IBAN ending in `...818` while the source Supplier contains `...819`. The expected reconciliation status is `failed`, specifically on `child:bank_accounts:iban`.

## Adapt this to a project

Typical project-specific additions can include:

- company-code views and reconciliation accounts;
- purchasing-organization views;
- BP/Supplier roles;
- tax data;
- withholding tax;
- bank details and payment methods;
- partner functions;
- account-group / BP-group rules and number-range strategy.

The data and mappings in this repository are synthetic examples, not SAP-delivered migration mappings.
