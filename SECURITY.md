# Security policy

Reconciliation as Code compares datasets and executes versioned reconciliation controls. Treat reconciliation specs, source/target data, Mapping as Code artifacts and generated evidence as untrusted inputs. Structural validity or a matching hash does not grant execution authority, business approval or permission to access additional systems.

## Supported versions

Security fixes target the current supported release line and `main`. Security advisories and release notes should identify the earliest fixed version when older releases are affected; indefinite security support for every historical release is not implied.

## Reporting a vulnerability

Use GitHub private vulnerability reporting / Security Advisories for this repository when available. Do not place credentials, proprietary datasets, exploit payloads or sensitive evidence in a public issue.

A useful private report includes the affected version/commit, the execution path, the intended boundary, observed impact and a minimal privacy-safe reproduction.

Ordinary reconciliation mismatches, rule semantics and data-quality defects can use public issues when no sensitive data is included.

## Security boundaries

### Specs and datasets are data, not executable authority

YAML controls, CSV/Excel/Parquet/JSON inputs and Mapping artifacts may influence deterministic reconciliation behavior, but accepting them must not silently enable arbitrary code execution, arbitrary network access or access outside documented file/data boundaries. New plugin or executable extension mechanisms require an explicit trust model.

### File and artifact access

Relative file references, Mapping artifacts, crosswalks and exception artifacts are security-sensitive inputs. Consumers should remain within documented local file behavior and fail explicitly on unsupported or integrity-mismatched artifacts rather than guessing or searching arbitrary locations.

A SHA-256 pin proves which bytes were consumed. It does not establish that the producer is authorized or that the business content is correct.

### SQL credentials and connections

Portable reconciliation specs store connection references rather than passwords or DSNs. Runtime connection URLs such as `RAC_CONNECTION_*` values are environment/runtime inputs and must not be copied into canonical evidence, logs or portable bundles.

SQL query inputs are executed against the connection supplied by the operator. Use database credentials with the minimum permissions required for the reconciliation task. The product does not turn a read-oriented reconciliation workflow into authorization for broader database changes.

### Evidence may contain sensitive data

JSON, Markdown, HTML, XLSX and CSV evidence can contain identifiers, source/target metadata and discrepancy values. Use the available masking/hash/omit controls where appropriate and review generated artifacts before attaching them to public issues, releases or CI artifacts.

Public examples and committed fixtures should remain synthetic or deliberately non-sensitive.

### GitHub Action and container boundaries

The reusable GitHub Action inherits permissions and secrets from the caller workflow. It must not require broader repository permissions merely to validate/run a reconciliation. Use least-privilege workflow permissions and avoid passing unnecessary secrets.

The Docker image is a CLI distribution surface, not a sandbox for hostile executable extensions. Mount only the files and credentials needed for the intended run.

### Cross-repository artifacts

Mapping as Code artifacts and other upstream references remain untrusted structured inputs until RAC validates a contract/version it explicitly supports. Unsupported required versions fail closed. Upstream artifacts cannot widen RAC's filesystem, network, database or workflow authority merely by being referenced.

## Examples of security issues

Private security reports are appropriate for issues such as:

- arbitrary file access or path traversal from crafted specs/artifact references;
- unintended command/code execution from data-only fields;
- leakage of DSNs, passwords, tokens or private data into canonical evidence/logs;
- SQL adapter behavior that escapes the documented query/connection boundary;
- integrity-pin or provenance bypass that makes different content appear verified;
- reusable Action behavior that unnecessarily widens permissions or exposes caller secrets;
- practical resource-exhaustion behavior outside documented bounds.

A false reconciliation result is normally a correctness defect unless it also crosses a security/trust boundary.

## Security claim boundary

The project provides deterministic controls, provenance and evidence handling. It does not claim formal security certification, isolation from a malicious operating environment, or production suitability for confidential enterprise data without the operator's surrounding access control, database permissions, CI security and review process.
