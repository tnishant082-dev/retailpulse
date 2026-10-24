-- Marts for analysis / Power BI

DROP TABLE IF EXISTS mart_customer_rfm;
DROP TABLE IF EXISTS mart_monthly_kpis;
DROP TABLE IF EXISTS mart_cohort_retention;
DROP TABLE IF EXISTS mart_product_abc;
DROP TABLE IF EXISTS mart_basket_pairs;

CREATE TABLE mart_customer_rfm AS
WITH sales AS (
  SELECT * FROM fact_sales WHERE customer_id IS NOT NULL
),
max_dt AS (SELECT MAX(invoice_ts)::DATE AS asof_date FROM sales)
SELECT
  customer_id,
  (SELECT asof_date FROM max_dt) AS asof_date,
  DATE_DIFF('day', MAX(invoice_ts)::DATE, (SELECT asof_date FROM max_dt)) AS recency_days,
  COUNT(DISTINCT invoice_no) AS frequency_orders,
  SUM(line_revenue) AS monetary_revenue
FROM sales
GROUP BY customer_id;

CREATE TABLE mart_monthly_kpis AS
WITH sales AS (
  SELECT
    DATE_TRUNC('month', invoice_ts)::DATE AS month,
    invoice_no,
    customer_id,
    quantity,
    line_revenue
  FROM fact_sales
)
SELECT
  month,
  SUM(line_revenue) AS revenue,
  SUM(quantity) AS units,
  COUNT(DISTINCT invoice_no) AS orders,
  COUNT(DISTINCT customer_id) AS customers,
  CASE WHEN COUNT(DISTINCT invoice_no) = 0 THEN NULL
       ELSE SUM(line_revenue) / COUNT(DISTINCT invoice_no) END AS aov
FROM sales
GROUP BY month;

CREATE TABLE mart_cohort_retention AS
WITH sales AS (
  SELECT customer_id, invoice_ts::DATE AS d
  FROM fact_sales
  WHERE customer_id IS NOT NULL
),
firsts AS (
  SELECT customer_id, DATE_TRUNC('month', MIN(d))::DATE AS cohort_month
  FROM sales
  GROUP BY customer_id
),
activity AS (
  SELECT
    f.cohort_month,
    DATE_TRUNC('month', s.d)::DATE AS activity_month,
    s.customer_id
  FROM sales s
  JOIN firsts f USING (customer_id)
  GROUP BY f.cohort_month, activity_month, s.customer_id
)
SELECT
  cohort_month,
  activity_month,
  DATE_DIFF('month', cohort_month, activity_month) AS cohort_age_months,
  COUNT(DISTINCT customer_id) AS active_customers
FROM activity
GROUP BY cohort_month, activity_month;

CREATE TABLE mart_product_abc AS
WITH prod AS (
  SELECT stock_code, SUM(line_revenue) AS revenue
  FROM fact_sales
  GROUP BY stock_code
),
tot AS (SELECT SUM(revenue) AS total_revenue FROM prod),
ranked AS (
  SELECT
    stock_code,
    revenue,
    revenue / NULLIF((SELECT total_revenue FROM tot), 0) AS revenue_share,
    SUM(revenue) OVER (ORDER BY revenue DESC) / NULLIF((SELECT total_revenue FROM tot), 0) AS cum_share
  FROM prod
)
SELECT
  stock_code,
  revenue,
  revenue_share,
  cum_share,
  CASE
    WHEN cum_share <= 0.80 THEN 'A'
    WHEN cum_share <= 0.95 THEN 'B'
    ELSE 'C'
  END AS abc_class
FROM ranked;

CREATE TABLE mart_basket_pairs AS
WITH items AS (
  SELECT invoice_no, stock_code
  FROM fact_sales
  WHERE stock_code IS NOT NULL
  GROUP BY invoice_no, stock_code
),
pairs AS (
  SELECT
    a.stock_code AS product_a,
    b.stock_code AS product_b,
    COUNT(*) AS pair_orders
  FROM items a
  JOIN items b
    ON a.invoice_no = b.invoice_no
   AND a.stock_code < b.stock_code
  GROUP BY product_a, product_b
)
SELECT *
FROM pairs
ORDER BY pair_orders DESC, product_a, product_b
LIMIT 2000;
