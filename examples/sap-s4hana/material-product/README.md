# SAP S/4HANA Material master migration reconciliation

This synthetic starter pack shows Material/Product validation across general material data and plant-level views.

## What it proves

- legacy 18-character, zero-padded material numbers can match target product IDs through explicit key normalization;
- material-type transformation can be expressed as a versioned value map;
- base UoM and descriptions are compared at root level;
- plant views are reconciled as child collections using material + plant identity;
- MRP type, procurement type and minimum lot size can be validated per plant.

## Run

```bash
rac run examples/sap-s4hana/material-product/reconciliation.yaml \
  --evidence build/material-product.json \
  --report build/material-product.md \
  --bundle build/material-product-bundle \
  --no-fail-on-diff
```

## Intentional failure

Material `1002`, plant `2000` has source minimum lot `20` and target minimum lot `25`. The expected status is `failed` on the plant-level `min-lot` control.

## Adapt this to a project

A real material migration may require additional children/controls for:

- valuation areas and prices;
- storage locations;
- sales views;
- purchasing views;
- units of measure;
- tax classifications;
- batch management;
- MRP areas and planning fields;
- material type / product type transformations.

The example mapping `ROH → RM` and `FERT → FG` is synthetic and must not be treated as an SAP standard mapping.
