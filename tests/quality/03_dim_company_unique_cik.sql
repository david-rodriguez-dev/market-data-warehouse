SELECT cik, count(*) AS n
FROM marts.dim_company
GROUP BY cik
HAVING count(*) > 1
