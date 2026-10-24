from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Insights:
    asof_date: date
    date_min: date
    date_max: date
    revenue: float
    orders: int
    customers: int
    cancellations_invoices: int
    return_rate_revenue: float
    top_country: str
    top_country_revenue: float
    peak_week: str
    peak_week_revenue: float
    peak_month: str
    peak_month_revenue: float
    top_product: str
    top_product_revenue: float
    abc_a_share: float
    top_pair: str
    top_pair_orders: int
    biggest_cohort: str
    biggest_cohort_size: int
    month1_retention: float | None
    champions_pct: float | None
    high_risk_customers: int | None
    revenue_at_risk: float | None
    avg_clv_6m: float | None
    forecast_wape_model: float | None


def _read_metrics(repo_root: Path) -> dict:
    path = repo_root / "reports" / "metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compute(repo_root: Path) -> Insights:
    powerbi = repo_root / "data" / "powerbi"
    if not powerbi.exists():
        raise FileNotFoundError(
            f"Missing {powerbi}. Run `python -m retailpulse.warehouse build` first."
        )

    con = duckdb.connect()
    try:
        con.execute("PRAGMA threads=4;")
        fact_sales = str(powerbi / "fact_sales.parquet")
        fact_returns = str(powerbi / "fact_returns.parquet")
        dim_product = str(powerbi / "dim_product.parquet")
        mart_abc = str(powerbi / "mart_product_abc.parquet")
        mart_pairs = str(powerbi / "mart_basket_pairs.parquet")
        mart_cohort = str(powerbi / "mart_cohort_retention.parquet")
        rfm_seg = str(powerbi / "rfm_segments.parquet")
        churn_scores = str(powerbi / "churn_scores.parquet")
        mart_rfm = str(powerbi / "mart_customer_rfm.parquet")
        clv_scores = str(powerbi / "clv_scores.parquet")

        base = con.execute(
            f"""
            SELECT
              MIN(CAST(invoice_ts AS DATE)) AS date_min,
              MAX(CAST(invoice_ts AS DATE)) AS date_max,
              SUM(line_revenue) AS revenue,
              COUNT(DISTINCT invoice_no) AS orders,
              COUNT(DISTINCT customer_id) AS customers
            FROM read_parquet('{fact_sales}')
            """
        ).fetchone()
        date_min, date_max, revenue, orders, customers = base

        canc = con.execute(
            f"""
            SELECT COUNT(DISTINCT invoice_no)
            FROM read_parquet('{fact_returns}')
            """
        ).fetchone()[0]

        # Return rate as absolute returned revenue / sales revenue
        ret_rev = con.execute(
            f"SELECT ABS(SUM(line_revenue)) FROM read_parquet('{fact_returns}')"
        ).fetchone()[0] or 0.0
        return_rate_revenue = float(ret_rev) / float(revenue) if revenue else 0.0

        top_country, top_country_revenue = con.execute(
            f"""
            SELECT country, SUM(line_revenue) AS rev
            FROM read_parquet('{fact_sales}')
            GROUP BY country
            ORDER BY rev DESC
            LIMIT 1
            """
        ).fetchone()

        peak_week, peak_week_revenue = con.execute(
            f"""
            SELECT
              STRFTIME(DATE_TRUNC('week', invoice_ts), '%Y-%m-%d') AS week_start,
              SUM(line_revenue) AS rev
            FROM read_parquet('{fact_sales}')
            GROUP BY week_start
            ORDER BY rev DESC
            LIMIT 1
            """
        ).fetchone()

        peak_month, peak_month_revenue = con.execute(
            f"""
            SELECT
              STRFTIME(DATE_TRUNC('month', invoice_ts), '%Y-%m') AS ym,
              SUM(line_revenue) AS rev
            FROM read_parquet('{fact_sales}')
            GROUP BY ym
            ORDER BY rev DESC
            LIMIT 1
            """
        ).fetchone()

        top_product, top_product_revenue = con.execute(
            f"""
            SELECT
              COALESCE(p.description, s.stock_code) AS product,
              SUM(s.line_revenue) AS rev
            FROM read_parquet('{fact_sales}') s
            LEFT JOIN (
              SELECT stock_code,
                COALESCE(
                  MAX(description) FILTER (WHERE description = UPPER(description)),
                  MAX(description)
                ) AS description
              FROM read_parquet('{dim_product}')
              GROUP BY stock_code
            ) p
              ON s.stock_code = p.stock_code
            GROUP BY product
            ORDER BY rev DESC
            LIMIT 1
            """
        ).fetchone()

        abc_a_share = con.execute(
            f"""
            SELECT
              SUM(CASE WHEN abc_class = 'A' THEN revenue ELSE 0 END)::DOUBLE
              / NULLIF(SUM(revenue)::DOUBLE, 0)
            FROM read_parquet('{mart_abc}')
            """
        ).fetchone()[0]

        top_pair_a, top_pair_b, top_pair_orders = con.execute(
            f"""
            SELECT product_a, product_b, pair_orders
            FROM read_parquet('{mart_pairs}')
            ORDER BY pair_orders DESC, product_a, product_b
            LIMIT 1
            """
        ).fetchone()
        top_pair = f"{top_pair_a} + {top_pair_b}"

        biggest_cohort, biggest_cohort_size = con.execute(
            f"""
            WITH c0 AS (
              SELECT cohort_month, active_customers
              FROM read_parquet('{mart_cohort}')
              WHERE cohort_age_months = 0
            )
            SELECT STRFTIME(cohort_month, '%Y-%m') AS cohort_month, active_customers
            FROM c0
            ORDER BY active_customers DESC, cohort_month
            LIMIT 1
            """
        ).fetchone()

        month1_retention = con.execute(
            f"""
            WITH base AS (
              SELECT cohort_month, cohort_age_months, active_customers
              FROM read_parquet('{mart_cohort}')
            ),
            c0 AS (
              SELECT cohort_month, active_customers AS c0
              FROM base WHERE cohort_age_months = 0
            ),
            c1 AS (
              SELECT cohort_month, active_customers AS c1
              FROM base WHERE cohort_age_months = 1
            )
            SELECT c1.c1::DOUBLE / NULLIF(c0.c0::DOUBLE, 0)
            FROM c0
            JOIN c1 USING (cohort_month)
            WHERE STRFTIME(c0.cohort_month, '%Y-%m') = '{biggest_cohort}'
            """
        ).fetchone()[0]

        champions_pct = None
        if Path(rfm_seg).exists():
            champions_pct = con.execute(
                f"""
                SELECT
                  SUM(CASE WHEN segment = 'Champions' THEN 1 ELSE 0 END)::DOUBLE / COUNT(*)::DOUBLE
                FROM read_parquet('{rfm_seg}')
                """
            ).fetchone()[0]

        high_risk_customers = None
        revenue_at_risk = None
        if Path(churn_scores).exists() and Path(mart_rfm).exists():
            high_risk_customers = con.execute(
                f"""
                SELECT COUNT(*)
                FROM read_parquet('{churn_scores}')
                WHERE churn_proba >= 0.7
                """
            ).fetchone()[0]
            revenue_at_risk = con.execute(
                f"""
                SELECT COALESCE(SUM(r.monetary_revenue), 0.0)
                FROM read_parquet('{churn_scores}') s
                JOIN read_parquet('{mart_rfm}') r
                  ON s.customer_id = r.customer_id
                WHERE s.churn_proba >= 0.7
                """
            ).fetchone()[0]

        avg_clv_6m = None
        if Path(clv_scores).exists():
            avg_clv_6m = con.execute(
                f"SELECT AVG(clv_6m_pred) FROM read_parquet('{clv_scores}')"
            ).fetchone()[0]

        metrics = _read_metrics(repo_root)
        forecast_wape_model = (
            metrics.get("forecast", {}).get("wape_model") if isinstance(metrics, dict) else None
        )
    finally:
        con.close()

    return Insights(
        asof_date=date_max,
        date_min=date_min,
        date_max=date_max,
        revenue=float(revenue),
        orders=int(orders),
        customers=int(customers),
        cancellations_invoices=int(canc),
        return_rate_revenue=float(return_rate_revenue),
        top_country=str(top_country),
        top_country_revenue=float(top_country_revenue),
        peak_week=str(peak_week),
        peak_week_revenue=float(peak_week_revenue),
        peak_month=str(peak_month),
        peak_month_revenue=float(peak_month_revenue),
        top_product=str(top_product),
        top_product_revenue=float(top_product_revenue),
        abc_a_share=float(abc_a_share),
        top_pair=str(top_pair),
        top_pair_orders=int(top_pair_orders),
        biggest_cohort=str(biggest_cohort),
        biggest_cohort_size=int(biggest_cohort_size),
        month1_retention=(float(month1_retention) if month1_retention is not None else None),
        champions_pct=(float(champions_pct) if champions_pct is not None else None),
        high_risk_customers=(int(high_risk_customers) if high_risk_customers is not None else None),
        revenue_at_risk=(float(revenue_at_risk) if revenue_at_risk is not None else None),
        avg_clv_6m=(float(avg_clv_6m) if avg_clv_6m is not None else None),
        forecast_wape_model=(
            float(forecast_wape_model) if forecast_wape_model is not None else None
        ),
    )


def to_markdown(i: Insights) -> str:
    champions = f"{i.champions_pct:.1%}" if i.champions_pct is not None else "n/a"
    high_risk = f"{i.high_risk_customers:,}" if i.high_risk_customers is not None else "n/a"
    at_risk = f"{i.revenue_at_risk:,.0f}" if i.revenue_at_risk is not None else "n/a"
    avg_clv = f"{i.avg_clv_6m:,.0f}" if i.avg_clv_6m is not None else "n/a"
    wape = f"{i.forecast_wape_model:.3f}" if i.forecast_wape_model is not None else "n/a"
    m1 = f"{i.month1_retention:.1%}" if i.month1_retention is not None else "n/a"

    return "\n".join(
        [
            "## Dashboard insight numbers (computed with DuckDB)",
            "",
            f"- **date range**: {i.date_min} to {i.date_max} (as-of {i.asof_date})",
            f"- **revenue**: {i.revenue:,.0f}",
            f"- **orders**: {i.orders:,}",
            f"- **customers**: {i.customers:,}",
            f"- **cancellations (distinct invoices)**: {i.cancellations_invoices:,}",
            f"- **return rate (by revenue)**: {i.return_rate_revenue:.2%}",
            f"- **top country**: {i.top_country} ({i.top_country_revenue:,.0f} revenue)",
            f"- **peak week (by revenue)**: week of {i.peak_week} "
            f"({i.peak_week_revenue:,.0f} revenue)",
            f"- **peak month (by revenue)**: {i.peak_month} ({i.peak_month_revenue:,.0f} revenue)",
            f"- **top product (by revenue)**: {i.top_product} "
            f"({i.top_product_revenue:,.0f} revenue)",
            f"- **ABC A share (by revenue)**: {i.abc_a_share:.1%}",
            f"- **top basket pair (by orders)**: {i.top_pair} ({i.top_pair_orders:,} orders)",
            f"- **biggest cohort (month 0 size)**: {i.biggest_cohort} "
            f"({i.biggest_cohort_size:,} customers)",
            f"- **month-1 retention for biggest cohort**: {m1}",
            f"- **champions share**: {champions}",
            f"- **high churn risk customers (p>=0.7)**: {high_risk}",
            f"- **revenue at risk (sum RFM monetary for p>=0.7)**: {at_risk}",
            f"- **avg predicted CLV (6m)**: {avg_clv}",
            f"- **forecast WAPE (model, from reports/metrics.json)**: {wape}",
            "",
        ]
    )


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    insights = compute(repo_root)
    out = repo_root / "reports" / "insights.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(insights), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

