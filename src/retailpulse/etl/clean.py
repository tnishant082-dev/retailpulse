from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger(__name__)

SHEET_HINTS = ("2009", "2010", "2011")


def _pick_sheet_names(xlsx: pd.ExcelFile) -> tuple[str, str]:
    sheets = list(xlsx.sheet_names)
    if len(sheets) < 2:
        msg = f"Expected at least 2 sheets, found {len(sheets)}: {sheets}"
        raise ValueError(msg)

    # Typical names in this dataset:
    # - "Year 2009-2010"
    # - "Year 2010-2011"
    by_name = {s.lower(): s for s in sheets}
    candidates = []
    for k in by_name:
        if "2009" in k and "2010" in k:
            candidates.append(by_name[k])
        if "2010" in k and "2011" in k:
            candidates.append(by_name[k])
    if len(candidates) >= 2:
        return candidates[0], candidates[1]

    # Fallback: take first two.
    return sheets[0], sheets[1]


def load_online_retail_xlsx(xlsx_path: Path) -> pd.DataFrame:
    log.info("Reading xlsx: %s", xlsx_path)
    xls = pd.ExcelFile(xlsx_path, engine="openpyxl")
    sheet_a, sheet_b = _pick_sheet_names(xls)
    log.info("Reading sheets: %s, %s", sheet_a, sheet_b)
    df_a = pd.read_excel(xls, sheet_name=sheet_a)
    df_b = pd.read_excel(xls, sheet_name=sheet_b)
    df_a["source_sheet"] = sheet_a
    df_b["source_sheet"] = sheet_b
    return pd.concat([df_a, df_b], ignore_index=True)


def clean_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean Online Retail II transactions.

    Rules:
    - drop rows with no StockCode
    - mark cancellations (Invoice starts with 'C') in a column instead of dropping
    - flag missing Customer ID
    - drop exact duplicates
    - add line_revenue = Quantity * Price
    - parse InvoiceDate
    """
    required = ["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "Customer ID"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        msg = f"Missing required columns: {missing}"
        raise ValueError(msg)

    step0 = len(df)
    log.info("rows start=%d", step0)

    out = df.copy()

    # Normalize a few fields early.
    out["Invoice"] = out["Invoice"].astype("string")
    out["StockCode"] = out["StockCode"].astype("string")
    for col in ("Description", "Country", "source_sheet"):
        if col in out.columns:
            out[col] = out[col].astype("string")

    before = len(out)
    out = out[~out["StockCode"].isna()]
    out = out[out["StockCode"].str.strip() != ""]
    log.info("drop missing StockCode: %d -> %d", before, len(out))

    before = len(out)
    out["is_cancellation"] = out["Invoice"].fillna("").str.startswith("C")
    log.info("mark cancellations (no drop): %d -> %d", before, len(out))

    before = len(out)
    out["missing_customer_id"] = out["Customer ID"].isna()
    log.info("flag missing Customer ID (no drop): %d -> %d", before, len(out))

    before = len(out)
    out = out.drop_duplicates()
    log.info("drop exact duplicates: %d -> %d", before, len(out))

    before = len(out)
    out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")
    bad_dt = int(out["InvoiceDate"].isna().sum())
    log.info("parse InvoiceDate (bad=%d): %d -> %d", bad_dt, before, len(out))

    before = len(out)
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    out["Price"] = pd.to_numeric(out["Price"], errors="coerce")
    out["line_revenue"] = out["Quantity"] * out["Price"]
    log.info("add line_revenue: %d -> %d", before, len(out))

    log.info("rows end=%d", len(out))
    return out


def default_clean_path(repo_root: Path) -> Path:
    return repo_root / "data" / "clean" / "transactions.parquet"


def run_clean(*, xlsx_path: Path, out_path: Path) -> pd.DataFrame:
    df_raw = load_online_retail_xlsx(xlsx_path)
    df_clean = clean_transactions(df_raw)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Writing parquet: %s", out_path)
    df_clean.to_parquet(out_path, index=False)
    return df_clean
