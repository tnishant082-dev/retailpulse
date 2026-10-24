from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import mlflow
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClvArtifacts:
    scores_path: Path
    metrics: dict[str, float]


def _invoice_totals(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return con.execute(
        """
        SELECT
          customer_id,
          invoice_no,
          invoice_ts::DATE AS invoice_date,
          SUM(line_revenue) AS revenue
        FROM fact_sales
        WHERE customer_id IS NOT NULL
        GROUP BY customer_id, invoice_no, invoice_ts::DATE
        """
    ).df()


def run_clv(
    *,
    warehouse_db: Path,
    out_scores: Path,
    tracking_db: Path,
) -> ClvArtifacts:
    con = duckdb.connect(database=str(warehouse_db), read_only=True)
    try:
        tx = _invoice_totals(con)
    finally:
        con.close()

    tx["invoice_date"] = pd.to_datetime(tx["invoice_date"])
    tx["revenue"] = pd.to_numeric(tx["revenue"], errors="coerce").fillna(0.0)
    tx = tx[tx["revenue"] > 0].copy()
    obs_end = tx["invoice_date"].max()
    calib_end = obs_end - pd.Timedelta(days=180)
    holdout_end = obs_end

    tracking_uri = f"sqlite:///{str(tracking_db.resolve()).replace('\\', '/')}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("clv")

    metrics: dict[str, float] = {}
    scores: pd.DataFrame

    try:
        from lifetimes import BetaGeoFitter, GammaGammaFitter
        from lifetimes.utils import summary_data_from_transaction_data

        summary = summary_data_from_transaction_data(
            tx,
            customer_id_col="customer_id",
            datetime_col="invoice_date",
            monetary_value_col="revenue",
            observation_period_end=calib_end,
            freq="D",
        )
        # lifetimes expects monetary_value for repeat customers; fill 0 for singletons
        summary["monetary_value"] = summary["monetary_value"].fillna(0.0)

        bgf = BetaGeoFitter(penalizer_coef=0.01)
        bgf.fit(summary["frequency"], summary["recency"], summary["T"])

        ggf = GammaGammaFitter(penalizer_coef=0.01)
        paid = summary["monetary_value"] > 0
        ggf.fit(summary.loc[paid, "frequency"], summary.loc[paid, "monetary_value"])

        horizon_days = 180
        pred_txn = bgf.conditional_expected_number_of_purchases_up_to_time(
            horizon_days, summary["frequency"], summary["recency"], summary["T"]
        )
        pred_m = ggf.conditional_expected_average_profit(
            summary["frequency"], summary["monetary_value"]
        )
        pred_6m = (pred_txn * pred_m).astype(float)

        actual = (
            tx[(tx["invoice_date"] > calib_end) & (tx["invoice_date"] <= holdout_end)]
            .groupby("customer_id")["revenue"]
            .sum()
        )

        scores = pd.DataFrame(
            {
                "customer_id": summary.index.astype(int),
                "clv_6m_pred": pred_6m.values,
                "calibration_end": calib_end.date().isoformat(),
            }
        )
        scores = scores.merge(
            actual.rename("clv_6m_actual"),
            left_on="customer_id",
            right_index=True,
            how="left",
        )
        scores["clv_6m_actual"] = scores["clv_6m_actual"].fillna(0.0)

        metrics = {
            "mae": float(mean_absolute_error(scores["clv_6m_actual"], scores["clv_6m_pred"])),
            "rmse": float(
                mean_squared_error(scores["clv_6m_actual"], scores["clv_6m_pred"]) ** 0.5
            ),
            "calibration_end_days_before_max": float((obs_end - calib_end).days),
        }
        model_used = "lifetimes_bg_nbd_gamma_gamma"
    except Exception as e:  # noqa: BLE001
        # Fallback: naive baseline (repeat-revenue last 180d)
        log.warning("CLV lifetimes fit failed, using baseline. error=%s", e)
        recent_start = calib_end - pd.Timedelta(days=180)
        recent = tx[(tx["invoice_date"] > recent_start) & (tx["invoice_date"] <= calib_end)]
        pred = recent.groupby("customer_id")["revenue"].sum()
        actual = (
            tx[(tx["invoice_date"] > calib_end) & (tx["invoice_date"] <= holdout_end)]
            .groupby("customer_id")["revenue"]
            .sum()
        )
        customers = (
            tx[tx["invoice_date"] <= calib_end][["customer_id"]]
            .drop_duplicates()
            .sort_values("customer_id")
        )
        scores = customers.merge(
            pred.rename("clv_6m_pred"),
            left_on="customer_id",
            right_index=True,
            how="left",
        )
        scores["clv_6m_pred"] = scores["clv_6m_pred"].fillna(0.0)
        scores = scores.merge(
            actual.rename("clv_6m_actual"),
            left_on="customer_id",
            right_index=True,
            how="left",
        )
        scores["clv_6m_actual"] = scores["clv_6m_actual"].fillna(0.0)
        metrics = {
            "mae": float(mean_absolute_error(scores["clv_6m_actual"], scores["clv_6m_pred"])),
            "rmse": float(
                mean_squared_error(scores["clv_6m_actual"], scores["clv_6m_pred"]) ** 0.5
            ),
        }
        model_used = "baseline_last180d_revenue"

    with mlflow.start_run(run_name="clv_6m"):
        mlflow.log_param("model", model_used)
        mlflow.log_param("calibration_end", calib_end.date().isoformat())
        mlflow.log_param("horizon_days", 180)
        for k, v in metrics.items():
            mlflow.log_metric(k, float(v))

    out_scores.parent.mkdir(parents=True, exist_ok=True)
    scores[["customer_id", "clv_6m_pred"]].to_parquet(out_scores, index=False)
    return ClvArtifacts(scores_path=out_scores, metrics=metrics)


def write_metrics_json(path: Path, metrics: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
