"""Data-quality assertions expressed as SQL.

Each ``tests/quality/*.sql`` file is a query that returns the rows that
violate an expectation. Zero rows = pass. This keeps the assertions readable
by anyone who knows SQL and makes a failure self-describing: the offending
rows come back with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from mdw import config


@dataclass(frozen=True)
class Result:
    name: str
    failing_rows: int
    sample: list[tuple]
    columns: list[str]

    @property
    def passed(self) -> bool:
        return self.failing_rows == 0


def run(
    con: duckdb.DuckDBPyConnection,
    quality_dir: Path = config.QUALITY_DIR,
    *,
    sample_size: int = 3,
    log=print,
) -> list[Result]:
    results: list[Result] = []
    for path in sorted(quality_dir.glob("*.sql")):
        sql = path.read_text(encoding="utf-8").strip().rstrip(";")
        cursor = con.execute(sql)
        rows = cursor.fetchall()
        columns = [d[0] for d in cursor.description]
        result = Result(path.stem, len(rows), rows[:sample_size], columns)
        results.append(result)
        status = "PASS" if result.passed else "FAIL"
        suffix = "" if result.passed else f"  ({result.failing_rows} rows)"
        log(f"[test] {status}  {result.name}{suffix}")
        if not result.passed:
            log(f"       columns: {', '.join(columns)}")
            for row in result.sample:
                log(f"       {row}")
    return results
