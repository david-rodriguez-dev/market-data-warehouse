-- Wide annual statement: one row per company per fiscal-year end, keyed by
-- the period the numbers cover (NOT the filing year).
--
-- Source facts come from 10-K filings only: instants (balance sheet) at the
-- year end, and durations of roughly one year (income and cash flow). The
-- 350-380 day window tolerates 52/53-week fiscal calendars.
--
-- Version choice: the newest 10-K that carries the period. This is applied
-- BEFORE picking a version, not after. A period's most recent report is very
-- often an 8-K exhibit or a 10-Q comparative; filtering to is_latest first
-- and then to 10-K would throw the value away entirely. (Found the hard way:
-- Apple's FY2013 balance sheet vanished because its last appearance was an
-- 8-K in 2015.)
WITH annual_facts AS (
    SELECT
        f.cik,
        m.concept,
        m.priority,
        f.period_end,
        f.value,
        f.filed
    FROM marts.fct_fact_revision AS f
    JOIN marts.dim_concept AS m ON m.tag = f.tag
    WHERE f.form IN ('10-K', '10-K/A')
      AND (f.period_type = 'instant' OR f.period_days BETWEEN 350 AND 380)
),
own_periods AS (
    -- A fiscal year belongs in this model once the company's OWN 10-K for it
    -- exists: some 10-K reported the period within 120 days of its end
    -- (filing deadlines are 60-90 days). Periods that only ever appear as
    -- comparatives, or as acquisition stubs inside another year's 10-K
    -- (Pfizer's FY2009 10-K carries a Wyeth period ending 2009-09-27), are
    -- excluded because they were never that filer's reporting year.
    SELECT cik, period_end
    FROM annual_facts
    GROUP BY ALL
    HAVING date_diff('day', period_end, min(filed)) <= 120
),
resolved AS (
    -- Preferred tag first; within a tag, the newest 10-K wins.
    SELECT a.*
    FROM annual_facts AS a
    JOIN own_periods USING (cik, period_end)
    QUALIFY row_number() OVER (
        PARTITION BY cik, concept, period_end
        ORDER BY priority, filed DESC
    ) = 1
)
SELECT
    cik,
    period_end                                                     AS fiscal_year_end,
    -- 52/53-week calendars end on a weekend near Dec 31, which can land in
    -- the first days of January: J&J's fiscal 2011 ended 2012-01-01. Shifting
    -- a week back before taking the year labels those correctly and leaves
    -- every other year-end (late Jan, June, Sep, Dec) untouched.
    year(period_end - INTERVAL 7 DAY)                              AS fiscal_year,
    max(CASE WHEN concept = 'revenue'             THEN value END)  AS revenue,
    max(CASE WHEN concept = 'operating_income'    THEN value END)  AS operating_income,
    max(CASE WHEN concept = 'net_income'          THEN value END)  AS net_income,
    max(CASE WHEN concept = 'total_assets'        THEN value END)  AS total_assets,
    max(CASE WHEN concept = 'total_equity'        THEN value END)  AS total_equity,
    max(CASE WHEN concept = 'cash'                THEN value END)  AS cash,
    max(CASE WHEN concept = 'long_term_debt'      THEN value END)  AS long_term_debt,
    max(CASE WHEN concept = 'operating_cash_flow' THEN value END)  AS operating_cash_flow,
    max(CASE WHEN concept = 'capex'               THEN value END)  AS capex,
    count(*)                                                       AS n_concepts_reported,
    max(filed)                                                     AS latest_source_filed
FROM resolved
GROUP BY cik, period_end
