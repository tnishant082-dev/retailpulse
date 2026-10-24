import pandas as pd

from retailpulse.etl.clean import clean_transactions


def test_clean_rules_drop_missing_stockcode_and_keep_cancellations_and_dedup() -> None:
    df = pd.DataFrame(
        [
            {
                "Invoice": "536365",
                "StockCode": "85123A",
                "Description": "WHITE HANGING HEART T-LIGHT HOLDER",
                "Quantity": 6,
                "InvoiceDate": "2009-12-01 08:26:00",
                "Price": 2.55,
                "Customer ID": 17850.0,
                "Country": "United Kingdom",
            },
            # Duplicate of the first row (exact)
            {
                "Invoice": "536365",
                "StockCode": "85123A",
                "Description": "WHITE HANGING HEART T-LIGHT HOLDER",
                "Quantity": 6,
                "InvoiceDate": "2009-12-01 08:26:00",
                "Price": 2.55,
                "Customer ID": 17850.0,
                "Country": "United Kingdom",
            },
            # Missing StockCode -> dropped
            {
                "Invoice": "536366",
                "StockCode": None,
                "Description": "SOME ITEM",
                "Quantity": 1,
                "InvoiceDate": "2009-12-01 08:28:00",
                "Price": 1.0,
                "Customer ID": 13047.0,
                "Country": "United Kingdom",
            },
            # Cancellation should be retained but flagged
            {
                "Invoice": "C536367",
                "StockCode": "POST",
                "Description": "POSTAGE",
                "Quantity": -1,
                "InvoiceDate": "2009-12-01 08:34:00",
                "Price": 18.0,
                "Customer ID": float("nan"),
                "Country": "United Kingdom",
            },
        ]
    )

    out = clean_transactions(df)

    # Start 4 rows -> drop missing StockCode (1) -> 3 -> drop duplicates (1) -> 2
    assert len(out) == 2

    canc = out.loc[out["Invoice"] == "C536367"].iloc[0]
    assert bool(canc["is_cancellation"]) is True
    assert bool(canc["missing_customer_id"]) is True

    non_canc = out.loc[out["Invoice"] == "536365"].iloc[0]
    assert bool(non_canc["is_cancellation"]) is False
    assert bool(non_canc["missing_customer_id"]) is False
    assert non_canc["line_revenue"] == 6 * 2.55
    assert pd.api.types.is_datetime64_any_dtype(out["InvoiceDate"])

