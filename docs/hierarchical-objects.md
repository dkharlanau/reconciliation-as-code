# Hierarchical enterprise objects

Flat row comparison is not enough for many enterprise migrations. A Customer or Business Partner can have addresses, sales areas, tax numbers, roles and bank accounts; an order has items and schedules; a material has plant and storage-location views.

Reconciliation as Code keeps the existing top-level source/target/checks model as the **root object** and optionally adds unordered child collections under `object.children`.

## Model

```yaml
source:
  file: source-customers.csv
  key: CUSTOMER_ID

target:
  file: target-business-partners.csv
  key: LEGACY_ID

checks:
  - id: root-coverage
    type: record_coverage

object:
  name: customer
  children:
    - name: addresses
      source:
        file: source-addresses.csv
        parent_key: CUSTOMER_ID
        key: ADDRESS_ID
      target:
        file: target-addresses.csv
        parent_key: LEGACY_ID
        key: ADDRESS_ID
      checks:
        - id: city
          type: field_match
          source: CITY
          target: CITY
```

The full child identity is:

```text
(parent business key, child local key)
```

For the example above, `C1 + A2` identifies one address. Row position is irrelevant, so target collections may be sorted differently without creating a false mismatch.

## Parent and local keys

`parent_key` links the child row to the root object. Its number of fields must match the root key width. A composite root therefore requires a composite parent key.

`key` identifies one member inside that parent collection. It may also be composite.

Both endpoints support independent `parent_key_normalize` and `key_normalize` arrays.

Current hierarchy support assumes source and target parent identities match after normalization. New target IDs, crosswalks, merges and splits are deliberately handled by the separate identity-reconciliation capability rather than implicit matching here.

## Child coverage

Every child collection automatically reports:

- matched child records;
- `missing_child_in_target`;
- `unexpected_child_in_target`.

Unexpected child records fail by default. To permit target-only children explicitly:

```yaml
coverage:
  allow_unexpected: true
```

Coverage severity may be `error` or `warning`.

## Child field checks

Child collections currently support deterministic `field_match` checks using the same normalization, mapping, null, numeric, percentage and date-tolerance behavior as root field checks.

```yaml
checks:
  - id: credit_limit
    type: field_match
    source: CREDIT_LIMIT
    target: CREDIT_LIMIT
    numeric_tolerance: 0.01
```

A changed child field is reported separately from missing/unexpected children.

## Evidence paths

Child discrepancies include an object path such as:

```text
customer/C1/addresses/A2
customer/C3/sales_areas/1000-10-00
```

This makes evidence actionable without requiring a reviewer to reconstruct parent/child joins manually.

When `evidence.key_mode: hash` is enabled, root keys, child keys, object paths and roll-up failure paths are hashed before evidence is rendered.

## Duplicate policy

By default, two rows with the same `(parent_key, child_key)` are ambiguous and fail child key integrity.

```yaml
duplicate_policy: error
```

Some extracts contain literal duplicate rows. `allow_identical` collapses only rows whose complete values are identical:

```yaml
duplicate_policy: allow_identical
```

Two rows with the same identity but different field values still fail. The number of identical duplicates ignored is preserved in check metrics.

## Object-level roll-up

The engine derives one status per root business object:

- `passed` — no failed/warning child or root control was attributable to that object;
- `warning` — only warning-severity attributable controls failed;
- `failed` — at least one error-severity attributable root or child control failed.

Each roll-up record contains failed check IDs and child failure paths. The roll-up is calculated from complete internal failure events, not from the bounded evidence sample, so `evidence.detail_limit` does not change object status counts.

Global totals and grouped controls are not force-assigned to individual objects when there is no deterministic object attribution.

## Child input provenance

Every child source and target file is fingerprinted in the run manifest/evidence, for example:

```text
child.addresses.source
child.addresses.target
child.sales_areas.source
child.sales_areas.target
```

That means a hierarchical reconciliation can be tied back to the exact root and child extracts used for the run.

## Executable example

[`examples/customer-object`](../examples/customer-object/) models a Customer → Business Partner-style object with:

- root customer data;
- addresses;
- sales areas;
- reordered target children;
- one changed child field;
- missing and unexpected child rows;
- object-level failure roll-up.

Run it with:

```bash
rac run examples/customer-object/reconciliation.yaml \
  --bundle build/customer-object-evidence \
  --no-fail-on-diff
```

The example intentionally fails so all important discrepancy categories are visible in generated evidence.
