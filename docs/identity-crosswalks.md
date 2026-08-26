# Identity crosswalks: changed IDs, splits and merges

Source and target business keys frequently change during ERP migration. A legacy Customer ID may become a new Business Partner ID; one source object may split into multiple target objects; several source records may merge into one target object.

`reconciliation-as-code` treats this as an explicit identity transformation, not fuzzy matching.

## Crosswalk

```yaml
identity:
  crosswalk:
    file: crosswalk.csv
    source_key: SOURCE_ID
    target_key: TARGET_ID
```

```csv
SOURCE_ID,TARGET_ID
1001,9001
1002,9002
1002,9003
1003,9004
1004,9004
```

The example contains three identity components:

- `1001 → 9001` — `1:1`, changed technical ID;
- `1002 → 9002 + 9003` — `1:N`, explicit split;
- `1003 + 1004 → 9004` — `N:1`, explicit merge.

The engine builds deterministic identity components from the crosswalk and compares source and target at component level.

## Aggregation policy

When an identity component contains more than one row on a side, values must have deterministic aggregation semantics.

```yaml
identity:
  aggregation:
    source:
      COUNTRY: require_equal
      AMOUNT: sum
    target:
      COUNTRY: require_equal
      AMOUNT: sum
```

Supported policies:

- `require_equal` — every value on that side must agree;
- `sum` — numeric sum;
- `min`;
- `max`;
- `first` — explicit order-dependent choice; use only when intentional;
- `set` — canonical sorted set joined for deterministic comparison.

Fields used by reconciliation checks default to `require_equal`. If multiple values disagree, execution stops and asks for an explicit policy rather than guessing.

## N:N is deliberately rejected

A connected component with multiple source and multiple target identities is ambiguous for deterministic migration assurance. The engine rejects it with an actionable validation error.

Model the transformation as separate explicit `1:N` / `N:1` components or introduce a project-specific transformation artifact instead of allowing implicit many-to-many matching.

## Unmapped identities

A source or target root record not represented in the crosswalk is not silently dropped. The run adds an `identity-crosswalk-integrity` check with explicit categories such as:

- `unmapped_source_identity`;
- `unmapped_target_identity`;
- `unmapped_source_child_parent`;
- `unmapped_target_child_parent`;
- unused crosswalk source/target references.

Unmapped runtime identities fail the error gate.

## Evidence provenance

The evidence bundle contains:

- SHA-256 fingerprint of the crosswalk;
- stable component IDs;
- component mode (`1:1`, `1:N`, `N:1`);
- original source keys;
- original target keys;
- aggregation policy;
- raw source/target record counts;
- crosswalk-integrity metrics.

Differences produced after canonicalization are annotated with the identity component so a reviewer can trace a synthetic comparison identity back to real source and target IDs.

## Hierarchy composition

Identity crosswalks also rewrite child parent identity before hierarchical reconciliation. This allows, for example:

```text
legacy customer 1001 / address BILL
             ↓ crosswalk
business partner 9001 / address BILL
```

to be reconciled as one business-object child even though the root technical ID changed.

## Runnable example

See [`examples/identity-merge-split`](../examples/identity-merge-split).

```bash
rac run examples/identity-merge-split/reconciliation.yaml \
  --evidence build/identity-evidence.json \
  --report build/identity-evidence.md \
  --bundle build/identity-bundle
```

The example is expected to pass and demonstrates changed IDs, a split and a merge in one run.
