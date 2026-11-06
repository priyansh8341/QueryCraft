-- Verified SQL workflow: this is an authored example, not model-generated SQL.
WITH totals AS (
  SELECT
    SUM(CASE WHEN EXTRACT(QUARTER FROM order_date)=3 THEN revenue_aed ELSE 0 END) AS q3,
    SUM(CASE WHEN EXTRACT(QUARTER FROM order_date)=4 THEN revenue_aed ELSE 0 END) AS q4
  FROM completed_sales
  WHERE EXTRACT(YEAR FROM order_date)=2025
)
SELECT ROUND(q3,2) AS q3_revenue_aed,
       ROUND(q4,2) AS q4_revenue_aed,
       ROUND(100.0*(q4-q3)/NULLIF(q3,0),2) AS growth_pct
FROM totals;
