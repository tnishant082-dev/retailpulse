from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Expected PBIR schema versions for the installed Power BI Desktop on this machine.
# (Aligned to the known-working Olist PBIP project.)
PBIR_SCHEMA_PAGES = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
)
PBIR_SCHEMA_REPORT = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.2.0/schema.json"
)
PBIR_SCHEMA_PAGE = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.3.0/schema.json"
)
PBIR_SCHEMA_VISUAL = (
    "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
)

@dataclass(frozen=True)
class ModelIndex:
    tables: set[str]
    columns: dict[str, set[str]]
    measures: dict[str, set[str]]


_TABLE_RE = re.compile(r"^table\s+(.+?)\s*$")
_COL_RE = re.compile(r"^\tcolumn\s+(.+?)\s*$")
_MEASURE_RE = re.compile(r"^\tmeasure\s+'(.+?)'\s*=")


def _unquote(name: str) -> str:
    n = name.strip()
    if (n.startswith("'") and n.endswith("'")) or (n.startswith('"') and n.endswith('"')):
        return n[1:-1]
    return n


def index_tmdl(semantic_model_dir: Path) -> ModelIndex:
    tables: set[str] = set()
    columns: dict[str, set[str]] = {}
    measures: dict[str, set[str]] = {}

    for tmdl in (semantic_model_dir / "definition" / "tables").glob("*.tmdl"):
        txt = tmdl.read_text(encoding="utf-8").splitlines()
        table_name: str | None = None
        for line in txt:
            m = _TABLE_RE.match(line)
            if m:
                table_name = _unquote(m.group(1))
                tables.add(table_name)
                columns.setdefault(table_name, set())
                measures.setdefault(table_name, set())
                continue
            if table_name is None:
                continue
            m = _COL_RE.match(line)
            if m:
                columns[table_name].add(_unquote(m.group(1)))
                continue
            m = _MEASURE_RE.match(line)
            if m:
                measures[table_name].add(_unquote(m.group(1)))
                continue

    return ModelIndex(tables=tables, columns=columns, measures=measures)


def _iter_query_refs(obj: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "queryRef" and isinstance(v, str):
                refs.append(v)
            refs.extend(_iter_query_refs(v))
    elif isinstance(obj, list):
        for it in obj:
            refs.extend(_iter_query_refs(it))
    return refs


def _split_query_ref(query_ref: str) -> tuple[str, str] | None:
    if "." not in query_ref:
        return None
    table, prop = query_ref.split(".", 1)
    return _unquote(table), _unquote(prop)


def validate_report_references(report_dir: Path, model: ModelIndex) -> list[str]:
    failures: list[str] = []
    for visual in report_dir.glob("definition/pages/*/visuals/*/visual.json"):
        try:
            obj = json.loads(visual.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{visual}: invalid json ({e})")
            continue

        for ref in _iter_query_refs(obj):
            sp = _split_query_ref(ref)
            if sp is None:
                continue
            table, prop = sp
            if table not in model.tables:
                failures.append(f"{visual}: unknown table in queryRef: {table}")
                continue
            if prop in model.columns.get(table, set()):
                continue
            if prop in model.measures.get(table, set()):
                continue
            failures.append(f"{visual}: unknown field in queryRef: {table}.{prop}")
    return failures


def validate_json_parses(root: Path) -> list[str]:
    failures: list[str] = []
    for p in root.rglob("*.json"):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{p}: invalid json ({e})")
    # PBIP and PBIR are JSON too (extensions differ)
    for p in root.rglob("*.pbip"):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{p}: invalid json ({e})")
    for p in root.rglob("*.pbism"):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{p}: invalid json ({e})")
    for p in root.rglob("*.pbir"):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            failures.append(f"{p}: invalid json ({e})")
    return failures


def validate_schema_versions(report_dir: Path) -> list[str]:
    failures: list[str] = []

    # pages metadata
    pages_json = report_dir / "definition" / "pages" / "pages.json"
    if pages_json.exists():
        obj = json.loads(pages_json.read_text(encoding="utf-8"))
        if obj.get("$schema") != PBIR_SCHEMA_PAGES:
            failures.append(f"{pages_json}: unsupported $schema {obj.get('$schema')}")
    else:
        failures.append(f"missing {pages_json}")

    # report.json
    report_json = report_dir / "definition" / "report.json"
    if report_json.exists():
        obj = json.loads(report_json.read_text(encoding="utf-8"))
        if obj.get("$schema") != PBIR_SCHEMA_REPORT:
            failures.append(f"{report_json}: unsupported $schema {obj.get('$schema')}")
    else:
        failures.append(f"missing {report_json}")

    # pages + visuals
    for page_json in report_dir.glob("definition/pages/*/page.json"):
        obj = json.loads(page_json.read_text(encoding="utf-8"))
        if obj.get("$schema") != PBIR_SCHEMA_PAGE:
            failures.append(f"{page_json}: unsupported $schema {obj.get('$schema')}")

    for visual_json in report_dir.glob("definition/pages/*/visuals/*/visual.json"):
        obj = json.loads(visual_json.read_text(encoding="utf-8"))
        if obj.get("$schema") != PBIR_SCHEMA_VISUAL:
            failures.append(f"{visual_json}: unsupported $schema {obj.get('$schema')}")

    return failures


def check(pbip_path: Path) -> list[str]:
    failures: list[str] = []
    root = pbip_path.parent
    report_dir = root / "RetailPulse.Report"
    model_dir = root / "RetailPulse.SemanticModel"

    failures.extend(validate_json_parses(root))
    model = index_tmdl(model_dir)
    failures.extend(validate_schema_versions(report_dir))
    failures.extend(validate_report_references(report_dir, model))
    return failures


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    pbip = repo_root / "dashboard" / "RetailPulse.pbip"
    failures = check(pbip)
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PBIP check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

