SELECT m.cik, m.fiscal_year
FROM marts.mart_fundamental_metrics AS m
LEFT JOIN marts.dim_company AS c USING (cik)
WHERE c.cik IS NULL
