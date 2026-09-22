-- Loose bounds: a margin outside -300%..+100% is a tag mapping error, not a business.
SELECT ticker, fiscal_year, net_margin, operating_margin
FROM marts.mart_fundamental_metrics
WHERE net_margin       NOT BETWEEN -3 AND 1
   OR operating_margin NOT BETWEEN -3 AND 1
