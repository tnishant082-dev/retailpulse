from __future__ import annotations

import re
from dataclasses import dataclass

FORBIDDEN = re.compile(
    r"\b(drop|delete|insert|update|alter|create|attach|copy|pragma|call)\b",
    flags=re.IGNORECASE,
)


_FROM_JOIN = re.compile(r"\b(from|join)\s+([a-zA-Z_][\w\.\-\"`]*)", flags=re.IGNORECASE)
_LIMIT = re.compile(r"\blimit\s+(\d+)\b", flags=re.IGNORECASE)


@dataclass(frozen=True)
class GuardrailResult:
    ok: bool
    sql: str | None
    reason: str | None


def _strip_identifier(token: str) -> str:
    t = token.strip().strip('"').strip("`")
    if "." in t:
        t = t.split(".")[-1]
    return t


def referenced_tables(sql: str) -> set[str]:
    tables: set[str] = set()
    for _, raw in _FROM_JOIN.findall(sql):
        t = _strip_identifier(raw)
        # ignore subqueries like "(select"
        if t.startswith("("):
            continue
        tables.add(t)
    return tables


def enforce_limit(sql: str, *, default_limit: int = 100, max_limit: int = 500) -> str:
    s = sql.strip().rstrip(";").strip()
    m = list(_LIMIT.finditer(s))
    if not m:
        return f"{s}\nLIMIT {default_limit}"

    last = m[-1]
    n = int(last.group(1))
    if n <= max_limit:
        return s

    # Replace the last LIMIT only.
    start, end = last.span(1)
    return s[:start] + str(max_limit) + s[end:]


def validate_sql(
    sql: str,
    *,
    known_tables: set[str],
    default_limit: int = 100,
    max_limit: int = 500,
) -> GuardrailResult:
    s = (sql or "").strip()
    if not s:
        return GuardrailResult(ok=False, sql=None, reason="empty sql")

    s = s.rstrip()
    s_no_trailing = s.rstrip(";").strip()
    if ";" in s_no_trailing:
        return GuardrailResult(ok=False, sql=None, reason="multiple statements not allowed")

    if FORBIDDEN.search(s_no_trailing):
        return GuardrailResult(ok=False, sql=None, reason="only select queries are allowed")

    if not re.match(r"^(select|with)\b", s_no_trailing, flags=re.IGNORECASE):
        return GuardrailResult(ok=False, sql=None, reason="only select queries are allowed")

    tables = referenced_tables(s_no_trailing)
    unknown = sorted(t for t in tables if t not in known_tables)
    if unknown:
        return GuardrailResult(ok=False, sql=None, reason=f"unknown table(s): {', '.join(unknown)}")

    limited = enforce_limit(s_no_trailing, default_limit=default_limit, max_limit=max_limit)
    return GuardrailResult(ok=True, sql=limited, reason=None)
