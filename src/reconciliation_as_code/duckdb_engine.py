from __future__ import annotations

import hashlib
import json
import platform
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any

from .errors import DataError
from .normalize import normalize_value
from .spec import validate_spec

EVIDENCE_SCHEMA_VERSION = "1.0"


def _duckdb():
    try:
        import duckdb
    except ImportError as exc:
        raise DataError(
            "DuckDB backend is not installed. Install with: pip install 'reconciliation-as-code[duckdb]'"
        ) from exc
    return duckdb


def _listify(value: str | list[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_object(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _engine_version() -> str:
    try:
        return package_version("reconciliation-as-code")
    except PackageNotFoundError:
        return "0+unknown"


def _qid(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _lit(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    text = str(value).replace("'", "''")
    return f"'{text}'"


def _path_literal(path: Path) -> str:
    return _lit(str(path))


def _format(endpoint: dict[str, Any], path: Path) -> str:
    declared = endpoint.get("format")
    if declared:
        return str(declared).lower()
    suffix = path.suffix.lower().lstrip(".")
    if suffix == "csv":
        return "csv"
    if suffix == "parquet":
        return "parquet"
    return suffix


def _reader_sql(endpoint: dict[str, Any], path: Path) -> str:
    fmt = _format(endpoint, path)
    if fmt == "csv":
        delimiter = endpoint.get("delimiter", ",")
        return (
            f"read_csv_auto({_path_literal(path)}, header=true, all_varchar=true, "
            f"delim={_lit(delimiter)})"
        )
    if fmt == "parquet":
        return f"read_parquet({_path_literal(path)})"
    raise DataError(
        f"DuckDB backend supports CSV and Parquet inputs; got {fmt or path.suffix!r} for {path}."
    )


def _normalize_expr(expr: str, operations: list[str] | None = None) -> str:
    operations = operations or ["trim"]
    current = f"CAST({expr} AS VARCHAR)"
    for operation in operations:
        if operation == "empty_to_null":
            current = f"CASE WHEN {current} IS NULL OR trim({current}) = '' THEN NULL ELSE {current} END"
        elif operation == "trim":
            current = f"trim({current})"
        elif operation == "uppercase":
            current = f"upper({current})"
        elif operation == "lowercase":
            current = f"lower({current})"
        elif operation == "strip_leading_zeros":
            text = f"trim({current})"
            positive = f"coalesce(nullif(regexp_replace({text}, '^0+', ''), ''), '0')"
            negative_digits = f"substr({text}, 2)"
            negative = (
                "'-' || coalesce(nullif(regexp_replace(" + negative_digits + ", '^0+', ''), ''), '0')"
            )
            current = (
                f"CASE WHEN regexp_full_match({text}, '[0-9]+') THEN {positive} "
                f"WHEN regexp_full_match({text}, '-[0-9]+') THEN {negative} ELSE {current} END"
            )
    return current


def _key_expr(alias: str, field: str, operations: list[str]) -> str:
    normalized = _normalize_expr(f"{alias}.{_qid(field)}", operations)
    return f"coalesce(CAST({normalized} AS VARCHAR), '')"


def _key_select(alias: str, fields: list[str], operations: list[str]) -> list[str]:
    return [f"{_key_expr(alias, field, operations)} AS __k{index}" for index, field in enumerate(fields)]


def _key_cols(count: int, prefix: str | None = None) -> list[str]:
    base = [f"__k{index}" for index in range(count)]
    if prefix:
        return [f"{prefix}.{name}" for name in base]
    return base


def _key_label(row: tuple[Any, ...]) -> str | list[str]:
    values = ["" if value is None else str(value) for value in row]
    return values[0] if len(values) == 1 else values


def _normalized_literal(value: Any, operations: list[str]) -> Any:
    return normalize_value(value, operations)


def _is_null_expr(expr: str) -> str:
    return f"({expr} IS NULL OR trim(CAST({expr} AS VARCHAR)) = '')"


def _try_decimal(expr: str) -> str:
    return f"try_cast(replace(trim(CAST({expr} AS VARCHAR)), ',', '') AS DECIMAL(38,10))"


def _predicate_sql(alias: str, predicate: dict[str, Any] | None) -> str:
    if not predicate:
        return "TRUE"
    if "all" in predicate:
        return "(" + " AND ".join(_predicate_sql(alias, item) for item in predicate["all"]) + ")"
    if "any" in predicate:
        return "(" + " OR ".join(_predicate_sql(alias, item) for item in predicate["any"]) + ")"
    if "not" in predicate:
        return f"(NOT {_predicate_sql(alias, predicate['not'])})"

    field_expr = f"{alias}.{_qid(predicate['field'])}"
    op = predicate.get("op", "eq")
    if op == "is_null":
        return _is_null_expr(field_expr)
    if op == "not_null":
        return f"NOT {_is_null_expr(field_expr)}"

    operations = predicate.get("normalize", ["trim"])
    left = _normalize_expr(field_expr, operations)
    expected = predicate.get("value")
    if op in {"in", "not_in"}:
        values = [_normalized_literal(item, operations) for item in expected]
        literals = ", ".join(_lit(item) for item in values) or "NULL"
        expr = f"{left} IN ({literals})"
        return f"NOT ({expr})" if op == "not_in" else expr

    right_value = _normalized_literal(expected, operations)
    if right_value is None:
        if op == "eq":
            return f"{left} IS NULL"
        if op == "ne":
            return f"{left} IS NOT NULL"
    right = _lit(right_value)
    if op == "eq":
        return f"{left} IS NOT DISTINCT FROM {right}"
    if op == "ne":
        return f"NOT ({left} IS NOT DISTINCT FROM {right})"
    if op == "contains":
        return f"strpos(CAST({left} AS VARCHAR), CAST({right} AS VARCHAR)) > 0"
    if op == "starts_with":
        return f"starts_with(CAST({left} AS VARCHAR), CAST({right} AS VARCHAR))"

    try:
        Decimal(str(right_value))
        numeric = True
    except (InvalidOperation, ValueError):
        numeric = False
    if numeric:
        comparable_left = _try_decimal(left)
        comparable_right = f"CAST({right} AS DECIMAL(38,10))"
    else:
        comparable_left = f"CAST({left} AS VARCHAR)"
        comparable_right = f"CAST({right} AS VARCHAR)"
    operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return f"{comparable_left} {operator} {comparable_right}"


def _and(*expressions: str) -> str:
    values = [expr for expr in expressions if expr and expr != "TRUE"]
    return " AND ".join(f"({expr})" for expr in values) if values else "TRUE"


def _scope_predicates(spec: dict[str, Any], check: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_predicate = None
    target_predicate = None
    scope_name = check.get("scope")
    if scope_name:
        scope = spec.get("scopes", {}).get(scope_name, {})
        source_predicate = scope.get("source")
        target_predicate = scope.get("target")
    when = check.get("when") or {}
    if when.get("source"):
        source_predicate = {"all": [source_predicate, when["source"]]} if source_predicate else when["source"]
    if when.get("target"):
        target_predicate = {"all": [target_predicate, when["target"]]} if target_predicate else when["target"]
    return source_predicate, target_predicate


def _decimal_text(value: Any) -> str:
    decimal = Decimal(str(value or 0))
    normalized = decimal.normalize()
    text = format(normalized, "f")
    return "0" if text in {"-0", ""} else text


def _result(
    check_id: str,
    check_type: str,
    severity: str,
    passed: bool,
    metrics: dict[str, Any],
    details: list[dict[str, Any]] | None = None,
    detail_limit: int = 100,
    total_details: int | None = None,
) -> dict[str, Any]:
    details = details or []
    total = len(details) if total_details is None else total_details
    return {
        "id": check_id,
        "type": check_type,
        "severity": severity,
        "status": "passed" if passed else "failed",
        "metrics": metrics,
        "details": details[:detail_limit],
        "details_truncated": total > detail_limit,
    }


def _fetch_keys(connection: Any, sql: str, count: int, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    rows = connection.execute(f"{sql} LIMIT {int(limit)}").fetchall()
    return [{"key": _key_label(tuple(row[:count]))} for row in rows]


def _duplicate_check(
    connection: Any, view: str, side: str, key_count: int, detail_limit: int
) -> dict[str, Any]:
    cols = ", ".join(_key_cols(key_count))
    grouped = f"SELECT {cols}, count(*) AS cnt FROM {view} GROUP BY {cols} HAVING count(*) > 1"
    duplicate_count = int(
        connection.execute(f"SELECT coalesce(sum(cnt - 1), 0) FROM ({grouped})").fetchone()[0]
    )
    details: list[dict[str, Any]] = []
    if detail_limit > 0 and duplicate_count:
        rows = connection.execute(f"{grouped} ORDER BY {cols} LIMIT {int(detail_limit)}").fetchall()
        for row in rows:
            key = _key_label(tuple(row[:key_count]))
            repeats = min(int(row[key_count]) - 1, detail_limit - len(details))
            details.extend({"key": key} for _ in range(max(repeats, 0)))
            if len(details) >= detail_limit:
                break
    return _result(
        f"{side}-key-integrity",
        "key_integrity",
        "error",
        duplicate_count == 0,
        {"duplicate_keys": duplicate_count},
        details,
        detail_limit,
        duplicate_count,
    )


def _coverage_stats(
    connection: Any,
    source_sql: str,
    target_sql: str,
    key_count: int,
    detail_limit: int,
    allow_unexpected: bool,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    cols = _key_cols(key_count)
    select_cols = ", ".join(cols)
    join = " AND ".join(f"s.{col} = t.{col}" for col in cols)
    first = cols[0]
    matched = int(
        connection.execute(
            f"SELECT count(*) FROM (SELECT DISTINCT {select_cols} FROM ({source_sql})) s "
            f"JOIN (SELECT DISTINCT {select_cols} FROM ({target_sql})) t ON {join}"
        ).fetchone()[0]
    )
    missing_sql = (
        f"SELECT {', '.join(f's.{col}' for col in cols)} FROM "
        f"(SELECT DISTINCT {select_cols} FROM ({source_sql})) s LEFT JOIN "
        f"(SELECT DISTINCT {select_cols} FROM ({target_sql})) t ON {join} "
        f"WHERE t.{first} IS NULL"
    )
    unexpected_sql = (
        f"SELECT {', '.join(f't.{col}' for col in cols)} FROM "
        f"(SELECT DISTINCT {select_cols} FROM ({target_sql})) t LEFT JOIN "
        f"(SELECT DISTINCT {select_cols} FROM ({source_sql})) s ON {join} "
        f"WHERE s.{first} IS NULL"
    )
    missing = int(connection.execute(f"SELECT count(*) FROM ({missing_sql})").fetchone()[0])
    unexpected = int(connection.execute(f"SELECT count(*) FROM ({unexpected_sql})").fetchone()[0])
    details: list[dict[str, Any]] = []
    if detail_limit > 0:
        for item in _fetch_keys(connection, missing_sql, key_count, detail_limit):
            details.append({**item, "difference": "missing_in_target"})
        remaining = max(detail_limit - len(details), 0)
        for item in _fetch_keys(connection, unexpected_sql, key_count, remaining):
            details.append({**item, "difference": "unexpected_in_target"})
    return {"matched": matched, "missing": missing, "unexpected": unexpected}, details


def _mapped_expr(expr: str, mapping: dict[Any, Any]) -> str:
    if not mapping:
        return expr
    branches = " ".join(
        f"WHEN {expr} IS NOT DISTINCT FROM {_lit(key)} THEN {_lit(value)}"
        for key, value in mapping.items()
    )
    return f"CASE {branches} ELSE {expr} END"


def _field_expressions(check: dict[str, Any]) -> tuple[str, str, str, str]:
    source_raw = f"s.{_qid(check['source'])}"
    target_raw = f"t.{_qid(check['target'])}"
    operations = check.get("normalize", ["trim"])
    left = _normalize_expr(source_raw, operations)
    right = _normalize_expr(target_raw, operations)
    null_semantics = check.get("null_semantics", "equal")
    if null_semantics == "empty_is_null":
        left = f"CASE WHEN {_is_null_expr(left)} THEN NULL ELSE {left} END"
        right = f"CASE WHEN {_is_null_expr(right)} THEN NULL ELSE {right} END"
    left = _mapped_expr(left, check.get("map") or {})

    never_equal_null = "FALSE"
    if null_semantics == "never_equal":
        never_equal_null = f"({_is_null_expr(left)} OR {_is_null_expr(right)})"

    if check.get("date_tolerance_days") is not None:
        left_date = f"try_cast({left} AS TIMESTAMP)"
        right_date = f"try_cast({right} AS TIMESTAMP)"
        tolerance = float(check["date_tolerance_days"])
        equal = (
            f"CASE WHEN {never_equal_null} THEN FALSE "
            f"WHEN {left_date} IS NULL OR {right_date} IS NULL THEN "
            f"({left_date} IS NULL AND {right_date} IS NULL) "
            f"ELSE abs(epoch({left_date}) - epoch({right_date})) / 86400.0 <= {tolerance} END"
        )
        return source_raw, target_raw, left, equal

    absolute_tolerance = check.get("numeric_tolerance")
    percentage_tolerance = check.get("percentage_tolerance")
    if absolute_tolerance is not None or percentage_tolerance is not None:
        left_num = f"coalesce({_try_decimal(left)}, CASE WHEN {_is_null_expr(left)} THEN 0 ELSE NULL END)"
        right_num = f"coalesce({_try_decimal(right)}, CASE WHEN {_is_null_expr(right)} THEN 0 ELSE NULL END)"
        difference = f"abs({left_num} - {right_num})"
        clauses: list[str] = []
        if absolute_tolerance is not None:
            clauses.append(f"{difference} <= {Decimal(str(absolute_tolerance))}")
        if percentage_tolerance is not None:
            clauses.append(
                f"CASE WHEN {left_num} = 0 THEN {difference} = 0 "
                f"ELSE ({difference} / abs({left_num}) * 100) <= {Decimal(str(percentage_tolerance))} END"
            )
        tolerance_expr = " OR ".join(f"({clause})" for clause in clauses)
        equal = (
            f"CASE WHEN {never_equal_null} THEN FALSE "
            f"WHEN {left_num} IS NULL OR {right_num} IS NULL THEN FALSE "
            f"ELSE ({tolerance_expr}) END"
        )
        return source_raw, target_raw, left, equal

    equal = f"CASE WHEN {never_equal_null} THEN FALSE ELSE ({left} IS NOT DISTINCT FROM {right}) END"
    return source_raw, target_raw, left, equal


def _check_where(spec: dict[str, Any], check: dict[str, Any]) -> tuple[str, str]:
    source_predicate, target_predicate = _scope_predicates(spec, check)
    return _predicate_sql("s", source_predicate), _predicate_sql("t", target_predicate)


def _numeric_validation(connection: Any, relation_sql: str, field: str, alias: str = "r") -> None:
    raw = f"{alias}.{_qid(field)}"
    invalid = int(
        connection.execute(
            f"SELECT count(*) FROM ({relation_sql}) {alias} WHERE NOT {_is_null_expr(raw)} "
            f"AND {_try_decimal(raw)} IS NULL"
        ).fetchone()[0]
    )
    if invalid:
        raise DataError(f"Field {field!r} contains {invalid} non-numeric value(s).")


def _group_expr(alias: str, field: str) -> str:
    return f"coalesce(CAST({_normalize_expr(f'{alias}.{_qid(field)}', ['trim'])} AS VARCHAR), '')"


def run_reconciliation_duckdb(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    validate_spec(spec)
    if spec.get("children") or spec.get("identity"):
        raise DataError(
            "DuckDB backend currently supports flat reconciliations only. "
            "Use the Python backend for hierarchy/identity controls until those stages have a streaming implementation."
        )

    duckdb = _duckdb()
    started_at = datetime.now(timezone.utc)
    timer_started = time.perf_counter()
    base = Path(base_dir).resolve()
    source_path = Path(spec["source"]["file"]).expanduser()
    target_path = Path(spec["target"]["file"]).expanduser()
    if not source_path.is_absolute():
        source_path = (base / source_path).resolve()
    if not target_path.is_absolute():
        target_path = (base / target_path).resolve()
    if not source_path.exists():
        raise DataError(f"Input file not found: {source_path}")
    if not target_path.exists():
        raise DataError(f"Input file not found: {target_path}")

    source_keys = _listify(spec["source"]["key"])
    target_keys = _listify(spec["target"]["key"])
    source_ops = spec["source"].get("key_normalize", ["trim"])
    target_ops = spec["target"].get("key_normalize", ["trim"])
    key_count = len(source_keys)
    detail_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))

    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE VIEW source_raw AS SELECT * FROM {_reader_sql(spec['source'], source_path)}")
        connection.execute(f"CREATE VIEW target_raw AS SELECT * FROM {_reader_sql(spec['target'], target_path)}")
        source_filter = _predicate_sql("s", spec["source"].get("filter"))
        target_filter = _predicate_sql("t", spec["target"].get("filter"))
        connection.execute(f"CREATE VIEW source_selected AS SELECT * FROM source_raw s WHERE {source_filter}")
        connection.execute(f"CREATE VIEW target_selected AS SELECT * FROM target_raw t WHERE {target_filter}")
        source_key_select = ", ".join(_key_select("s", source_keys, source_ops))
        target_key_select = ", ".join(_key_select("t", target_keys, target_ops))
        connection.execute(
            f"CREATE VIEW source_norm AS SELECT s.*, {source_key_select} FROM source_selected s"
        )
        connection.execute(
            f"CREATE VIEW target_norm AS SELECT t.*, {target_key_select} FROM target_selected t"
        )

        source_raw_count = int(connection.execute("SELECT count(*) FROM source_raw").fetchone()[0])
        target_raw_count = int(connection.execute("SELECT count(*) FROM target_raw").fetchone()[0])
        source_count = int(connection.execute("SELECT count(*) FROM source_selected").fetchone()[0])
        target_count = int(connection.execute("SELECT count(*) FROM target_selected").fetchone()[0])

        checks: list[dict[str, Any]] = [
            _duplicate_check(connection, "source_norm", "source", key_count, detail_limit),
            _duplicate_check(connection, "target_norm", "target", key_count, detail_limit),
        ]

        base_stats, _ = _coverage_stats(
            connection, "SELECT * FROM source_norm", "SELECT * FROM target_norm", key_count, 0, False
        )
        matched_count = base_stats["matched"]
        missing_count = base_stats["missing"]
        unexpected_count = base_stats["unexpected"]
        key_cols = _key_cols(key_count)
        join = " AND ".join(f"s.{col} = t.{col}" for col in key_cols)

        for position, check in enumerate(spec["checks"], start=1):
            check_id = check.get("id", f"check-{position}")
            check_type = check["type"]
            severity = check.get("severity", "error")
            source_where, target_where = _check_where(spec, check)
            source_sql = f"SELECT * FROM source_norm s WHERE {source_where}"
            target_sql = f"SELECT * FROM target_norm t WHERE {target_where}"

            if check_type == "record_coverage":
                allow_unexpected = bool(check.get("allow_unexpected", False))
                stats, details = _coverage_stats(
                    connection, source_sql, target_sql, key_count, detail_limit, allow_unexpected
                )
                source_scope_records = int(connection.execute(f"SELECT count(*) FROM ({source_sql})").fetchone()[0])
                target_scope_records = int(connection.execute(f"SELECT count(*) FROM ({target_sql})").fetchone()[0])
                failures = stats["missing"] + (0 if allow_unexpected else stats["unexpected"])
                checks.append(
                    _result(
                        check_id,
                        check_type,
                        severity,
                        failures == 0,
                        {
                            "matched": stats["matched"],
                            "missing_in_target": stats["missing"],
                            "unexpected_in_target": stats["unexpected"],
                            "allow_unexpected": allow_unexpected,
                            "source_scope_records": source_scope_records,
                            "target_scope_records": target_scope_records,
                        },
                        details,
                        detail_limit,
                        stats["missing"] + stats["unexpected"],
                    )
                )
                continue

            if check_type == "field_match":
                source_raw, target_raw, normalized_source, equal_expr = _field_expressions(check)
                operations = check.get("normalize", ["trim"])
                normalized_target = _normalize_expr(target_raw, operations)
                if check.get("null_semantics") == "empty_is_null":
                    normalized_target = (
                        f"CASE WHEN {_is_null_expr(normalized_target)} THEN NULL ELSE {normalized_target} END"
                    )
                pair_where = _and(source_where, target_where)
                joined = f"source_norm s JOIN target_norm t ON {join}"
                compared = int(
                    connection.execute(f"SELECT count(*) FROM {joined} WHERE {pair_where}").fetchone()[0]
                )
                mismatch_where = _and(pair_where, f"NOT ({equal_expr})")
                mismatch_count = int(
                    connection.execute(f"SELECT count(*) FROM {joined} WHERE {mismatch_where}").fetchone()[0]
                )
                select_keys = ", ".join(f"s.{col}" for col in key_cols)
                detail_rows = connection.execute(
                    f"SELECT {select_keys}, {source_raw}, {target_raw}, {normalized_source}, {normalized_target} "
                    f"FROM {joined} WHERE {mismatch_where} ORDER BY {select_keys} LIMIT {detail_limit}"
                ).fetchall() if detail_limit > 0 and mismatch_count else []
                details = []
                for row in detail_rows:
                    key = _key_label(tuple(row[:key_count]))
                    offset = key_count
                    details.append(
                        {
                            "key": key,
                            "source": row[offset],
                            "target": row[offset + 1],
                            "normalized_source": row[offset + 2],
                            "normalized_target": row[offset + 3],
                        }
                    )
                max_mismatches = int(check.get("max_mismatches", 0))
                checks.append(
                    _result(
                        check_id,
                        check_type,
                        severity,
                        mismatch_count <= max_mismatches,
                        {
                            "compared": compared,
                            "skipped_by_scope_or_when": max(matched_count - compared, 0),
                            "mismatches": mismatch_count,
                            "max_mismatches": max_mismatches,
                            "source_field": check["source"],
                            "target_field": check["target"],
                        },
                        details,
                        detail_limit,
                        mismatch_count,
                    )
                )
                continue

            if check_type == "control_total":
                _numeric_validation(connection, source_sql, check["source"])
                _numeric_validation(connection, target_sql, check["target"])
                source_num = f"coalesce({_try_decimal(f's.{_qid(check['source'])}')}, 0)"
                target_num = f"coalesce({_try_decimal(f't.{_qid(check['target'])}')}, 0)"
                source_total = connection.execute(
                    f"SELECT coalesce(sum({source_num}), 0) FROM ({source_sql}) s"
                ).fetchone()[0]
                target_total = connection.execute(
                    f"SELECT coalesce(sum({target_num}), 0) FROM ({target_sql}) t"
                ).fetchone()[0]
                difference = abs(Decimal(str(source_total)) - Decimal(str(target_total)))
                tolerance = Decimal(str(check.get("tolerance", 0)))
                checks.append(
                    _result(
                        check_id,
                        check_type,
                        severity,
                        difference <= tolerance,
                        {
                            "source_total": _decimal_text(source_total),
                            "target_total": _decimal_text(target_total),
                            "absolute_difference": _decimal_text(difference),
                            "tolerance": _decimal_text(tolerance),
                            "source_field": check["source"],
                            "target_field": check["target"],
                            "source_scope_records": int(connection.execute(f"SELECT count(*) FROM ({source_sql})").fetchone()[0]),
                            "target_scope_records": int(connection.execute(f"SELECT count(*) FROM ({target_sql})").fetchone()[0]),
                        },
                        detail_limit=detail_limit,
                    )
                )
                continue

            if check_type == "row_count":
                source_rows = int(connection.execute(f"SELECT count(*) FROM ({source_sql})").fetchone()[0])
                target_rows = int(connection.execute(f"SELECT count(*) FROM ({target_sql})").fetchone()[0])
                difference = abs(source_rows - target_rows)
                tolerance = int(check.get("tolerance", 0))
                checks.append(
                    _result(
                        check_id,
                        check_type,
                        severity,
                        difference <= tolerance,
                        {
                            "source_rows": source_rows,
                            "target_rows": target_rows,
                            "absolute_difference": difference,
                            "tolerance": tolerance,
                        },
                        detail_limit=detail_limit,
                    )
                )
                continue

            if check_type == "aggregate_match":
                operation = check.get("operation", "count")
                source_groups = _listify(check["group_by"]["source"])
                target_groups = _listify(check["group_by"]["target"])
                source_group_exprs = [_group_expr("s", field) for field in source_groups]
                target_group_exprs = [_group_expr("t", field) for field in target_groups]
                source_group_select = ", ".join(
                    f"{expr} AS __g{index}" for index, expr in enumerate(source_group_exprs)
                )
                target_group_select = ", ".join(
                    f"{expr} AS __g{index}" for index, expr in enumerate(target_group_exprs)
                )
                group_cols = [f"__g{index}" for index in range(len(source_groups))]
                group_list = ", ".join(group_cols)

                if operation == "count":
                    source_agg = "count(*)"
                    target_agg = "count(*)"
                elif operation == "distinct_count":
                    source_value = _normalize_expr(f"s.{_qid(check['source'])}", ["trim"])
                    target_value = _normalize_expr(f"t.{_qid(check['target'])}", ["trim"])
                    source_agg = f"count(DISTINCT coalesce(CAST({source_value} AS VARCHAR), ''))"
                    target_agg = f"count(DISTINCT coalesce(CAST({target_value} AS VARCHAR), ''))"
                else:
                    _numeric_validation(connection, source_sql, check["source"])
                    _numeric_validation(connection, target_sql, check["target"])
                    source_agg = f"sum(coalesce({_try_decimal(f's.{_qid(check['source'])}')}, 0))"
                    target_agg = f"sum(coalesce({_try_decimal(f't.{_qid(check['target'])}')}, 0))"

                source_grouped = (
                    f"SELECT {source_group_select}, {source_agg} AS value FROM ({source_sql}) s GROUP BY {group_list}"
                )
                target_grouped = (
                    f"SELECT {target_group_select}, {target_agg} AS value FROM ({target_sql}) t GROUP BY {group_list}"
                )
                group_join = " AND ".join(f"s.{col} = t.{col}" for col in group_cols)
                coalesced_groups = ", ".join(
                    f"coalesce(s.{col}, t.{col}) AS {col}" for col in group_cols
                )
                combined = (
                    f"SELECT {coalesced_groups}, coalesce(s.value, 0) AS source_value, "
                    f"coalesce(t.value, 0) AS target_value FROM ({source_grouped}) s FULL OUTER JOIN "
                    f"({target_grouped}) t ON {group_join}"
                )
                tolerance = Decimal(str(check.get("tolerance", 0)))
                percentage_tolerance = check.get("percentage_tolerance")
                source_value = "source_value"
                target_value = "target_value"
                difference = f"abs({source_value} - {target_value})"
                pass_parts = [f"{difference} <= {tolerance}"]
                if percentage_tolerance is not None:
                    pct = Decimal(str(percentage_tolerance))
                    pass_parts.append(
                        f"CASE WHEN {source_value}=0 THEN {difference}=0 "
                        f"ELSE ({difference}/abs({source_value})*100) <= {pct} END"
                    )
                passed_expr = " OR ".join(f"({part})" for part in pass_parts)
                failures_sql = (
                    f"SELECT *, {difference} AS absolute_difference, "
                    f"CASE WHEN {source_value}=0 THEN CASE WHEN {difference}=0 THEN 0 ELSE NULL END "
                    f"ELSE {difference}/abs({source_value})*100 END AS percentage_difference "
                    f"FROM ({combined}) WHERE NOT ({passed_expr})"
                )
                groups_compared = int(connection.execute(f"SELECT count(*) FROM ({combined})").fetchone()[0])
                groups_failed = int(connection.execute(f"SELECT count(*) FROM ({failures_sql})").fetchone()[0])
                order = ", ".join(group_cols)
                rows = connection.execute(
                    f"SELECT * FROM ({failures_sql}) ORDER BY {order} LIMIT {detail_limit}"
                ).fetchall() if detail_limit > 0 and groups_failed else []
                details: list[dict[str, Any]] = []
                for row in rows:
                    group = _key_label(tuple(row[: len(group_cols)]))
                    offset = len(group_cols)
                    details.append(
                        {
                            "group": group,
                            "source_value": _decimal_text(row[offset]),
                            "target_value": _decimal_text(row[offset + 1]),
                            "absolute_difference": _decimal_text(row[offset + 2]),
                            "percentage_difference": (
                                _decimal_text(row[offset + 3]) if row[offset + 3] is not None else None
                            ),
                        }
                    )
                checks.append(
                    _result(
                        check_id,
                        check_type,
                        severity,
                        groups_failed == 0,
                        {
                            "operation": operation,
                            "groups_compared": groups_compared,
                            "groups_failed": groups_failed,
                            "tolerance": _decimal_text(tolerance),
                            "percentage_tolerance": (
                                _decimal_text(percentage_tolerance) if percentage_tolerance is not None else None
                            ),
                            "source_group_by": source_groups,
                            "target_group_by": target_groups,
                            "source_field": check.get("source"),
                            "target_field": check.get("target"),
                            "source_scope_records": int(connection.execute(f"SELECT count(*) FROM ({source_sql})").fetchone()[0]),
                            "target_scope_records": int(connection.execute(f"SELECT count(*) FROM ({target_sql})").fetchone()[0]),
                        },
                        details,
                        detail_limit,
                        groups_failed,
                    )
                )

        failed_errors = [
            item for item in checks if item["severity"] == "error" and item["status"] == "failed"
        ]
        failed_warnings = [
            item for item in checks if item["severity"] == "warning" and item["status"] == "failed"
        ]
        inputs: dict[str, Any] = {
            "source": {"path": spec["source"]["file"], "sha256": _sha256(source_path)},
            "target": {"path": spec["target"]["file"], "sha256": _sha256(target_path)},
        }
        if spec_path:
            resolved_spec = Path(spec_path).resolve()
            if resolved_spec.exists():
                inputs["specification"] = {"path": resolved_spec.name, "sha256": _sha256(resolved_spec)}

        finished_at = datetime.now(timezone.utc)
        duration_ms = round((time.perf_counter() - timer_started) * 1000, 3)
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "spec_version": int(spec.get("version", 1)),
            "engine_version": _engine_version(),
            "configuration_sha256": _sha256_object(spec),
            "run": {
                "id": str(uuid.uuid4()),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": duration_ms,
                "python_version": platform.python_version(),
                "platform": platform.platform(),
                "backend": "duckdb",
                "duckdb_version": getattr(duckdb, "__version__", "unknown"),
            },
            "reconciliation": spec["reconciliation"]["name"],
            "description": spec["reconciliation"].get("description"),
            "status": "failed" if failed_errors else "passed",
            "generated_at": finished_at.isoformat(),
            "inputs": inputs,
            "selection": {
                "source": {
                    "raw_records": source_raw_count,
                    "selected_records": source_count,
                    "filter": spec["source"].get("filter"),
                },
                "target": {
                    "raw_records": target_raw_count,
                    "selected_records": target_count,
                    "filter": spec["target"].get("filter"),
                },
            },
            "summary": {
                "source_records": source_count,
                "target_records": target_count,
                "matched_records": matched_count,
                "missing_in_target": missing_count,
                "unexpected_in_target": unexpected_count,
                "checks_total": len(checks),
                "checks_failed": len(failed_errors),
                "warnings_failed": len(failed_warnings),
            },
            "checks": checks,
        }
    finally:
        connection.close()
