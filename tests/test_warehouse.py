from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from retailpulse.warehouse.build import build_warehouse, export_powerbi


def _write_clean_parquet(path: Path) -> None:
    df = pd.DataFrame(
        [
            # Sale
            {
                "Invoice": "1",
                "StockCode": "A",
                "Description": "A",
                "Quantity": 2,
                "InvoiceDate": "2010-01-01 10:00:00",
                "Price": 1.5,
                "Customer ID": 10.0,
                "Country": "UK",
                "is_cancellation": False,
                "line_revenue": 3.0,
            },
            # Another item in same order
            {
                "Invoice": "1",
                "StockCode": "B",
                "Description": "B",
                "Quantity": 1,
                "InvoiceDate": "2010-01-01 10:00:00",
                "Price": 2.0,
                "Customer ID": 10.0,
                "Country": "UK",
                "is_cancellation": False,
                "line_revenue": 2.0,
            },
            # Cancellation / return
            {
                "Invoice": "C2",
                "StockCode": "A",
                "Description": "A",
                "Quantity": -1,
                "InvoiceDate": "2010-01-02 10:00:00",
                "Price": 1.5,
                "Customer ID": 10.0,
                "Country": "UK",
                "is_cancellation": True,
                "line_revenue": -1.5,
            },
            # Sale w/ missing customer id (kept in clean, excluded from dim_customer)
            {
                "Invoice": "3",
                "StockCode": "C",
                "Description": "C",
                "Quantity": 1,
                "InvoiceDate": "2010-01-03 10:00:00",
                "Price": 5.0,
                "Customer ID": float("nan"),
                "Country": "FR",
                "is_cancellation": False,
                "line_revenue": 5.0,
            },
        ]
    )
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def test_warehouse_reconciles_counts_and_unique_dim_keys(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "sql").mkdir(parents=True, exist_ok=True)
    (repo_root / "sql" / "schema.sql").write_text(
        (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo_root / "sql" / "marts.sql").write_text(
        (Path(__file__).resolve().parents[1] / "sql" / "marts.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    clean_parquet = repo_root / "data" / "clean" / "transactions.parquet"
    _write_clean_parquet(clean_parquet)

    db_path = repo_root / "warehouse" / "retailpulse.duckdb"
    build_warehouse(repo_root=repo_root, db_path=db_path, clean_parquet=clean_parquet)

    con = duckdb.connect(database=str(db_path), read_only=True)
    try:
        clean_rows = con.execute("SELECT COUNT(*) FROM stg_transactions;").fetchone()[0]
        sales_rows = con.execute("SELECT COUNT(*) FROM fact_sales;").fetchone()[0]
        return_rows = con.execute("SELECT COUNT(*) FROM fact_returns;").fetchone()[0]
        assert sales_rows + return_rows == clean_rows

        # dim keys should be unique by design (natural keys)
        assert (
            con.execute(
                "SELECT COUNT(*) = COUNT(DISTINCT stock_code) FROM dim_product;"
            ).fetchone()[0]
            is True
        )
        assert (
            con.execute(
                "SELECT COUNT(*) = COUNT(DISTINCT country) FROM dim_country;"
            ).fetchone()[0]
            is True
        )
        assert (
            con.execute(
                "SELECT COUNT(*) = COUNT(DISTINCT customer_id) FROM dim_customer;"
            ).fetchone()[0]
            is True
        )
        assert (
            con.execute(
                "SELECT COUNT(*) = COUNT(DISTINCT date_key) FROM dim_date;"
            ).fetchone()[0]
            is True
        )
    finally:
        con.close()


def test_export_powerbi_writes_parquet(tmp_path: Path) -> None:
    repo_root = tmp_path
    (repo_root / "sql").mkdir(parents=True, exist_ok=True)
    (repo_root / "sql" / "schema.sql").write_text(
        (Path(__file__).resolve().parents[1] / "sql" / "schema.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (repo_root / "sql" / "marts.sql").write_text(
        (Path(__file__).resolve().parents[1] / "sql" / "marts.sql").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    clean_parquet = repo_root / "data" / "clean" / "transactions.parquet"
    _write_clean_parquet(clean_parquet)
    db_path = repo_root / "warehouse" / "retailpulse.duckdb"
    build_warehouse(repo_root=repo_root, db_path=db_path, clean_parquet=clean_parquet)

    out_dir = repo_root / "data" / "powerbi"
    written = export_powerbi(repo_root=repo_root, db_path=db_path, out_dir=out_dir)
    assert written
    assert all(p.exists() for p in written)
