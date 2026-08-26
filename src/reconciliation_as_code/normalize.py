from __future__ import annotations

from typing import Any


def normalize_value(value: Any, operations: list[str] | None = None) -> Any:
    operations = operations or ["trim"]
    current: Any = value

    for operation in operations:
        if operation == "empty_to_null":
            if current is None or str(current).strip() == "":
                current = None
        elif current is None:
            continue
        elif operation == "trim":
            current = str(current).strip()
        elif operation == "uppercase":
            current = str(current).upper()
        elif operation == "lowercase":
            current = str(current).lower()
        elif operation == "strip_leading_zeros":
            text = str(current).strip()
            sign = "-" if text.startswith("-") else ""
            digits = text[1:] if sign else text
            if digits.isdigit():
                current = sign + (digits.lstrip("0") or "0")
    return current


def comparable_key(row: dict[str, Any], fields: list[str], operations: list[str]) -> tuple[str, ...]:
    return tuple(str(normalize_value(row.get(field), operations) or "") for field in fields)
