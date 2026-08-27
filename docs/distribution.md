# Distribution and release

Reconciliation as Code treats distribution as a reproducibility problem: the same tagged source state must produce the Python package, container and GitHub Action behavior that users run.

## Current source install

Until a public package tag is published, install from a checked-out repository:

```bash
python -m pip install .
```

Optional adapters remain explicit extras:

```bash
python -m pip install '.[duckdb]'
python -m pip install '.[excel]'
python -m pip install '.[sql]'
```

## GitHub Action

The root `action.yml` is a composite action. It installs the exact action revision from `github.action_path`, validates the supplied spec, runs the reconciliation, and uploads the JSON evidence plus Markdown report.

After an immutable public tag exists, a consumer workflow can pin it:

```yaml
- uses: actions/checkout@v4
- uses: dkharlanau/reconciliation-as-code@v0.1.0
  with:
    spec: controls/customer/reconciliation.yaml
    evidence: build/customer-evidence.json
    report: build/customer-evidence.md
    artifact-name: customer-reconciliation
```

For an adapter extra:

```yaml
    extras: duckdb
```

The Action does not upload source/target datasets. Only the explicitly configured evidence/report paths are uploaded.

## Container

The image is a minimal CLI image with `rac` as its entry point. It has no embedded web service and no enterprise credentials.

Build locally:

```bash
docker build -t reconciliation-as-code:local .
docker run --rm -v "$PWD:/work" -w /work reconciliation-as-code:local \
  run examples/mapping-as-code-bridge/reconciliation.yaml \
  --evidence /work/build/evidence.json \
  --report /work/build/evidence.md
```

On a valid release tag, the release workflow publishes the same source revision to GitHub Container Registry as:

```text
ghcr.io/dkharlanau/reconciliation-as-code:0.1.0
ghcr.io/dkharlanau/reconciliation-as-code:v0.1.0
ghcr.io/dkharlanau/reconciliation-as-code:latest
```

`latest` means latest explicitly tagged release, not `main`.

## Release verification

A release candidate must pass, from the exact repository state:

1. tag/package-version consistency;
2. full current test suite through normal CI;
3. sdist and wheel build;
4. `twine check` metadata validation;
5. install of the built wheel into a clean virtual environment;
6. installed CLI validation and execution of the passing Mapping as Code bridge example;
7. Docker build and execution of the same passing example;
8. root composite Action smoke test producing evidence artifacts.

The release workflow runs its verification job on PR changes to distribution metadata without publishing anything.

## GitHub Release and GHCR

A matching explicit tag such as `v0.1.0` is the publication trigger. Only after verification succeeds does the workflow create the GitHub Release and push the container image.

Do not move/reuse a public version tag for different bytes. Fix forward with a new package version.

## PyPI

PyPI is separately gated. Publication requires:

- PyPI Trusted Publisher configured for this repository, `release.yml` workflow and `pypi` environment;
- repository variable `PYPI_PUBLISH_ENABLED=true`.

No long-lived PyPI API token is part of the repository setup. If the variable is absent or false, GitHub Release and GHCR publication can still occur from an explicit tag while PyPI is skipped.

After PyPI publication is confirmed, the normal CLI install becomes:

```bash
pipx install reconciliation-as-code
```

Do not place that command in the primary quick start as an already-working path until the package is actually public.

## Failure boundary

A release verification failure publishes nothing. If GitHub Release/GHCR succeeds but PyPI fails due to external publisher configuration, preserve the immutable verified artifacts; repair the external configuration and retry only if PyPI did not partially publish the version. If package bytes need to change, increment the version first.
