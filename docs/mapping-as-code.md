# Mapping as Code integration

[Mapping as Code](https://github.com/dkharlanau/mapping-as-code) can generate a safe starting Reconciliation as Code contract from an approved field mapping.

```bash
map-code project mapping.yaml \
  --target reconciliation-as-code \
  --source-file legacy.csv \
  --target-file target.csv \
  --source-key customer_id \
  --target-key BusinessPartner \
  --format yaml \
  --output reconciliation.yaml
```

The adapter intentionally requires evidence locations and identity keys as explicit inputs. Mapping metadata does not prove where runtime evidence lives or how records should be joined.

Projection policy:

- add a `record_coverage` check;
- convert deterministic `copy` mappings into `field_match` checks;
- convert `lookup` mappings into `field_match` checks with the declared value map;
- preserve high/critical mapping fields as critical materiality policies;
- support comma-separated composite keys;
- do **not** turn constants or arbitrary expressions into equality checks, because that would assert transformation semantics the adapter cannot prove.

Mapping as Code owns mapping intent; Reconciliation as Code owns evidence execution, exceptions, tolerances, scopes, materiality, and retained reconciliation evidence.
