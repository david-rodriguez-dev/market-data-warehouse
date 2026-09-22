-- One row per reported fact, typed and annotated with period semantics.
--
-- Scope: US-GAAP concepts denominated in USD. That drops share counts,
-- per-share figures and the dei taxonomy, which is deliberate: the marts
-- below are about statement amounts, and mixing units in one value column
-- is how bad numbers get published.
--
-- Two things worth knowing about EDGAR's companyfacts API:
--   * fiscal_year / fiscal_period describe the FILING a fact came from, not
--     the period the fact covers. A FY2016 revenue number appears in the
--     FY2018 10-K as a comparative, tagged fy=2018. Never key on fy.
--   * period_start is NULL for balance-sheet (instant) facts and present
--     for income/cash-flow (duration) facts.
SELECT
    cik,
    tag,
    unit,
    period_start,
    period_end,
    CASE WHEN period_start IS NULL THEN 'instant' ELSE 'duration' END       AS period_type,
    date_diff('day', period_start, period_end)                             AS period_days,
    CAST(value AS DECIMAL(24, 4))                                          AS value,
    accession_number,
    fiscal_year                                                            AS filing_fiscal_year,
    fiscal_period                                                          AS filing_fiscal_period,
    form,
    filed,
    frame
FROM raw.company_facts
WHERE taxonomy = 'us-gaap'
  AND unit = 'USD'
