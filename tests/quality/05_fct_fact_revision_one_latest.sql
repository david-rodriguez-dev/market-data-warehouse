-- Exactly one version of each (company, concept, period) may be flagged latest.
SELECT cik, tag, unit, period_start, period_end, sum(CASE WHEN is_latest THEN 1 ELSE 0 END) AS n_latest
FROM marts.fct_fact_revision
GROUP BY ALL
HAVING n_latest <> 1
