# SAP S/4HANA migration reconciliation examples

These examples are synthetic, runnable migration-assurance patterns for SAP S/4HANA projects. They are designed to show how to version the expected business state and produce repeatable evidence around migration execution.

| Pack | Core pattern | Intentional failure |
| --- | --- | --- |
| [Customer → Business Partner](customer-to-bp/) | changed IDs + hierarchy + value mapping | postal-code mismatch + missing sales-area view |
| [Supplier → Business Partner](supplier-to-bp/) | changed IDs + bank child data | IBAN mismatch |
| [Material/Product](material-product/) | leading-zero normalization + plant hierarchy | minimum-lot mismatch in one plant |
| [Finance + inventory balances](finance-inventory-balances/) | record controls + grouped totals | finance and stock variances beyond tolerance |

Every specification is exercised by `.github/workflows/sap-starter-packs.yml`, and the unit suite verifies the exact expected discrepancy class.

## Positioning

These packs are not SAP standard mappings and do not replace SAP-delivered migration or validation tools. Their purpose is to make project-specific reconciliation logic versioned, portable and evidence-producing across boundaries such as source extracts, transformation artifacts, target exports and CI/cutover gates.

See [SAP-native validation scope comparison](../../docs/sap-native-validation.md).
