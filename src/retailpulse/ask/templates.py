from __future__ import annotations

import re


def template_sql(question: str) -> str | None:
    q = (question or "").strip().lower()
    if not q:
        return None

    if re.search(r"\b(monthly|per month)\b", q) and re.search(r"\b(revenue|sales)\b", q):
        return "SELECT * FROM mart_monthly_kpis ORDER BY month DESC"

    if re.search(r"\b(top)\b", q) and re.search(r"\b(customers?)\b", q):
        return (
            "SELECT customer_id, monetary_revenue "
            "FROM mart_customer_rfm "
            "ORDER BY monetary_revenue DESC "
            "LIMIT 20"
        )

    if re.search(r"\b(retention|cohort)\b", q):
        return "SELECT * FROM mart_cohort_retention ORDER BY cohort_month, activity_month"

    if re.search(r"\b(abc)\b", q) or re.search(r"\b(top products?)\b", q):
        return "SELECT * FROM mart_product_abc ORDER BY revenue DESC LIMIT 100"

    if re.search(r"\b(pairs?|baskets?)\b", q):
        return "SELECT * FROM mart_basket_pairs ORDER BY pair_orders DESC LIMIT 100"

    return None
