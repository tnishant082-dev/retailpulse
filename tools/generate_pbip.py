from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import duckdb


@dataclass(frozen=True)
class Visual:
    name: str
    kind: str
    x: int
    y: int
    w: int
    h: int
    z: int
    tab: int
    definition: dict


def _hex20(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:20]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _insights_text(repo_root: Path) -> str:
    p = repo_root / "reports" / "insights.md"
    if not p.exists():
        return "Run tools/compute_insights.py to generate real insights."
    return p.read_text(encoding="utf-8").strip()


def _proj_column(table: str, column: str) -> dict:
    return {
        "field": {
            "Column": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": column,
            }
        },
        "queryRef": f"{table}.{column}",
        "nativeQueryRef": column,
    }


def _proj_measure(table: str, measure: str) -> dict:
    return {
        "field": {
            "Measure": {
                "Expression": {"SourceRef": {"Entity": table}},
                "Property": measure,
            }
        },
        "queryRef": f"{table}.{measure}",
        "nativeQueryRef": measure,
    }


def _textbox_visual(
    name: str,
    *,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {
                        "properties": {
                            "paragraphs": [
                                {
                                    "textRuns": [
                                        {
                                            "value": text,
                                            "textStyle": {
                                                "fontFamily": "Segoe UI",
                                                "fontSize": "12pt",
                                            },
                                        }
                                    ],
                                    "horizontalTextAlignment": "left",
                                }
                            ]
                        }
                    }
                ]
            },
            "visualContainerObjects": {
                "background": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "border": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
                "title": [{"properties": {"show": {"expr": {"Literal": {"Value": "false"}}}}}],
            },
        },
    }


def _card_visual(
    name: str,
    *,
    measure: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "card",
            "query": {
                "queryState": {"Values": {"projections": [_proj_measure("_Measures", measure)]}}
            },
            "drillFilterOtherVisuals": True,
        },
    }


def _slicer_visual(
    name: str,
    *,
    table: str,
    column: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "slicer",
            "query": {"queryState": {"Values": {"projections": [_proj_column(table, column)]}}},
            "drillFilterOtherVisuals": True,
        },
    }


def _line_visual(
    name: str,
    *,
    axis_table: str,
    axis_col: str,
    measure: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "lineChart",
            "query": {
                "queryState": {
                    "Category": {"projections": [_proj_column(axis_table, axis_col)]},
                    "Y": {"projections": [_proj_measure("_Measures", measure)]},
                }
            },
            "drillFilterOtherVisuals": True,
        },
    }


def _bar_visual(
    name: str,
    *,
    cat_table: str,
    cat_col: str,
    measure: str,
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "clusteredBarChart",
            "query": {
                "queryState": {
                    "Category": {"projections": [_proj_column(cat_table, cat_col)]},
                    "Y": {"projections": [_proj_measure("_Measures", measure)]},
                }
            },
            "drillFilterOtherVisuals": True,
        },
    }


def _table_visual(
    name: str,
    *,
    columns: list[tuple[str, str]],
    measures: list[str],
    x: int,
    y: int,
    w: int,
    h: int,
    z: int,
    tab: int,
) -> dict:
    projs = [_proj_column(t, c) for (t, c) in columns] + [
        _proj_measure("_Measures", m) for m in measures
    ]
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.9.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "tableEx",
            "query": {"queryState": {"Values": {"projections": projs}}},
            "drillFilterOtherVisuals": True,
        },
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: dict) -> None:
    _write(path, json.dumps(obj, indent=1))


def _duckdb_schema(parquet_path: Path) -> list[tuple[str, str]]:
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{parquet_path.as_posix()}')"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        con.close()


def _tmdl_type(duck_type: str) -> tuple[str, dict]:
    t = duck_type.upper()
    if "BIGINT" in t or "HUGEINT" in t or t in {"INTEGER", "INT", "SMALLINT", "TINYINT"}:
        return "int64", {}
    if "DOUBLE" in t or "DECIMAL" in t or "REAL" in t:
        return "double", {}
    if "BOOLEAN" in t:
        return "boolean", {}
    if "TIMESTAMP" in t or t == "DATE":
        anno = {}
        if t == "DATE":
            anno["UnderlyingDateTimeDataType"] = "Date"
        return "dateTime", anno
    return "string", {}


def _tmdl_table(name: str, parquet_filename: str, schema: list[tuple[str, str]]) -> str:
    # Measures MUST NOT appear here; just columns then partition (per Power BI loader expectations).
    lines: list[str] = [f"table {name}", ""]
    for col, dt in schema:
        col_name = col if col.isidentifier() else f"'{col}'"
        dtype, ann = _tmdl_type(dt)
        lines.append(f"\tcolumn {col_name}")
        lines.append(f"\t\tdataType: {dtype}")
        lines.append("\t\tsummarizeBy: none")
        lines.append(f"\t\tsourceColumn: {col}")
        for k, v in ann.items():
            lines.append(f"\t\tannotation {k} = {v}")
        lines.append("")

    lines.extend(
        [
            f"\tpartition {name} = m",
            "\t\tmode: import",
            "\t\tsource =",
            "\t\t\tlet",
            "\t\t\t\tSource = Parquet.Document("
            f'File.Contents(DataFolder & "\\\\{parquet_filename}")',
            "\t\t\t\t)",
            "\t\t\tin",
            "\t\t\t\tSource",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _tmdl_measures_table(measures: list[tuple[str, str, str]]) -> str:
    # measures: (name, dax, formatString)
    lines: list[str] = ["table _Measures", ""]
    for name, dax, fmt in measures:
        lines.append(f"\t/// {name}")
        if "\n" in dax:
            lines.append(f"\tmeasure '{name}' = ```")
            for ln in dax.splitlines():
                lines.append(f"\t{ln}")
            lines.append("\t```")
        else:
            lines.append(f"\tmeasure '{name}' = {dax}")
        lines.append(f"\t\tformatString: {fmt}")
        lines.append("")

    lines.extend(
        [
            "\tcolumn Dummy",
            "\t\tisHidden",
            "\t\tsummarizeBy: none",
            "\t\tsourceColumn: [Dummy]",
            "",
            "\tpartition _Measures = calculated",
            "\t\tmode: import",
            '\t\tsource = ROW("Dummy", BLANK())',
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def generate(repo_root: Path) -> None:
    dash = repo_root / "dashboard"
    report_dir = dash / "RetailPulse.Report"
    model_dir = dash / "RetailPulse.SemanticModel"
    pbip = dash / "RetailPulse.pbip"

    dash.mkdir(parents=True, exist_ok=True)

    # PBIP entrypoint
    _write_json(
        pbip,
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
            "version": "1.0",
            "artifacts": [{"report": {"path": "RetailPulse.Report"}}],
            "settings": {"enableAutoRecovery": True},
        },
    )

    # .platform files
    _write_json(
        report_dir / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "Report", "displayName": "RetailPulse"},
            "config": {"version": "2.0", "logicalId": "e0000000-0000-0000-0000-0000000000e2"},
        },
    )
    _write_json(
        model_dir / ".platform",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": "RetailPulse"},
            "config": {"version": "2.0", "logicalId": "e0000000-0000-0000-0000-0000000000e1"},
        },
    )

    # Report skeleton
    _write_json(
        report_dir / "definition.pbir",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
            "version": "4.0",
            "datasetReference": {"byPath": {"path": "../RetailPulse.SemanticModel"}},
        },
    )
    _write_json(
        report_dir / "definition" / "version.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
            "version": "2.0.0",
        },
    )
    _write_json(
        report_dir / "definition" / "report.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.3.0/schema.json",
            "themeCollection": {
                "baseTheme": {
                    "name": "CY25SU11",
                    "reportVersionAtImport": {
                        "visual": "2.10.0",
                        "report": "3.4.0",
                        "page": "2.3.1",
                    },
                    "type": "SharedResources",
                }
            },
            "settings": {"useEnhancedTooltips": False},
        },
    )

    # Pages (13)
    page_titles = [
        "Executive Summary",
        "Revenue Trends",
        "Seasonality & Peak Weeks",
        "Country Performance",
        "Customer RFM Segments",
        "Cohort Retention",
        "Churn Risk",
        "Customer Lifetime Value",
        "Product ABC Analysis",
        "Market Basket",
        "Returns & Cancellations",
        "Demand Forecast",
        "Revenue Rescue Plan",
    ]
    page_names = [f"page{i+1}" for i in range(len(page_titles))]
    _write_json(
        report_dir / "definition" / "pages" / "pages.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/2.0.0/schema.json",
            "pageOrder": page_names,
            "activePageName": page_names[0],
        },
    )

    insights_blob = _insights_text(repo_root)
    insights_snip = "\n".join(insights_blob.splitlines()[:14])

    for _idx, (page, title) in enumerate(zip(page_names, page_titles, strict=True), start=1):
        page_dir = report_dir / "definition" / "pages" / page
        _write_json(
            page_dir / "page.json",
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.1.0/schema.json",
                "name": page,
                "displayName": title,
                "displayOption": "FitToPage",
                "height": 720,
                "width": 1280,
            },
        )
        (page_dir / "visuals").mkdir(parents=True, exist_ok=True)

        # Layout: title + insight + 4 KPI cards + 2 slicers + 2 charts + 1 table.
        base_z = 1000
        v = []
        v.append(
            (
                "textbox",
                _textbox_visual(
                    _hex20(f"{page}-title"),
                    text=title,
                    x=20,
                    y=10,
                    w=800,
                    h=50,
                    z=base_z,
                    tab=0,
                ),
            )
        )
        v.append(
            (
                "textbox",
                _textbox_visual(
                    _hex20(f"{page}-insight"),
                    text=f"Insights (from real data):\n{insights_snip}",
                    x=20,
                    y=560,
                    w=1240,
                    h=150,
                    z=base_z + 1000,
                    tab=1,
                ),
            )
        )

        kpi_measures = ["Revenue", "Orders", "Customers", "AOV"]
        for j, m in enumerate(kpi_measures):
            v.append(
                (
                    "card",
                    _card_visual(
                        _hex20(f"{page}-kpi-{m}"),
                        measure=m,
                        x=20 + j * 250,
                        y=70,
                        w=240,
                        h=80,
                        z=base_z + 2000 + j * 1000,
                        tab=10 + j,
                    ),
                )
            )

        v.append(
            (
                "slicer",
                _slicer_visual(
                    _hex20(f"{page}-slicer-year"),
                    table="dim_date",
                    column="year",
                    x=1040,
                    y=70,
                    w=220,
                    h=80,
                    z=base_z + 7000,
                    tab=20,
                ),
            )
        )
        v.append(
            (
                "slicer",
                _slicer_visual(
                    _hex20(f"{page}-slicer-country"),
                    table="dim_country",
                    column="country",
                    x=1040,
                    y=160,
                    w=220,
                    h=120,
                    z=base_z + 8000,
                    tab=21,
                ),
            )
        )

        v.append(
            (
                "lineChart",
                _line_visual(
                    _hex20(f"{page}-line-revenue"),
                    axis_table="dim_date",
                    axis_col="date",
                    measure="Revenue",
                    x=20,
                    y=160,
                    w=650,
                    h=260,
                    z=base_z + 9000,
                    tab=30,
                ),
            )
        )
        v.append(
            (
                "barChart",
                _bar_visual(
                    _hex20(f"{page}-bar-country"),
                    cat_table="dim_country",
                    cat_col="country",
                    measure="Revenue",
                    x=690,
                    y=160,
                    w=330,
                    h=260,
                    z=base_z + 10000,
                    tab=31,
                ),
            )
        )

        v.append(
            (
                "table",
                _table_visual(
                    _hex20(f"{page}-table-products"),
                    columns=[("dim_product", "stock_code")],
                    measures=["Revenue"],
                    x=20,
                    y=430,
                    w=1000,
                    h=120,
                    z=base_z + 11000,
                    tab=40,
                ),
            )
        )

        for _kind, obj in v:
            name = obj["name"]
            _write_json(page_dir / "visuals" / name / "visual.json", obj)

    # Semantic model skeleton
    _write_json(
        model_dir / "definition.pbism",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2",
            "settings": {"qnaEnabled": True},
        },
    )
    _write(model_dir / "definition" / "database.tmdl", "database\n compatibilityLevel: 1600\n")

    data_folder = str((repo_root / "data" / "powerbi").resolve())
    _write(
        model_dir / "definition" / "expressions.tmdl",
        "\n".join(
            [
                "/// Local folder containing `data/powerbi/*.parquet` exports",
                (
                    'expression DataFolder = "'
                    + data_folder
                    + '" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
                ),
                "",
                " annotation PBI_ResultType = Text",
                "",
            ]
        ),
    )

    tables = [
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
        "rfm_segments",
        "churn_scores",
        "clv_scores",
        "forecast",
    ]

    # Build table tmdl files from parquet schema
    powerbi = repo_root / "data" / "powerbi"
    for t in tables:
        pq = powerbi / f"{t}.parquet"
        if not pq.exists():
            continue
        schema = _duckdb_schema(pq)
        tmdl = _tmdl_table(t, pq.name, schema)
        if t == "dim_date":
            # mark as date table: dataCategory Time and date key
            tmdl = tmdl.replace("table dim_date\n", "table dim_date\n\tdataCategory: Time\n\n")
            tmdl = tmdl.replace(
                "\tcolumn date\n\t\tdataType",
                "\tcolumn date\n\t\tisKey\n\t\tdataType",
            )
        _write(model_dir / "definition" / "tables" / f"{t}.tmdl", tmdl)

    measures: list[tuple[str, str, str]] = [
        ("Revenue", "SUM(fact_sales[line_revenue])", "#,##0"),
        ("Orders", "DISTINCTCOUNT(fact_sales[invoice_no])", "#,##0"),
        ("Units", "SUM(fact_sales[quantity])", "#,##0"),
        ("Customers", "DISTINCTCOUNT(fact_sales[customer_id])", "#,##0"),
        ("AOV", "DIVIDE([Revenue],[Orders])", "#,##0.00"),
        ("Return Revenue", "SUM(fact_returns[line_revenue])", "#,##0"),
        ("Return Revenue Abs", "ABS([Return Revenue])", "#,##0"),
        ("Return Rate %", "DIVIDE([Return Revenue Abs],[Revenue])", "0.00%"),
        ("Revenue MoM %", "DIVIDE([Revenue]-[Revenue Prev Month],[Revenue Prev Month])", "0.00%"),
        ("Revenue YoY %", "DIVIDE([Revenue]-[Revenue Prev Year],[Revenue Prev Year])", "0.00%"),
        ("Revenue Prev Month", "CALCULATE([Revenue], DATEADD(dim_date[date], -1, MONTH))", "#,##0"),
        ("Revenue Prev Year", "CALCULATE([Revenue], DATEADD(dim_date[date], -1, YEAR))", "#,##0"),
        (
            "Revenue Rolling 3M",
            "CALCULATE([Revenue], DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -3, MONTH))",
            "#,##0",
        ),
        (
            "Revenue Running Total",
            "CALCULATE("
            "[Revenue], "
            "FILTER(ALL(dim_date[date]), dim_date[date] <= MAX(dim_date[date]))"
            ")",
            "#,##0",
        ),
        (
            "New Customers",
            "CALCULATE("
            "DISTINCTCOUNT(dim_customer[customer_id]), "
            "DATESBETWEEN(dim_date[date], MIN(dim_date[date]), MAX(dim_date[date]))"
            ")",
            "#,##0",
        ),
        ("Returning Customers", "[Customers]-[New Customers]", "#,##0"),
        ("Avg CLV 6M", "AVERAGE(clv_scores[clv_6m_pred])", "#,##0"),
        (
            "High Churn Risk Customers",
            "CALCULATE(DISTINCTCOUNT(churn_scores[customer_id]), churn_scores[churn_proba] >= 0.7)",
            "#,##0",
        ),
        (
            "Revenue At Risk",
            "SUMX("
            "FILTER(churn_scores, churn_scores[churn_proba] >= 0.7), "
            "LOOKUPVALUE("
            "mart_customer_rfm[monetary_revenue], "
            "mart_customer_rfm[customer_id], "
            "churn_scores[customer_id]"
            ")"
            ")",
            "#,##0",
        ),
        ("Forecast Units", "SUM(forecast[units])", "#,##0"),
        ("Forecast Pred Model", "SUM(forecast[pred_model])", "#,##0"),
        ("Forecast Pred Baseline", "SUM(forecast[pred_baseline])", "#,##0"),
        (
            "Forecast Error Abs",
            "SUMX(forecast, ABS(forecast[units]-forecast[pred_model]))",
            "#,##0",
        ),
        (
            "Forecast WAPE",
            "DIVIDE([Forecast Error Abs], SUMX(forecast, ABS(forecast[units])))",
            "0.00%",
        ),
        (
            "ABC A Share",
            "DIVIDE("
            "SUMX("
            "FILTER(mart_product_abc, mart_product_abc[abc_class]=\"A\"), "
            "mart_product_abc[revenue]"
            "), "
            "SUM(mart_product_abc[revenue])"
            ")",
            "0.00%",
        ),
        ("Top Pair Orders", "MAX(mart_basket_pairs[pair_orders])", "#,##0"),
        ("Distinct Products", "DISTINCTCOUNT(fact_sales[stock_code])", "#,##0"),
        ("Orders per Customer", "DIVIDE([Orders],[Customers])", "#,##0.00"),
        ("Revenue per Customer", "DIVIDE([Revenue],[Customers])", "#,##0.00"),
        ("Avg Units per Order", "DIVIDE([Units],[Orders])", "#,##0.00"),
        ("Active Customers (Cohort)", "SUM(mart_cohort_retention[active_customers])", "#,##0"),
        (
            "Cohort Retention %",
            "DIVIDE("
            "SUM(mart_cohort_retention[active_customers]), "
            "CALCULATE("
            "SUM(mart_cohort_retention[active_customers]), "
            "mart_cohort_retention[cohort_age_months]=0"
            ")"
            ")",
            "0.00%",
        ),
        ("Churn Avg Proba", "AVERAGE(churn_scores[churn_proba])", "0.000"),
        ("CLV Customers", "DISTINCTCOUNT(clv_scores[customer_id])", "#,##0"),
        (
            "RFM Champions",
            "CALCULATE(COUNTROWS(rfm_segments), rfm_segments[segment]=\"Champions\")",
            "#,##0",
        ),
        ("RFM Champions %", "DIVIDE([RFM Champions], COUNTROWS(rfm_segments))", "0.00%"),
        ("Cancellations Orders", "DISTINCTCOUNT(fact_returns[invoice_no])", "#,##0"),
        ("Sales Orders", "DISTINCTCOUNT(fact_sales[invoice_no])", "#,##0"),
        ("Cancellation Rate %", "DIVIDE([Cancellations Orders], [Sales Orders])", "0.00%"),
        (
            "Max Weekly Revenue",
            'MAXX(SUMMARIZE(fact_sales, dim_date[week_of_year], "rev", [Revenue]), [rev])',
            "#,##0",
        ),
        (
            "Revenue Last 30D",
            "CALCULATE([Revenue], DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -30, DAY))",
            "#,##0",
        ),
        (
            "Revenue Last 90D",
            "CALCULATE([Revenue], DATESINPERIOD(dim_date[date], MAX(dim_date[date]), -90, DAY))",
            "#,##0",
        ),
        ("Revenue Share Top Country", "DIVIDE([Revenue Top Country],[Revenue])", "0.00%"),
        (
            "Revenue Top Country",
            "CALCULATE([Revenue], TOPN(1, VALUES(dim_country[country]), [Revenue]))",
            "#,##0",
        ),
        (
            "Median Order Value",
            "MEDIANX(VALUES(fact_sales[invoice_no]), CALCULATE([Revenue]))",
            "#,##0.00",
        ),
        ("Revenue per Unit", "DIVIDE([Revenue],[Units])", "#,##0.00"),
    ]

    _write(model_dir / "definition" / "tables" / "_Measures.tmdl", _tmdl_measures_table(measures))

    # Model file with refs
    ref_tables = "\n".join([f"ref table {t}" for t in tables] + ["ref table _Measures"])
    _write(
        model_dir / "definition" / "model.tmdl",
        "\n".join(
            [
                "model Model",
                " culture: en-GB",
                " defaultPowerBIDataSourceVersion: powerBI_V3",
                " discourageImplicitMeasures",
                " sourceQueryCulture: en-US",
                "",
                'annotation PBI_ProTooling = ["DevMode","CopilotTooling"]',
                "",
                ref_tables,
                "",
                "ref cultureInfo en-GB",
                "",
            ]
        ),
    )

    # Relationships
    rels: list[tuple[str, str]] = [
        ("fact_sales.stock_code", "dim_product.stock_code"),
        ("fact_sales.customer_id", "dim_customer.customer_id"),
        ("fact_sales.country", "dim_country.country"),
        ("fact_sales.date_key", "dim_date.date_key"),
        ("fact_returns.stock_code", "dim_product.stock_code"),
        ("fact_returns.customer_id", "dim_customer.customer_id"),
        ("fact_returns.country", "dim_country.country"),
        ("fact_returns.date_key", "dim_date.date_key"),
        ("mart_customer_rfm.customer_id", "dim_customer.customer_id"),
        ("rfm_segments.customer_id", "dim_customer.customer_id"),
        ("churn_scores.customer_id", "dim_customer.customer_id"),
        ("clv_scores.customer_id", "dim_customer.customer_id"),
        ("forecast.stock_code", "dim_product.stock_code"),
        ("mart_product_abc.stock_code", "dim_product.stock_code"),
    ]
    rel_lines: list[str] = []
    for i, (frm, to) in enumerate(rels, start=1):
        rel_lines.append(f"relationship c0000000-0000-0000-0000-{i:012d}")
        rel_lines.append(f" fromColumn: {frm}")
        rel_lines.append(f" toColumn: {to}")
        rel_lines.append("")
    _write(model_dir / "definition" / "relationships.tmdl", "\n".join(rel_lines).rstrip() + "\n")


def main() -> int:
    generate(_repo_root())
    print("Generated dashboard/RetailPulse.pbip project.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

