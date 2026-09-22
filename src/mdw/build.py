"""Run the SQL model layers in order.

Convention (borrowed from dbt, without the dependency):

    sql/staging/NN_<name>.sql   ->  CREATE OR REPLACE VIEW  staging.<name> AS <file>
    sql/macros/*.sql            ->  executed verbatim (table macros, helpers)
    sql/marts/NN_<name>.sql     ->  CREATE OR REPLACE TABLE marts.<name>   AS <file>

Model files are plain SELECTs. The numeric prefix fixes execution order and
is stripped from the object name, so ``02_fct_fact_revision.sql`` becomes
``marts.fct_fact_revision``. Staging is views (always reflects raw); marts are
tables (computed once, queried many times).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import duckdb

from mdw import config

_PREFIX = re.compile(r"^\d+_")


@dataclass(frozen=True)
class Model:
    schema: str
    name: str
    materialization: str  # "view" | "table" | "raw"
    path: Path

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}"


def discover(sql_dir: Path = config.SQL_DIR) -> list[Model]:
    layers = (
        ("staging", "staging", "view"),
        ("macros", "marts", "raw"),
        ("marts", "marts", "table"),
    )
    models: list[Model] = []
    for folder, schema, materialization in layers:
        for path in sorted((sql_dir / folder).glob("*.sql")):
            models.append(Model(schema, _PREFIX.sub("", path.stem), materialization, path))
    return models


def _body(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip().rstrip(";").strip()


def statement_for(model: Model) -> str:
    body = _body(model.path)
    if model.materialization == "raw":
        return body
    kind = "VIEW" if model.materialization == "view" else "TABLE"
    return f"CREATE OR REPLACE {kind} {model.qualified_name} AS\n{body}"


def run(con: duckdb.DuckDBPyConnection, sql_dir: Path = config.SQL_DIR, log=print) -> list[Model]:
    for schema in ("staging", "marts"):
        con.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")
    models = discover(sql_dir)
    for model in models:
        con.execute(statement_for(model))
        if model.materialization == "raw":
            log(f"[build] ran     {model.path.name}")
        else:
            n = con.execute(f"SELECT count(*) FROM {model.qualified_name}").fetchone()[0]
            log(f"[build] {model.materialization:<5} {model.qualified_name:<36} {n:>10,} rows")
    return models
