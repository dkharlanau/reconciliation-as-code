# Changelog

## 0.1.0 — release candidate

The first public package release establishes Reconciliation as Code as a deterministic migration-assurance CLI and control format.

### Core reconciliation
- versioned YAML specification and evidence schemas;
- record coverage, field comparison, control totals and grouped aggregate controls;
- composite keys, normalization, tolerances, scopes and conditional checks;
- CSV/Excel reference execution plus DuckDB CSV/Parquet scale path;
- bounded SQLite/PostgreSQL query inputs through credential-free connection references.

### Enterprise migration semantics
- hierarchical business-object reconciliation;
- explicit identity crosswalks for changed IDs, splits and merges;
- accepted exceptions with expiry and provenance;
- materiality and critical-field policy;
- multi-stage source → extract → transform → target reconciliation with first-divergence evidence;
- SAP S/4HANA starter packs for Customer/BP, Supplier/BP, Material/Product, finance and inventory controls.

### Evidence and interoperability
- deterministic JSON/Markdown evidence plus offline HTML/XLSX/CSV bundles;
- SHA-256 provenance for configuration and external input artifacts;
- Mapping as Code pinned value-map bridge;
- Cutover Graph-compatible run identity/evidence contract;
- rehearsal-to-rehearsal evidence diff.

### Distribution included by this release gate
- Python sdist/wheel verification and clean-install smoke;
- minimal CLI container image;
- reusable GitHub Action that validates/runs a spec and uploads evidence artifacts;
- GitHub Release and GHCR publication from an explicit immutable tag;
- optional PyPI Trusted Publisher path with no long-lived token.

### Boundaries
- RAC proves deterministic comparisons and retained evidence from supplied inputs; it does not certify migration correctness beyond those controls.
- It does not connect to SAP production systems by default or perform enterprise writes.
- Agent/plugin platform expansion remains outside the 0.1.0 release gate.
