# SAP S/4HANA finance and inventory balance reconciliation

Migration sign-off should not rely only on row-by-row equality. Business control totals must also reconcile at the dimensions used to manage risk.

This pack contains two synthetic controls:

- `finance-reconciliation.yaml` — account balances and grouped totals by company code/currency;
- `inventory-reconciliation.yaml` — stock quantity by plant/material plus plant-level totals.

## Finance

```bash
rac run examples/sap-s4hana/finance-inventory-balances/finance-reconciliation.yaml \
  --evidence build/finance.json \
  --report build/finance.md \
  --no-fail-on-diff
```

The source G/L account uses leading zeros while the target example does not. Key normalization makes the business identity explicit.

The target contains a deliberate EUR variance of `0.02`. The configured tolerance is `0.01`, so the example fails both the affected account-level comparison and company/currency control total.

## Inventory

```bash
rac run examples/sap-s4hana/finance-inventory-balances/inventory-reconciliation.yaml \
  --evidence build/inventory.json \
  --report build/inventory.md \
  --no-fail-on-diff
```

Material IDs are normalized across legacy and target representations. One target quantity is `49.5` instead of `50.0`; the `0.1` tolerance is exceeded and the plant-level grouped total also fails.

## Why grouped controls matter

A migration can preserve the total number of rows while moving value into the wrong organizational bucket. Grouping by company code, currency, plant, storage location, valuation area, or another business dimension catches problems that a global grand total can hide.

## Adapt this to a project

Use the dimensions and measures that business owners actually sign off. Examples can include:

- company code / G/L account / currency balances;
- customer/vendor open-item totals;
- plant / storage-location stock quantities;
- stock values by valuation area;
- batch quantities;
- asset balances;
- document counts by fiscal period or company code.

Tolerance and materiality values must be approved project controls, not copied from these synthetic fixtures.
