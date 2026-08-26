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
    return "'" + str(value).replace("'", "''") + "'"


def _format(endpoint: dict[str, Any], path: Path) -> str:
    declared = endpoint.get("format")
    if declared:
        return str(declared).lower()
    return path.suffix.lower().lstrip(".")


def _reader_sql(endpoint: dict[str, Any], path: Path) -> str:
    fmt = _format(endpoint, path)
    if fmt == "csv":
        delimiter = endpoint.get("delimiter", ",")
        return (
            f"read_csv_auto({_lit(str(path))}, header=true, all_varchar=true, "
            f"delim={_lit(delimiter)})"
        )
    if fmt == "parquet":
        return f"read_parquet({_lit(str(path))})"
    raise DataError(
        f"DuckDB backend supports CSV and Parquet inputs; got {fmt!r} for {path}."
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
            digits = f"substr({text}, 2)"
            negative = f"'-' || coalesce(nullif(regexp_replace({digits}, '^0+', ''), ''), '0')"
            current = (
                f"CASE WHEN regexp_full_match({text}, '[0-9]+') THEN {positive} "
                f"WHEN regexp_full_match({text}, '-[0-9]+') THEN {negative} ELSE {current} END"
            )
    return current


def _key_expr(alias: str, field: str, operations: list[str]) -> str:
    normalized = _normalize_expr(f"{alias}.{_qid(field)}", operations)
    return f"coalesce(CAST({normalized} AS VARCHAR), '')"


def _key_select(alias: str, fields: list[str], operations: list[str]) -> str:
    return ", ".join(
        f"{_key_expr(alias, field, operations)} AS __k{index}"
        for index, field in enumerate(fields)
    )


def _key_cols(count: int, alias: str | None = None) -> list[str]:
    values = [f"__k{index}" for index in range(count)]
    if alias:
        return [f"{alias}.{value}" for value in values]
    return values


def _key_label(values: tuple[Any, ...]) -> str | list[str]:
    text = ["" if value is None else str(value) for value in values]
    return text[0] if len(text) == 1 else text


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
        return f"NOT ({_predicate_sql(alias, predicate['not'])})"

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
        normalized = [normalize_value(value, operations) for value in expected]
        clause = f"{left} IN ({', '.join(_lit(value) for value in normalized)})"
        return f"NOT ({clause})" if op == "not_in" else clause

    right_value = normalize_value(expected, operations)
    if right_value is None:
        return f"{left} IS NULL" if op == "eq" else f"{left} IS NOT NULL"
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
        left_cmp = _try_decimal(left)
        right_cmp = f"CAST({right} AS DECIMAL(38,10))"
    except (InvalidOperation, ValueError):
        left_cmp = f"CAST({left} AS VARCHAR)"
        right_cmp = f"CAST({right} AS VARCHAR)"
    operator = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}[op]
    return f"{left_cmp} {operator} {right_cmp}"


def _scope_predicates(
    spec: dict[str, Any], check: dict[str, Any]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    source_predicate = None
    target_predicate = None
    scope_name = check.get("scope")
    if scope_name:
        scope = spec.get("scopes", {}).get(scope_name, {})
        source_predicate = scope.get("source")
        target_predicate = scope.get("target")
    when = check.get("when") or {}
    if when.get("source"):
        source_predicate = (
            {"all": [source_predicate, when["source"]]} if source_predicate else when["source"]
        )
    if when.get("target"):
        target_predicate = (
            {"all": [target_predicate, when["target"]]} if target_predicate else when["target"]
        )
    return source_predicate, target_predicate


def _decimal_text(value: Any) -> str:
    decimal = Decimal(str(value or 0))
    text = format(decimal.normalize(), "f")
    return "0" if text in {"", "-0"} else text


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


def _duplicate_check(connection: Any, view: str, side: str, key_count: int, limit: int) -> dict[str, Any]:
    cols = ", ".join(_key_cols(key_count))
    grouped = f"SELECT {cols}, count(*) cnt FROM {view} GROUP BY {cols} HAVING count(*) > 1"
    duplicate_count = int(connection.execute(f"SELECT coalesce(sum(cnt - 1), 0) FROM ({grouped})").fetchone()[0])
    details: list[dict[str, Any]] = []
    if duplicate_count and limit:
        rows = connection.execute(f"{grouped} ORDER BY {cols} LIMIT {limit}").fetchall()
        for row in rows:
            repeats = min(int(row[key_count]) - 1, limit - len(details))
            details.extend({"key": _key_label(tuple(row[:key_count]))} for _ in range(max(repeats, 0)))
            if len(details) >= limit:
                break
    return _result(
        f"{side}-key-integrity",
        "key_integrity",
        "error",
        duplicate_count == 0,
        {"duplicate_keys": duplicate_count},
        details,
        limit,
        duplicate_count,
    )


def _coverage(
    connection: Any, source_sql: str, target_sql: str, key_count: int, limit: int
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    cols = _key_cols(key_count)
    col_list = ", ".join(cols)
    join = " AND ".join(f"s.{col} = t.{col}" for col in cols)
    source_distinct = f"SELECT DISTINCT {col_list} FROM ({source_sql})"
    target_distinct = f"SELECT DISTINCT {col_list} FROM ({target_sql})"
    matched = int(
        connection.execute(
            f"SELECT count(*) FROM ({source_distinct}) s JOIN ({target_distinct}) t ON {join}"
        ).fetchone()[0]
    )
    source_cols = ", ".join(f"s.{col}" for col in cols)
    target_cols = ", ".join(f"t.{col}" for col in cols)
    missing_sql = (
        f"SELECT {source_cols} FROM ({source_distinct}) s LEFT JOIN ({target_distinct}) t ON {join} "
        f"WHERE t.{cols[0]} IS NULL"
    )
    unexpected_sql = (
        f"SELECT {target_cols} FROM ({target_distinct}) t LEFT JOIN ({source_distinct}) s ON {join} "
        f"WHERE s.{cols[0]} IS NULL"
    )
    missing = int(connection.execute(f"SELECT count(*) FROM ({missing_sql})").fetchone()[0])
    unexpected = int(connection.execute(f"SELECT count(*) FROM ({unexpected_sql})").fetchone()[0])
    details: list[dict[str, Any]] = []
    if limit:
        missing_rows = connection.execute(f"{missing_sql} LIMIT {limit}").fetchall()
        details.extend(
            {"key": _key_label(tuple(row[:key_count])), "difference": "missing_in_target"}
            for row in missing_rows
        )
        remaining = max(limit - len(details), 0)
        if remaining:
            unexpected_rows = connection.execute(f"{unexpected_sql} LIMIT {remaining}").fetchall()
            details.extend(
                {"key": _key_label(tuple(row[:key_count])), "difference": "unexpected_in_target"}
                for row in unexpected_rows
            )
    return {"matched": matched, "missing": missing, "unexpected": unexpected}, details


def _mapped_expr(expr: str, mapping: dict[Any, Any]) -> str:
    if not mapping:
        return expr
    branches = " ".join(
        f"WHEN {expr} IS NOT DISTINCT FROM {_lit(key)} THEN {_lit(value)}"
        for key, value in mapping.items()
    )
    return f"CASE {branches} ELSE {expr} END"


def _field_expressions(check: dict[str, Any]) -> tuple[str, str, str, str, str]:
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
    never_equal_null = (
        f"({_is_null_expr(left)} OR {_is_null_expr(right)})"
        if null_semantics == "never_equal"
        else "FALSE"
    )

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
        return source_raw, target_raw, left, right, equal

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
        equal = (
            f"CASE WHEN {never_equal_null} THEN FALSE "
            f"WHEN {left_num} IS NULL OR {right_num} IS NULL THEN FALSE "
            f"ELSE ({' OR '.join(f'({clause})' for clause in clauses)}) END"
        )
        return source_raw, target_raw, left, right, equal

    equal = f"CASE WHEN {never_equal_null} THEN FALSE ELSE ({left} IS NOT DISTINCT FROM {right}) END"
    return source_raw, target_raw, left, right, equal


def _numeric_validation(connection: Any, relation_sql: str, field: str) -> None:
    raw = f"r.{_qid(field)}"
    invalid = int(
        connection.execute(
            f"SELECT count(*) FROM ({relation_sql}) r WHERE NOT {_is_null_expr(raw)} AND {_try_decimal(raw)} IS NULL"
        ).fetchone()[0]
    )
    if invalid:
        raise DataError(f"Field {field!r} contains {invalid} non-numeric value(s).")


def _group_expr(alias: str, field: str) -> str:
    normalized = _normalize_expr(f"{alias}.{_qid(field)}", ["trim"])
    return f"coalesce(CAST({normalized} AS VARCHAR), '')"


def _absolute_percentage(source_expr: str, target_expr: str) -> tuple[str, str]:
    difference = f"abs({source_expr} - {target_expr})"
    percentage = (
        f"CASE WHEN {source_expr}=0 THEN CASE WHEN {difference}=0 THEN 0 ELSE NULL END "
        f"ELSE {difference}/abs({source_expr})*100 END"
    )
    return difference, percentage


def run_reconciliation_duckdb(
    spec: dict[str, Any], *, base_dir: str | Path = ".", spec_path: str | Path | None = None
) -> dict[str, Any]:
    validate_spec(spec)
    if spec.get("children") or spec.get("identity"):
        raise DataError(
            "DuckDB backend currently supports flat reconciliations only. Use --engine python for hierarchy/identity controls."
        )

    duckdb = _duckdb()
    base = Path(base_dir).resolve()
    source_path = Path(spec["source"]["file"]).expanduser()
    target_path = Path(spec["target"]["file"]).expanduser()
    if not source_path.is_absolute():
        source_path = (base / source_path).resolve()
    if not target_path.is_absolute():
        target_path = (base / target_path).resolve()
    for path in (source_path, target_path):
        if not path.exists():
            raise DataError(f"Input file not found: {path}")

    started_at = datetime.now(timezone.utc)
    started_timer = time.perf_counter()
    source_keys = _listify(spec["source"]["key"])
    target_keys = _listify(spec["target"]["key"])
    key_count = len(source_keys)
    source_ops = spec["source"].get("key_normalize", ["trim"])
    target_ops = spec["target"].get("key_normalize", ["trim"])
    detail_limit = int((spec.get("evidence") or {}).get("detail_limit", 100))
    key_cols = _key_cols(key_count)
    key_join = " AND ".join(f"s.{col} = t.{col}" for col in key_cols)

    connection = duckdb.connect(database=":memory:")
    try:
        source_reader = _reader_sql(spec["source"], source_path)
        target_reader = _reader_sql(spec["target"], target_path)
        connection.execute(f"CREATE VIEW source_raw AS SELECT * FROM {source_reader}")
        connection.execute(f"CREATE VIEW target_raw AS SELECT * FROM {target_reader}")
        source_filter = _predicate_sql("s", spec["source"].get("filter"))
        target_filter = _predicate_sql("t", spec["target"].get("filter"))
        connection.execute(f"CREATE VIEW source_selected AS SELECT * FROM source_raw s WHERE {source_filter}")
        connection.execute(f"CREATE VIEW target_selected AS SELECT * FROM target_raw t WHERE {target_filter}")
        connection.execute(
            f"CREATE VIEW source_norm AS SELECT s.*, {_key_select('s', source_keys, source_ops)} FROM source_selected s"
        )
        connection.execute(
            f"CREATE VIEW target_norm AS SELECT t.*, {_key_select('t', target_keys, target_ops)} FROM target_selected t"
        )

        source_raw_count = int(connection.execute("SELECT count(*) FROM source_raw").fetchone()[0])
        target_raw_count = int(connection.execute("SELECT count(*) FROM target_raw").fetchone()[0])
        source_count = int(connection.execute("SELECT count(*) FROM source_norm").fetchone()[0])
        target_count = int(connection.execute("SELECT count(*) FROM target_norm").fetchone()[0])
        base_stats, _ = _coverage(
            connection, "SELECT * FROM source_norm", "SELECT * FROM target_norm", key_count, 0
        )

        checks: list[dict[str, Any]] = [
            _duplicate_check(connection, "source_norm", "source", key_count, detail_limit),
            _duplicate_check(connection, "target_norm", "target", key_count, detail_limit),
        ]

        for position, check in enumerate(spec["checks"], start=1):
            check_id = check.get("id", f"check-{position}")
            check_type = check["type"]
            severity = check.get("severity", "error")
            source_predicate, target_predicate = _scope_predicates(spec, check)
            source_where = _predicate_sql("s", source_predicate)
            target_where = _predicate_sql("t", target_predicate)
            source_sql = f"SELECT * FROM source_norm s WHERE {source_where}"
            target_sql = f"SELECT * FROM target_norm t WHERE {target_where}"

            if check_type == "record_coverage":
                stats, details = _coverage(connection, source_sql, target_sql, key_count, detail_limit)
                allow_unexpected = bool(check.get("allow_unexpected", False))
                failures = stats["missing"] + (0 if allow_unexpected else stats["unexpected"])
                source_scope_records = int(connection.execute(f"SELECT count(*) FROM ({source_sql})").fetchone()[0])
                target_scope_records = int(connection.execute(f"SELECT count(*) FROM ({target_sql})").fetchone()[0])
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
                source_raw, target_raw, normalized_source, normalized_target, equal_expr = _field_expressions(check)
                pair_where = f"({source_where}) AND ({target_where})"
                joined = f"source_norm s JOIN target_norm t ON {key_join}"
                compared = int(connection.execute(f"SELECT count(*) FROM {joined} WHERE {pair_where}").fetchone()[0])
                mismatch_where = f"({pair_where}) AND NOT ({equal_expr})"
                mismatches = int(connection.execute(f"SELECT count(*) FROM {joined} WHERE {mismatch_where}").fetchone()[0])
                details: list[dict[str, Any]] = []
                if mismatches and detail_limit:
                    select_keys = ", ".join(_key_cols(key_count, "s"))
                    rows = connection.execute(
                        f"SELECT {select_keys}, {source_raw}, {target_raw}, {normalized_source}, {normalized_target} "
                        f"FROM {joined} WHERE {mismatch_where} LIMIT {detail_limit}"
                    ).fetchall()
                    for row in rows:
                        offset = key_count
                        details.append(
                            {
                                "key": _key_label(tuple(row[:key_count])),
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
                        mismatches <= max_mismatches,
                        {
                            "compared": compared,
                            "skipped_by_scope_or_when": max(base_stats["matched"] - compared, 0),
                            "mismatches": mismatches,
                            "max_mismatches": max_mismatches,
                            "source_field": check["source"],
                            "target_field": check["target"],
                        },
                        details,
                        detail_limit,
                        mismatches,
                    )
                )
                continue

            if check_type == "control_total":
                source_field = check["source"]
                target_field = check["target"]
                _numeric_validation(connection, source_sql, source_field)
                _numeric_validation(connection, target_sql, target_field)
                source_raw_expr = f"s.{_qid(source_field)}"
                target_raw_expr = f"t.{_qid(target_field)}"
                source_num = f"coalesce({_try_decimal(source_raw_expr)}, 0)"
                target_num = f"coalesce({_try_decimal(target_raw_expr)}, 0)"
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
                            "source_field": source_field,
                            "target_field": target_field,
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
                source_group_select = ", ".join(
                    f"{_group_expr('s', field)} AS __g{index}"
                    for index, field in enumerate(source_groups)
                )
                target_group_select = ", ".join(
                    f"{_group_expr('t', field)} AS __g{index}"
                    for index, field in enumerate(target_groups)
                )
                group_cols = [f"__g{index}" for index in range(len(source_groups))]
                group_list = ", ".join(group_cols)
                if operation == "count":
                    source_agg = target_agg = "count(*)"
                elif operation == "distinct_count":
                    source_field = check["source"]
                    target_field = check["target"]
                    source_value = _normalize_expr(f"s.{_qid(source_field)}", ["trim"])
                    target_value = _normalize_expr(f"t.{_qid(target_field)}", ["trim"])
                    source_agg = f"count(DISTINCT coalesce(CAST({source_value} AS VARCHAR), ''))"
                    target_agg = f"count(DISTINCT coalesce(CAST({target_value} AS VARCHAR), ''))"
                else:
                    source_field = check["source"]
                    target_field = check["target"]
                    _numeric_validation(connection, source_sql, source_field)
                    _numeric_validation(connection, target_sql, target_field)
                    source_raw_expr = f"s.{_qid(source_field)}"
                    target_raw_expr = f"t.{_qid(target_field)}"
                    source_agg = f"sum(coalesce({_try_decimal(source_raw_expr)}, 0))"
                    target_agg = f"sum(coalesce({_try_decimal(target_raw_expr)}, 0))"
                source_grouped = (
                    f"SELECT {source_group_select}, {source_agg} value FROM ({source_sql}) s GROUP BY {group_list}"
                )
                target_grouped = (
                    f"SELECT {target_group_select}, {target_agg} value FROM ({target_sql}) t GROUP BY {group_list}"
                )
                group_join = " AND ".join(f"s.{col} = t.{col}" for col in group_cols)
                coalesced_groups = ", ".join(f"coalesce(s.{col}, t.{col}) AS {col}" for col in group_cols)
                combined = (
                    f"SELECT {coalesced_groups}, coalesce(s.value, 0) source_value, coalesce(t.value, 0) target_value "
                    f"FROM ({source_grouped}) s FULL OUTER JOIN ({target_grouped}) t ON {group_join}"
                )
                difference, percentage = _absolute_percentage("source_value", "target_value")
                tolerance = Decimal(str(check.get("tolerance", 0)))
                pass_parts = [f"{difference} <= {tolerance}"]
                if check.get("percentage_tolerance") is not None:
                    pct = Decimal(str(check["percentage_tolerance"]))
                    pass_parts.append(
                        f"CASE WHEN source_value=0 THEN {difference}=0 ELSE ({difference}/abs(source_value)*100) <= {pct} END"
                    )
                pass_expr = " OR ".join(f"({part})" for part in pass_parts)
                failures_sql = (
                    f"SELECT *, {difference} absolute_difference, {percentage} percentage_difference "
                    f"FROM ({combined}) WHERE NOT ({pass_expr})"
                )
                groups_compared = int(connection.execute(f"SELECT count(*) FROM ({combined})").fetchone()[0])
                groups_failed = int(connection.execute(f"SELECT count(*) FROM ({failures_sql})").fetchone()[0])
                details: list[dict[str, Any]] = []
                if groups_failed and detail_limit:
                    rows = connection.execute(
                        f"SELECT * FROM ({failures_sql}) LIMIT {detail_limit}"
                    ).fetchall()
                    for row in rows:
                        offset = len(group_cols)
                        details.append(
                            {
                                "group": _key_label(tuple(row[:offset])),
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
                                _decimal_text(check["percentage_tolerance"])
                                if check.get("percentage_tolerance") is not None
                                else None
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
            resolved = Path(spec_path).resolve()
            if resolved.exists():
                inputs["specification"] = {"path": resolved.name, "sha256": _sha256(resolved)}
        finished_at = datetime.now(timezone.utc)
        return {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "spec_version": int(spec.get("version", 1)),
            "engine_version": _engine_version(),
            "configuration_sha256": _sha256_object(spec),
            "run": {
                "id": str(uuid.uuid4()),
                "started_at": started_at.isoformat(),
                "finished_at": finished_at.isoformat(),
                "duration_ms": round((time.perf_counter() - started_timer) * 1000, 3),
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
                "matched_records": base_stats["matched"],
                "missing_in_target": base_stats["missing"],
                "unexpected_in_target": base_stats["unexpected"],
                "checks_total": len(checks),
                "checks_failed": len(failed_errors),
                "warnings_failed": len(failed_warnings),
            },
            "checks": checks,
        }
    finally:
        connection.close()
