-- One row per tracked company. Thin by design: raw.companies is already
-- clean, this view exists so marts never reference the raw schema directly.
SELECT
    cik,
    ticker,
    company_name,
    loaded_at
FROM raw.companies
