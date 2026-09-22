-- Ratios, growth and peer ranks on top of the annual statement.
--
-- Growth uses LAG guarded by a year check: if a company is missing a year,
-- "prior" must be NULL rather than silently reaching back two years.
-- Peer ranks are within fiscal year across every tracked company.
WITH base AS (
    SELECT
        c.ticker,
        c.company_name,
        f.*
    FROM marts.fct_financials_annual AS f
    JOIN marts.dim_company AS c USING (cik)
),
lagged AS (
    SELECT
        *,
        CASE WHEN lag(fiscal_year, 1) OVER w = fiscal_year - 1
             THEN lag(revenue, 1) OVER w END       AS revenue_prior,
        CASE WHEN lag(fiscal_year, 3) OVER w = fiscal_year - 3
             THEN lag(revenue, 3) OVER w END       AS revenue_3y_ago,
        CASE WHEN lag(fiscal_year, 1) OVER w = fiscal_year - 1
             THEN lag(net_income, 1) OVER w END    AS net_income_prior,
        CASE WHEN lag(fiscal_year, 1) OVER w = fiscal_year - 1
             THEN lag(total_equity, 1) OVER w END  AS total_equity_prior
    FROM base
    WINDOW w AS (PARTITION BY cik ORDER BY fiscal_year_end)
),
ratios AS (
    SELECT
        ticker,
        company_name,
        cik,
        fiscal_year,
        fiscal_year_end,
        revenue,
        operating_income,
        net_income,
        total_assets,
        total_equity,
        cash,
        long_term_debt,
        operating_cash_flow,
        capex,
        operating_cash_flow - capex                                      AS free_cash_flow,
        net_income       / nullif(revenue, 0)                            AS net_margin,
        operating_income / nullif(revenue, 0)                            AS operating_margin,
        revenue / nullif(revenue_prior, 0) - 1                           AS revenue_growth_yoy,
        power(revenue / nullif(revenue_3y_ago, 0), 1.0 / 3) - 1          AS revenue_cagr_3y,
        net_income / nullif(net_income_prior, 0) - 1                     AS net_income_growth_yoy,
        net_income / nullif((total_equity + total_equity_prior) / 2, 0)  AS return_on_avg_equity,
        total_assets   / nullif(total_equity, 0)                         AS assets_to_equity,
        long_term_debt / nullif(total_equity, 0)                         AS debt_to_equity,
        (operating_cash_flow - capex) / nullif(revenue, 0)               AS fcf_margin,
        n_concepts_reported,
        latest_source_filed
    FROM lagged
)
SELECT
    *,
    percent_rank() OVER (PARTITION BY fiscal_year ORDER BY net_margin)          AS net_margin_peer_pct_rank,
    percent_rank() OVER (PARTITION BY fiscal_year ORDER BY revenue_growth_yoy)  AS revenue_growth_peer_pct_rank,
    count(*)       OVER (PARTITION BY fiscal_year)                              AS n_peers_in_year
FROM ratios
