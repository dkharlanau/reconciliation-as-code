from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def create(path: Path, rows: list[tuple[str, str, str, str]]) -> None:
    if path.exists():
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE customers (id TEXT PRIMARY KEY, country TEXT, amount TEXT, active TEXT)"
        )
        connection.executemany("INSERT INTO customers VALUES (?, ?, ?, ?)", rows)
        connection.commit()
    finally:
        connection.close()


def main() -> None:
    rows = [
        ("1001", "DE", "100.00", "Y"),
        ("1002", "US", "250.00", "Y"),
        ("1003", "GB", "75.00", "N"),
    ]
    create(ROOT / "legacy.db", rows)
    create(ROOT / "target.db", rows)
    print(f"created={ROOT / 'legacy.db'}")
    print(f"created={ROOT / 'target.db'}")


if __name__ == "__main__":
    main()
