# Governed accepted exceptions

A migration or cutover rarely reaches literal zero-difference. `reconciliation-as-code` therefore supports explicit, versioned accepted exceptions without deleting or hiding the underlying mismatch.

## Configure the reconciliation

```yaml
exceptions:
  file: exceptions.yaml
  expiry_policy: error
```

`expiry_policy` may be `error` or `warning`. An expired entry is never treated as accepted.

## Exception artifact

```yaml
version: 1
exceptions:
  - check: country
    key: '1002'
    field: COUNTRY
    reason_code: approved-target-code
    reason: Target intentionally stores the approved target code.
    owner: migration-lead
    reference: CUT-123
    expires: 2026-12-31
```

Each entry requires:

- `check` — the reconciliation check ID;
- exactly one of `key` or `group`;
- `reason_code`;
- `reason`.

Optional governance metadata:

- `field` — restrict acceptance to a source/target field used by the check;
- `owner` — accountable person/team identifier;
- `reference` — ticket, decision, defect or sign-off reference;
- `expires` — ISO date after which the exception is no longer accepted.

## Evidence semantics

Accepted exceptions remain present in check details with:

```json
{
  "disposition": "accepted-exception",
  "exception": {
    "reason_code": "approved-target-code",
    "reference": "CUT-123",
    "status": "used"
  }
}
```

For exception-aware checks, metrics distinguish:

- `gross_failures` — raw reconciliation failures before exception policy;
- `accepted_exceptions` — failures matched by active approved entries;
- `unaccepted_failures` — remaining failures that drive the gate.

The run summary also reports used, unused and expired exception counts.

## Unused and expired entries

Every configured exception is accounted for:

- **used** — matched a current reconciliation failure;
- **unused** — active entry did not match any current failure; this is surfaced because stale allowlists should be reviewed;
- **expired** — expiry date is in the past and the difference is not accepted.

Expired entries produce an `accepted-exceptions-policy` check using the configured `expiry_policy` severity.

## Provenance

The exception artifact is included in `inputs` with its SHA-256 fingerprint. This lets reviewers prove exactly which allowlist version influenced the run.

## Important constraints

Accepted exceptions are governance decisions, not data transformations. They cannot change source/target values, mappings or tolerances. They only change the disposition of an already-detected deterministic difference.

The current implementation supports detail-level acceptance for `record_coverage`, `field_match`, and `aggregate_match`. Key-integrity failures and global control-total failures remain non-exceptionable by design.

## Runnable example

See [`examples/accepted-exceptions`](../examples/accepted-exceptions).

```bash
rac run examples/accepted-exceptions/reconciliation.yaml \
  --evidence build/accepted-evidence.json \
  --report build/accepted-evidence.md \
  --bundle build/accepted-bundle
```

The example contains one raw field mismatch that is explicitly accepted. The run still records the mismatch, but the net gate passes because there are no unaccepted failures and the exception has not expired.
