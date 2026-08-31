# Documentation

Reconciliation as Code defines repeatable source-to-target controls in YAML and produces evidence that can be reviewed by people or consumed by automation. Start with the quickstart, then use the references that match the shape and scale of the migration.

The [runnable use-case gallery](https://dkharlanau.github.io/reconciliation-as-code/use-cases/) provides problem-first entry points for source-to-target, SAP S/4HANA, cutover, and grouped-control scenarios. Each page links back to a checked-in synthetic specification and command.

## Start here

- [Real-data quickstart](quickstart-real-data.md) — inspect two extracts, generate a conservative first specification, validate it, and run it.
- [Specification reference](specification.md) — source and target definitions, checks, tolerances, scopes, and evidence behavior.
- [Architecture and extension boundaries](architecture.md) — runtime structure, deterministic core, and current limits.
- [Compatibility policy](compatibility.md) — versioning expectations for specifications and evidence.

## Enterprise migration controls

- [Hierarchical objects](hierarchical-objects.md) — parent/child collections and object-level roll-up.
- [Identity crosswalks](identity-crosswalks.md) — changed IDs and deterministic 1:1, 1:N, and N:1 reconciliation.
- [Accepted exceptions](accepted-exceptions.md) — governed, expiring exceptions that remain visible in evidence.
- [Materiality](materiality.md) — business criticality without hiding raw differences.
- [Multi-stage reconciliation](multi-stage.md) — localize the first pipeline transition where drift appears.
- [Rehearsal diff](rehearsal-diff.md) — compare retained evidence from two migration runs.

## Inputs, scale, and interoperability

- [DuckDB backend](duckdb-backend.md) — scalable flat CSV/Parquet reconciliation and supported control boundaries.
- [SQL adapters](sql-adapters.md) — SQLite/PostgreSQL connection references and safe evidence provenance.
- [Mapping as Code integration](mapping-as-code-integration.md) — consume a pinned lookup mapping without executing transformation code.
- [SAP-native validation](sap-native-validation.md) — how the included SAP starter packs are structured and tested.
- [Scale benchmarks](../benchmarks/README.md) — reproducible 100k, 1M, and 5M fixture generation and measurements.

## Evidence and distribution

- [Evidence bundle and privacy controls](evidence-bundle.md) — JSON, Markdown, offline HTML, XLSX, CSV details, hashes, and value redaction.
- [Distribution and release](distribution.md) — source install, composite Action, container, and release gates.
- [Agent manifest](agent-manifest.json) — machine-readable capabilities and safe operating loop.

Runnable examples live under [`examples/`](../examples/). They use synthetic data and are exercised in continuous integration. Reconciliation evidence can still contain sensitive values when used on real data; review the evidence policy before publishing or attaching generated artifacts.
