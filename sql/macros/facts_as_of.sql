-- Point-in-time view of the facts table.
--
--   SELECT * FROM marts.facts_as_of(DATE '2017-01-31') WHERE tag = 'Revenues'
--
-- returns, for every (company, concept, period), the value that was on file
-- as of that date: the most recent filing with filed <= as_of. This is what a
-- backtest or an audit needs; the "latest" flag in fct_fact_revision is what
-- a dashboard needs. Same data, different question.
CREATE OR REPLACE MACRO marts.facts_as_of(as_of) AS TABLE
SELECT * EXCLUDE (rn)
FROM (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY cik, tag, unit, period_start, period_end
            ORDER BY filed DESC, accession_number DESC
        ) AS rn
    FROM staging.stg_company_facts
    WHERE filed <= as_of
)
WHERE rn = 1
