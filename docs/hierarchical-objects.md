# Hierarchical enterprise-object reconciliation

Flat source-to-target comparison is not enough for many ERP migrations. A business object such as a Customer, Business Partner, Supplier, Material, Sales Order or Purchase Order spans a root record plus repeating child collections.

`reconciliation-as-code` can reconcile the root and those child collections as one evidence-producing object.

## Example: SAP Customer to Business Partner

A simplified migrated customer can contain:

```text
CustomerBP 100003
├── root data
├── addresses[]
└── sales_areas[]
```

The root may reconcile successfully while one address is missing and one sales-area field differs. The final object must still be reported as failed.

See the runnable example in [`examples/customer-bp-hierarchy`](../examples/customer-bp-hierarchy).

## Specification

```yaml
object:
  type: CustomerBP

source:
  file: legacy_customers.csv
  key: CUSTOMER_ID

target:
  file: business_partners.csv
  key: LEGACY_ID

checks:
  - id: root-coverage
    type: record_coverage

children:
  addresses:
    source:
      file: legacy_addresses.csv
      key: [CUSTOMER_ID, ADDRESS_TYPE]
      parent_key: CUSTOMER_ID
    target:
      file: bp_addresses.csv
      key: [LEGACY_ID, ADDRESS_TYPE]
      parent_key: LEGACY_ID
    checks:
      - id: coverage
        type: record_coverage
      - id: city
        type: field_match
        source: CITY
        target: CITY
```

## Child identity

A child collection has its own business key. The parent identity must be included in that key.

For example:

```yaml
key: [CUSTOMER_ID, SALES_ORG, DIST_CHANNEL, DIVISION]
parent_key: CUSTOMER_ID
```

This makes child identity deterministic and lets evidence roll failures back to the root business object.

Composite root keys are supported as long as `parent_key` contains the same number of identity components as the corresponding root key.

## Unordered collections

Child rows do not need to appear in the same physical order. They are indexed by the configured child key, so two address exports can be sorted differently and still reconcile correctly.

## Parent integrity

The engine automatically checks that each child belongs to an existing root object on its own side.

An address referencing a nonexistent Customer produces a synthetic check such as:

```text
child:addresses:source-parent-integrity
```

The discrepancy is classified as an orphan child rather than being silently ignored.

## Evidence paths

Child discrepancies receive an object path, for example:

```text
CustomerBP/100003/addresses/100003/BILL
CustomerBP/100003/sales_areas/100003/3000/10/00
```

This gives engineers and reviewers a stable explanation of where the failure lives inside the business object.

## Object-level roll-up

Evidence contains a `hierarchy` section plus summary metrics:

- `child_collections`
- `child_collections_failed`
- `objects_evaluated`
- `objects_passed`
- `objects_failed`

A root object is failed when an error-severity root or child discrepancy is attributed to it.

## Duplicate policy

Child collections default to:

```yaml
duplicate_policy: error
```

For collections where duplicate identity should only raise a review warning:

```yaml
duplicate_policy: warning
```

The raw duplicate evidence remains visible; only severity changes.

## Accepted exceptions

Hierarchical checks compose with governed accepted exceptions. A child check ID is namespaced:

```text
child:addresses:city
```

An exception can therefore target a specific child discrepancy without hiding other failures.

## Changed root IDs

Hierarchy composes with the identity-crosswalk layer. If a legacy Customer `1001` becomes Business Partner `9001`, child parent identities are rewritten through the same explicit crosswalk before child reconciliation:

```text
legacy customer 1001 / address BILL
             ↓ identity crosswalk
business partner 9001 / address BILL
```

The crosswalk may also represent supported `1:N` splits and `N:1` merges. Evidence retains the original source/target identities and the identity component used for comparison. See [Identity crosswalks](identity-crosswalks.md).

## Execution backend

Hierarchical reconciliation currently runs on the reference Python backend. The DuckDB backend intentionally rejects hierarchy specs until child and identity processing have a true query/stream-based implementation; this avoids overstating scale support.
