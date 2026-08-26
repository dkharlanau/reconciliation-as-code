# Five-minute first reconciliation

This workflow is designed for the common starting point: two CSV or Excel exports and no existing reconciliation YAML.

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
