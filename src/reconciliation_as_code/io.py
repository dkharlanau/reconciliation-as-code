from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .errors import DataError


def _load_csv(path: Path, delimiter: str = ",") -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=delimiter)
            if not reader.fieldnames:
                raise DataError(f"CSV has no header: {path}")
            return [dict(row) for row in reader]
    except UnicodeDecodeError as exc:
        raise DataError(f"CSV must be UTF-8 encoded: {path}") from exc


def _load_excel(path: Path, sheet: str | None = None) -> list[dict[str, Any]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise DataError(
            "Excel input requires the optional dependency. Install with: pip install 'reconciliation-as-code[excel]'"
        ) from exc

    workbook = load_workbook(path, read_only=True, data_only=True)
    if sheet:
        if sheet not in workbook.sheetnames:
            raise DataError(f"Sheet {sheet!r} not found in {path}. Available: {workbook.sheetnames}")
        worksheet = workbook[sheet]
    else:
        worksheet = workbook[workbook.sheetnames[0]]

    rows = worksheet.iter_rows(values_only=True)
    try:
        header_row = next(rows)
    except StopIteration:
        return []

    headers = [str(cell).strip() if cell is not None else "" for cell in header_row]
    if not any(headers):
        raise DataError(f"Excel header row is empty: {path}")
    if any(not header for header in headers):
        raise DataError(f"Excel header contains an empty column name: {path}")

    return [dict(zip(headers, row, strict=False)) for row in rows]


def load_table(endpoint: dict[str, Any], base_dir: Path) -> tuple[Path, list[dict[str, Any]]]:
    path = Path(endpoint["file"])
    if not path.is_absolute():
        path = base_dir / path
    path = path.resolve()
    if not path.exists():
        raise DataError(f"Input file not found: {path}")

    file_format = str(endpoint.get("format") or path.suffix.lstrip(".")).lower()
    if file_format == "csv":
        delimiter = endpoint.get("delimiter", ",")
        if not isinstance(delimiter, str) or len(delimiter) != 1:
            raise DataError("CSV delimiter must be exactly one character.")
        rows = _load_csv(path, delimiter)
    elif file_format in {"xlsx", "xlsm"}:
        rows = _load_excel(path, endpoint.get("sheet"))
    else:
        raise DataError(f"Unsupported input format {file_format!r} for {path}")

    return path, rows
