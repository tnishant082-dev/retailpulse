# AGENTS.md

Rules for anyone (human or tool) changing this repo.

## Project
RetailPulse: churn, CLV and demand forecasting for a UK online gift wholesaler,
on the public UCI Online Retail II dataset. Output is a DuckDB warehouse, ML models,
an "ask your data" API and a Power BI dashboard (12+ pages).

## Layout
- `src/retailpulse/etl`      raw -> clean -> marts (DuckDB)
- `src/retailpulse/models`   rfm, churn, clv, forecast
- `src/retailpulse/copilot`  text-to-sql + docs search, FastAPI
- `sql/`                     star schema and mart sql
- `dashboard/`               Power BI project (pbip)
- `tests/`                   pytest

## Rules
- Small changes. One milestone per branch, one PR.
- Every number in README must come from a real run. No made up metrics.
- Keep files under ~300 lines. Plain names, short docstrings.
- Add a test for every new function that has logic.
- Don't commit data files over 50 MB or any secrets / .env.
- No new dependency without a reason in the PR.
- Python 3.13, run `pytest -q` and `ruff check .` before saying done.
- Stop and ask the human before deleting files or changing the schema.
