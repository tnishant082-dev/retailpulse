from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd

log = logging.getLogger(__name__)

# Dataset is commonly described as covering Dec 2009 through Dec 2011.
EXPECTED_MIN_DATE = datetime(2009, 12, 1)
EXPECTED_MAX_DATE = datetime(2011, 12, 10)


def check_quality(df: pd.DataFrame) -> list[str]:
    failures: list[str] = []

    if "Invoice" not in df.columns:
        failures.append("missing column: Invoice")
    else:
        null_invoice = df["Invoice"].isna() | (df["Invoice"].astype("string").str.strip() == "")
        if null_invoice.any():
            failures.append(f"null/blank Invoice rows: {int(null_invoice.sum())}")

    if "Price" not in df.columns:
        failures.append("missing column: Price")
    else:
        price = pd.to_numeric(df["Price"], errors="coerce")
        desc = df.get("Description", pd.Series([""] * len(df))).astype("string")
        stock = df.get("StockCode", pd.Series([""] * len(df))).astype("string")
        invoice = df.get("Invoice", pd.Series([""] * len(df))).astype("string")

        adjustment_mask = (
            desc.fillna("").str.contains("adjust", case=False)
            | stock.fillna("").str.upper().isin({"ADJUST", "ADJUST2"})
            | invoice.fillna("").str.startswith("A")
        )
        bad_price = (price < 0) & (~adjustment_mask)
        if bad_price.any():
            failures.append(f"negative Price rows (non-adjustment): {int(bad_price.sum())}")

    if "InvoiceDate" not in df.columns:
        failures.append("missing column: InvoiceDate")
    else:
        dt = pd.to_datetime(df["InvoiceDate"], errors="coerce")
        null_dt = dt.isna()
        if null_dt.any():
            failures.append(f"null/unparseable InvoiceDate rows: {int(null_dt.sum())}")
        else:
            out_of_range = (dt < EXPECTED_MIN_DATE) | (dt > EXPECTED_MAX_DATE)
            if out_of_range.any():
                failures.append(
                    "InvoiceDate out of expected range "
                    f"[{EXPECTED_MIN_DATE.date()}..{EXPECTED_MAX_DATE.date()}]: "
                    f"{int(out_of_range.sum())}"
                )

    return failures


def run_quality(df: pd.DataFrame) -> list[str]:
    failures = check_quality(df)
    if failures:
        for f in failures:
            log.error("QUALITY FAIL: %s", f)
    else:
        log.info("Quality checks passed.")
    return failures
