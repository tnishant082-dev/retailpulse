"""Write the Power BI project (PBIP) under dashboard/.

Semantic model (TMDL) and report pages (PBIR json) live in one script so the
names stay in sync. Ids and lineage tags are uuid5, so reruns give the same
files. Page insight text is computed from data/powerbi with DuckDB.
Open dashboard/RetailPulse.pbip in Power BI Desktop.
"""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "dashboard"
NAME = "RetailPulse"
PBI_DATA = ROOT / "data" / "powerbi"
NS = uuid.UUID("3c1d2b7e-8f0a-4e55-9a61-2b7c0d4e5f60")


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def wjson(path: Path, obj: dict) -> None:
    write(path, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- model

TABLES = {
    "fact_sales": "Sales lines (non-cancelled invoices)",
    "fact_returns": "Cancelled invoice lines (C-prefixed invoices)",
    "dim_date": "Trading days 2009-12-01 to 2011-12-09",
    "dim_customer": "One row per customer id",
    "dim_product": "One row per stock code (trimmed, case-insensitive)",
    "dim_country": "Countries",
    "mart_cohort_retention": "Monthly acquisition cohorts",
    "mart_product_abc": "ABC class per stock code by revenue",
    "mart_basket_pairs": "Product pairs bought on the same invoice",
    "rfm_segments": "RFM scores and segment per customer",
    "churn_scores": "Churn probability per customer, joined with RFM and CLV",
    "clv_scores": "Predicted 6 month CLV per customer",
    "forecast": "Weekly units: actual vs baseline vs model (holdout weeks)",
}

HIDDEN = {"date_key"}

DTYPE = {
    "VARCHAR": ("string", None, "type text"),
    "INTEGER": ("int64", "0", "Int64.Type"),
    "BIGINT": ("int64", "0", "Int64.Type"),
    "DOUBLE": ("double", "#,0.00", "type number"),
    "DATE": ("dateTime", "yyyy-mm-dd", "type date"),
    "TIMESTAMP": ("dateTime", "yyyy-mm-dd hh:nn", "type datetime"),
}

# extra M steps per table: (column, duckdb-like type, M expression)
EXTRA = {
    "dim_date": [
        ("month_start", "DATE", "Date.StartOfMonth([date])"),
        ("year_month", "VARCHAR", 'Date.ToText([date], "yyyy-MM")'),
        ("month_name", "VARCHAR", 'Date.ToText([date], "MMM")'),
        ("week_start", "DATE", "Date.StartOfWeek([date], Day.Monday)"),
        ("weekday_name", "VARCHAR", 'Date.ToText([date], "ddd")'),
    ],
    "dim_product": [
        ("product", "VARCHAR", 'if [description] = null then [stock_code] else [stock_code] & " " & [description]'),
    ],
    "mart_cohort_retention": [
        ("cohort", "VARCHAR", 'Date.ToText([cohort_month], "yyyy-MM")'),
    ],
    "mart_basket_pairs": [
        ("pair", "VARCHAR", '[product_a] & " + " & [product_b]'),
    ],
    "churn_scores": [
        ("risk_band", "VARCHAR", 'if [churn_proba] >= 0.7 then "High (0.7+)" else if [churn_proba] >= 0.4 then "Medium (0.4-0.7)" else "Low (<0.4)"'),
        ("proba_bucket", "VARCHAR", 'Number.ToText(Number.RoundDown([churn_proba] * 10) / 10, "0.0")'),
    ],
    "clv_scores": [
        ("clv_band", "VARCHAR", 'if [clv_6m_pred] < 250 then "1. <250" else if [clv_6m_pred] < 500 then "2. 250-500" '
         'else if [clv_6m_pred] < 1000 then "3. 500-1k" else if [clv_6m_pred] < 5000 then "4. 1k-5k" else "5. 5k+"'),
    ],
}

SORT_BY = {
    ("dim_date", "month_name"): "month",
    ("dim_date", "weekday_name"): "day_of_week",
}

RELS = [
    ("fact_sales", "date_key", "dim_date", "date_key"),
    ("fact_sales", "customer_id", "dim_customer", "customer_id"),
    ("fact_sales", "stock_code", "dim_product", "stock_code"),
    ("fact_sales", "country", "dim_country", "country"),
    ("fact_returns", "date_key", "dim_date", "date_key"),
    ("fact_returns", "stock_code", "dim_product", "stock_code"),
    ("fact_returns", "country", "dim_country", "country"),
    ("rfm_segments", "customer_id", "dim_customer", "customer_id"),
    ("clv_scores", "customer_id", "dim_customer", "customer_id"),
    ("mart_product_abc", "stock_code", "dim_product", "stock_code"),
    ("forecast", "stock_code", "dim_product", "stock_code"),
]

HI = "churn_scores[churn_proba] >= 0.7"
MEASURES = [
    ("Sales", "Revenue", "SUM ( fact_sales[line_revenue] )", "£#,0"),
    ("Sales", "Orders", "DISTINCTCOUNT ( fact_sales[invoice_no] )", "#,0"),
    ("Sales", "Units", "SUM ( fact_sales[quantity] )", "#,0"),
    ("Sales", "Customers", "DISTINCTCOUNTNOBLANK ( fact_sales[customer_id] )", "#,0"),
    ("Sales", "AOV", "DIVIDE ( [Revenue], [Orders] )", "£#,0.00"),
    ("Sales", "Products Sold", "DISTINCTCOUNT ( fact_sales[stock_code] )", "#,0"),
    ("Sales", "Countries", "DISTINCTCOUNT ( fact_sales[country] )", "#,0"),
    ("Sales", "Revenue per Customer", "DIVIDE ( [Revenue], [Customers] )", "£#,0"),
    ("Sales", "Revenue Share", "DIVIDE ( [Revenue], CALCULATE ( [Revenue], ALL ( dim_country ) ) )", "0.0%"),
    ("Time", "Revenue PY", "CALCULATE ( [Revenue], SAMEPERIODLASTYEAR ( dim_date[date] ) )", "£#,0"),
    ("Time", "Revenue YoY %", "VAR py = [Revenue PY] RETURN IF ( NOT ISBLANK ( py ), DIVIDE ( [Revenue] - py, py ) )", "+0.0%;-0.0%;0.0%"),
    ("Time", "Revenue Running Total", "VAR d = MAX ( dim_date[date] ) RETURN CALCULATE ( [Revenue], dim_date[date] <= d, ALL ( dim_date ) )", "£#,0"),
    ("Time", "Trading Days", "COUNTROWS ( dim_date )", "#,0"),
    ("Time", "Revenue per Trading Day", "DIVIDE ( [Revenue], [Trading Days] )", "£#,0"),
    ("Returns", "Return Revenue", "-SUM ( fact_returns[line_revenue] )", "£#,0"),
    ("Returns", "Returned Units", "-SUM ( fact_returns[quantity] )", "#,0"),
    ("Returns", "Cancelled Invoices", "DISTINCTCOUNT ( fact_returns[invoice_no] )", "#,0"),
    ("Returns", "Return Rate %", "DIVIDE ( [Return Revenue], [Revenue] )", "0.00%"),
    ("Customers", "RFM Customers", "COUNTROWS ( rfm_segments )", "#,0"),
    ("Customers", "Avg Recency Days", "AVERAGE ( rfm_segments[recency_days] )", "#,0"),
    ("Customers", "Avg Frequency", "AVERAGE ( rfm_segments[frequency_orders] )", "0.0"),
    ("Customers", "Avg Monetary", "AVERAGE ( rfm_segments[monetary_revenue] )", "£#,0"),
    ("Customers", "Segment Revenue", "SUM ( rfm_segments[monetary_revenue] )", "£#,0"),
    ("Customers", "Champions %", "DIVIDE ( CALCULATE ( COUNTROWS ( rfm_segments ), rfm_segments[segment] = \"Champions\" ), CALCULATE ( COUNTROWS ( rfm_segments ), ALL ( rfm_segments[segment] ) ) )", "0.0%"),
    ("Cohorts", "Cohort Active", "SUM ( mart_cohort_retention[active_customers] )", "#,0"),
    ("Cohorts", "Cohort Size", "CALCULATE ( SUM ( mart_cohort_retention[active_customers] ), ALL ( mart_cohort_retention[cohort_age_months], mart_cohort_retention[activity_month] ), mart_cohort_retention[cohort_age_months] = 0 )", "#,0"),
    ("Cohorts", "Retention %", "DIVIDE ( [Cohort Active], [Cohort Size] )", "0.0%"),
    ("Cohorts", "Month 1 Retention %", "CALCULATE ( [Retention %], mart_cohort_retention[cohort_age_months] = 1 )", "0.0%"),
    ("Cohorts", "Cohorts", "CALCULATE ( DISTINCTCOUNT ( mart_cohort_retention[cohort_month] ) )", "#,0"),
    ("Churn", "Scored Customers", "COUNTROWS ( churn_scores )", "#,0"),
    ("Churn", "Avg Churn Probability", "AVERAGE ( churn_scores[churn_proba] )", "0.0%"),
    ("Churn", "High Risk Customers", f"CALCULATE ( COUNTROWS ( churn_scores ), {HI} )", "#,0"),
    ("Churn", "High Risk %", "DIVIDE ( [High Risk Customers], [Scored Customers] )", "0.0%"),
    ("Churn", "Actual Churn Rate", "AVERAGE ( churn_scores[churned] )", "0.0%"),
    ("Churn", "Revenue at Risk", f"CALCULATE ( SUM ( churn_scores[monetary_revenue] ), {HI} )", "£#,0"),
    ("Churn", "CLV at Risk", f"CALCULATE ( SUM ( churn_scores[clv_6m_pred] ), {HI} )", "£#,0"),
    ("CLV", "Avg Predicted CLV", "AVERAGE ( clv_scores[clv_6m_pred] )", "£#,0"),
    ("CLV", "Total Predicted CLV", "SUM ( clv_scores[clv_6m_pred] )", "£#,0"),
    ("CLV", "CLV Customers", "COUNTROWS ( clv_scores )", "#,0"),
    ("CLV", "Median Predicted CLV", "MEDIAN ( clv_scores[clv_6m_pred] )", "£#,0"),
    ("Products", "ABC Revenue", "SUM ( mart_product_abc[revenue] )", "£#,0"),
    ("Products", "ABC Products", "COUNTROWS ( mart_product_abc )", "#,0"),
    ("Products", "ABC Revenue Share", "DIVIDE ( [ABC Revenue], CALCULATE ( [ABC Revenue], ALL ( mart_product_abc ) ) )", "0.0%"),
    ("Products", "Pair Orders", "SUM ( mart_basket_pairs[pair_orders] )", "#,0"),
    ("Products", "Product Pairs", "COUNTROWS ( mart_basket_pairs )", "#,0"),
    ("Products", "Top Pair Orders", "MAX ( mart_basket_pairs[pair_orders] )", "#,0"),
    ("Forecast", "Actual Units", "SUM ( forecast[units] )", "#,0"),
    ("Forecast", "Baseline Units", "SUM ( forecast[pred_baseline] )", "#,0"),
    ("Forecast", "Model Units", "SUM ( forecast[pred_model] )", "#,0"),
    ("Forecast", "WAPE Model", "DIVIDE ( SUMX ( forecast, ABS ( forecast[units] - forecast[pred_model] ) ), SUM ( forecast[units] ) )", "0.0%"),
    ("Forecast", "WAPE Baseline", "DIVIDE ( SUMX ( forecast, ABS ( forecast[units] - forecast[pred_baseline] ) ), SUM ( forecast[units] ) )", "0.0%"),
    ("Forecast", "Forecast Products", "DISTINCTCOUNT ( forecast[stock_code] )", "#,0"),
]


def duck_type(t: str) -> str:
    t = t.upper()
    if t.startswith("TIMESTAMP"):
        return "TIMESTAMP"
    if t in ("FLOAT", "DECIMAL") or t.startswith("DECIMAL"):
        return "DOUBLE"
    return t if t in DTYPE else "VARCHAR"


def m_source(name: str, typed: list[str], extra: list[tuple[str, str, str]]) -> list[str]:
    src = f'Parquet.Document ( File.Contents ( DataFolder & "\\{name}.parquet" ) )'
    steps = [f"Source = {src}", f"Typed = Table.TransformColumnTypes ( Source, {{{', '.join(typed)}}} )"]
    last = "Typed"
    if name == "dim_product":
        steps += [
            'Trimmed = Table.TransformColumns ( Typed, {{"stock_code", Text.Trim, type text}} )',
            'Ranked = Table.AddColumn ( Trimmed, "desc_rank", each if [description] = null then 2 '
            'else if Text.Upper ( [description] ) = [description] then 0 else 1, Int64.Type )',
            'Sorted = Table.Buffer ( Table.Sort ( Ranked, {{"desc_rank", Order.Ascending}, {"description", Order.Ascending}} ) )',
            'Deduped = Table.Distinct ( Sorted, {"stock_code", Comparer.OrdinalIgnoreCase} )',
            'Clean = Table.RemoveColumns ( Deduped, {"desc_rank"} )',
        ]
        last = "Clean"
    if name == "churn_scores":
        steps += [
            'Rfm = Parquet.Document ( File.Contents ( DataFolder & "\\rfm_segments.parquet" ) )',
            'Clv = Parquet.Document ( File.Contents ( DataFolder & "\\clv_scores.parquet" ) )',
            'J1 = Table.ExpandTableColumn ( Table.NestedJoin ( Typed, {"customer_id"}, Rfm, {"customer_id"}, "r", JoinKind.LeftOuter ), "r", {"segment", "monetary_revenue"} )',
            'J2 = Table.ExpandTableColumn ( Table.NestedJoin ( J1, {"customer_id"}, Clv, {"customer_id"}, "c", JoinKind.LeftOuter ), "c", {"clv_6m_pred"} )',
            'Joined = Table.TransformColumnTypes ( J2, {{"segment", type text}, {"monetary_revenue", type number}, {"clv_6m_pred", type number}} )',
        ]
        last = "Joined"
    for i, (col, t, expr) in enumerate(extra):
        steps.append(f'X{i} = Table.AddColumn ( {last}, "{col}", each {expr}, {DTYPE[t][2]} )')
        last = f"X{i}"
    out = ["\t\t\t\tlet"]
    out += [f"\t\t\t\t    {s}," for s in steps[:-1]] + [f"\t\t\t\t    {steps[-1]}"]
    return out + ["\t\t\t\tin", f"\t\t\t\t    {last}"]


def table_columns(con: duckdb.DuckDBPyConnection, name: str) -> list[tuple[str, str]]:
    rows = con.execute(f"describe select * from '{(PBI_DATA / (name + '.parquet')).as_posix()}'").fetchall()
    return [(c, duck_type(t)) for c, t, *_ in rows]


def model_columns(con: duckdb.DuckDBPyConnection, name: str) -> list[tuple[str, str]]:
    cols = table_columns(con, name)
    if name == "churn_scores":
        cols += [("segment", "VARCHAR"), ("monetary_revenue", "DOUBLE"), ("clv_6m_pred", "DOUBLE")]
    return cols + [(c, t) for c, t, _ in EXTRA.get(name, [])]


def tmdl_table(con: duckdb.DuckDBPyConnection, name: str) -> str:
    lines = [f"/// {TABLES[name]}", f"table {name}", f"\tlineageTag: {tag('t', name)}"]
    if name == "dim_date":
        lines.append("\tdataCategory: Time")
    lines.append("")
    typed = []
    for c, t in table_columns(con, name):
        typed.append(f'{{"{c}", {DTYPE[t][2]}}}')
    for c, t in model_columns(con, name):
        dt, fmt, _ = DTYPE[t]
        if c.endswith(("_id", "_key", "year", "month", "day", "day_of_week", "week_of_year", "quarter", "_months")) and dt == "int64":
            fmt = "0"
        if c in ("churn_proba", "revenue_share", "cum_share"):
            fmt = "0.0%"
        lines += [f"\tcolumn {c}", f"\t\tdataType: {dt}"]
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        if name == "dim_date" and c == "date":
            lines.append("\t\tisKey")
        if c in HIDDEN and name.startswith("fact"):
            lines.append("\t\tisHidden")
        lines += [f"\t\tlineageTag: {tag('c', name, c)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {c}"]
        if (name, c) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(name, c)]}")
        lines += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="]
    lines += m_source(name, typed, EXTRA.get(name, [])) + [""]
    return "\n".join(lines)


def tmdl_measures() -> str:
    lines = ["table _Measures", f"\tlineageTag: {tag('t', '_Measures')}", ""]
    for folder, name, expr, fmt in MEASURES:
        lines += [f"\tmeasure '{name}' = {expr}", f"\t\tformatString: {fmt}",
                  f"\t\tdisplayFolder: {folder}", f"\t\tlineageTag: {tag('m', name)}", ""]
    lines += ["\tcolumn Value", "\t\tdataType: string", "\t\tisHidden", f"\t\tlineageTag: {tag('c', '_Measures', 'Value')}",
              "\t\tsummarizeBy: none", "\t\tisNameInferred", "\t\tsourceColumn: [Value]", "",
              "\t\tannotation SummarizationSetBy = Automatic", "",
              "\tpartition _Measures = calculated", "\t\tmode: import", '\t\tsource = ROW ( "Value", BLANK () )', ""]
    return "\n".join(lines)


def data_folder_literal() -> str:
    return str(PBI_DATA).replace("/", "\\").replace("\\", "\\\\")


def build_model(con: duckdb.DuckDBPyConnection) -> None:
    sm = DASH / f"{NAME}.SemanticModel"
    if sm.exists():
        shutil.rmtree(sm)
    d = sm / "definition"
    wjson(sm / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": tag("sm")}})
    wjson(sm / "definition.pbism", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    write(d / "database.tmdl", "database\n\tcompatibilityLevel: 1601\n")
    write(d / "expressions.tmdl",
          "/// Full path to the repo's data\\powerbi folder\n"
          f'expression DataFolder = "{data_folder_literal()}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
          f"\tlineageTag: {tag('e', 'DataFolder')}\n\n\tannotation PBI_ResultType = Text\n")
    order = list(TABLES) + ["_Measures"]
    write(d / "model.tmdl",
          "model Model\n\tculture: en-US\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n\tsourceQueryCulture: en-US\n\n"
          f"annotation PBI_QueryOrder = {json.dumps(['DataFolder'] + order)}\n\n"
          + "".join(f"ref table {t}\n" for t in order))
    rel = [f"relationship {tag('r', ft, fc, tt)}\n\tfromColumn: {ft}.{fc}\n\ttoColumn: {tt}.{tc}\n" for ft, fc, tt, tc in RELS]
    write(d / "relationships.tmdl", "\n".join(rel))
    for t in TABLES:
        write(d / "tables" / f"{t}.tmdl", tmdl_table(con, t))
    write(d / "tables" / "_Measures.tmdl", tmdl_measures())


def check_relationships(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Each relationship must join existing columns with the same type."""
    problems = []
    for ft, fc, tt, tc in RELS:
        a = dict(model_columns(con, ft)).get(fc)
        b = dict(model_columns(con, tt)).get(tc)
        if a is None or b is None or DTYPE[a][0] != DTYPE[b][0]:
            problems.append(f"{ft}.{fc} ({a}) -> {tt}.{tc} ({b})")
    return problems


if __name__ == "__main__":
    from pbip_report import build_report  # noqa: E402

    c = duckdb.connect()
    bad = check_relationships(c)
    if bad:
        raise SystemExit("bad relationships: " + "; ".join(bad))
    build_model(c)
    build_report(c)
    wjson(DASH / f"{NAME}.pbip", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}})
    write(DASH / ".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    print("wrote", DASH.relative_to(ROOT))
