## RetailPulse (Milestone 1: ingest + clean)

### Setup

- Create a venv (uses the existing Anaconda Python you specified):

```bash
C:\Users\nishant\anaconda3\python.exe -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

### M1: Run ETL (download -> clean -> quality)

```bash
.\.venv\Scripts\python -m retailpulse.etl run
```

Outputs:
- `data/raw/online+retail+ii.zip` and the extracted `.xlsx`
- `data/clean/transactions.parquet`

### M2: Build warehouse + marts + Power BI exports

```bash
.\.venv\Scripts\python -m retailpulse.warehouse build
```

Outputs:
- `warehouse/retailpulse.duckdb`
- `data/powerbi/*.parquet` (exported tables)

### M3: Train + score models (mlflow + Power BI outputs)

```bash
.\.venv\Scripts\python -m retailpulse.models run
```

Outputs:
- `mlruns.db` (mlflow sqlite tracking db)
- `reports/metrics.json`
- `data/powerbi/churn_scores.parquet`, `clv_scores.parquet`, `forecast.parquet`, `rfm_segments.parquet`

### M4: Run copilot API (FastAPI)

```bash
.\.venv\Scripts\python -m retailpulse.copilot serve --host 127.0.0.1 --port 8000
```

LLM configuration (OpenAI-compatible):
- `LLM_BASE_URL`
- `LLM_API_KEY`
- `LLM_MODEL`

If unset, `POST /ask` falls back to offline templates (and says so in the response).

### Real model metrics (from `reports/metrics.json`)

```json
{
  "churn": {
    "pr_auc_gbdt": 0.8042768157874725,
    "pr_auc_logreg": 0.8163562892227424,
    "precision_at_top10_gbdt": 0.8901515151515151,
    "precision_at_top10_logreg": 0.9204545454545454,
    "roc_auc_gbdt": 0.7858496227484081,
    "roc_auc_logreg": 0.7911623176685378
  },
  "clv": {
    "mae": 619.7199620253165,
    "rmse": 3849.9463155816625
  },
  "forecast": {
    "mape_baseline": 6.791016200835314,
    "mape_model": 2.4847302910506435,
    "wape_baseline": 0.9959638605887903,
    "wape_model": 0.7148990147810437
  }
}
```
