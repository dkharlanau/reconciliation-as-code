# Reconciliation as Code and SAP-native validation tools

`reconciliation-as-code` should not be presented as a replacement for SAP-delivered migration and conversion validation capabilities. Use the SAP-native tool when it directly fits the project scenario; use an external versioned reconciliation control when the required proof spans systems, extracts, custom transformations, or delivery evidence that lives outside one SAP runtime.

## SAP Data Transition Validation (DTV)

SAP documents Data Transition Validation as a tool for comparing business data before and after SAP ECC → SAP S/4HANA conversion and during S/4HANA upgrades/updates. SAP DTV supports defining a validation test specification, extracting results in source/target releases, and comparing those results.

Official reference:

- [SAP Help — Data Transition Validation](https://help.sap.com/docs/PRODUCTS/66906ae3920c4fc684cf588290fb9267/30a1187ba7eb4460981a7ede8d4f02e7.html)

Use DTV when the validation is naturally part of an SAP conversion/update scenario and the required comparison content is available inside that framework.

`reconciliation-as-code` can be useful when the migration path is instead something like:

```text
legacy SAP / non-SAP
    → custom extract
    → transformation files
    → migration tooling
    → SAP S/4HANA
    → downstream replication
```

and the team wants one portable Git-versioned control across those artifacts.

## Master Data Synchronization / MDS Cockpit

SAP Master Data Synchronization includes comparison functionality for Customer/Vendor and Business Partner synchronization. SAP Help describes the compare operation as comparing Customer/Vendor data against the corresponding BP and reporting mismatches by field/path before synchronization.

Official references:

- [SAP Help — Master Data Synchronization](https://help.sap.com/saphelp_snc70/helpdata/en/46/ba5a70d19e1bb5e10000000a155369/content.htm)
- [SAP Help — Synchronization Cockpit](https://help.sap.com/saphelp_snc70/helpdata/en/14/1b4e867d5b4749b1dc6da10d6c320d/content.htm)

Use SAP synchronization/compare functions where Customer/Supplier ↔ BP synchronization inside the SAP landscape is the actual job.

The Customer→BP and Supplier→BP packs in this repository solve a different control problem: version a project-specific expected migration state, including explicit changed-ID crosswalks, hierarchical exported datasets, accepted exceptions, evidence hashes and CI/cutover gating.

## SAP S/4HANA Migration Cockpit

SAP Migration Cockpit is the migration execution framework, not something this project should reimplement. SAP documents migration approaches including migrating data directly from an SAP system to SAP S/4HANA using RFC connections for supported migration objects/scenarios.

Official reference:

- [SAP Help — Migrating Data Directly from an SAP System to SAP S/4HANA](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/29193bf0ebdd4583930b2176cb993268/7d255c7ba1f34e72a91e2e2467954ca0.html)

`reconciliation-as-code` sits after or around migration execution: it checks whether the intended business state arrived and produces independent, repeatable evidence.

## Decision guide

| Need | Prefer |
| --- | --- |
| SAP conversion/update business-data validation inside DTV scope | SAP DTV |
| Customer/Supplier ↔ BP synchronization compare inside SAP | SAP MDS/Synchronization tooling |
| Execute supported SAP migration objects | SAP Migration Cockpit / project migration tooling |
| Compare external source extract to S/4 target extract | Reconciliation as Code |
| Validate custom value mappings or changed technical IDs | Reconciliation as Code |
| Validate hierarchy across multiple exported tables | Reconciliation as Code |
| Reconcile multiple migration stages or non-SAP systems | Reconciliation as Code |
| Keep control logic and evidence in Git/CI | Reconciliation as Code |
| Need both SAP-native validation and independent delivery evidence | Use both |

The useful positioning is complementary: **SAP-native tools understand the SAP runtime; Reconciliation as Code versions the project-specific proof across boundaries.**
