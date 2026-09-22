-- A tracked company with no facts means the load silently produced nothing.
SELECT cik, ticker, n_facts
FROM marts.dim_company
WHERE coalesce(n_facts, 0) = 0
