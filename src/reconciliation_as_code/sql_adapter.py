from __future__ import annotations

import copy
import csv
import hashlib
import json
import os
import re
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .errors import DataError

_DEFAULT_MAX_ROWS = 1_000_000
_DEFAULT_TIMEOUT_SECONDS = 60.0
_DEFAULT_CHUNK_SIZE = 10_000
_SUPPORTED_DIALECTS = {"sqlite", "postgresql"}


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def connection_env_name(reference: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", reference).strip("_").upper()
    if not normalized:
        raise DataError("SQL connection reference must contain at least one alphanumeric character.")
    return f"RAC_CONNECTION_{normalized}"


def validate_sql_config(config: Any, label: str) -> None:
    if not isinstance(config, dict):
        raise DataError(f"{label} must be an object.")
    unknown = set(config) - {
        "connection",
        "query",
        "params",
        "max_rows",
        "timeout_seconds",
        "chunk_size",
    }
    if unknown:
        raise DataError(f"{label} contains unsupported keys: {sorted(unknown)}.")
    for required in ("connection", "query"):
        if not isinstance(config.get(required), str) or not config.get(required).strip():
            raise DataError(f"{label}.{required} must be a non-empty string.")
    query = config["query"].lstrip()
    first_token = query.split(None, 1)[0].lower() if query else ""
    if first_token not in {"select", "with"}:
        raise DataError(f"{label}.query must be a read query beginning with SELECT or WITH.")
    params = config.get("params", {})
    if not isinstance(params, dict):
        raise DataError(f"{label}.params must be an object when supplied.")
    max_rows = config.get("max_rows", _DEFAULT_MAX_ROWS)
    if not isinstance(max_rows, int) or max_rows < 1:
        raise DataError(f"{label}.max_rows must be an integer >= 1.")
    chunk_size = config.get("chunk_size", _DEFAULT_CHUNK_SIZE)
    if not isinstance(chunk_size, int) or chunk_size < 1:
        raise DataError(f"{label}.chunk_size must be an integer >= 1.")
    timeout = config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise DataError(f"{label}.timeout_seconds must be > 0.")
    connection_env_name(config["connection"])


def _sqlalchemy():
    try:
        import sqlalchemy
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        from sqlalchemy.exc import SQLAlchemyError
    except ImportError as exc:
        raise DataError(
            "SQL endpoints require SQLAlchemy. Install with: pip install 'reconciliation-as-code[sql]'"
        ) from exc
    return sqlalchemy, create_engine, text, make_url, SQLAlchemyError


def _resolve_url(reference: str) -> tuple[str, str]:
    _, _, _, make_url, _ = _sqlalchemy()
    env_name = connection_env_name(reference)
    url = os.environ.get(env_name)
    if not url:
        raise DataError(
            f"SQL connection {reference!r} is not configured. Set environment variable {env_name}."
        )
    try:
        parsed = make_url(url)
        dialect = parsed.get_backend_name()
    except Exception as exc:
        raise DataError(f"SQL connection {reference!r} has an invalid connection URL.") from exc
    if dialect not in _SUPPORTED_DIALECTS:
        raise DataError(
            f"SQL connection {reference!r} uses unsupported dialect {dialect!r}; "
            f"supported dialects are {sorted(_SUPPORTED_DIALECTS)}."
        )
    return url, dialect


def _query_fingerprint(config: dict[str, Any]) -> str:
    payload = {
        "query": config["query"],
        "params": config.get("params", {}),
    }
    return _sha256_text(_canonical(payload))


def _set_read_only_and_timeout(connection: Any, dialect: str, timeout_seconds: float):
    sqlite_raw = None
    if dialect == "postgresql":
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql(
            f"SET LOCAL statement_timeout = {max(1, int(timeout_seconds * 1000))}"
        )
    elif dialect == "sqlite":
        connection.exec_driver_sql("PRAGMA query_only = ON")
        sqlite_raw = connection.connection.driver_connection
        deadline = time.monotonic() + timeout_seconds

        def _progress() -> int:
            return 1 if time.monotonic() >= deadline else 0

        sqlite_raw.set_progress_handler(_progress, 1000)
    return sqlite_raw


def extract_sql_to_csv(
    config: dict[str, Any], output: Path, *, label: str
) -> dict[str, Any]:
    validate_sql_config(config, label)
    _, create_engine, text, _, SQLAlchemyError = _sqlalchemy()
    reference = config["connection"]
    url, dialect = _resolve_url(reference)
    max_rows = int(config.get("max_rows", _DEFAULT_MAX_ROWS))
    timeout_seconds = float(config.get("timeout_seconds", _DEFAULT_TIMEOUT_SECONDS))
    chunk_size = int(config.get("chunk_size", _DEFAULT_CHUNK_SIZE))
    query_sha256 = _query_fingerprint(config)
    output.parent.mkdir(parents=True, exist_ok=True)

    engine = None
    sqlite_raw = None
    row_count = 0
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            with connection.begin():
                sqlite_raw = _set_read_only_and_timeout(connection, dialect, timeout_seconds)
                result = connection.execution_options(stream_results=True).execute(
                    text(config["query"]), config.get("params", {})
                )
                headers = [str(name) for name in result.keys()]
                if not headers:
                    raise DataError(f"{label}.query did not return columns.")
                with output.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(headers)
                    while True:
                        rows = result.fetchmany(chunk_size)
                        if not rows:
                            break
                        row_count += len(rows)
                        if row_count > max_rows:
                            raise DataError(
                                f"{label}.query exceeded max_rows={max_rows}; narrow the query or raise the explicit safety limit."
                            )
                        writer.writerows(tuple(row) for row in rows)
    except DataError:
        raise
    except SQLAlchemyError as exc:
        raise DataError(
            f"SQL extraction failed for connection {reference!r} ({dialect}); credentials and URL are not included in this error."
        ) from exc
    except Exception as exc:
        raise DataError(
            f"SQL extraction failed for connection {reference!r} ({dialect}); credentials and URL are not included in this error."
        ) from exc
    finally:
        if sqlite_raw is not None:
            try:
                sqlite_raw.set_progress_handler(None, 0)
            except Exception:
                pass
        if engine is not None:
            engine.dispose()

    return {
        "path": f"sql:{reference}",
        "sha256": _sha256_file(output),
        "input_type": "sql",
        "connection_ref": reference,
        "connection_env": connection_env_name(reference),
        "dialect": dialect,
        "query_sha256": query_sha256,
        "parameter_names": sorted(str(name) for name in (config.get("params") or {})),
        "rows": row_count,
        "max_rows": max_rows,
        "timeout_seconds": timeout_seconds,
        "chunk_size": chunk_size,
    }


def _sql_endpoint(endpoint: dict[str, Any]) -> bool:
    return isinstance(endpoint, dict) and endpoint.get("sql") is not None


@contextmanager
def prepare_sql_inputs(
    spec: dict[str, Any], *, base_dir: str | Path
) -> Iterator[tuple[dict[str, Any], dict[str, dict[str, Any]]]]:
    """Extract SQL endpoints to bounded temporary CSVs without storing credentials in the spec."""
    execution_spec = copy.deepcopy(spec)
    metadata: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="rac-sql-") as temporary:
        root = Path(temporary)
        for side in ("source", "target"):
            endpoint = execution_spec.get(side)
            if not _sql_endpoint(endpoint):
                continue
            config = endpoint["sql"]
            output = root / f"{side}.csv"
            metadata[side] = extract_sql_to_csv(config, output, label=f"{side}.sql")
            endpoint.pop("sql", None)
            endpoint["file"] = str(output)
            endpoint["format"] = "csv"
            endpoint["delimiter"] = ","
        yield execution_spec, metadata


def apply_sql_input_metadata(
    result: dict[str, Any], original_spec: dict[str, Any], metadata: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if not metadata:
        return result
    for side, info in metadata.items():
        result.setdefault("inputs", {})[side] = dict(info)
    result["sql_inputs"] = {
        side: {
            "connection_ref": info["connection_ref"],
            "dialect": info["dialect"],
            "query_sha256": info["query_sha256"],
            "rows": info["rows"],
            "max_rows": info["max_rows"],
            "timeout_seconds": info["timeout_seconds"],
            "chunk_size": info["chunk_size"],
        }
        for side, info in metadata.items()
    }
    result["configuration_sha256"] = _sha256_text(_canonical(original_spec))
    return result
