-- Every staged fact must identify its company, concept, period, value and filing.
SELECT cik, tag, period_end, filed, accession_number
FROM staging.stg_company_facts
WHERE cik IS NULL
   OR tag IS NULL
   OR period_end IS NULL
   OR value IS NULL
   OR filed IS NULL
   OR accession_number IS NULL
