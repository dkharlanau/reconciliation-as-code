# Evidence bundles

A reconciliation run can create a self-contained hand-off directory for cutover review, sign-off, audit support, or ticket attachment.

```bash
pip install -e '.[excel]'

rac run reconciliation.yaml \
  --bundle build/cutover-evidence \
  --no-fail-on-diff
```

The bundle contains:

```text
cutover-evidence/
├── evidence.json
├── evidence.md
├── evidence.html
├── evidence.xlsx
├── manifest.json
└── details/
    ├── missing.csv
    ├── unexpected.csv
    ├── field-mismatches.csv
    ├── aggregate-mismatches.csv
    └── exceptions.csv
```

`evidence.json` remains the canonical machine-readable result. The other files are review formats derived from the same prepared evidence.

## Offline HTML

`evidence.html` contains its styles inline and has no remote JavaScript, fonts, images, or CSS dependencies. It can be opened directly from a cutover evidence folder without network access.

## Excel hand-off

`evidence.xlsx` contains filterable sheets for:

- Summary;
- Checks;
- Missing;
- Unexpected;
- Field Mismatches;
- Aggregate Mismatches;
- Totals;
- Exceptions.

The Exceptions sheet is present even before governed accepted exceptions are introduced, so the evidence package has a stable hand-off shape. Exception governance is tracked separately in the product backlog.

XLSX output requires the `excel` optional dependency (`openpyxl`).

## Discrepancy CSVs

The `details/` files are intentionally simple flat extracts suitable for Excel, ticket attachments, local scripts, or downstream automation. Empty categories still produce a CSV with headers so consumers do not need special missing-file logic.

## Manifest and provenance

`manifest.json` records:

- bundle format version;
- reconciliation status and run ID;
- engine and evidence schema versions;
- configuration fingerprint;
- source/target/specification input fingerprints;
- active privacy policy;
- SHA-256 and byte size for every generated bundle file except the manifest itself.

This lets a reviewer tie presentation files back to the exact reconciliation run and detect later modifications to generated evidence files.

## Sensitive values

Raw enterprise values should not be copied into review artifacts merely because a field mismatch occurred. Configure sensitive fields in the reconciliation spec:

```yaml
evidence:
  detail_limit: 100
  sensitive_fields:
    - EMAIL
    - TAX_NUMBER
  sensitive_value_mode: hash
  key_mode: hash
```

Supported `sensitive_value_mode` values:

- `mask` — replace protected values with `***`;
- `hash` — hash-only evidence using SHA-256; useful when reviewers need to establish that values differ or recur without seeing them;
- `omit` — suppress protected values entirely.

`key_mode: hash` hashes discrepancy business keys before any evidence renderer receives them. `key_mode: plain` is the default.

Privacy preparation happens before JSON, Markdown, HTML, XLSX, and CSV generation. A renderer therefore does not receive raw configured sensitive mismatch values. The reconciliation engine itself still needs the source/target values in memory to perform deterministic comparison; this feature controls generated evidence rather than encrypting runtime data.

## What is not copied into the bundle

Source and target datasets are not copied. The manifest carries their fingerprints and configured paths only. Credentials are never part of the reconciliation specification and are outside the evidence bundle model.

## Practical cutover pattern

Use one immutable directory per run, for example:

```text
evidence/
  rehearsal-01/
  rehearsal-02/
  dress-rehearsal/
  production-load-01/
```

The future run-to-run diff capability can compare canonical evidence documents without requiring the original source and target exports.
