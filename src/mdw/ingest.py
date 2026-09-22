"""Land raw EDGAR JSON, flatten it, and load typed rows into DuckDB.

Two layers on disk, mirroring a real warehouse:

    data/raw/       exact JSON as EDGAR served it (auditable, re-loadable offline)
    data/staging/   one flat NDJSON file per company, ready for DuckDB

and one table in the database, ``raw.company_facts``, which is the only thing
the SQL layers ever read. Loading is idempotent per company: re-running
replaces that company's rows rather than duplicating them.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import duckdb

from mdw import config
from mdw.edgar import EdgarClient

FACT_COLUMNS: dict[str, str] = {
    "cik": "BIGINT",
    "entity_name": "VARCHAR",
    "taxonomy": "VARCHAR",
    "tag": "VARCHAR",
    "unit": "VARCHAR",
    "period_start": "DATE",
    "period_end": "DATE",
    "value": "DOUBLE",
    "accession_number": "VARCHAR",
    "fiscal_year": "INTEGER",
    "fiscal_period": "VARCHAR",
    "form": "VARCHAR",
    "filed": "DATE",
    "frame": "VARCHAR",
}

RAW_DDL = """
CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.companies (
    cik           BIGINT PRIMARY KEY,
    ticker        VARCHAR NOT NULL,
    company_name  VARCHAR,
    loaded_at     TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS raw.company_facts (
    cik               BIGINT   NOT NULL,
    entity_name       VARCHAR,
    taxonomy          VARCHAR  NOT NULL,
    tag               VARCHAR  NOT NULL,
    unit              VARCHAR  NOT NULL,
    period_start      DATE,
    period_end        DATE     NOT NULL,
    value             DOUBLE   NOT NULL,
    accession_number  VARCHAR  NOT NULL,
    fiscal_year       INTEGER,
    fiscal_period     VARCHAR,
    form              VARCHAR,
    filed             DATE     NOT NULL,
    frame             VARCHAR
);

CREATE TABLE IF NOT EXISTS raw.load_log (
    cik          BIGINT    NOT NULL,
    ticker       VARCHAR   NOT NULL,
    source_file  VARCHAR   NOT NULL,
    row_count    BIGINT    NOT NULL,
    loaded_at    TIMESTAMP NOT NULL
);
"""


def flatten_company_facts(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Turn EDGAR's nested companyfacts document into one dict per reported fact.

    EDGAR shape: facts[taxonomy][tag]["units"][unit] -> list of fact objects.
    Every level is preserved as a column so nothing is lost between raw and
    staging; filtering to a taxonomy or unit is a SQL decision, not a Python one.
    """
    cik = int(payload["cik"])
    entity_name = payload.get("entityName")
    for taxonomy, tags in payload.get("facts", {}).items():
        for tag, body in tags.items():
            for unit, facts in body.get("units", {}).items():
                for fact in facts:
                    yield {
                        "cik": cik,
                        "entity_name": entity_name,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "period_start": fact.get("start"),
                        "period_end": fact["end"],
                        "value": fact["val"],
                        "accession_number": fact["accn"],
                        "fiscal_year": fact.get("fy"),
                        "fiscal_period": fact.get("fp"),
                        "form": fact.get("form"),
                        "filed": fact["filed"],
                        "frame": fact.get("frame"),
                    }


def write_ndjson(payload: dict[str, Any], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in flatten_company_facts(payload):
            fh.write(json.dumps(row, separators=(",", ":")))
            fh.write("\n")
            n += 1
    return n


def is_fresh(path: Path, max_age_days: float) -> bool:
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < max_age_days * 86400


def ensure_raw_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(RAW_DDL)


def load_company(
    con: duckdb.DuckDBPyConnection,
    *,
    cik: int,
    ticker: str,
    company_name: str | None,
    ndjson_path: Path,
) -> int:
    """Replace one company's rows in raw.company_facts from its NDJSON file."""
    column_spec = ", ".join(f"'{name}': '{typ}'" for name, typ in FACT_COLUMNS.items())
    column_list = ", ".join(FACT_COLUMNS)
    file_literal = ndjson_path.as_posix().replace("'", "''")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    con.execute("BEGIN")
    try:
        con.execute("DELETE FROM raw.company_facts WHERE cik = ?", [cik])
        con.execute(
            f"INSERT INTO raw.company_facts ({column_list}) "
            f"SELECT {column_list} FROM read_ndjson('{file_literal}', columns={{{column_spec}}})"
        )
        row_count = con.execute(
            "SELECT count(*) FROM raw.company_facts WHERE cik = ?", [cik]
        ).fetchone()[0]
        con.execute(
            "INSERT OR REPLACE INTO raw.companies VALUES (?, ?, ?, ?)",
            [cik, ticker, company_name, now],
        )
        con.execute(
            "INSERT INTO raw.load_log VALUES (?, ?, ?, ?, ?)",
            [cik, ticker, ndjson_path.name, row_count, now],
        )
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    return row_count


def fetch_ticker_map(client: EdgarClient, *, force: bool, max_age_days: float) -> dict[str, dict[str, Any]]:
    cache = config.RAW_DIR / "company_tickers.json"
    if force or not is_fresh(cache, max_age_days):
        cache.parent.mkdir(parents=True, exist_ok=True)
        payload = client.ticker_map()
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return json.loads(cache.read_text(encoding="utf-8"))


def run(
    con: duckdb.DuckDBPyConnection,
    client: EdgarClient,
    companies: config.Companies,
    *,
    force: bool = False,
    max_age_days: float = 7.0,
    log=print,
) -> None:
    ensure_raw_schema(con)
    ticker_map = fetch_ticker_map(client, force=force, max_age_days=max_age_days)

    for ticker in companies.tickers:
        meta = ticker_map.get(ticker)
        if meta is None:
            raise config.ConfigError(f"ticker {ticker!r} is not in EDGAR's company_tickers.json")
        cik = int(meta["cik"])
        raw_path = config.RAW_DIR / f"companyfacts_CIK{cik:010d}.json"

        if force or not is_fresh(raw_path, max_age_days):
            log(f"[ingest] {ticker:<6} downloading companyfacts for CIK {cik}")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            payload = client.company_facts(cik)
            raw_path.write_text(json.dumps(payload), encoding="utf-8")
        else:
            log(f"[ingest] {ticker:<6} raw file is fresh, skipping download")
            payload = json.loads(raw_path.read_text(encoding="utf-8"))

        ndjson_path = config.STAGING_DIR / f"facts_CIK{cik:010d}.ndjson"
        n_flat = write_ndjson(payload, ndjson_path)
        n_loaded = load_company(
            con, cik=cik, ticker=ticker, company_name=payload.get("entityName"), ndjson_path=ndjson_path
        )
        log(f"[ingest] {ticker:<6} flattened {n_flat:,} facts, loaded {n_loaded:,} rows")

    pruned = prune_untracked(con, companies.tickers)
    for ticker, cik in pruned:
        log(f"[ingest] {ticker:<6} no longer tracked, removed CIK {cik}")


def prune_untracked(con: duckdb.DuckDBPyConnection, tickers: tuple[str, ...]) -> list[tuple[str, int]]:
    """Drop companies that left config/companies.json so the warehouse mirrors it exactly."""
    placeholders = ", ".join("?" for _ in tickers)
    gone = con.execute(
        f"SELECT ticker, cik FROM raw.companies WHERE ticker NOT IN ({placeholders})", list(tickers)
    ).fetchall()
    for _, cik in gone:
        con.execute("DELETE FROM raw.company_facts WHERE cik = ?", [cik])
        con.execute("DELETE FROM raw.companies WHERE cik = ?", [cik])
    return [(t, int(c)) for t, c in gone]
