# Mapping as Code integration

Reconciliation controls should not copy value-mapping logic that is already governed as a Mapping as Code artifact.

The first integration boundary is intentionally local, deterministic and read-only. Reconciliation as Code reads a YAML Mapping as Code artifact, verifies its optional SHA-256 pin, resolves a named mapping field, and reuses only a compatible `lookup` value map for a `field_match` check.

```yaml
mapping_artifacts:
  customer-country:
    file: customer.mapping.yaml
    sha256: 39e87e7039053c75e16402b5a0a7d610bc04ca919bacce96064c2c0034169ade

checks:
  - id: country
    type: field_match
    source: country
    target: Country
    map_ref:
      artifact: customer-country
      field: customer-country
```

The referenced Mapping as Code field must declare matching source/target fields and a lookup transform:

```yaml
mapping:
  id: country-iso2-to-iso3
  fields:
    - id: customer-country
      source: {field: country}
      target: {field: Country}
      transform:
        type: lookup
        reference: iso3-country
value_maps:
  iso3-country:
    DE: DEU
    GB: GBR
```

## Evidence and fingerprint

Every used mapping artifact is added to reconciliation evidence with:

- local path;
- exact SHA-256;
- Mapping as Code `mapping.id`;
- mapping schema version;
- referenced field IDs.

The artifact hash is folded into `configuration_sha256`. Even if a file changes without changing the effective lookup values, the retained reconciliation fingerprint changes. This makes the exact transformation-design input reviewable later.

## Failure behavior

The run fails before reconciliation when:

- the artifact file cannot be loaded;
- a configured SHA-256 pin does not match;
- the referenced artifact alias or field ID is unresolved;
- Mapping as Code source/target fields disagree with the reconciliation check;
- the referenced field is not a lookup transform;
- the lookup's `value_maps` entry is missing or ambiguous.

No scripts, expressions or Mapping as Code runtime code are executed.

## Current boundary

Only local YAML artifacts and lookup value maps are supported in v1 of the bridge. URL/package resolution, transformation execution, constants and expression compilation remain out of scope until concrete use cases justify them. Mapping as Code remains the source of transformation design; Reconciliation as Code consumes a pinned artifact as evidence/input rather than becoming a second mapping editor.

Runnable example: [`examples/mapping-as-code-bridge/`](../examples/mapping-as-code-bridge/).