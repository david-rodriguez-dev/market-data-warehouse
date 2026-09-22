-- Every version of every fact, ranked so downstream can choose deliberately.
--
-- The same (company, concept, period) is reported many times: in its original
-- filing, again as a comparative in the next two years of filings, and
-- occasionally restated. This model keeps all of them and answers, per row:
--
--   revision_rank              1 = the most recent filing of this period
--   is_latest                  revision_rank = 1
--   n_reports                  how many filings carried this period
--   originally_reported_value  what the first filing said
--   is_restated                latest value differs from the original
--
-- Nothing is dropped here. "Latest known" is a filter (is_latest); "as known
-- on date X" is the facts_as_of macro. Both are explicit choices, not defaults
-- hidden in an ingest script.
WITH ranked AS (
    SELECT
        *,
        row_number()       OVER w_desc AS revision_rank,
        count(*)           OVER w_all  AS n_reports,
        min(filed)         OVER w_all  AS first_filed,
        first_value(value) OVER w_asc  AS originally_reported_value
    FROM staging.stg_company_facts
    WINDOW
        w_all  AS (PARTITION BY cik, tag, unit, period_start, period_end),
        w_desc AS (PARTITION BY cik, tag, unit, period_start, period_end
                   ORDER BY filed DESC, accession_number DESC),
        w_asc  AS (PARTITION BY cik, tag, unit, period_start, period_end
                   ORDER BY filed ASC, accession_number ASC
                   ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
)
SELECT
    *,
    revision_rank = 1                   AS is_latest,
    value <> originally_reported_value  AS is_restated
FROM ranked
