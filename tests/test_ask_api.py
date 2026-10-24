from __future__ import annotations

from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from retailpulse.ask.app import create_app


def _make_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database=str(path))
    try:
        con.execute(
            """
            CREATE TABLE fact_sales (
              invoice_no VARCHAR,
              customer_id BIGINT,
              line_revenue DOUBLE
            );
            """
        )
        con.execute("INSERT INTO fact_sales VALUES ('1', 1, 10.0), ('2', 2, 20.0);")
        con.execute("CREATE TABLE mart_monthly_kpis (month DATE, revenue DOUBLE);")
        con.execute("INSERT INTO mart_monthly_kpis VALUES ('2010-01-01', 30.0);")
    finally:
        con.close()


def test_ask_rejects_malicious_sql(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "w.duckdb"
    _make_db(db)
    app = create_app(warehouse_db=db, known_tables={"fact_sales", "mart_monthly_kpis"})

    monkeypatch.setattr(
        "retailpulse.ask.app.generate_sql",
        lambda *_args, **_kw: "DROP TABLE fact_sales",
    )
    client = TestClient(app)
    r = client.post("/ask", json={"question": "drop the table"})
    assert r.status_code == 400


def test_ask_offline_template_works_without_llm(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "w.duckdb"
    _make_db(db)
    app = create_app(warehouse_db=db, known_tables={"fact_sales", "mart_monthly_kpis"})

    # No LLM configured -> generate_sql returns None
    monkeypatch.setattr("retailpulse.ask.app.generate_sql", lambda *_args, **_kw: None)
    client = TestClient(app)
    r = client.post("/ask", json={"question": "monthly revenue"})
    assert r.status_code == 200
    body = r.json()
    assert body["used_fallback"] is True
    assert "mart_monthly_kpis" in body["sql"].lower()
    assert len(body["rows"]) == 1


def test_metrics_and_health(tmp_path: Path, monkeypatch) -> None:
    db = tmp_path / "w.duckdb"
    _make_db(db)
    app = create_app(warehouse_db=db, known_tables={"fact_sales", "mart_monthly_kpis"})
    monkeypatch.setattr(
        "retailpulse.ask.app.generate_sql",
        lambda *_args, **_kw: "SELECT * FROM fact_sales",
    )

    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/metrics").status_code == 200
