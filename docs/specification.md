# Specification reference

A reconciliation specification is a versioned YAML document describing two datasets, their business keys, scope, and the controls that must hold between them.

## Minimal structure

```yaml
version: 1
reconciliation:
  name: Customer migration
source:
  file: legacy.csv
  key: CUSTOMER_ID
target:
  file: s4.csv
  key: LEGACY_ID
checks:
  - id: coverage
    type: record_coverage
```

Paths are resolved relative to the YAML file. CSV is supported without optional dependencies. `.xlsx` and `.xlsm` are supported when `openpyxl` is installed (`pip install 'reconciliation-as-code[excel]'`).

## Endpoints

Both `source` and `target` support:

| Property | Meaning |
| --- | --- |
| `file` | Relative or absolute input path. |
| `key` | One business-key field or a list for composite keys. |
| `format` | Optional override: `csv`, `xlsx`, or `xlsm`. |
| `delimiter` | CSV delimiter, default `,`. |
| `sheet` | Excel sheet name; first sheet is used when omitted. |
| `key_normalize` | Normalizers applied before key matching. Default: `[trim]`. |
| `filter` | Optional predicate selecting the dataset that is globally in scope. |

Supported key and field normalizers: `trim`, `uppercase`, `lowercase`, `empty_to_null`, `strip_leading_zeros`.

Endpoint filters are applied before key integrity, global coverage, summary counts and all checks. Evidence records both raw and selected row counts plus the filter definition; filtering is therefore explicit rather than hidden.

## Predicate language

Filters, named scopes and conditional checks use the same deterministic predicate structure.

```yaml
field: COUNTRY
op: in
value: [DE, AT, CH]
normalize: [trim, uppercase]
```

Operators: `eq`, `ne`, `in`, `not_in`, `contains`, `starts_with`, `is_null`, `not_null`, `gt`, `gte`, `lt`, `lte`.

Predicates can be composed without executing arbitrary expressions:

```yaml
all:
  - field: ACTIVE
    op: eq
    value: Y
  - any:
      - field: COUNTRY
        op: eq
        value: DE
      - field: COUNTRY
        op: eq
        value: AT
```

Logical forms are `all`, `any`, and `not`.

## Reusable scopes

Use `scopes` when multiple controls apply to the same business population.

```yaml
scopes:
  active-customers:
    source:
      field: ACTIVE
      op: eq
      value: Y
    target:
      field: ACTIVE
      op: eq
      value: Y

checks:
  - id: active-count
    type: row_count
    scope: active-customers
```

Source and target predicates are intentionally separate because source and target field names or encodings may differ.

## Conditional checks

`when` narrows one check without defining a reusable scope.

```yaml
- id: tax-number
  type: field_match
  source: TAX_NUMBER
  target: TAX_NO
  when:
    source:
      field: COUNTRY
      op: eq
      value: DE
    target:
      field: COUNTRY_CODE
      op: eq
      value: DE
```

For matched-record field checks, a pair is compared only when all supplied source/target scope and `when` predicates are satisfied. Evidence reports compared and skipped counts.

## Checks

### `record_coverage`

Compares source and target business-key sets. It reports matched keys, source keys missing from target, and unexpected target keys. Set `allow_unexpected: true` when target-only rows are valid. A named `scope` or `when` can restrict the coverage population.

### `field_match`

Compares a source field and target field only for matched business keys.

```yaml
- id: country
  type: field_match
  source: COUNTRY
  target: COUNTRY_CODE
  normalize: [trim, uppercase]
  map:
    DE: DEU
    US: USA
```

Optional controls:

- `map`: translate normalized source values before comparison;
- `numeric_tolerance`: absolute numeric tolerance;
- `percentage_tolerance`: percentage difference relative to the source value; when source is zero only an exact zero difference can pass percentage tolerance;
- `date_tolerance_days`: ISO date/datetime difference allowed in days;
- `null_semantics`: `equal` (default), `empty_is_null`, or `never_equal`;
- `max_mismatches`: permit a bounded number of mismatches;
- `scope`: apply a named reusable business scope;
- `when`: apply check-specific source/target predicates;
- `severity: warning`: record the failure without failing the reconciliation run.

If both absolute and percentage numeric tolerances are supplied, satisfying either tolerance passes the value comparison.

### `control_total`

Sums numeric source and target fields and compares the absolute difference against `tolerance`.

```yaml
- id: credit-total
  type: control_total
  source: CREDIT_LIMIT
  target: CREDIT_LIMIT
  scope: active-customers
  tolerance: 0.01
```

Blank numeric cells count as zero. Non-numeric values cause a data error instead of being silently ignored.

### `row_count`

Compares source and target row counts with an integer `tolerance`. Named scopes and `when` predicates are supported.

### `aggregate_match`

Compares business controls by one or more dimensions. Supported operations are `count`, `distinct_count`, and `sum`.

Count active customers by country:

```yaml
- id: customer-count-by-country
  type: aggregate_match
  operation: count
  scope: active-customers
  group_by:
    source: COUNTRY
    target: COUNTRY_CODE
  tolerance: 0
```

Sum credit limits by company code:

```yaml
- id: credit-by-company
  type: aggregate_match
  operation: sum
  source: CREDIT_LIMIT
  target: CREDIT_LIMIT
  group_by:
    source: COMPANY_CODE
    target: COMPANY_CODE
  tolerance: 0.01
  percentage_tolerance: 0.1
```

`group_by.source` and `group_by.target` may each be a list for composite dimensions. Their field counts must match. Failed evidence identifies the exact group and source/target aggregate values rather than reporting only a global failure.

For `distinct_count`, `source` and `target` identify the fields whose distinct values are counted within each group.

## Automatic key-integrity controls

Every run adds source and target key-integrity checks after global endpoint filters have been applied. Duplicate business keys are treated as errors because field-level reconciliation would otherwise be ambiguous.

## Evidence

The result contains:

- selected row counts and coverage totals;
- raw vs selected endpoint counts and filter definitions under `selection`;
- pass/fail status for every check;
- bounded mismatch or failing-group samples;
- scope-specific record counts in check metrics;
- SHA-256 fingerprints of the specification and input files;
- canonical configuration fingerprint, including filters/scopes;
- JSON evidence for machines and Markdown evidence for reviews, tickets, or cutover sign-off.

Use `evidence.detail_limit` to cap detailed mismatch rows in generated evidence.

See [`examples/scoped-controls`](../examples/scoped-controls/) for an executable example combining global filters, a reusable active-customer scope, date tolerance, and grouped business controls.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Reconciliation passed, or `--no-fail-on-diff` was used. |
| `1` | One or more error-severity controls failed. |
| `2` | Invalid specification or input-data error. |
