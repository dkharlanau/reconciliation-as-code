"""Malformed exports must not become apparently usable reconciliation evidence."""

import pytest
from openpyxl import Workbook

from reconciliation_as_code.cli import main
from reconciliation_as_code.duckdb_engine import _reader_sql
from reconciliation_as_code.errors import DataError
from reconciliation_as_code.io import load_table


@pytest.mark.parametrize("content, message", [
    ("ID,AMOUNT,AMOUNT\n1,100,0\n", "duplicate"),
    ("ID,\n1,100\n", "empty column"),
    ("ID,  \n1,100\n", "empty column"),
    ("ID,AMOUNT\n1,100,extra\n", "line 2"),
    ("ID,AMOUNT\n1\n", "line 2"),
    ('ID,NOTE\n1,"unterminated\n', "CSV"),
])
def test_csv_rejects_ambiguous_export(tmp_path, content, message):
    path = tmp_path / "source.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DataError, match=message):
        load_table({"file": path.name}, tmp_path)
    assert path.read_text(encoding="utf-8") == content


def test_csv_keeps_bom_delimiter_quoted_newlines_and_explicit_empty_cells(tmp_path):
    path = tmp_path / "source.csv"
    path.write_text('\ufeffID;NOTE;AMOUNT\n001;"first\nsecond";\n', encoding="utf-8")
    _, rows = load_table({"file": path.name, "delimiter": ";"}, tmp_path)
    assert rows == [{"ID": "001", "NOTE": "first\nsecond", "AMOUNT": ""}]


@pytest.mark.parametrize("headers", [["ID", "AMOUNT", "AMOUNT"], ["ID", " AMOUNT ", "AMOUNT"]])
def test_excel_rejects_duplicate_normalized_headers(tmp_path, headers):
    path = tmp_path / "source.xlsx"
    workbook = Workbook()
    workbook.active.append(headers)
    workbook.active.append(["001", 100, 0])
    workbook.save(path)
    workbook.close()
    with pytest.raises(DataError, match="duplicate"):
        load_table({"file": path.name}, tmp_path)


def test_excel_preserves_optional_empty_cells(tmp_path):
    path = tmp_path / "source.xlsx"
    workbook = Workbook()
    workbook.active.append(["ID", "AMOUNT"])
    workbook.active.append(["001", None])
    workbook.save(path)
    workbook.close()
    _, rows = load_table({"file": path.name}, tmp_path)
    assert rows == [{"ID": "001", "AMOUNT": None}]


@pytest.mark.parametrize("headers", ["ID,AMOUNT,AMOUNT", "ID,AMOUNT,amount", "ID,"])
def test_duckdb_does_not_silently_rename_ambiguous_csv_columns(tmp_path, headers):
    path = tmp_path / "source.csv"
    path.write_text(headers + "\n", encoding="utf-8")
    with pytest.raises(DataError):
        _reader_sql({"file": path.name}, path)


def test_inspect_cli_returns_input_error_without_partial_json(tmp_path, capsys):
    path = tmp_path / "source.csv"
    path.write_text("ID,AMOUNT,AMOUNT\n1,100,0\n", encoding="utf-8")
    assert main(["inspect", str(path), "--json"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "duplicate" in captured.err
    assert "Traceback" not in captured.err
