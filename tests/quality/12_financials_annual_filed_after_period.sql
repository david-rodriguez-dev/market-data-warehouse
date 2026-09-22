-- An annual statement figure cannot be filed before the year it describes ends.
SELECT cik, fiscal_year_end, latest_source_filed
FROM marts.fct_financials_annual
WHERE latest_source_filed < fiscal_year_end
