# Run-to-run migration rehearsal diff

A reconciliation run answers **what is wrong now**. A migration program also needs to know **what changed since the previous rehearsal**.

`rac diff` compares two canonical evidence JSON files. It does not need the original source or target datasets.

```bash
rac diff \
  examples/rehearsal-diff/rehearsal-1.json \
  examples/rehearsal-diff/rehearsal-2.json \
  --output build/rehearsal-diff.json \
  --report build/rehearsal-diff.md \
  --html build/rehearsal-diff.html
```

## Discrepancy lifecycle

The diff classifies evidence details into four states.

### New

A discrepancy identity exists in the current run but not in the baseline.

Example:

```text
check=tax-number, key=1004
```

This is a regression signal even if the total number of failed checks did not increase.

### Resolved

A discrepancy existed in the baseline and no longer exists in the current evidence.

Example:

```text
rehearsal 1: customer-name / 1001 failed
rehearsal 2: customer-name / 1001 absent from discrepancy evidence
```

### Persistent

The same check + business locator still has the same discrepancy content.

Example:

```text
country / customer 1002: DE vs US
```

Persistent defects should not be repeatedly presented as new failures.

### Changed

The discrepancy identity is the same but its evidence content changed.

Example:

```text
credit-by-country / DE
rehearsal 1: source 10000, target 9000, difference 1000
rehearsal 2: source 10000, target 9800, difference 200
```

This is neither resolved nor a new defect. The business locator is stable and the gap has changed.

## How discrepancy identity is formed

A discrepancy is identified by:

- check ID;
- check type;
- a stable business locator from the detail evidence.

Locator priority is:

1. `object_path` for hierarchical objects;
2. `key` for record/field controls;
3. `group` for aggregate-by-dimension controls;
4. `difference` where coverage classification matters.

The source/target values are **not** part of identity. They are part of discrepancy content, which is why a changed value becomes `changed` rather than `resolved + new`.

## Check transitions

In addition to individual discrepancies, the diff compares check status:

- `regressed`: passed → failed;
- `improved`: failed → passed;
- `unchanged`: status stayed the same;
- `changed`: another status transition;
- `added` / `removed`: check only exists in one evidence file.

Numeric metric changes are retained per check. For aggregate controls this exposes changes in values such as `groups_failed`; for field controls it exposes `mismatches`; for coverage it exposes missing/unexpected counts.

## Regression gate

By default `rac diff` returns:

- `0` when no new discrepancy and no passed→failed check regression is found;
- `1` when regression is detected;
- `2` for incompatible/invalid evidence.

Use:

```bash
rac diff rehearsal-1.json rehearsal-2.json --no-fail-on-regression
```

when the goal is status reporting rather than a CI/cutover gate.

A changed existing discrepancy does not automatically count as regression because the change may be an improvement. The JSON artifact preserves before/after values so project-specific trend logic can be applied later.

## Compatibility

The diff requires:

- the same reconciliation name;
- a supported evidence schema major version.

It records but does not reject:

- evidence schema minor-version change;
- spec-version change;
- engine-version change;
- configuration fingerprint change.

This matters because a migration control may legitimately evolve between rehearsals. The report surfaces that fact instead of pretending that the control was identical.

## Example without original data

[`examples/rehearsal-diff`](../examples/rehearsal-diff/) contains only:

- `rehearsal-1.json`;
- `rehearsal-2.json`.

There are intentionally no source/target extracts in the directory. This proves the rehearsal diff can be generated from retained canonical evidence alone.

The example shows:

- one resolved customer-name defect;
- one persistent country defect;
- one changed grouped credit-control discrepancy where the difference improves from `1000` to `200`;
- failed checks decrease from `3` to `2`.

## Output

One command writes:

- versioned JSON diff for machines/agents;
- Markdown for cutover status notes;
- self-contained HTML for review.

The diff artifact fingerprints both input evidence files and includes their run IDs, generated timestamps, statuses, versions and configuration hashes.
