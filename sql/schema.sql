-- Star schema (Online Retail II)
-- Source: stg_transactions view (from clean parquet)

DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS fact_returns;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_product;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_country;

CREATE TABLE dim_country AS
SELECT DISTINCT
  CAST(Country AS VARCHAR) AS country
FROM stg_transactions
WHERE country IS NOT NULL
  AND TRIM(country) <> '';

CREATE TABLE dim_product AS
SELECT DISTINCT
  CAST(StockCode AS VARCHAR) AS stock_code,
  CAST(Description AS VARCHAR) AS description
FROM stg_transactions
WHERE stock_code IS NOT NULL
  AND TRIM(stock_code) <> '';

CREATE TABLE dim_customer AS
WITH base AS (
  SELECT
    CAST("Customer ID" AS BIGINT) AS customer_id,
    CAST(Country AS VARCHAR) AS country,
    CAST(InvoiceDate AS TIMESTAMP) AS invoice_ts
  FROM stg_transactions
  WHERE "Customer ID" IS NOT NULL
)
SELECT
  customer_id,
  MIN(invoice_ts) AS first_purchase_ts,
  MAX(invoice_ts) AS last_purchase_ts,
  -- mode() isn't available everywhere; take most frequent country per customer
  (SELECT country FROM base b2
   WHERE b2.customer_id = b.customer_id AND b2.country IS NOT NULL
   GROUP BY country
   ORDER BY COUNT(*) DESC, country ASC
   LIMIT 1) AS country
FROM base b
GROUP BY customer_id;

CREATE TABLE dim_date AS
WITH d AS (
  SELECT DISTINCT CAST(InvoiceDate AS DATE) AS d
  FROM stg_transactions
  WHERE InvoiceDate IS NOT NULL
)
SELECT
  CAST(STRFTIME(d, '%Y%m%d') AS INTEGER) AS date_key,
  d AS date,
  EXTRACT(year FROM d) AS year,
  EXTRACT(month FROM d) AS month,
  EXTRACT(day FROM d) AS day,
  EXTRACT(dow FROM d) AS day_of_week,
  EXTRACT(week FROM d) AS week_of_year,
  EXTRACT(quarter FROM d) AS quarter
FROM d;

CREATE TABLE fact_sales AS
SELECT
  CAST(Invoice AS VARCHAR) AS invoice_no,
  CAST(InvoiceDate AS TIMESTAMP) AS invoice_ts,
  CAST(STRFTIME(CAST(InvoiceDate AS DATE), '%Y%m%d') AS INTEGER) AS date_key,
  CAST(StockCode AS VARCHAR) AS stock_code,
  CAST("Customer ID" AS BIGINT) AS customer_id,
  CAST(Country AS VARCHAR) AS country,
  CAST(Quantity AS DOUBLE) AS quantity,
  CAST(Price AS DOUBLE) AS unit_price,
  CAST(line_revenue AS DOUBLE) AS line_revenue
FROM stg_transactions
WHERE is_cancellation = FALSE;

CREATE TABLE fact_returns AS
SELECT
  CAST(Invoice AS VARCHAR) AS invoice_no,
  CAST(InvoiceDate AS TIMESTAMP) AS invoice_ts,
  CAST(STRFTIME(CAST(InvoiceDate AS DATE), '%Y%m%d') AS INTEGER) AS date_key,
  CAST(StockCode AS VARCHAR) AS stock_code,
  CAST("Customer ID" AS BIGINT) AS customer_id,
  CAST(Country AS VARCHAR) AS country,
  CAST(Quantity AS DOUBLE) AS quantity,
  CAST(Price AS DOUBLE) AS unit_price,
  CAST(line_revenue AS DOUBLE) AS line_revenue
FROM stg_transactions
WHERE is_cancellation = TRUE;
