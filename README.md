# market-data-warehouse

SEC EDGAR fundamentals → DuckDB, with layered SQL models, point-in-time
correctness, and data-quality assertions. Python 3.11+, two dependencies,
runs end to end in about ten seconds.

[![ci](https://github.com/davrod-dev/market-data-warehouse/actions/workflows/ci.yml/badge.svg)](https://github.com/davrod-dev/market-data-warehouse/actions/workflows/ci.yml)

**What it does**

- Pulls XBRL *company facts* for a configured list of filers from the SEC's
  public EDGAR API (no key, no vendor).
- Lands the raw JSON untouched, flattens it, and loads typed rows into DuckDB.
- Builds SQL models in layers, `staging → marts`, with dbt's conventions and
  none of its dependencies.
- Keeps **every revision of every fact**. "Latest known" and "as known on
  date X" are explicit queries, not something an ingest script decided.
- Guards the result with 13 SQL assertions and 17 offline tests that drive
  the whole pipeline through a synthetic filing in CI.

## Quickstart

```bash
git clone https://github.com/davrod-dev/market-data-warehouse
cd market-data-warehouse
pip install -e ".[dev]"

# SEC requires a User-Agent that identifies you. There is no default on purpose.
export EDGAR_USER_AGENT="market-data-warehouse you@example.com"   # PowerShell: $env:EDGAR_USER_AGENT = "..."

python -m mdw all        # ingest → build → test → report
pytest                   # offline suite, no network
```

Subcommands run individually too: `ingest`, `build`, `test`, `report`.
Raw downloads are cached for seven days; `--force` refreshes them.

## What comes out

`python -m mdw report` prints the fundamentals mart. Eight filers, latest
fiscal year, as of September 2026 (columns trimmed):

| ticker | fiscal_year | revenue_bn | net_margin | operating_margin | revenue_growth_yoy | revenue_cagr_3y | return_on_avg_equity | fcf_bn |
|---|---|---|---|---|---|---|---|---|
| AAPL | 2025 | 416.2 | 0.269 | 0.320 | 0.064 | 0.018 | 1.714 | 98.8 |
| MSFT | 2026 | 331.8 | 0.403 | 0.468 | 0.178 | 0.161 | 0.340 | 67.0 |
| COST | 2025 | 275.2 | 0.029 | 0.038 | 0.082 | 0.066 | 0.307 | 7.8 |
| NVDA | 2026 | 215.9 | 0.556 | 0.604 | 0.655 | 1.000 | 1.015 | 96.7 |
| JPM  | 2025 | 182.4 | 0.313 |  | 0.028 | 0.123 | 0.161 |  |
| JNJ  | 2025 | 94.2 | 0.285 |  | 0.060 | 0.056 | 0.350 | 19.7 |
| PFE  | 2025 | 62.6 | 0.124 |  | -0.016 | -0.148 | 0.089 | 9.1 |
| KO   | 2025 | 47.9 | 0.273 | 0.287 | 0.019 | 0.037 | 0.460 | 5.3 |

The blanks are correct blanks: JPMorgan does not report an operating income
line or capital expenditure, so the model says nothing rather than something.

It also lists the largest restatements it found between a figure's first
and latest filing:

| ticker | tag | period_end | original_mm | latest_mm | n_reports | first_filed | latest_filed |
|---|---|---|---|---|---|---|---|
| PFE | AssetsOfDisposalGroupIncludingDiscontinuedOperation | 2011-12-31 | 101.0 | 5,317.0 | 5 | 2012-02-28 | 2013-02-28 |
| AAPL | OtherNoncashIncomeExpense | 2021-09-25 | 147.0 | 4,921.0 | 3 | 2021-10-29 | 2023-11-03 |
| MSFT | IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic | 2016-06-30 | -325.0 | 5,125.0 | 3 | 2016-07-28 | 2018-08-03 |

## How it is put together

```
 EDGAR companyfacts API
        │  src/mdw/edgar.py      rate-limited client, retries, mandatory User-Agent
        ▼
 data/raw/*.json                 exact bytes as served; re-loadable offline
        │  src/mdw/ingest.py     flatten → NDJSON → typed load, idempotent per company
        ▼
 raw.company_facts               one row per reported fact, every taxonomy and unit
        │  src/mdw/build.py      runs sql/ in order: staging (views) → macros → marts (tables)
        ▼
 staging.stg_company_facts       us-gaap / USD, typed, period semantics derived
        │
        ├─▶ marts.fct_fact_revision        every version of every fact, ranked
        ├─▶ marts.facts_as_of(date)        table macro: what was on file on a given day
        ├─▶ marts.dim_company              coverage per filer
        ├─▶ marts.dim_concept              statement line item ↔ XBRL tag(s), with priority
        ├─▶ marts.fct_financials_annual    one row per company per own fiscal year
        └─▶ marts.mart_fundamental_metrics margins, growth, returns, peer ranks
                │  src/mdw/quality.py      tests/quality/*.sql, zero rows = pass
                ▼
        13 assertions, run every build
```

## The problem this is built around

EDGAR does not give you *a* number for Apple's FY2016 revenue. It gives you
every time Apple reported it: in the FY2016 10-K, again as a comparative in
the FY2017 and FY2018 10-Ks, and possibly restated along the way. The
companyfacts API returns all of them, and its `fy`/`fp` fields describe the
**filing** each one came from, not the period it covers. A FY2016 figure
carried in the FY2018 10-K is tagged `fy=2018`.

Most quick scripts take the last row, or the first, or group by `fy`, and
get quietly wrong answers. This warehouse instead keeps every version in
`marts.fct_fact_revision` and makes the choice explicit:

```sql
-- Dashboard: what do we believe now?
SELECT value FROM marts.fct_fact_revision
WHERE tag = 'Revenues' AND period_end = DATE '2016-09-24' AND is_latest;

-- Backtest or audit: what was on file on 31 Jan 2017?
SELECT value FROM marts.facts_as_of(DATE '2017-01-31')
WHERE tag = 'Revenues' AND period_end = DATE '2016-09-24';

-- Which figures changed between first and latest report, and by how much?
SELECT tag, period_end, originally_reported_value, value, n_reports
FROM marts.fct_fact_revision
WHERE is_latest AND is_restated;
```

The ranking is one window function over the natural key
(`cik, tag, unit, period_start, period_end`), ordered by `filed`. Nothing is
deleted upstream of it. See
[`sql/marts/02_fct_fact_revision.sql`](sql/marts/02_fct_fact_revision.sql).

## Design notes: what the data taught this repo

Each of these started as a failing assertion on live data.

1. **Filter forms before choosing a version, never after.** Apple's FY2013
   balance sheet disappeared from the annual model. Its most recent report
   was an 8-K exhibit in 2015, so "latest, then 10-K only" left nothing.
   The annual model now takes the latest *10-K* version of each period.
2. **A fiscal year is only real once the filer's own 10-K exists.** Pfizer's
   FY2009 10-K carries a Wyeth period ending 2009-09-27. Pre-XBRL years show
   up as half-empty comparatives inside 2009-2011 filings. Both are excluded
   by one rule: some 10-K must have reported the period within 120 days of
   its end. Coverage per filer is now 16-17 complete years, and the
   balance-sheet completeness assertion holds with no year floor.
3. **52/53-week calendars break `year(period_end)`.** J&J's fiscal 2011 ended
   on 2012-01-01, giving two rows labelled 2012 and corrupting every LAG-based
   growth figure. Labels are taken from `period_end - 7 days`, and an
   assertion guarantees one row per company per label.
4. **Tags drift.** `SalesRevenueGoodsNet` was the revenue tag for goods
   companies until ASC 606 retired it in 2018; NVIDIA books capex under
   `PaymentsToAcquireProductiveAssets`. `marts.dim_concept` maps each line
   item to its tags with a priority, so adding a filer is a data change.
5. **Tickers are not identifiers.** `XOM` now resolves to a CIK created in
   2025 with a single filing (Exxon reincorporated). The coverage assertion
   caught a filer with no annual rows; the fix was to track the entity by
   CIK and treat ticker mapping as an ingest-time lookup.
6. **Forward-looking facts exist.** Remaining buyback authorisations are
   filed before their period ends. The "filed after period end" check moved
   from staging, where it was wrong, to the annual model, where it is right.
7. **Growth guards against gaps.** `LAG` reaches back one row, not one year.
   Every prior-year value is wrapped in a check that the previous row *is*
   the previous year, so a missing year yields NULL instead of a wrong ratio.

## Layout

```
config/companies.json          tickers to track; add one and re-run
src/mdw/
  edgar.py                     EDGAR client: 5 req/s, backoff on 429/5xx, 403 explained
  ingest.py                    raw landing, flatten, idempotent load, prune untracked
  build.py                     model runner (filename prefix = order, folder = layer)
  quality.py                   assertion runner
  report.py                    Markdown tables
  cli.py                       python -m mdw {ingest,build,test,report,all}
sql/
  staging/                     views over raw
  macros/facts_as_of.sql       point-in-time table macro
  marts/                       dimensions, fact revisions, annual statement, metrics
tests/
  quality/*.sql                13 assertions; a query returning zero rows passes
  test_edgar.py                client behaviour with a fake session and clock
  test_pipeline.py             synthetic filing through every layer, incl. a restatement
.github/workflows/ci.yml       pytest on 3.11 and 3.12, no network
CLAUDE.md                      conventions, and how this was built
```

## Quality assertions

Each file in `tests/quality/` is a query that returns the rows violating an
expectation. The runner prints a sample of any failures, so a red build tells
you *which* company-year is wrong, not just that something is.

| # | asserts |
|---|---|
| 01 | every staged fact has a company, tag, period, value and filing |
| 02 | duration facts start before they end |
| 03 | one row per CIK in the company dimension |
| 04 | every tracked company loaded at least one fact |
| 05 | exactly one version of each fact is flagged latest |
| 06 | one annual row per company per year-end date |
| 07 | annual revenue is positive |
| 08 | assets ≥ equity; revenue, net income, assets and equity all present |
| 09 | margins are within -300 % .. +100 % (a tag-mapping error, not a business) |
| 10 | every metrics row joins to a company |
| 11 | every company has an annual row within 18 months of its latest filing |
| 12 | annual figures were filed after the year they describe |
| 13 | one annual row per company per fiscal-year label |

## Testing

The offline suite never touches sec.gov. `tests/test_pipeline.py` builds a
small companyfacts document by hand, with one period reported in three
successive 10-Ks and restated in the third, a quarterly fact, a non-USD
fact, and a period that appears only as a comparative. It then runs ingest,
build and every quality assertion against an in-memory DuckDB and checks
the numbers by hand: `n_reports = 3`, `originally_reported_value = 100`,
`value = 110`, `facts_as_of('2017-06-30') = 100`, and so on.

The client tests use a fake session and clock to prove rate spacing, backoff
on 503/429, no retry on 404, and the `User-Agent` header.

## Built with Claude Code

This repository was written in one session with Claude Code doing the
typing and first drafts, and a human choosing the data source, the layering,
what counts as correct for a restated number, and what to ship. Every design
note above began as a real failure on live EDGAR data that the model and I
diagnosed with SQL and fixed in the model, not by relaxing the test.
[`CLAUDE.md`](CLAUDE.md) has the conventions the tool follows and a plain
account of the process.

## Not done, on purpose

- **Quarterly statement.** 10-Qs report year-to-date; Q4 must be derived as
  FY minus 9M. Straightforward on top of `fct_fact_revision`, not yet built.
- **Dimensional facts.** The companyfacts API omits segment and geography
  breakdowns; they need the per-filing XBRL instance documents.
- **Another engine.** The SQL is standard apart from `QUALIFY` and the
  table macro; a Postgres target would swap those for a CTE and a function.

## License

MIT. Data is from the U.S. Securities and Exchange Commission and is public
domain; see [SEC's fair-access policy](https://www.sec.gov/os/accessing-edgar-data)
before pointing this at more than a handful of filers.

---

David Rodriguez · [github.com/davrod-dev](https://github.com/davrod-dev)
