from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .errors import SpecError
from .normalize import normalize_value

SUPPORTED_OPERATORS = {
    "eq",
    "ne",
    "in",
    "not_in",
    "contains",
    "starts_with",
    "is_null",
    "not_null",
    "gt",
    "gte",
    "lt",
    "lte",
}


def _is_null(value: Any) -> bool:
    return value is None or str(value).strip() == ""


def validate_predicate(predicate: Any, label: str = "predicate") -> None:
    if not isinstance(predicate, dict) or not predicate:
        raise SpecError(f"{label} must be a non-empty object.")
    logical = [name for name in ("all", "any", "not") if name in predicate]
    if logical:
        if len(logical) != 1 or len(predicate) != 1:
            raise SpecError(f"{label} logical predicate must contain exactly one of all/any/not.")
        name = logical[0]
        value = predicate[name]
        if name in {"all", "any"}:
            if not isinstance(value, list) or not value:
                raise SpecError(f"{label}.{name} must be a non-empty list.")
            for index, child in enumerate(value, start=1):
                validate_predicate(child, f"{label}.{name}[{index}]")
        else:
            validate_predicate(value, f"{label}.not")
        return

    field = predicate.get("field")
    op = predicate.get("op", "eq")
    if not isinstance(field, str) or not field:
        raise SpecError(f"{label}.field must be a non-empty string.")
    if op not in SUPPORTED_OPERATORS:
        raise SpecError(f"{label}.op must be one of {sorted(SUPPORTED_OPERATORS)}; got {op!r}.")
    if op in {"is_null", "not_null"}:
        return
    if "value" not in predicate:
        raise SpecError(f"{label}.value is required for operator {op!r}.")
    if op in {"in", "not_in"} and not isinstance(predicate["value"], list):
        raise SpecError(f"{label}.value must be a list for operator {op!r}.")
    normalize = predicate.get("normalize", ["trim"])
    if not isinstance(normalize, list):
        raise SpecError(f"{label}.normalize must be a list.")


def _comparable_pair(left: Any, right: Any) -> tuple[Any, Any]:
    try:
        return Decimal(str(left)), Decimal(str(right))
    except (InvalidOperation, ValueError):
        pass
    try:
        return datetime.fromisoformat(str(left)), datetime.fromisoformat(str(right))
    except ValueError:
        return str(left), str(right)


def predicate_matches(row: dict[str, Any], predicate: dict[str, Any]) -> bool:
    if "all" in predicate:
        return all(predicate_matches(row, item) for item in predicate["all"])
    if "any" in predicate:
        return any(predicate_matches(row, item) for item in predicate["any"])
    if "not" in predicate:
        return not predicate_matches(row, predicate["not"])

    field = predicate["field"]
    op = predicate.get("op", "eq")
    raw = row.get(field)
    if op == "is_null":
        return _is_null(raw)
    if op == "not_null":
        return not _is_null(raw)

    operations = predicate.get("normalize", ["trim"])
    left = normalize_value(raw, operations)
    expected = predicate.get("value")

    if op in {"in", "not_in"}:
        normalized_values = [normalize_value(item, operations) for item in expected]
        result = left in normalized_values
        return result if op == "in" else not result

    right = normalize_value(expected, operations)
    if op == "eq":
        return left == right
    if op == "ne":
        return left != right
    if op == "contains":
        return str(right) in str(left)
    if op == "starts_with":
        return str(left).startswith(str(right))

    comparable_left, comparable_right = _comparable_pair(left, right)
    if op == "gt":
        return comparable_left > comparable_right
    if op == "gte":
        return comparable_left >= comparable_right
    if op == "lt":
        return comparable_left < comparable_right
    if op == "lte":
        return comparable_left <= comparable_right
    return False


def filter_rows(rows: list[dict[str, Any]], predicate: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not predicate:
        return list(rows)
    return [row for row in rows if predicate_matches(row, predicate)]
