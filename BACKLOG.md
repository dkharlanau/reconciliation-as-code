# Product Backlog

This backlog is ordered by product value, not by implementation convenience. The product strategy is documented in [PRODUCT_STRATEGY.md](PRODUCT_STRATEGY.md).

## Priority model

- **P0 — prove the product:** required to make Reconciliation as Code materially useful on real enterprise migration work.
- **P1 — broaden adoption:** scale, distribution, discoverability and adjacent workflows.
- **P2 — ecosystem:** extensibility and agent-native usage after the deterministic core is mature.

## P0 — Real migration value

| Order | Issue | Outcome | Status |
|---:|---|---|---|
| 1 | [#1 Stable reconciliation contract and evidence schema](https://github.com/dkharlanau/reconciliation-as-code/issues/1) | Make controls and evidence safely reusable/versionable. | ✅ Done |
| 2 | [#2 `rac init` guided spec generation](https://github.com/dkharlanau/reconciliation-as-code/issues/2) | Reduce first-use friction from YAML authoring to guided setup. | ✅ Done |
| 3 | [#3 Hierarchical enterprise-object reconciliation](https://github.com/dkharlanau/reconciliation-as-code/issues/3) | Reconcile real Customer/BP, Material, Supplier and document structures rather than flat rows only. | ✅ Done |
| 4 | [#4 Identity crosswalks and 1:N / N:1 reconciliation](https://github.com/dkharlanau/reconciliation-as-code/issues/4) | Handle changed IDs, merges and splits across migrations. | ✅ Done |
| 5 | [#5 Scope, conditional checks and aggregate-by-dimension controls](https://github.com/dkharlanau/reconciliation-as-code/issues/5) | Express migration scope and prove grouped business controls. | ✅ Done |
| 6 | [#6 Governed accepted-exception allowlists](https://github.com/dkharlanau/reconciliation-as-code/issues/6) | Allow known exceptions without hiding them or losing auditability. | ✅ Done |
| 7 | [#7 Audit-grade evidence bundle](https://github.com/dkharlanau/reconciliation-as-code/issues/7) | Produce JSON + HTML + XLSX + CSV evidence usable by engineers and business reviewers. | ✅ Done |
| 8 | [#8 DuckDB backend and 1M+ row benchmarks](https://github.com/dkharlanau/reconciliation-as-code/issues/8) | Prove the engine works on realistic migration volumes. | ✅ Done |
| 9 | [#9 SQL adapters](https://github.com/dkharlanau/reconciliation-as-code/issues/9) | Run against database sources/targets without embedding credentials in specs. | ✅ Done |
| 10 | [#10 SAP S/4HANA starter packs](https://github.com/dkharlanau/reconciliation-as-code/issues/10) | Turn product capabilities into immediately useful and searchable migration scenarios. | ✅ Done |

### P0 release gate

Do not call the product broadly production-ready until P0 is substantially complete and benchmarked. A useful milestone before that is **v0.5 — migration-ready beta**.

## P1 — Adoption, scale and discoverability

| Order | Issue | Outcome | Status |
|---:|---|---|---|
| 11 | [#12 Run-to-run rehearsal diff](https://github.com/dkharlanau/reconciliation-as-code/issues/12) | Show regression/improvement across migration rehearsals. | ✅ Done |
| 12 | [#11 Multi-stage reconciliation](https://github.com/dkharlanau/reconciliation-as-code/issues/11) | Identify the stage where a mismatch was first introduced. | ✅ Done |
| 13 | [#20 Materiality and business criticality policies](https://github.com/dkharlanau/reconciliation-as-code/issues/20) | Separate critical breaks from low-risk differences while preserving raw evidence. | ✅ Done |
| 14 | [#19 JSON/JSONL and Parquet adapters](https://github.com/dkharlanau/reconciliation-as-code/issues/19) | Cover common modern pipeline formats. | Open; Parquet is delivered, JSON/JSONL is pending. |
| 15 | [#16 Mapping as Code interoperability](https://github.com/dkharlanau/reconciliation-as-code/issues/16) | Reuse transformation mappings instead of duplicating reconciliation logic. | ✅ Done |
| 16 | [#13 PyPI, Docker and reusable GitHub Action](https://github.com/dkharlanau/reconciliation-as-code/issues/13) | Make installation and CI adoption trivial. | Open; source package, container, and Action are implemented, public release activation is pending. |
| 17 | [#14 Search-oriented docs site and example gallery](https://github.com/dkharlanau/reconciliation-as-code/issues/14) | Capture real search intent with runnable use cases. | Open; Pages and a documentation hub are available, broader scenario coverage is pending. |
| 18 | [#15 GitHub discoverability and trust signals](https://github.com/dkharlanau/reconciliation-as-code/issues/15) | Improve GitHub search classification, clarity and contributor confidence. | Open; metadata and public guidance exist, continued discoverability work remains. |

## P2 — Ecosystem and agent-native operation

| Order | Issue | Outcome |
|---:|---|---|
| 19 | [#17 Plugin SDK and reusable rule packs](https://github.com/dkharlanau/reconciliation-as-code/issues/17) | Let teams extend adapters/checks without forking the engine. |
| 20 | [#18 MCP/agent interface](https://github.com/dkharlanau/reconciliation-as-code/issues/18) | Let agents draft/run/explain controls while deterministic code remains authoritative. |

## Recommended delivery slices

### Slice A — “Better than a one-off script” ✅

Issues #1, #2, #5, #7.

The user can create a control quickly, run realistic scoped checks and hand off professional evidence.

### Slice B — “Actually enterprise migration aware”

Issues #3, #4, #6, #20. **Delivered.**

The product handles hierarchy, changed identities, merges/splits, governed exceptions and criticality—the areas generic CSV diff tools handle poorly.

### Slice C — “Credible on project data”

Issues #8, #9, #19, #12. DuckDB, SQL, Parquet, and rehearsal diff are delivered; JSON/JSONL remains open.

The engine handles volume, databases/modern formats and repeated rehearsals.

### Slice D — “SAP wedge”

Issues #10, #16. **Delivered.**

Ship deeply worked examples for Customer/BP, Supplier, Material and balances, plus mapping interoperability.

### Slice E — “People can find and adopt it”

Issues #13, #14, #15. **Active:** implementation and public guidance exist, while immutable release activation and broader discoverability remain open.

Package, publish, document and optimize discovery only after the product has concrete proof points to show.

### Slice F — “Platform edge”

Issues #11, #17, #18. Multi-stage reconciliation is delivered; plugin and MCP interfaces remain open.

Add multi-stage diagnosis, ecosystem extensions and agent interfaces after the core value proposition is stable.

## Explicitly deferred

The following are intentionally not backlog priorities yet:

- hosted SaaS UI / multi-tenant control plane;
- automatic remediation of target systems;
- fuzzy matching as the default identity mechanism;
- broad data observability;
- generic ETL/transformation execution;
- LLM-generated acceptance decisions;
- dozens of connectors before the file/SQL engine is excellent.

They may become useful later, but implementing them now would dilute the migration-reconciliation wedge.

## Definition of a high-quality backlog item

A feature should normally enter implementation only when it has:

- a concrete migration/user problem;
- one runnable example or fixture;
- deterministic acceptance criteria;
- evidence/output behavior defined;
- failure/edge cases included;
- documentation implications considered;
- no unnecessary dependency on a hosted service.

The backlog should stay outcome-oriented: fewer features that prove difficult migrations are more valuable than many generic integrations.
