-- Revenue can be missing for a year (tag drift) but never zero or negative.
SELECT cik, fiscal_year_end, revenue
FROM marts.fct_financials_annual
WHERE revenue <= 0
