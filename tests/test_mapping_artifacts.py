from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from reconciliation_as_code.errors import DataError
from reconciliation_as_code.runtime import run_reconciliation_runtime
from reconciliation_as_code.spec import load_spec


EXAMPLE = Path(__file__).parents[1] / "examples" / "mapping-as-code-bridge"


def test_mapping_as_code_value_map_is_reused_with_provenance():
    spec_path = EXAMPLE / "reconciliation.yaml"
    spec = load_spec(spec_path)

    result = run_reconciliation_runtime(spec, base_dir=EXAMPLE, spec_path=spec_path)

    assert result["status"] == "passed"
    country = next(check for check in result["checks"] if check["id"] == "country")
    assert country["status"] == "passed"
    mapping_input = result["inputs"]["mapping:customer-country"]
    assert mapping_input["path"] == "customer.mapping.yaml"
    assert mapping_input["sha256"] == "39e87e7039053c75e16402b5a0a7d610bc04ca919bacce96064c2c0034169ade"
    assert mapping_input["mapping_id"] == "country-iso2-to-iso3"
    assert mapping_input["fields"] == ["customer-country"]


def test_mapping_artifact_change_recomputes_configuration_fingerprint(tmp_path):
    for name in ("source.csv", "target.csv", "customer.mapping.yaml"):
        (tmp_path / name).write_bytes((EXAMPLE / name).read_bytes())
    spec = yaml.safe_load((EXAMPLE / "reconciliation.yaml").read_text(encoding="utf-8"))
    del spec["mapping_artifacts"]["customer-country"]["sha256"]

    first = run_reconciliation_runtime(copy.deepcopy(spec), base_dir=tmp_path)

    mapping_path = tmp_path / "customer.mapping.yaml"
    mapping_path.write_text(
        mapping_path.read_text(encoding="utf-8").replace("Country ISO2 to ISO3", "Country ISO2 to ISO3 reviewed"),
        encoding="utf-8",
    )
    second = run_reconciliation_runtime(copy.deepcopy(spec), base_dir=tmp_path)

    assert first["status"] == second["status"] == "passed"
    assert first["configuration_sha256"] != second["configuration_sha256"]
    assert first["inputs"]["mapping:customer-country"]["sha256"] != second["inputs"]["mapping:customer-country"]["sha256"]


def test_mapping_artifact_sha_pin_fails_closed_when_file_changes(tmp_path):
    for name in ("source.csv", "target.csv", "customer.mapping.yaml"):
        (tmp_path / name).write_bytes((EXAMPLE / name).read_bytes())
    spec = load_spec(EXAMPLE / "reconciliation.yaml")
    mapping_path = tmp_path / "customer.mapping.yaml"
    mapping_path.write_text(mapping_path.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")

    with pytest.raises(DataError, match="SHA-256 mismatch"):
        run_reconciliation_runtime(spec, base_dir=tmp_path)


def test_mapping_artifact_unknown_field_fails_closed():
    spec = load_spec(EXAMPLE / "reconciliation.yaml")
    spec["checks"][1]["map_ref"]["field"] = "missing-field"

    with pytest.raises(DataError, match="unknown Mapping as Code field"):
        run_reconciliation_runtime(spec, base_dir=EXAMPLE)
