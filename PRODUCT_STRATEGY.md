# Product Strategy

## Product thesis

**Reconciliation as Code should become the portable control layer that proves enterprise data arrived correctly after migration, transformation, cutover, or replication.**

The product should not compete as another generic data-quality platform or file diff utility. Its strongest wedge is a harder problem: proving that the intended **business state** survived a cross-system change even when technical IDs, field names, structures, scopes, mappings, and cardinality changed.

The first market is SAP S/4HANA migration and enterprise integration because the need is concrete and the failure cost is high. The engine remains vendor-neutral so the same model can be used for Salesforce, ERP replacements, data-platform migrations, middleware replication, finance interfaces, or other enterprise transformations.

## Primary job to be done

> Given source state, target state, explicit transformation/mapping knowledge and an agreed migration scope, prove what arrived correctly, what did not, why the comparison was performed that way, and produce evidence that can be reviewed later.

A strong run should answer five questions:

1. **Coverage:** did every in-scope business object arrive, and did anything unexpected appear?
2. **Correctness:** did critical business values arrive according to the intended mappings and tolerances?
3. **Structure:** did child collections and organizational views arrive correctly?
4. **Controls:** do counts, balances and grouped totals reconcile?
5. **Evidence:** can a reviewer reproduce exactly what was checked and distinguish new defects from accepted exceptions?

## Target users

### Primary

- SAP / ERP data migration consultants
- cutover and migration leads
- functional consultants validating business objects
- data migration engineers
- integration / replication support teams

### Secondary

- enterprise architects
- test and assurance teams
- finance/data control owners
- auditors and reviewers consuming generated evidence
- coding/enterprise agents operating deterministic controls

## Product wedge

Generic tools already cover row-level file comparison, data quality checks, query comparison, fuzzy matching, and financial reconciliation. Therefore the product should win on the combination below.

### 1. Transformation-aware reconciliation

Source and target are often not structurally identical. Reconciliation must understand explicit field maps, value maps, normalized keys, crosswalks, merges, splits and scoped transformations.

### 2. Enterprise-object hierarchy

A Customer/BP, Supplier, Material, Sales Order or Purchase Order is not one row. The product should reconcile roots plus repeating child collections such as addresses, roles, sales areas, tax numbers, bank accounts, items and schedules.

### 3. Migration evidence, not only diff output

Every run should produce a versioned manifest, canonical JSON evidence, human-readable reports, discrepancy extracts, fingerprints and accepted-exception provenance suitable for rehearsal, cutover and sign-off.

### 4. Portable and local-first

The control must work outside a specific ERP product and without requiring enterprise data to be uploaded to a SaaS platform. Runtime credentials and data remain outside committed specs.

### 5. Git-native reuse

The valuable asset is not the one-time report. It is the reusable reconciliation control: versioned scope, mapping, tolerances, materiality and exception policy that can be reviewed and replayed across DEV, QA, rehearsals, production and operations.

## First flagship scenario

The flagship should be **SAP ECC / legacy Customer → SAP S/4HANA Business Partner reconciliation**.

It naturally demonstrates the product's differentiation:

- legacy and target IDs can differ;
- Customer/BP has hierarchical child structures;
- organizational views matter;
- value mappings and normalization are common;
- some records are intentionally out of scope;
- known exceptions need controlled acceptance;
- business reviewers want Excel/HTML evidence while automation wants JSON/exit codes.

If this scenario feels materially easier and more controlled than rebuilding an Excel workbook or custom Python script, the product has real value.

## North-star product experience

A migration consultant should be able to:

1. export two datasets;
2. run `rac init source target`;
3. review generated key/field suggestions;
4. add explicit mappings/scope/rules;
5. run reconciliation locally;
6. receive an evidence bundle that explains every failure;
7. rerun the same control in the next rehearsal and see what changed.

Target activation goal: **first useful real-data reconciliation in under 15 minutes** for a flat object, without writing Python.

## What should not become the product

- a generic ETL engine;
- a hosted data warehouse;
- a broad observability platform;
- a fuzzy entity-resolution engine by default;
- a system that silently accepts AI-generated tolerances or mappings;
- an SAP-only runtime that requires ABAP/BTP installation;
- a finance transaction-matching platform competing directly with specialist reconciliation suites.

## Trust principles

1. Deterministic result first.
2. Every transformation used in comparison is explicit.
3. Raw differences remain visible even when materiality/exception policy changes final status.
4. AI may draft or explain controls but cannot silently change reconciliation truth.
5. Evidence should be reproducible and privacy-conscious.
6. Do not claim “enterprise-grade” until scale, security and compatibility guarantees are demonstrated.

## Distribution and discoverability strategy

The repository should be discoverable through **problems**, not only through the project name.

High-intent content should include working pages/examples for:

- SAP S/4HANA data migration reconciliation
- Customer to Business Partner migration validation
- source-to-target data reconciliation
- CSV source target comparison by key
- data migration validation and control totals
- cutover reconciliation and sign-off evidence
- SAP MDG replication reconciliation
- data migration accepted exceptions

Each page should contain a runnable example rather than marketing-only copy.

Distribution priorities:

1. GitHub topics and precise repository metadata
2. PyPI / pipx installation
3. GitHub Pages documentation site
4. reusable GitHub Action
5. real SAP migration starter packs
6. comparison/scope documentation versus spreadsheets, dbt audit helpers, generic data-diff tools and SAP-native validation
7. later: MCP interface and community rule/plugin ecosystem

## Competitive position

### Versus spreadsheet / one-off Python

Win on repeatability, versioning, evidence provenance, CI and reusable rule definitions.

### Versus generic file diff tools

Win on explicit business mappings, hierarchy, scope, cardinality changes, control totals and accepted exceptions.

### Versus dbt/data-quality tools

Win on migration/cutover source→target verification across heterogeneous systems and files rather than warehouse-model testing alone.

### Versus SAP-native DTV / MDS comparison

Do not claim replacement. Win where teams need external, portable, Git-versioned controls across multiple stages/systems, extracts, non-SAP sources, custom transformation logic, or evidence that lives with delivery artifacts.

### Versus reconciliation platforms

Stay narrower and easier to adopt: local-first CLI/spec/evidence layer rather than a hosted multi-user operations platform.

## v1.0 definition

The product can reasonably call itself v1.0 when all of the following are true:

- stable spec/evidence compatibility contract;
- guided first-run workflow;
- hierarchical object support;
- changed-ID and 1:N/N:1 identity handling;
- filters, conditional checks and grouped controls;
- accepted-exception governance;
- audit-grade HTML/XLSX/CSV/JSON evidence bundle with PII controls;
- proven 1M-row execution path;
- SQL plus major file adapters;
- at least four high-quality SAP starter packs;
- PyPI/pipx distribution and reusable GitHub Action;
- searchable documentation site with runnable use-case pages;
- run-to-run rehearsal diff;
- integration with external mapping artifacts.

## Product metrics

Avoid vanity-only metrics. Track:

- time to first successful real reconciliation;
- number of runnable starter/use-case packs;
- percentage of examples continuously tested in CI;
- maximum demonstrated dataset size and benchmark regression;
- spec/evidence compatibility test coverage;
- external installs/downloads and GitHub clones/stars as secondary distribution signals;
- issues/discussions describing real migration use cases as the strongest qualitative signal.

## Current priority

The next work should maximize **proof value**, not feature count.

The critical sequence is:

1. stable contract;
2. guided onboarding;
3. hierarchy + changed identities/cardinality;
4. scope/aggregate/exception policy;
5. evidence bundle;
6. scalable execution;
7. SAP starter packs;
8. distribution/search;
9. ecosystem and agents.

See [BACKLOG.md](BACKLOG.md) and GitHub Issues for execution.