# Specification reference

A reconciliation specification is a versioned YAML document describing two datasets, their business keys, and the controls that must hold between them.

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

Supported key and field normalizers: `trim`, `uppercase`, `lowercase`, `empty_to_null`, `strip_leading_zeros`.

## Checks

### `record_coverage`

Compares source and target business-key sets. It reports matched keys, source keys missing from target, and unexpected target keys. Set `allow_unexpected: true` when target-only rows are valid.

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

- `map`: translate normalized source values before comparison.
- `numeric_tolerance`: compare values numerically within the supplied absolute tolerance.
- `max_mismatches`: permit a bounded number of mismatches.
- `severity: warning`: record the failure without failing the reconciliation run.

### `control_total`

Sums numeric source and target fields and compares the absolute difference against `tolerance`.

```yaml
- id: credit-total
  type: control_total
  source: CREDIT_LIMIT
  target: CREDIT_LIMIT
  tolerance: 0.01
```

Blank numeric cells count as zero. Non-numeric values cause a data error instead of being silently ignored.

### `row_count`

Compares total source and target row counts with an integer `tolerance`.

## Automatic key-integrity controls

Every run adds source and target key-integrity checks. Duplicate business keys are treated as errors because field-level reconciliation would otherwise be ambiguous.

## Evidence

The result contains:

- input row counts and coverage totals;
- pass/fail status for every check;
- bounded mismatch samples;
- SHA-256 fingerprints of the specification and input files;
- JSON evidence for machines and Markdown evidence for reviews, tickets, or cutover sign-off.

Use `evidence.detail_limit` to cap detailed mismatch rows in generated evidence.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Reconciliation passed, or `--no-fail-on-diff` was used. |
| `1` | One or more error-severity controls failed. |
| `2` | Invalid specification or input-data error. |
