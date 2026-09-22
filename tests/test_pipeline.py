"""End-to-end: synthetic companyfacts -> raw -> staging -> marts -> quality.

The fixture is small enough to reason about by hand and contains the three
things that make EDGAR data hard: a period reported in three successive
filings, a restatement, and a quarterly fact that must not leak into the
annual model.
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from mdw import build, ingest, quality

CIK = 999001


def fact(start, end, val, accn, filed, fy, fp="FY", form="10-K"):
    return {"start": start, "end": end, "val": val, "accn": accn, "fy": fy,
            "fp": fp, "form": form, "filed": filed}


def instant(end, val, accn, filed, fy):
    f = fact(None, end, val, accn, filed, fy)
    del f["start"]
    return f


# Three 10-Ks: FY2016 (accn A), FY2017 (B), FY2018 (C). Each carries the prior
# years as comparatives. The FY2016 revenue is restated in C from 100 to 110.
A, B, C = ("0000999001-16-000001", "0000999001-17-000001", "0000999001-18-000001")
FA, FB, FC = ("2016-11-01", "2017-11-01", "2018-11-01")
Y16 = ("2015-10-01", "2016-09-30")
Y17 = ("2016-10-01", "2017-09-30")
Y18 = ("2017-10-01", "2018-09-30")


def usd(*facts):
    return {"units": {"USD": list(facts)}}


PAYLOAD = {
    "cik": CIK,
    "entityName": "Test Co",
    "facts": {
        "us-gaap": {
            "Revenues": usd(
                # FY2015 appears ONLY as a comparative, 13 months after it ended:
                # never this filer's own reporting year, so no annual row.
                fact("2014-10-01", "2015-09-30", 90, A, FA, 2016),
                fact(*Y16, 100, A, FA, 2016),
                fact(*Y16, 100, B, FB, 2017),
                fact(*Y16, 110, C, FC, 2018),   # restated
                fact(*Y17, 120, B, FB, 2017),
                fact(*Y17, 120, C, FC, 2018),
                fact(*Y18, 150, C, FC, 2018),
                # quarterly fact must not reach the annual model
                fact("2017-10-01", "2017-12-31", 40, "0000999001-18-000009", "2018-02-01", 2018, "Q1", "10-Q"),
            ),
            "NetIncomeLoss": usd(
                fact(*Y16, 10, A, FA, 2016), fact(*Y17, 12, B, FB, 2017), fact(*Y18, 30, C, FC, 2018),
            ),
            "OperatingIncomeLoss": usd(
                fact(*Y16, 15, A, FA, 2016), fact(*Y17, 18, B, FB, 2017), fact(*Y18, 40, C, FC, 2018),
            ),
            "Assets": usd(
                instant(Y16[1], 500, A, FA, 2016), instant(Y17[1], 600, B, FB, 2017), instant(Y18[1], 700, C, FC, 2018),
            ),
            "StockholdersEquity": usd(
                instant(Y16[1], 200, A, FA, 2016), instant(Y17[1], 250, B, FB, 2017), instant(Y18[1], 300, C, FC, 2018),
            ),
            "NetCashProvidedByUsedInOperatingActivities": usd(
                fact(*Y16, 20, A, FA, 2016), fact(*Y17, 25, B, FB, 2017), fact(*Y18, 40, C, FC, 2018),
            ),
            "PaymentsToAcquirePropertyPlantAndEquipment": usd(
                fact(*Y16, 5, A, FA, 2016), fact(*Y17, 5, B, FB, 2017), fact(*Y18, 10, C, FC, 2018),
            ),
            # share counts are not USD and must be filtered out in staging
            "CommonStockSharesOutstanding": {"units": {"shares": [instant(Y18[1], 1000, C, FC, 2018)]}},
        },
        "dei": {"EntityPublicFloat": usd(instant(Y18[1], 5000, C, FC, 2018))},
    },
}


@pytest.fixture
def warehouse(tmp_path):
    con = duckdb.connect(":memory:")
    ingest.ensure_raw_schema(con)
    path = tmp_path / "facts.ndjson"
    ingest.write_ndjson(PAYLOAD, path)
    ingest.load_company(con, cik=CIK, ticker="TST", company_name="Test Co", ndjson_path=path)
    build.run(con, log=lambda *_: None)
    yield con
    con.close()


def q(con, sql, *params):
    return con.execute(sql, list(params)).fetchall()


def test_flatten_yields_one_row_per_fact_across_all_taxonomies_and_units():
    rows = list(ingest.flatten_company_facts(PAYLOAD))
    assert len(rows) == 8 + 3 * 6 + 1 + 1
    assert {r["taxonomy"] for r in rows} == {"us-gaap", "dei"}
    assert rows[0]["period_start"] == "2014-10-01" and rows[0]["cik"] == CIK


def test_load_is_idempotent_per_company(warehouse, tmp_path):
    before = q(warehouse, "SELECT count(*) FROM raw.company_facts")[0][0]
    ingest.load_company(warehouse, cik=CIK, ticker="TST", company_name="Test Co", ndjson_path=tmp_path / "facts.ndjson")
    after = q(warehouse, "SELECT count(*) FROM raw.company_facts")[0][0]
    assert before == after == 28
    assert q(warehouse, "SELECT count(*) FROM raw.load_log")[0][0] == 2


def test_staging_keeps_only_usgaap_usd_and_types_periods(warehouse):
    assert q(warehouse, "SELECT count(*) FROM staging.stg_company_facts")[0][0] == 26
    types = dict(q(warehouse, "SELECT period_type, count(*) FROM staging.stg_company_facts GROUP BY 1"))
    assert types == {"duration": 20, "instant": 6}


def test_fact_revision_tracks_every_report_and_flags_restatement(warehouse):
    (row,) = q(warehouse, """
        SELECT n_reports, value, originally_reported_value, is_restated, first_filed, filed
        FROM marts.fct_fact_revision
        WHERE tag = 'Revenues' AND period_end = DATE '2016-09-30' AND is_latest
    """)
    assert row == (3, 110, 100, True, date(2016, 11, 1), date(2018, 11, 1))
    assert q(warehouse, "SELECT count(*) FROM marts.fct_fact_revision WHERE is_restated AND is_latest")[0][0] == 1


def test_facts_as_of_returns_what_was_known_on_that_date(warehouse):
    sql = "SELECT value FROM marts.facts_as_of(?::DATE) WHERE tag = 'Revenues' AND period_end = DATE '2016-09-30'"
    assert q(warehouse, sql, "2016-10-31") == []
    assert q(warehouse, sql, "2017-06-30") == [(100,)]
    assert q(warehouse, sql, "2018-12-31") == [(110,)]


def test_annual_model_is_keyed_by_period_not_filing_year(warehouse):
    rows = q(warehouse, "SELECT fiscal_year, revenue, net_income, total_assets FROM marts.fct_financials_annual ORDER BY 1")
    assert rows == [(2016, 110, 10, 500), (2017, 120, 12, 600), (2018, 150, 30, 700)]


def test_annual_model_excludes_periods_seen_only_as_comparatives(warehouse):
    # The FY2015 revenue fact exists in staging but no filing reported it promptly.
    assert q(warehouse, "SELECT count(*) FROM staging.stg_company_facts WHERE period_end = DATE '2015-09-30'") == [(1,)]
    assert q(warehouse, "SELECT count(*) FROM marts.fct_financials_annual WHERE fiscal_year = 2015") == [(0,)]


def test_metrics_growth_and_returns(warehouse):
    rows = q(warehouse, """
        SELECT fiscal_year, round(revenue_growth_yoy, 6), round(return_on_avg_equity, 6), round(free_cash_flow, 2)
        FROM marts.mart_fundamental_metrics ORDER BY 1
    """)
    assert rows[0] == (2016, None, None, 15)
    assert rows[1] == (2017, round(120 / 110 - 1, 6), round(12 / 225, 6), 20)
    assert rows[2] == (2018, round(150 / 120 - 1, 6), round(30 / 275, 6), 30)


def test_all_quality_assertions_pass_on_fixture(warehouse):
    results = quality.run(warehouse, log=lambda *_: None)
    assert len(results) >= 10
    assert [r.name for r in results if not r.passed] == []


def test_model_discovery_orders_layers_and_strips_prefixes():
    models = build.discover()
    names = [m.qualified_name for m in models]
    assert names[0] == "staging.stg_companies"
    assert "marts.fct_fact_revision" in names
    assert names.index("marts.dim_concept") < names.index("marts.fct_financials_annual")
    assert all(m.materialization == "raw" for m in models if "macros" in m.path.parts)
