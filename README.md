## RetailPulse (Milestone 1: ingest + clean)

### Setup

- Create a venv (uses the existing Anaconda Python you specified):

```bash
C:\Users\nishant\anaconda3\python.exe -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -e ".[dev]"
```

### Run ETL (download -> clean -> quality)

```bash
.\.venv\Scripts\python -m retailpulse.etl run
```

Outputs:
- `data/raw/online+retail+ii.zip` and the extracted `.xlsx`
- `data/clean/transactions.parquet`
