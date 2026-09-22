"""market-data-warehouse: SEC EDGAR fundamentals -> DuckDB, with layered SQL models.

Pipeline stages, each a subcommand of ``python -m mdw``:

    ingest  -> pull company facts from EDGAR, land raw JSON, load typed rows
    build   -> run sql/staging then sql/marts in order
    test    -> run every tests/quality/*.sql; any returned row is a failure
    report  -> print the fundamentals mart for a quick look
    all     -> the four above, in order
"""

__version__ = "0.1.0"
