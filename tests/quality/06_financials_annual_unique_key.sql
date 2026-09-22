SELECT cik, fiscal_year_end, count(*) AS n
FROM marts.fct_financials_annual
GROUP BY ALL
HAVING count(*) > 1
