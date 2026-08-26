# Migration rehearsal 1 → rehearsal 2

This example demonstrates run-to-run reconciliation comparison using **only retained evidence JSON**.

There are deliberately no source or target datasets in this directory.

```bash
rac diff rehearsal-1.json rehearsal-2.json \
  --output build/rehearsal-diff.json \
  --report build/rehearsal-diff.md \
  --html build/rehearsal-diff.html
```

Expected result:

| Signal | Count |
| --- | ---: |
| New discrepancies | 0 |
| Resolved discrepancies | 1 |
| Persistent discrepancies | 1 |
| Changed discrepancies | 1 |
| Improved checks | 1 |
| Regressed checks | 0 |

The resolved item is `customer-name / 1001`.

The persistent item is `country / 1002`.

The changed item is aggregate group `credit-by-country / DE`: the difference improves from `1000` to `200`, so it remains the same business discrepancy but with changed evidence content.

Because there is no new discrepancy and no check transitioned from passed to failed, the forward diff returns exit code `0`.

Reverse the files to simulate regression:

```bash
rac diff rehearsal-2.json rehearsal-1.json
```

That returns exit code `1` because the customer-name discrepancy reappears and the check regresses from passed to failed.
