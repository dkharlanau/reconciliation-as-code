# Contributing

Reconciliation as Code welcomes focused fixes, documentation improvements, and deterministic reconciliation capabilities. The project is still pre-1.0, so a small, well-evidenced change is easier to review and safer to adopt than a broad redesign.

## Before opening a change

1. Read [README.md](README.md), [AGENTS.md](AGENTS.md), and the relevant file under [`docs/`](docs/index.md).
2. Search existing issues and pull requests to avoid duplicating active work.
3. Keep credentials, client data, proprietary field names, and real reconciliation evidence out of the repository. Fixtures must be synthetic.
4. Preserve the documented security boundaries: specifications and referenced artifacts are data, not executable authority.

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
```

Run a representative CLI flow when changing behavior:

```bash
rac inspect examples/customer-migration/legacy.csv --json
rac validate examples/customer-migration/reconciliation.yaml
rac run examples/mapping-as-code-bridge/reconciliation.yaml \
  --evidence build/evidence.json \
  --report build/evidence.md
```

## Change expectations

- Add or update tests for observable behavior.
- Keep the JSON Schema, examples, CLI help, and documentation aligned.
- Make evidence deterministic and retain explicit provenance.
- Do not silently relax validation or convert missing evidence into success.
- Describe compatibility or migration effects when changing a published schema.
- Run `python -m build` when changing packaging or distribution metadata.

Pull requests should state the user problem, the implemented boundary, validation performed, and any deliberately deferred work. Security-sensitive findings should follow [SECURITY.md](SECURITY.md) instead of being disclosed in a public issue.
