from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field
from starlette.responses import Response

from retailpulse.copilot.guardrails import validate_sql
from retailpulse.copilot.llm import generate_sql
from retailpulse.copilot.templates import template_sql

ASK_COUNT = Counter("retailpulse_ask_requests_total", "Total /ask requests", ["mode"])
ASK_LATENCY = Histogram("retailpulse_ask_latency_seconds", "Latency for /ask", ["mode"])


DEFAULT_TABLES: set[str] = {
    "dim_country",
    "dim_customer",
    "dim_date",
    "dim_product",
    "fact_sales",
    "fact_returns",
    "mart_customer_rfm",
    "mart_monthly_kpis",
    "mart_cohort_retention",
    "mart_product_abc",
    "mart_basket_pairs",
    "stg_transactions",
}


class AskRequest(BaseModel):
    question: str = Field(min_length=1)
    limit: int | None = Field(default=None, ge=1, le=500)


class AskResponse(BaseModel):
    sql: str
    rows: list[dict[str, Any]]
    answer: str
    used_fallback: bool


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def default_warehouse_db() -> Path:
    return _repo_root() / "warehouse" / "retailpulse.duckdb"


def create_app(
    *,
    warehouse_db: Path | None = None,
    known_tables: set[str] | None = None,
) -> FastAPI:
    app = FastAPI(title="RetailPulse Copilot", version="0.1.0")
    db = warehouse_db or default_warehouse_db()
    tables = known_tables or DEFAULT_TABLES

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/ask", response_model=AskResponse)
    def ask(req: AskRequest) -> AskResponse:
        t0 = time.time()
        fallback = False

        sql = generate_sql(req.question, known_tables=tables)
        mode = "llm"
        if sql is None:
            mode = "offline"
            fallback = True
            sql = template_sql(req.question)
            if sql is None:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No LLM configured (set LLM_BASE_URL/LLM_API_KEY/LLM_MODEL) "
                        "and no offline template matched."
                    ),
                )

        limit = req.limit or 100
        guard = validate_sql(sql, known_tables=tables, default_limit=limit, max_limit=500)
        if not guard.ok or guard.sql is None:
            raise HTTPException(status_code=400, detail=guard.reason or "sql rejected")

        con = duckdb.connect(database=str(db), read_only=True)
        try:
            df = con.execute(guard.sql).df()
        finally:
            con.close()

        rows = df.to_dict(orient="records")
        if fallback:
            answer = f"(offline templates) returned {len(rows)} rows"
        else:
            answer = f"returned {len(rows)} rows"

        ASK_COUNT.labels(mode=mode).inc()
        ASK_LATENCY.labels(mode=mode).observe(time.time() - t0)
        return AskResponse(sql=guard.sql, rows=rows, answer=answer, used_fallback=fallback)

    return app


app = create_app()
