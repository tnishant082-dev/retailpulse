from __future__ import annotations

from retailpulse.ask.guardrails import validate_sql

KNOWN = {"fact_sales", "mart_monthly_kpis"}


def test_guardrails_rejects_non_select() -> None:
    r = validate_sql("DROP TABLE fact_sales", known_tables=KNOWN)
    assert r.ok is False


def test_guardrails_rejects_multiple_statements() -> None:
    r = validate_sql("SELECT 1; SELECT 2", known_tables=KNOWN)
    assert r.ok is False


def test_guardrails_rejects_unknown_table() -> None:
    r = validate_sql("SELECT * FROM nope", known_tables=KNOWN)
    assert r.ok is False
    assert "unknown table" in (r.reason or "")


def test_guardrails_adds_limit() -> None:
    r = validate_sql("SELECT * FROM fact_sales", known_tables=KNOWN, default_limit=10, max_limit=50)
    assert r.ok is True
    assert r.sql is not None
    assert "limit 10" in r.sql.lower()


def test_guardrails_caps_limit() -> None:
    r = validate_sql(
        "SELECT * FROM fact_sales LIMIT 9999",
        known_tables=KNOWN,
        default_limit=10,
        max_limit=50,
    )
    assert r.ok is True
    assert r.sql is not None
    assert "limit 50" in r.sql.lower()
