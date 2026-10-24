from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import duckdb

from retailpulse.models.churn import run_churn
from retailpulse.models.clv import run_clv
from retailpulse.models.forecast import run_forecast
from retailpulse.models.rfm import rfm_segments


def _repo_root() -> Path:
    # .../retailpulse/src/retailpulse/models/__main__.py -> .../retailpulse
    return Path(__file__).resolve().parents[3]


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def _warehouse_db(repo_root: Path) -> Path:
    return repo_root / "warehouse" / "retailpulse.duckdb"


def _tracking_db(repo_root: Path) -> Path:
    return repo_root / "mlruns.db"


def _metrics_path(repo_root: Path) -> Path:
    return repo_root / "reports" / "metrics.json"


def _powerbi_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "powerbi"


def cmd_run(_: argparse.Namespace) -> int:
    repo_root = _repo_root()
    warehouse_db = _warehouse_db(repo_root)
    tracking_db = _tracking_db(repo_root)
    powerbi_dir = _powerbi_dir(repo_root)

    powerbi_dir.mkdir(parents=True, exist_ok=True)

    # RFM segments from warehouse mart
    con = duckdb.connect(database=str(warehouse_db), read_only=True)
    try:
        rfm = con.execute(
            """
            SELECT
              customer_id,
              recency_days,
              frequency_orders,
              monetary_revenue
            FROM mart_customer_rfm
            """
        ).df()
    finally:
        con.close()

    seg = rfm_segments(rfm)
    seg_path = powerbi_dir / "rfm_segments.parquet"
    seg.to_parquet(seg_path, index=False)

    churn = run_churn(
        warehouse_db=warehouse_db,
        out_scores=powerbi_dir / "churn_scores.parquet",
        tracking_db=tracking_db,
    )
    clv = run_clv(
        warehouse_db=warehouse_db,
        out_scores=powerbi_dir / "clv_scores.parquet",
        tracking_db=tracking_db,
    )
    fc = run_forecast(
        warehouse_db=warehouse_db,
        out_forecast=powerbi_dir / "forecast.parquet",
        tracking_db=tracking_db,
    )

    metrics = {"churn": churn.metrics, "clv": clv.metrics, "forecast": fc.metrics}
    metrics_path = _metrics_path(repo_root)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(
        json.dumps(metrics, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m retailpulse.models")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="train + score churn/clv/forecast and write artifacts")
    r.set_defaults(func=cmd_run)
    return p


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

