from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import duckdb
import mlflow
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from retailpulse.models.features import ChurnWindow, churn_label, rfm_features

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChurnArtifacts:
    scores_path: Path
    metrics: dict[str, float]


def _load_sales_lines(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    # Build a lean line-level table for features/labels.
    return con.execute(
        """
        SELECT
          customer_id,
          invoice_no,
          invoice_ts::DATE AS invoice_date,
          stock_code,
          quantity,
          line_revenue AS revenue
        FROM fact_sales
        WHERE customer_id IS NOT NULL
        """
    ).df()


def _precision_at_top_k(y_true: pd.Series, y_score: pd.Series, top_frac: float = 0.10) -> float:
    n = len(y_true)
    if n == 0:
        return float("nan")
    k = max(1, int(round(n * top_frac)))
    idx = y_score.sort_values(ascending=False).head(k).index
    return float(y_true.loc[idx].mean())


def _fit_and_eval(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> dict:
    num_cols = [c for c in X_train.columns if c not in ("customer_id", "cutoff_date")]

    pre = ColumnTransformer(
        [("num", StandardScaler(), num_cols)],
        remainder="drop",
    )

    lr = Pipeline(
        [
            ("pre", pre),
            ("model", LogisticRegression(max_iter=2000, class_weight="balanced")),
        ]
    )
    gbdt = Pipeline(
        [
            ("pre", pre),
            ("model", HistGradientBoostingClassifier(max_depth=6, learning_rate=0.05)),
        ]
    )

    lr.fit(X_train, y_train)
    gbdt.fit(X_train, y_train)

    lr_p = pd.Series(lr.predict_proba(X_test)[:, 1], index=X_test.index)
    gb_p = pd.Series(gbdt.predict_proba(X_test)[:, 1], index=X_test.index)

    metrics = {
        "roc_auc_logreg": float(roc_auc_score(y_test, lr_p)),
        "pr_auc_logreg": float(average_precision_score(y_test, lr_p)),
        "precision_at_top10_logreg": _precision_at_top_k(y_test, lr_p, 0.10),
        "roc_auc_gbdt": float(roc_auc_score(y_test, gb_p)),
        "pr_auc_gbdt": float(average_precision_score(y_test, gb_p)),
        "precision_at_top10_gbdt": _precision_at_top_k(y_test, gb_p, 0.10),
    }
    return {"metrics": metrics, "best_proba": gb_p, "best_model": "gbdt"}


def run_churn(
    *,
    warehouse_db: Path,
    out_scores: Path,
    tracking_db: Path,
) -> ChurnArtifacts:
    con = duckdb.connect(database=str(warehouse_db), read_only=True)
    try:
        tx = _load_sales_lines(con)
    finally:
        con.close()

    max_dt = pd.to_datetime(tx["invoice_date"]).max().date()
    test_cutoff = max_dt - timedelta(days=90)
    train_cutoff = max_dt - timedelta(days=180)

    train_X = rfm_features(tx, cutoff=train_cutoff)
    train_y = churn_label(tx, window=ChurnWindow(cutoff=train_cutoff, horizon_days=90))[
        ["customer_id", "churned"]
    ]
    test_X = rfm_features(tx, cutoff=test_cutoff)
    test_y = churn_label(tx, window=ChurnWindow(cutoff=test_cutoff, horizon_days=90))[
        ["customer_id", "churned"]
    ]

    train = train_X.merge(train_y, on=["customer_id"], how="inner")
    test = test_X.merge(test_y, on=["customer_id"], how="inner")

    X_train = train.drop(columns=["churned"])
    y_train = train["churned"]
    X_test = test.drop(columns=["churned"])
    y_test = test["churned"]

    tracking_uri = f"sqlite:///{str(tracking_db.resolve()).replace('\\', '/')}"
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment("churn")
    with mlflow.start_run(run_name=f"cutoff_{test_cutoff}"):
        result = _fit_and_eval(X_train, y_train, X_test, y_test)
        for k, v in result["metrics"].items():
            mlflow.log_metric(k, float(v))
        mlflow.log_param("train_cutoff", str(train_cutoff))
        mlflow.log_param("test_cutoff", str(test_cutoff))
        mlflow.log_param("label_horizon_days", 90)
        mlflow.log_param("best_model", result["best_model"])

    out_scores.parent.mkdir(parents=True, exist_ok=True)
    scores = pd.DataFrame(
        {
            "customer_id": test["customer_id"],
            "cutoff_date": test["cutoff_date"],
            "churned": y_test,
            "churn_proba": result["best_proba"].values,
        }
    )
    scores.to_parquet(out_scores, index=False)
    return ChurnArtifacts(scores_path=out_scores, metrics=result["metrics"])


def write_metrics_json(path: Path, metrics: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, sort_keys=True), encoding="utf-8")
