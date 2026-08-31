# Roadmap

This roadmap distinguishes shipped behavior from planned work. A checked item is present in the repository with tests or a runnable example; it is not a claim that the project is production-ready for every enterprise environment.

## 0.1 — Working MVP — delivered

- YAML reconciliation specification and published JSON Schemas
- CSV source/target adapter, with optional Excel support
- single/composite business keys, normalization, and duplicate detection
- record coverage, field comparison, row counts, totals, and grouped controls
- explicit mappings, null rules, and numeric/date/percentage tolerances
- deterministic evidence JSON and Markdown with SHA-256 provenance
- CI-oriented exit codes, examples, and tests

## 0.2 — Enterprise migration semantics — delivered

- guided `rac inspect` and `rac init` onboarding
- scopes, conditional checks, and aggregate-by-dimension controls
- hierarchical enterprise objects and object-level failure roll-up
- identity crosswalks with deterministic 1:1, 1:N, and N:1 handling
- versioned accepted-exception governance
- materiality and critical-field policies
- evidence bundles with offline HTML, XLSX, CSV detail files, and value masking/hash/omit controls

## 0.3 — Scale and integration — active

Delivered:

- DuckDB execution backend for supported flat controls
- reproducible 100k / 1M / 5M benchmark tooling and a required 1M-row CI run
- CSV and Parquet support on DuckDB
- SQLite and PostgreSQL query adapters using runtime connection references
- pinned Mapping as Code lookup-artifact integration
- multi-stage pipeline reconciliation
- retained-evidence rehearsal diff

Remaining:

- first-class JSON and JSONL adapters
- documented plugin interface for source/target adapters and checks
- reusable rule-pack packaging
- JUnit or SARIF-style CI output
- optional externally signed run manifests

## 0.4 — SAP migration wedge — delivered

- Customer to Business Partner starter pack
- Supplier to Business Partner starter pack
- Material master starter pack
- finance and inventory balance controls
- Mapping as Code interoperability example
- realistic multi-stage migration example

The packs are deterministic reference implementations with synthetic fixtures. They do not replace project-specific scope, mappings, business approval, or validation in a target SAP landscape.

## 0.5 — Distribution and discoverability — active

Delivered:

- source-installable Python package with sdist/wheel verification
- minimal Docker CLI image
- reusable composite GitHub Action
- GitHub Pages product and documentation entry point
- repository security, contribution, agent, and package metadata
- runnable example catalog

Remaining:

- first immutable public version tag and GitHub Release
- confirmed GHCR image publication from that tag
- optional PyPI publication after Trusted Publisher configuration
- broader search-oriented scenario documentation

## 1.0 — Portable migration assurance layer

Before a 1.0 claim, the project should have a compatibility-stable specification/evidence model, an explicit extension boundary, repeatable distribution, and evidence from independent usage. Production suitability remains an operator decision shaped by data sensitivity, access controls, review, and the surrounding delivery process.

## Later — Connected as-code toolkit

- consume additional governed Mapping as Code artifacts
- link transformation stages to Transformation Graph
- bind relevant checks to Interface as Code contracts
- publish reconciliation evidence into a project evidence model
- provide agent-readable run summaries and remediation context
- consider an MCP interface only after the deterministic core and authority model are stable

## Non-goals

- storing enterprise credentials in YAML
- replacing source-system extraction tooling
- silently applying AI-generated reconciliation decisions
- becoming an ETL/transformation engine
- becoming a broad hosted data-observability platform
