from __future__ import annotations

from datetime import date

import pandas as pd

from retailpulse.models.features import ChurnWindow, churn_label, max_date, rfm_features


def test_rfm_features_only_use_data_up_to_cutoff() -> None:
    tx = pd.DataFrame(
        [
            {"customer_id": 1, "invoice_no": "1", "invoice_date": "2010-01-01", "revenue": 10.0},
            {"customer_id": 1, "invoice_no": "2", "invoice_date": "2010-02-01", "revenue": 20.0},
            {"customer_id": 1, "invoice_no": "3", "invoice_date": "2010-03-01", "revenue": 30.0},
        ]
    )
    out = rfm_features(tx, cutoff=date(2010, 2, 15))
    row = out.loc[out["customer_id"] == 1].iloc[0]
    assert row["frequency_orders"] == 2
    assert row["monetary_revenue"] == 30.0


def test_churn_label_is_based_on_future_window_only() -> None:
    tx = pd.DataFrame(
        [
            {"customer_id": 1, "invoice_date": "2010-01-01"},
            {"customer_id": 1, "invoice_date": "2010-02-15"},
            {"customer_id": 1, "invoice_date": "2010-03-10"},  # future inside horizon
            {"customer_id": 2, "invoice_date": "2010-02-01"},
            {"customer_id": 2, "invoice_date": "2010-10-01"},  # far future outside horizon
        ]
    )
    window = ChurnWindow(cutoff=date(2010, 2, 20), horizon_days=90)
    labels = churn_label(tx, window=window).set_index("customer_id")
    assert labels.loc[1, "churned"] == 0
    assert labels.loc[2, "churned"] == 1


def test_max_date_extracts_latest_date() -> None:
    df = pd.DataFrame({"d": ["2010-01-01", "2010-02-01"]})
    assert max_date(df, date_col="d") == date(2010, 2, 1)

