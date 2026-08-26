# Multi-stage migration reconciliation

A final source→target mismatch tells you that migration state is wrong. It does not tell you **where the state first became wrong**.

`rac pipeline` reconciles an ordered chain such as:

```text
legacy source → extract → transformed load file → target
```

Each adjacent transition uses the same deterministic checks as a normal reconciliation. The pipeline evidence then derives the first transition where each business discrepancy appears.

## Run

```bash
rac pipeline examples/multi-stage/pipeline.yaml \
  --evidence build/pipeline-evidence.json \
  --report build/pipeline-evidence.md \
  --html build/pipeline-evidence.html \
  --no-fail-on-diff
```

## Pipeline specification

```yaml
version: 1

pipeline:
  name: Customer migration

stages:
  - id: source
    endpoint:
      file: source.csv
      key: ID

  - id: extract
    endpoint:
      file: extract.csv
      key: ID

  - id: transformed
    endpoint:
      file: transformed.csv
      key: ID

  - id: target
    endpoint:
      file: target.csv
      key: ID

transitions:
  - id: source-to-extract
    from: source
    to: extract
    checks:
      - id: coverage
        type: record_coverage
      - id: country
        type: field_match
        source: COUNTRY
        target: COUNTRY

  - id: extract-to-transformed
    from: extract
    to: transformed
    checks:
      - id: coverage
        type: record_coverage
      - id: country
        type: field_match
        source: COUNTRY
        target: COUNTRY_CODE
        map:
          DE: DEU
          US: USA

  - id: transformed-to-target
    from: transformed
    to: target
    checks:
      - id: coverage
        type: record_coverage
      - id: country
        type: field_match
        source: COUNTRY_CODE
        target: COUNTRY_CODE
```

The ordered `stages` list defines the migration path. A transition is required for every adjacent pair.

## Expected transformations are explicit

A legitimate transformation should not be reported as drift.

In the example, two-letter country codes intentionally become three-letter codes between `extract` and `transformed`:

```yaml
map:
  DE: DEU
  US: USA
```

The country check therefore passes on that edge. An unexpected amount change on the same edge fails.

This is the same principle used by normal Reconciliation as Code controls: transformation knowledge is explicit and versioned rather than inferred.

## First-divergence evidence

For every observed discrepancy, pipeline evidence identifies:

- check ID and type;
- stable business locator (`key`, `group`, `object_path`, coverage difference);
- first failing transition;
- from/to stage IDs;
- underlying discrepancy detail.

Example:

```json
{
  "check_id": "amount",
  "locator": {"key": "1002"},
  "first_transition": "extract-to-transformed",
  "from_stage": "extract",
  "to_stage": "transformed"
}
```

If the same `amount / 1002` problem is also visible on a later edge, the first-divergence record still points to the earlier transition.

Stable check IDs should therefore represent the same logical business control across stage transitions even when physical field names change.

## End-to-end control

An optional `end_to_end` comparison independently checks the first stage against the last stage:

```yaml
end_to_end:
  id: source-to-target
  checks:
    - id: coverage
      type: record_coverage
    - id: country
      type: field_match
      source: COUNTRY
      target: COUNTRY_CODE
      map:
        DE: DEU
        US: USA
```

This keeps two questions separate:

1. **Did the final target reconcile end-to-end?**
2. **At which adjacent transition did each discrepancy first appear?**

## Run only part of a pipeline

During troubleshooting you can run a contiguous stage subset:

```bash
rac pipeline pipeline.yaml \
  --from-stage extract \
  --to-stage transformed
```

Only transitions inside the selected range are executed. Full `end_to_end` is skipped for a subset.

## Stage fingerprints

Every stage is fingerprinted in pipeline evidence. File stages carry their SHA-256. SQL stages carry the same safe SQL provenance used by normal SQL endpoints, including connection reference, dialect, query fingerprint and extracted-data fingerprint without the runtime DSN/password.

A SQL stage is extracted **once per pipeline run** and reused by adjacent transitions. This avoids querying one logical stage twice and accidentally diagnosing database movement between two reads as migration drift.

## Transition capabilities

Each transition composes the normal reconciliation runtime and can use:

- coverage, field, row-count, total and grouped controls;
- scopes and `when` predicates;
- mappings and tolerances;
- changed-ID identity crosswalks;
- hierarchical children;
- accepted exceptions;
- materiality policies.

Backend restrictions remain unchanged. For example, hierarchy/identity transitions require the Python backend until those features have query-native DuckDB execution.

## Reports

One pipeline run produces:

- versioned pipeline evidence JSON;
- Markdown summary;
- offline HTML with a visible stage path and transition status;
- embedded canonical evidence for every transition and optional end-to-end comparison.

Expose schemas with:

```bash
rac schema pipeline
rac schema pipeline-evidence
```

## Included example

[`examples/multi-stage`](../examples/multi-stage/) has four stages and two deliberate drift points:

1. `extract → transformed`: Customer `1002` amount changes from `200` to `190` unexpectedly;
2. `transformed → target`: Customer `1002` disappears entirely.

The expected country-code transformation passes. The pipeline therefore localizes the actual defects instead of treating every transformed field as suspicious.
