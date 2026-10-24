from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import duckdb
import mlflow
import numpy as np
import pandas as pd

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForecastArtifacts:
    forecast_path: Path
    metrics: dict[str, float]


def _weekly_units(con: duckdb.DuckDBPyConnection, top_n: int = 50) -> pd.DataFrame:
    top = con.execute(
        """
        WITH prod AS (
          SELECT stock_code, SUM(quantity) AS units
          FROM fact_sales
          WHERE quantity IS NOT NULL
          GROUP BY stock_code
        )
        SELECT stock_code
        FROM prod
        ORDER BY units DESC
        LIMIT ?
        """,
        [top_n],
    ).df()["stock_code"].tolist()

    df = con.execute(
        """
        SELECT
          stock_code,
          DATE_TRUNC('week', invoice_ts)::DATE AS week_start,
          SUM(quantity) AS units
        FROM fact_sales
        WHERE stock_code IN (SELECT * FROM UNNEST(?))
        GROUP BY stock_code, DATE_TRUNC('week', invoice_ts)::DATE
        """,
        [top],
    ).df()
    df["week_start"] = pd.to_datetime(df["week_start"])
    df["units"] = pd.to_numeric(df["units"], errors="coerce").fillna(0.0)
    return df


def _make_features(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.sort_values(["stock_code", "week_start"]).copy()
    for lag in (1, 2, 4, 8, 52):
        df[f"lag_{lag}"] = df.groupby("stock_code")["units"].shift(lag)
    prev = df.groupby("stock_code")["units"].shift(1)
    df["roll4"] = prev.rolling(4).mean().reset_index(level=0, drop=True)
    df["roll8"] = prev.rolling(8).mean().reset_index(level=0, drop=True)
    df["weekofyear"] = df["week_start"].dt.isocalendar().week.astype(int)
    df["year"] = df["week_start"].dt.year
    return df


def _wape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.sum(np.abs(y_true))
    if denom == 0:
        return float("nan")
    return float(np.sum(np.abs(y_true - y_pred)) / denom)


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    denom = np.maximum(np.abs(y_true), 1e-9)
    return float(np.mean(np.abs((y_true - y_pred) / denom)))


def run_forecast(
    *,
    warehouse_db: Path,
    out_forecast: Path,
    tracking_db: Path,
    top_n_products: int = 50,
    test_weeks: int = 8,
) -> ForecastArtifacts:
    con = duckdb.connect(database=str(warehouse_db), read_only=True)
    try:
        weekly = _weekly_units(con, top_n=top_n_products)
    finally:
        con.close()

    feats = _make_features(weekly)
    feats = feats.dropna(subset=["lag_1"]).copy()

    max_week = feats["week_start"].max()
    split_week = max_week - pd.Timedelta(weeks=test_weeks)
    train = feats[feats["week_start"] <= split_week].copy()
    test = feats[feats["week_start"] > split_week].copy()

    # seasonal naive baseline: use lag_52 if available, else lag_1
    test["pred_baseline"] = test["lag_52"].fillna(test["lag_1"]).clip(lower=0.0)

    feature_cols = ["lag_1", "lag_2", "lag_4", "lag_8", "roll4", "roll8", "weekofyear", "year"]
    X_train = train[feature_cols]
    y_train = train["units"]
    X_test = test[feature_cols]
    y_test = test["units"].to_numpy()

    tracking_uri = f"sqlite:///{str(tracking_db.resolve()).replace('\\', '/')}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("forecast")

    try:
        import lightgbm as lgb

        model = lgb.LGBMRegressor(
            n_estimators=500,
            learning_rate=0.05,
            num_leaves=63,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        )
        model.fit(X_train, y_train)
        pred = np.clip(model.predict(X_test), 0.0, None)
        model_name = "lightgbm"
    except Exception as e:  # noqa: BLE001
        log.warning("LightGBM failed, using baseline only. error=%s", e)
        pred = test["pred_baseline"].to_numpy()
        model_name = "baseline_only"

    baseline = test["pred_baseline"].to_numpy()
    metrics = {
        "mape_baseline": _mape(y_test, baseline),
        "wape_baseline": _wape(y_test, baseline),
        "mape_model": _mape(y_test, pred),
        "wape_model": _wape(y_test, pred),
    }

    with mlflow.start_run(run_name="weekly_top50"):
        mlflow.log_param("model", model_name)
        mlflow.log_param("top_n_products", top_n_products)
        mlflow.log_param("test_weeks", test_weeks)
        for k, v in metrics.items():
            mlflow.log_metric(k, float(v))

    out_forecast.parent.mkdir(parents=True, exist_ok=True)
    out = test[["stock_code", "week_start", "units", "pred_baseline"]].copy()
    out["pred_model"] = pred
    out.to_parquet(out_forecast, index=False)
    return ForecastArtifacts(forecast_path=out_forecast, metrics=metrics)


def write_metrics_json(path: Path, metrics: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
