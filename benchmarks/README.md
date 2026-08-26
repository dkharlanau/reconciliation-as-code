# Scale benchmarks

The DuckDB execution backend is intended for flat migration extracts that are too large to materialize as Python dictionaries.

Generate a deterministic fixture and run the same reconciliation contract at different sizes:

```bash
pip install -e '.[duckdb]'

python benchmarks/generate_large_fixture.py --rows 100000 --output build/benchmark-100k
rac run build/benchmark-100k/reconciliation.yaml --engine duckdb --evidence build/benchmark-100k/evidence.json --report build/benchmark-100k/evidence.md

python benchmarks/generate_large_fixture.py --rows 1000000 --output build/benchmark-1m
rac run build/benchmark-1m/reconciliation.yaml --engine duckdb --evidence build/benchmark-1m/evidence.json --report build/benchmark-1m/evidence.md

python benchmarks/generate_large_fixture.py --rows 5000000 --output build/benchmark-5m
rac run build/benchmark-5m/reconciliation.yaml --engine duckdb --evidence build/benchmark-5m/evidence.json --report build/benchmark-5m/evidence.md
```

The fixture exercises:

- one million+ normalized business keys;
- coverage joins;
- row-level field comparison;
- date comparison;
- control totals;
- grouped counts;
- grouped numeric sums.

The benchmark output records `run.duration_ms`, `run.backend=duckdb`, DuckDB version, input hashes and the normal canonical evidence summary. CI continuously exercises the 1M-row case. The 5M-row workflow can also be run manually so normal pull requests are not forced to create very large temporary files.

## Current boundary

The DuckDB backend currently accelerates **flat** source-to-target reconciliation. Hierarchical child collections and changed-ID merge/split identity processing remain on the Python backend until those stages have a true streaming/query implementation. `rac` rejects `--engine duckdb` for those specs instead of presenting misleading scale claims.
