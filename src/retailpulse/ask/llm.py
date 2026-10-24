from __future__ import annotations

import os
import re
from dataclasses import dataclass

import requests


@dataclass(frozen=True)
class LlmConfig:
    base_url: str
    api_key: str
    model: str


def load_config() -> LlmConfig | None:
    base_url = (os.getenv("LLM_BASE_URL") or "").strip().rstrip("/")
    api_key = (os.getenv("LLM_API_KEY") or "").strip()
    model = (os.getenv("LLM_MODEL") or "").strip()
    if not (base_url and api_key and model):
        return None
    return LlmConfig(base_url=base_url, api_key=api_key, model=model)


_CODEBLOCK = re.compile(r"```(?:sql)?\s*([\s\S]*?)```", flags=re.IGNORECASE)


def _extract_sql(text: str) -> str:
    m = _CODEBLOCK.search(text or "")
    if m:
        return m.group(1).strip()
    return (text or "").strip()


def generate_sql(question: str, *, known_tables: set[str], timeout_s: float = 15.0) -> str | None:
    cfg = load_config()
    if cfg is None:
        return None

    system = (
        "You are a data analyst. Produce exactly ONE SQL query for DuckDB.\n"
        "- Only SELECT queries are allowed.\n"
        "- Only use these tables: " + ", ".join(sorted(known_tables)) + "\n"
        "- Add LIMIT if the user did not specify a limit.\n"
        "- Return SQL only, no explanation."
    )
    payload = {
        "model": cfg.model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": question},
        ],
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    url = f"{cfg.base_url}/v1/chat/completions"
    r = requests.post(url, json=payload, headers=headers, timeout=timeout_s)
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"]["content"]
    return _extract_sql(text)
