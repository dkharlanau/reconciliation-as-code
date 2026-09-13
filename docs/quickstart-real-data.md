# Five-minute first reconciliation

This workflow is designed for the common starting point: two CSV or Excel exports and no existing reconciliation YAML.

## Fast path: guarded preflight

When the two exports have a clear business key and the comparable fields can be mapped conservatively, start with one command:

```bash
rac preflight source.csv target.csv \
  --output-dir build/preflight
```

`rac preflight` reuses the same deterministic `inspect -> init -> run` semantics as the normal CLI. It writes a generated `reconciliation.yaml` first and executes it only when the generated control contains no unresolved field-mapping TODOs.

Expected artifacts after an executable preflight:

```text
build/preflight/
  reconciliation.yaml
  evidence.json
  evidence.md
```

If the business key cannot be selected safely, provide it explicitly or use `--interactive`:

```bash
rac preflight legacy.csv s4.csv \
  --source-key LEGACY_ID \
  --target-key LEGACY_ID \
  --output-dir build/preflight
```

If source and target fields still require semantic review, preflight stops with `status=needs_review`. It leaves the generated YAML and its `# TODO:` comments for review and does **not** create reconciliation evidence.

Preflight is diagnostic by default: a completed reconciliation may report `failed` while the command still exits `0`, so a consultant can inspect the evidence. Add `--fail-on-diff` only when a reviewed preflight should fail automation on differences.

A generated preflight is not cutover sign-off. It does not invent value maps, tolerances, crosswalks, expected counts, hierarchy semantics, or business acceptance rules. For complex changed identities and repeating SAP business objects, start from the relevant project-grade starter pack instead.

The runnable SAP example is [`examples/sap-s4hana/customer-bp-preflight/`](../examples/sap-s4hana/customer-bp-preflight/).

## 1. Inspect both files

```bash
rac inspect legacy-customers.csv
rac inspect s4-business-partners.csv
```

`rac inspect` reports row count, inferred primitive types, null rate, distinct count, uniqueness, and single-column candidate keys that are unique and non-null. Use `--json` when another tool or agent should consume the profile.

For Excel:

```bash
rac inspect legacy.xlsx --sheet Customers
```

## 2. Generate the first control

If both datasets have exactly one safely matching same-named candidate key, the key can be selected automatically:

```bash
rac init source.csv target.csv -o reconciliation.yaml
```

Migration keys often change names or meaning. In that case Reconciliation as Code deliberately refuses to guess business identity. Review the candidates printed by `rac inspect`, then specify the relationship explicitly:

```bash
rac init legacy.csv s4.csv \
  --source-key CUSTOMER_ID \
  --target-key LEGACY_ID \
  -o reconciliation.yaml
```

You can also use `--interactive` to select candidate keys from a terminal.

## 3. Review the generated YAML

The generated file is syntactically valid immediately. Exact and normalized-name column matches are converted into conservative `field_match` checks.

Unresolved or ambiguous columns are not silently mapped. They appear as `# TODO:` comments at the end of the generated YAML. Review these before using the control as migration evidence.

This is intentional: column-name similarity is useful for authoring assistance but is not proof that two enterprise fields have the same business meaning.

## 4. Validate

```bash
rac validate reconciliation.yaml
```

## 5. Run and inspect evidence

```bash
rac run reconciliation.yaml \
  --evidence build/evidence.json \
  --report build/evidence.md \
  --no-fail-on-diff
```

`--no-fail-on-diff` is useful during exploration. Remove it when the reconciliation should act as a CI/cutover gate.

A generated control is a starting point, not an automatically approved migration design. Add project-specific value mappings, normalization rules, tolerances and controls before treating it as sign-off evidence.
