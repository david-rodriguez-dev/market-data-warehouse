-- Two expectations on every annual row:
--   1. Assets >= equity whenever both are present and equity is positive.
--   2. Revenue, net income, assets and equity are all present.
-- Completeness holds without a year floor because the annual model only
-- admits a company's own XBRL-era fiscal years (see own_periods in
-- 03_fct_financials_annual.sql); pre-2009 comparatives never get this far.
SELECT cik, fiscal_year_end, total_assets, total_equity, revenue, net_income
FROM marts.fct_financials_annual
WHERE (total_assets IS NOT NULL AND total_equity > 0 AND total_assets < total_equity)
   OR total_assets IS NULL OR total_equity IS NULL OR revenue IS NULL OR net_income IS NULL
