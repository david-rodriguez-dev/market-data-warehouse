-- One row per company with coverage stats, so a consumer can tell at a
-- glance how much history sits behind each ticker.
SELECT
    c.cik,
    c.ticker,
    c.company_name,
    f.first_filed,
    f.last_filed,
    f.n_facts,
    f.n_tags,
    c.loaded_at
FROM staging.stg_companies AS c
LEFT JOIN (
    SELECT
        cik,
        min(filed)          AS first_filed,
        max(filed)          AS last_filed,
        count(*)            AS n_facts,
        count(DISTINCT tag) AS n_tags
    FROM staging.stg_company_facts
    GROUP BY cik
) AS f USING (cik)
