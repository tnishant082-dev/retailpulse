from __future__ import annotations

import logging
from pathlib import Path

import duckdb

log = logging.getLogger(__name__)


def _read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sql_literal(value: str) -> str:
    # DuckDB uses standard SQL string literals with single-quote escaping.
    return "'" + value.replace("'", "''") + "'"


def sql_dir(repo_root: Path) -> Path:
    return repo_root / "sql"


def warehouse_path(repo_root: Path) -> Path:
    return repo_root / "warehouse" / "retailpulse.duckdb"


def clean_path(repo_root: Path) -> Path:
    return repo_root / "data" / "clean" / "transactions.parquet"


def powerbi_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "powerbi"


def build_warehouse(*, repo_root: Path, db_path: Path, clean_parquet: Path) -> None:
    if not clean_parquet.exists():
        msg = f"Missing clean parquet: {clean_parquet}. Run `python -m retailpulse.etl run` first."
        raise FileNotFoundError(msg)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    log.info("Building warehouse: %s", db_path)

    con = duckdb.connect(database=str(db_path))
    try:
        con.execute("PRAGMA threads=4;")
        con.execute("PRAGMA enable_progress_bar=false;")

        parquet = _sql_literal(str(clean_parquet))
        con.execute(
            "CREATE OR REPLACE VIEW stg_transactions AS "
            f"SELECT * FROM read_parquet({parquet});"
        )

        schema_sql = _read_sql(sql_dir(repo_root) / "schema.sql")
        marts_sql = _read_sql(sql_dir(repo_root) / "marts.sql")

        con.execute(schema_sql)
        con.execute(marts_sql)
    finally:
        con.close()


def export_powerbi(*, repo_root: Path, db_path: Path, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=str(db_path), read_only=True)
    try:
        tables = [r[0] for r in con.execute("SHOW TABLES;").fetchall()]
        written: list[Path] = []
        for t in sorted(tables):
            out_path = out_dir / f"{t}.parquet"
            log.info("Exporting %s -> %s", t, out_path)
            con.execute(
                "COPY (SELECT * FROM " + t + ") TO ? (FORMAT PARQUET, OVERWRITE TRUE);",
                [str(out_path)],
            )
            written.append(out_path)
        return written
    finally:
        con.close()


def build_and_export(repo_root: Path) -> None:
    db_path = warehouse_path(repo_root)
    build_warehouse(repo_root=repo_root, db_path=db_path, clean_parquet=clean_path(repo_root))
    export_powerbi(repo_root=repo_root, db_path=db_path, out_dir=powerbi_dir(repo_root))
