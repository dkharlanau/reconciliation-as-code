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

## 0.2 — Migration controls beta — in progress

Completed:

- stable specification and evidence compatibility contract
- `rac inspect` and `rac init` guided onboarding
- source/target scopes and deterministic predicates
- conditional checks
- aggregate-by-dimension controls
- date and percentage tolerances
- configurable null semantics
- audit-grade evidence bundle: JSON, Markdown, HTML, XLSX, CSV
- PII masking/hash/omit controls

Next:

- hierarchical enterprise-object reconciliation
- identity crosswalks and changed-ID handling
- 1:N and N:1 merge/split reconciliation
- versioned accepted-exception governance
- materiality and critical-field policies

## 0.3 — Scale and enterprise integration

- DuckDB execution backend
- benchmarks for 100k / 1M / 5M rows
- JSON / JSONL and Parquet adapters
- SQL adapter
- plugin interface for source/target adapters
- reusable rule packs
- external mapping-file references
- JUnit/SARIF-like CI output
- signed run manifest
- baseline vs current reconciliation diff

## 0.4 — SAP migration wedge

- Customer → Business Partner starter pack
- Supplier → Business Partner starter pack
- Material master starter pack
- finance/inventory balance control pack
- Mapping as Code interoperability
- realistic multi-stage migration example

## 0.5 — Distribution and discoverability

- PyPI / pipx distribution
- Docker image
- reusable GitHub Action
- search-oriented GitHub Pages documentation
- repository trust/discoverability metadata
- screenshots and runnable example gallery

## 1.0 — Portable migration assurance layer

- compatibility-stable spec/evidence model
- enterprise hierarchy and identity transformations
- scalable file/SQL execution
- governed evidence and accepted exceptions
- run-to-run rehearsal diff
- SAP reference packs
- documented extension/plugin model

## Later — Connected “as-code” toolkit

- consume Mapping as Code artifacts
- link transformation steps to Transformation Graph
- bind checks to Interface as Code contracts
- publish reconciliation evidence to Project Evidence Graph
- agent-readable run summaries and remediation context
- MCP interface after deterministic core is mature

## Non-goals

- storing enterprise credentials in YAML
- replacing source-system extraction tooling
- silently applying AI-generated reconciliation decisions
- becoming an ETL/transformation engine
- becoming a broad hosted data-observability platform
