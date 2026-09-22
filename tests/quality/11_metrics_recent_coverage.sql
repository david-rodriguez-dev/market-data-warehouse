-- Every company should have an annual row within the last 18 months of its
-- latest filing; otherwise the annual model is dropping recent 10-Ks.
SELECT c.ticker, c.last_filed, max(m.fiscal_year_end) AS latest_annual
FROM marts.dim_company AS c
LEFT JOIN marts.mart_fundamental_metrics AS m USING (cik)
GROUP BY ALL
HAVING max(m.fiscal_year_end) IS NULL
    OR max(m.fiscal_year_end) < c.last_filed - INTERVAL 18 MONTH
