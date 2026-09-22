-- A duration fact must start before it ends. (Filing-before-period-end is
-- NOT asserted here: EDGAR legitimately carries forward-looking amounts such
-- as remaining buyback authorisations. That check belongs to the annual model,
-- where every fact is a reported statement figure. See test 12.)
SELECT cik, tag, period_start, period_end, filed
FROM staging.stg_company_facts
WHERE period_start IS NOT NULL
  AND period_start >= period_end
