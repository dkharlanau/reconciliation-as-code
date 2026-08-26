# Materiality and business criticality

Reconciliation should preserve raw differences while allowing an explicit, versioned policy to decide whether those differences are material enough to fail a migration gate.

`materiality` is evaluated **after accepted-exception governance**. A known approved exception therefore does not become a critical failure again, while an unaccepted difference still does.

## Example

```yaml
materiality:
  fields:
    NAME:
      severity: warning
      max_failures: 1
    CREDIT_LIMIT:
      critical: true
```

With this policy:

- one customer-name mismatch remains in `details` and the raw mismatch count remains `1`;
- the name check can still pass the materiality gate;
- any unaccepted `CREDIT_LIMIT` mismatch fails the reconciliation because the field is critical.

The runnable example is in [`examples/materiality`](../examples/materiality).

```bash
rac run examples/materiality/reconciliation.yaml \
  --evidence build/materiality.json \
  --report build/materiality.md \
  --no-fail-on-diff
```

## Policy precedence

For a declared reconciliation check, policy is resolved in this order, with later layers overriding earlier ones:

1. `materiality.default`
2. `materiality.fields.<field>`
3. `materiality.checks.<check-id>`
4. `checks[].materiality`

Automatic engine controls such as source/target key-integrity checks are **not** relaxed by `materiality.default`. This prevents a broad business threshold from accidentally allowing duplicate business keys or similar integrity failures.

## Supported policy fields

| Property | Meaning |
| --- | --- |
| `severity` | Final severity: `error` or `warning`. |
| `critical` | Any unaccepted failure makes this an error-level failed check. |
| `max_failures` | Maximum number of unaccepted failures allowed. |
| `max_failure_percentage` | Maximum percentage of compared records/groups allowed to fail. |
| `max_absolute_difference` | Maximum observed numeric absolute difference. |
| `max_percentage_difference` | Maximum observed numeric percentage difference. |

Numeric materiality uses normalized source/target values when available. If a numeric threshold is configured for a failing check whose differences cannot be interpreted numerically, the policy fails rather than silently ignoring the threshold.

## Evidence semantics

Materiality changes the gate outcome, not history. Every evaluated check records:

```json
{
  "materiality": {
    "policy": {"max_failures": 1},
    "raw_status": "failed",
    "raw_severity": "error",
    "status": "passed",
    "observed": {
      "failures": 1,
      "denominator": 3,
      "failure_percentage": "33.33333333333333333333333333"
    }
  }
}
```

This distinction is intentional: reviewers can see that a raw difference existed, which policy was applied, and why the final gate passed or failed.

## Relationship to accepted exceptions

Accepted exceptions and materiality solve different problems:

- **accepted exception** — this exact discrepancy is known, reviewed and approved;
- **materiality** — this class or amount of unaccepted discrepancy is within an explicit business risk threshold.

Neither mechanism deletes raw evidence.
