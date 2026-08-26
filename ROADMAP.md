# Roadmap

## 0.1 — Working MVP ✅

- YAML reconciliation specification
- CSV source/target adapter
- optional Excel adapter
- single/composite business keys
- key normalization and duplicate detection
- record coverage
- mapping-aware field comparison
- numeric tolerances
- control totals and row counts
- warning/error severity
- evidence JSON + Markdown
- input/spec SHA-256 fingerprints
- CLI exit codes for CI gates
- example, tests, JSON Schema, GitHub Actions

## 0.2 — Useful on real migration files

- JSON / JSONL and Parquet adapters
- aggregate-by-dimension controls
- date and percentage tolerances
- conditional checks (`when`)
- ignore/filter rules
- richer exception categories
- evidence CSV export
- configurable null semantics
- performance tests for 100k–1M rows

## 0.3 — Enterprise integration

- SQL adapter
- plugin interface for source/target adapters
- reusable rule packs
- external mapping-file references
- JUnit/SARIF-like CI output
- signed run manifest
- baseline vs current reconciliation diff

## 0.4 — Connected “as-code” toolkit

- consume Mapping as Code artifacts
- link transformation steps to Transformation Graph
- bind checks to Interface as Code contracts
- publish reconciliation evidence to Project Evidence Graph
- agent-readable run summaries and remediation context

## Non-goals

- storing enterprise credentials in YAML
- replacing source-system extraction tooling
- silently applying AI-generated reconciliation decisions
- becoming an ETL/transformation engine
