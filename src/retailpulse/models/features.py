from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import pandas as pd


@dataclass(frozen=True)
class ChurnWindow:
    cutoff: date
    horizon_days: int = 90

    @property
    def horizon_end(self) -> date:
        return self.cutoff + timedelta(days=self.horizon_days)


def _to_date(ts: pd.Series) -> pd.Series:
    return pd.to_datetime(ts, errors="coerce").dt.date


def rfm_features(
    tx: pd.DataFrame,
    *,
    cutoff: date,
    customer_col: str = "customer_id",
    invoice_col: str = "invoice_no",
    date_col: str = "invoice_date",
    revenue_col: str = "revenue",
    qty_col: str = "quantity",
    product_col: str = "stock_code",
) -> pd.DataFrame:
    """
    Build RFM-style features from transactions up to (and including) cutoff.

    Expects a line-level or invoice-level table; frequency is by distinct invoices.
    """
    df = tx.copy()
    df[date_col] = _to_date(df[date_col])
    df = df[df[date_col].notna()]
    df = df[df[date_col] <= cutoff]

    grp = df.groupby(customer_col, dropna=False)
    last_date = grp[date_col].max()

    out = pd.DataFrame({customer_col: last_date.index})
    last_dt = pd.to_datetime(last_date).reset_index(drop=True)
    out["recency_days"] = (pd.Timestamp(cutoff) - last_dt).dt.days
    out["frequency_orders"] = grp[invoice_col].nunique().values
    out["monetary_revenue"] = grp[revenue_col].sum().values

    if qty_col in df.columns:
        out["units"] = grp[qty_col].sum().values
    else:
        out["units"] = 0.0

    if product_col in df.columns:
        out["distinct_products"] = grp[product_col].nunique().values
    else:
        out["distinct_products"] = 0

    out["aov"] = out["monetary_revenue"] / out["frequency_orders"].clip(lower=1)
    out["cutoff_date"] = pd.to_datetime(cutoff)

    return out


def churn_label(
    tx: pd.DataFrame,
    *,
    window: ChurnWindow,
    customer_col: str = "customer_id",
    date_col: str = "invoice_date",
) -> pd.DataFrame:
    """
    Label churn at cutoff: churned==1 if no purchase in (cutoff, cutoff+horizon].
    """
    df = tx[[customer_col, date_col]].copy()
    df[date_col] = _to_date(df[date_col])
    df = df[df[date_col].notna()]

    future = df[(df[date_col] > window.cutoff) & (df[date_col] <= window.horizon_end)]
    future_any = future.groupby(customer_col).size().rename("future_purchases").reset_index()

    all_customers = df[df[date_col] <= window.cutoff][[customer_col]].drop_duplicates()
    out = all_customers.merge(future_any, on=customer_col, how="left")
    out["future_purchases"] = out["future_purchases"].fillna(0).astype(int)
    out["churned"] = (out["future_purchases"] == 0).astype(int)
    out["cutoff_date"] = pd.to_datetime(window.cutoff)
    out["horizon_days"] = window.horizon_days
    return out[[customer_col, "churned", "cutoff_date", "horizon_days"]]


def max_date(df: pd.DataFrame, *, date_col: str) -> date:
    d = pd.to_datetime(df[date_col], errors="coerce").max()
    if pd.isna(d):
        msg = "No valid dates found"
        raise ValueError(msg)
    return datetime.fromtimestamp(d.timestamp()).date()
