# Compatibility policy

Reconciliation controls and their evidence are intended to survive multiple migration rehearsals, releases, environments and engine upgrades. For that reason the project versions the input specification and output evidence independently from the Python package version.

## Specification versions

`version: 1` is the current reconciliation specification contract.

Within specification version 1, compatible releases may:

- add optional fields;
- add new check types or normalizers;
- add new output/report formats;
- improve validation and error messages without changing the meaning of valid existing controls.

A release must not silently change the meaning of an existing valid v1 field or check. A change that requires existing valid v1 specifications to be rewritten requires a new specification version.

Unknown specification versions fail validation explicitly. Existing v1 specifications remain supported throughout compatible 0.x releases and are a compatibility requirement for v1.0.

## Evidence schema versions

Every evidence document contains `schema_version`. The current evidence contract is `1.0` and is published at `schema/evidence.schema.json`.

Compatible changes within evidence 1.x may add optional properties. Removing or renaming required properties, changing their semantic meaning, or changing established value types requires a new major evidence schema version.

The canonical JSON evidence is the machine-readable contract. HTML, Markdown, XLSX and other reports are presentations derived from that evidence and do not define compatibility.

## Provenance

Every run records:

- evidence schema version;
- reconciliation specification version;
- engine/package version;
- unique run ID;
- start and finish timestamps plus duration;
- runtime Python/platform metadata;
- SHA-256 fingerprints of source, target and specification files when available;
- a canonical SHA-256 fingerprint of the parsed reconciliation configuration.

This metadata is designed to show exactly which inputs and control definition produced an evidence bundle. It does not make two run files byte-identical: run IDs, timestamps and durations are intentionally execution-specific.

## Schema discovery

Published schemas live under `schema/` in the repository and are also bundled in the Python package. They can be exported without locating repository files:

```bash
rac schema spec
rac schema evidence
rac schema evidence --output evidence.schema.json
```

CI tests verify that bundled schemas and repository schemas remain semantically identical.

## Deprecation policy

Before a compatible field, command or behavior is removed:

1. it should be marked deprecated in documentation;
2. users should receive a migration path;
3. the replacement should be available before removal;
4. removal that breaks valid specifications or evidence consumers must coincide with an appropriate contract version change.

During alpha the package API may evolve faster than the specification/evidence contracts. The CLI, Python API and report presentation are not yet covered by a full semantic-versioning guarantee unless explicitly documented.
