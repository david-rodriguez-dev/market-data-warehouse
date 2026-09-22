"""Print what the warehouse knows, as Markdown tables.

Deliberately minimal: the interesting logic lives in SQL, this just shows it.
"""
from __future__ import annotations

import duckdb

METRICS_SQL = """
SELECT
    ticker,
    fiscal_year,
    revenue / 1e9                 AS revenue_bn,
    net_margin,
    operating_margin,
    revenue_growth_yoy,
    revenue_cagr_3y,
    return_on_avg_equity,
    free_cash_flow / 1e9          AS fcf_bn,
    net_margin_peer_pct_rank
FROM marts.mart_fundamental_metrics
QUALIFY row_number() OVER (PARTITION BY cik ORDER BY fiscal_year_end DESC) = 1
ORDER BY revenue_bn DESC
"""

RESTATEMENTS_SQL = """
SELECT
    c.ticker,
    f.tag,
    f.period_end,
    f.originally_reported_value / 1e6                     AS original_mm,
    f.value / 1e6                                         AS latest_mm,
    f.value / nullif(f.originally_reported_value, 0) - 1  AS pct_change,
    f.n_reports,
    f.first_filed,
    f.filed                                               AS latest_filed
FROM marts.fct_fact_revision f
JOIN marts.dim_company c USING (cik)
WHERE f.is_latest
  AND f.is_restated
  AND abs(f.originally_reported_value) >= 1e8
ORDER BY abs(pct_change) DESC
LIMIT 10
"""


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:,.3f}" if abs(v) < 10 else f"{v:,.1f}"
    return str(v)


def markdown_table(columns: list[str], rows: list[tuple]) -> str:
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(_fmt(v) for v in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def run(con: duckdb.DuckDBPyConnection, log=print) -> None:
    sections = (
        ("Latest fiscal year, per company", METRICS_SQL),
        ("Largest restatements between first and latest filing (>= $100mm)", RESTATEMENTS_SQL),
    )
    for title, sql in sections:
        cur = con.execute(sql)
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description]
        log(f"\n### {title}\n")
        log(markdown_table(cols, rows))
