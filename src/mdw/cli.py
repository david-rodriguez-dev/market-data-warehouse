"""``python -m mdw <command>``. Thin: parses args, opens the DB, delegates."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb

from mdw import build, config, ingest, quality, report
from mdw.edgar import EdgarClient


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mdw", description="SEC EDGAR fundamentals warehouse")
    p.add_argument("--db", default=None, help=f"DuckDB file (default: {config.DEFAULT_DB_PATH})")
    sub = p.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="pull company facts from EDGAR and load raw tables")
    ing.add_argument("--force", action="store_true", help="re-download even if the raw file is fresh")
    ing.add_argument("--max-age-days", type=float, default=7.0, help="reuse raw files younger than this")

    sub.add_parser("build", help="run sql/staging, sql/macros, sql/marts")
    sub.add_parser("test", help="run tests/quality/*.sql assertions")
    sub.add_parser("report", help="print the fundamentals mart")

    all_ = sub.add_parser("all", help="ingest, build, test, report")
    all_.add_argument("--force", action="store_true")
    all_.add_argument("--max-age-days", type=float, default=7.0)
    return p


def _do_ingest(con: duckdb.DuckDBPyConnection, args: argparse.Namespace) -> None:
    client = EdgarClient(user_agent=config.user_agent())
    ingest.run(con, client, config.load_companies(), force=args.force, max_age_days=args.max_age_days)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    path = Path(args.db) if args.db else config.db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        con = duckdb.connect(str(path))
        try:
            if args.command == "ingest":
                _do_ingest(con, args)
            elif args.command == "build":
                build.run(con)
            elif args.command == "test":
                results = quality.run(con)
                return 0 if all(r.passed for r in results) else 1
            elif args.command == "report":
                report.run(con)
            elif args.command == "all":
                _do_ingest(con, args)
                build.run(con)
                results = quality.run(con)
                report.run(con)
                return 0 if all(r.passed for r in results) else 1
        finally:
            con.close()
    except config.ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0
