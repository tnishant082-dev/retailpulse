from __future__ import annotations

import pandas as pd


def rfm_segments(rfm: pd.DataFrame) -> pd.DataFrame:
    """
    Segment customers with simple quantile scoring.

    Input must include: customer_id, recency_days, frequency_orders, monetary_revenue.
    """
    df = rfm.copy()
    for c in ("recency_days", "frequency_orders", "monetary_revenue"):
        if c not in df.columns:
            raise ValueError(f"Missing column: {c}")

    # Lower recency is better; higher frequency/monetary is better.
    df["r_score"] = pd.qcut(df["recency_days"], 5, labels=[5, 4, 3, 2, 1]).astype(int)
    df["f_score"] = (
        pd.qcut(
            df["frequency_orders"].rank(method="first"),
            5,
            labels=[1, 2, 3, 4, 5],
        )
        .astype(int)
    )
    df["m_score"] = (
        pd.qcut(
            df["monetary_revenue"].rank(method="first"),
            5,
            labels=[1, 2, 3, 4, 5],
        )
        .astype(int)
    )
    df["rfm_score"] = df["r_score"] * 100 + df["f_score"] * 10 + df["m_score"]

    def segment(row: pd.Series) -> str:
        r, f, m = int(row["r_score"]), int(row["f_score"]), int(row["m_score"])
        if r >= 4 and f >= 4 and m >= 4:
            return "Champions"
        if r >= 3 and f >= 4:
            return "Loyal"
        if r >= 4 and f <= 2:
            return "New"
        if r <= 2 and f >= 3:
            return "At Risk"
        if r == 1 and f <= 2:
            return "Lost"
        return "Regular"

    df["segment"] = df.apply(segment, axis=1)
    return df
