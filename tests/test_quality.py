import pandas as pd

from retailpulse.etl.quality import EXPECTED_MAX_DATE, EXPECTED_MIN_DATE, check_quality


def test_quality_finds_null_invoice_negative_price_and_date_out_of_range() -> None:
    df = pd.DataFrame(
        [
            # Null invoice -> fail
            {
                "Invoice": None,
                "StockCode": "85123A",
                "Description": "ITEM",
                "Price": 1.0,
                "InvoiceDate": EXPECTED_MIN_DATE,
            },
            # Negative price (non-adjustment) -> fail
            {
                "Invoice": "536365",
                "StockCode": "85123A",
                "Description": "ITEM",
                "Price": -1.0,
                "InvoiceDate": EXPECTED_MIN_DATE,
            },
            # Date out of range -> fail
            {
                "Invoice": "536366",
                "StockCode": "85123A",
                "Description": "ITEM",
                "Price": 1.0,
                "InvoiceDate": EXPECTED_MAX_DATE.replace(year=2012),
            },
            # Negative price but adjustment -> ok
            {
                "Invoice": "A12345",
                "StockCode": "ADJUST",
                "Description": "Adjustment",
                "Price": -5.0,
                "InvoiceDate": EXPECTED_MIN_DATE,
            },
        ]
    )

    failures = check_quality(df)
    joined = "\n".join(failures)

    assert "null/blank Invoice rows" in joined
    assert "negative Price rows" in joined
    assert "InvoiceDate out of expected range" in joined
