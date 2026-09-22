-- fiscal_year is a label derived from the year-end date; each company may
-- carry it exactly once. Two rows sharing a label means the derivation has
-- mislabelled a 52/53-week year-end, and every LAG-based growth figure and
-- peer rank downstream would be silently wrong.
SELECT cik, fiscal_year, count(*) AS n, string_agg(fiscal_year_end::VARCHAR, ', ') AS year_ends
FROM marts.fct_financials_annual
GROUP BY ALL
HAVING count(*) > 1
