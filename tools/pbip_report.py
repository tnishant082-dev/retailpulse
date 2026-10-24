"""Report pages (PBIR json) for the RetailPulse PBIP. Used by generate_pbip.py."""

from __future__ import annotations

import json
import shutil

import duckdb
from generate_pbip import DASH, NAME, PBI_DATA, ROOT, tag, wjson

VC = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.4.0/schema.json"
SUBTITLE = "Online Retail II, UK gift wholesaler · Dec 2009 – Dec 2011 · GBP"


def lit(v: str) -> dict:
    return {"expr": {"Literal": {"Value": v}}}


def field(ref: str) -> dict:
    """'table.column' or '[Measure]'"""
    if ref.startswith("["):
        m = ref[1:-1]
        return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": m}},
                "queryRef": f"_Measures.{m}", "nativeQueryRef": m}
    t, c = ref.split(".", 1)
    return {"field": {"Column": {"Expression": {"SourceRef": {"Entity": t}}, "Property": c}},
            "queryRef": ref, "nativeQueryRef": c}


def container(title: str) -> dict:
    return {
        "title": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'"),
                                  "fontSize": lit("11D"), "fontFamily": lit("'Segoe UI Semibold'"),
                                  "fontColor": {"solid": {"color": lit("'#E2E8F0'")}}}}],
        "border": [{"properties": {"show": lit("true"),
                                   "color": {"solid": {"color": lit("'#334155'")}}, "radius": lit("8D")}}],
    }


def textbox(paragraphs: list[tuple[str, dict]]) -> dict:
    return {"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": [
        {"textRuns": [{"value": text, "textStyle": style}]} for text, style in paragraphs]}}]}}


class Page:
    def __init__(self, name: str, display: str, subtitle: str = SUBTITLE):
        self.name, self.display, self.subtitle = name, display, subtitle
        self.visuals: list[tuple[str, int, int, int, int, dict]] = []

    def add(self, vtype, title, x, y, w, h, roles, sort=None, objects=None):
        v = {"visualType": vtype,
             "query": {"queryState": {r: {"projections": [field(f) for f in fs]} for r, fs in roles.items()}},
             "drillFilterOtherVisuals": True,
             "visualContainerObjects": container(title)}
        if sort:
            ref, direction = sort
            v["query"]["sortDefinition"] = {"sort": [{"field": field(ref)["field"], "direction": direction}],
                                            "isDefaultSort": True}
        if objects:
            v["objects"] = objects
        self.visuals.append((f"{self.name}_v{len(self.visuals) + 1:02d}", x, y, w, h, v))
        return self

    def slicers(self, items):
        for i, (title, col) in enumerate(items):
            obj = {"data": [{"properties": {"mode": lit("'Dropdown'")}}]}
            self.add("slicer", title, 20 + i * 234, 80, 220, 70, {"Values": [col]}, objects=obj)
        return self

    def cards(self, measures):
        w = (1880 - 14 * (len(measures) - 1)) // len(measures)
        for i, m in enumerate(measures):
            self.add("card", m, 20 + i * (w + 14), 170, w, 110, {"Values": [f"[{m}]"]})
        return self

    def insight(self, lines: list[str], x=1214, y=684, w=686, h=376):
        paras = [("Insights", {"fontFamily": "Segoe UI Semibold", "fontSize": "14pt", "color": "#2DD4BF"})]
        paras += [(f"• {s}", {"fontSize": "11pt", "color": "#E2E8F0"}) for s in lines]
        v = textbox(paras)
        v["visualContainerObjects"] = {"border": container("")["border"]}
        self.visuals.append((f"{self.name}_insight", x, y, w, h, v))
        return self


# ---------------------------------------------------------------- insight numbers

def q(con, sql: str):
    return con.execute(sql.replace("@", PBI_DATA.as_posix() + "/")).fetchall()


def money(v: float) -> str:
    return f"£{v:,.0f}"


PRODUCT = """(select trim(stock_code) as stock_code,
  coalesce(max(description) filter (where description = upper(description)), max(description)) as description
  from '@dim_product.parquet' group by 1)"""


def insights(con) -> dict[str, list[str]]:
    metrics_path = ROOT / "reports" / "metrics.json"
    metrics = json.loads(metrics_path.read_text()) if metrics_path.exists() else {}
    out: dict[str, list[str]] = {}

    rev, orders, cust = q(con, "select sum(line_revenue), count(distinct invoice_no), count(distinct customer_id) from '@fact_sales.parquet'")[0]
    uk = q(con, "select sum(line_revenue) from '@fact_sales.parquet' where country = 'United Kingdom'")[0][0]
    out["exec"] = [f"Revenue {money(rev)} from {orders:,} orders and {cust:,} known customers.",
                   f"Average order value {money(rev / orders)}.",
                   f"United Kingdom is {uk / rev:.1%} of revenue."]

    yr = dict(q(con, "select year(invoice_ts), sum(line_revenue) from '@fact_sales.parquet' group by 1"))
    ytd10 = q(con, "select sum(line_revenue) from '@fact_sales.parquet' where invoice_ts < '2010-12-10' and invoice_ts >= '2010-01-01'")[0][0]
    pm, pmr = q(con, "select strftime(invoice_ts, '%Y-%m') m, sum(line_revenue) r from '@fact_sales.parquet' group by 1 order by 2 desc limit 1")[0]
    out["trends"] = [f"2010 revenue {money(yr[2010])}; 2011 to 9 Dec {money(yr[2011])}.",
                     f"Same period 1 Jan – 9 Dec: {money(ytd10)} in 2010 vs {money(yr[2011])} in 2011 ({yr[2011] / ytd10 - 1:+.1%}).",
                     f"Best month {pm}: {money(pmr)}."]

    wk, wkr = q(con, "select strftime(date_trunc('week', invoice_ts), '%Y-%m-%d'), sum(line_revenue) from '@fact_sales.parquet' group by 1 order by 2 desc limit 1")[0]
    q4 = q(con, "select sum(line_revenue) filter (where month(invoice_ts) between 9 and 11) / sum(line_revenue) from '@fact_sales.parquet' where year(invoice_ts) in (2010)")[0][0]
    wd, wdr = q(con, "select dayname(invoice_ts), sum(line_revenue) from '@fact_sales.parquet' group by 1 order by 2 desc limit 1")[0]
    out["season"] = [f"Peak week starts {wk}: {money(wkr)}.",
                     f"Sep–Nov made {q4:.1%} of 2010 revenue.",
                     f"Strongest weekday is {wd} ({money(wdr)} total)."]

    top = q(con, "select country, sum(line_revenue) r from '@fact_sales.parquet' where country <> 'United Kingdom' group by 1 order by 2 desc limit 3")
    ncty = q(con, "select count(distinct country) from '@fact_sales.parquet'")[0][0]
    out["country"] = [f"{ncty} countries buy; UK is {uk / rev:.1%} of revenue.",
                      "Top export markets: " + ", ".join(f"{c} {money(r)}" for c, r in top) + ".",
                      f"Non-UK revenue {money(rev - uk)}."]

    seg = q(con, "select segment, count(*), sum(monetary_revenue) from '@rfm_segments.parquet' group by 1 order by 3 desc")
    tot_c = sum(s[1] for s in seg)
    tot_m = sum(s[2] for s in seg)
    ch = next(s for s in seg if s[0] == "Champions")
    out["rfm"] = [f"{tot_c:,} customers scored on recency, frequency, monetary.",
                  f"Champions: {ch[1]:,} customers ({ch[1] / tot_c:.1%}) bring {ch[2] / tot_m:.1%} of customer revenue.",
                  "Largest segments: " + ", ".join(f"{s[0]} {s[1]:,}" for s in sorted(seg, key=lambda s: -s[1])[:3]) + "."]

    coh = q(con, """with b as (select cohort_month, cohort_age_months a, active_customers n from '@mart_cohort_retention.parquet'),
        c0 as (select cohort_month, n from b where a = 0), c1 as (select cohort_month, n from b where a = 1)
        select strftime(c0.cohort_month, '%Y-%m'), c0.n, c1.n * 1.0 / c0.n from c0 join c1 using (cohort_month) order by c0.n desc""")
    avg1 = sum(r[2] for r in coh) / len(coh)
    out["cohort"] = [f"Biggest cohort {coh[0][0]}: {coh[0][1]:,} first-time customers, {coh[0][2]:.1%} back in month 1.",
                     f"Average month-1 retention across {len(coh)} cohorts: {avg1:.1%}.",
                     "Dec 2009 cohort includes customers who bought before the data starts, so it looks stronger."]

    hi, hir, hic = q(con, """select count(*), sum(r.monetary_revenue), sum(c.clv_6m_pred) from '@churn_scores.parquet' s
        left join '@rfm_segments.parquet' r using (customer_id) left join '@clv_scores.parquet' c using (customer_id)
        where s.churn_proba >= 0.7""")[0]
    nsc = q(con, "select count(*) from '@churn_scores.parquet'")[0][0]
    cm = metrics.get("churn", {})
    out["churn"] = [f"{hi:,} of {nsc:,} scored customers ({hi / nsc:.1%}) have churn probability 0.7+.",
                    f"Their past revenue: {money(hir)}."]
    if cm:
        out["churn"].append(f"Holdout ROC AUC {cm['roc_auc_logreg']:.3f} (logreg) / {cm['roc_auc_gbdt']:.3f} (gbdt); "
                            f"precision in top 10% {cm['precision_at_top10_logreg']:.1%}.")

    n, avg, tot = q(con, "select count(*), avg(clv_6m_pred), sum(clv_6m_pred) from '@clv_scores.parquet'")[0]
    top10 = q(con, f"select sum(clv_6m_pred) from (select clv_6m_pred from '@clv_scores.parquet' order by 1 desc limit {n // 10})")[0][0]
    out["clv"] = [f"{n:,} customers scored; average 6 month CLV {money(avg)}, total {money(tot)}.",
                  f"Top 10% of customers hold {top10 / tot:.1%} of predicted CLV."]
    if "clv" in metrics:
        out["clv"].append(f"Holdout MAE {money(metrics['clv']['mae'])}, RMSE {money(metrics['clv']['rmse'])} (heavy tail).")

    abc = q(con, "select abc_class, count(*), sum(revenue) from '@mart_product_abc.parquet' group by 1 order by 1")
    na = sum(r[1] for r in abc)
    ra = sum(r[2] for r in abc)
    a = abc[0]
    out["abc"] = [f"{a[1]:,} of {na:,} products ({a[1] / na:.1%}) are class A and make {a[2] / ra:.1%} of revenue.",
                  f"Class C: {abc[-1][1]:,} products, {abc[-1][2] / ra:.1%} of revenue.",
                  "Codes M (manual) and DOT (postage) sit in class A but are not products."]

    pairs = q(con, f"""select p.pair_orders, a.description, b.description from '@mart_basket_pairs.parquet' p
        left join {PRODUCT} a on a.stock_code = p.product_a left join {PRODUCT} b on b.stock_code = p.product_b
        order by 1 desc limit 3""")
    out["basket"] = [f"{o:,} orders: {(x or '?').strip().title()} + {(y or '?').strip().title()}" for o, x, y in pairs]

    canc, rr = q(con, "select count(distinct invoice_no), -sum(line_revenue) from '@fact_returns.parquet'")[0]
    tr = q(con, f"""select p.description, -sum(r.line_revenue) v from '@fact_returns.parquet' r left join {PRODUCT} p
        on p.stock_code = trim(r.stock_code) group by 1 order by 2 desc limit 1""")[0]
    out["returns"] = [f"{canc:,} cancelled invoices worth {money(rr)}.",
                      f"Return rate by revenue {rr / rev:.2%}.",
                      f"Largest cancelled value: {(tr[0] or '?').title()} ({money(tr[1])})."]

    fm = metrics.get("forecast", {})
    nf, wk0, wk1 = q(con, "select count(distinct stock_code), min(week_start)::date, max(week_start)::date from '@forecast.parquet'")[0]
    out["forecast"] = [f"{nf} top products, holdout weeks {wk0} to {wk1}."]
    if fm:
        out["forecast"].append(f"WAPE: model {fm['wape_model']:.1%} vs baseline {fm['wape_baseline']:.1%}.")

    seg_hi = q(con, """select r.segment, count(*), sum(r.monetary_revenue) from '@churn_scores.parquet' s
        join '@rfm_segments.parquet' r using (customer_id) where s.churn_proba >= 0.7 group by 1 order by 3 desc""")
    out["rescue"] = [f"{hi:,} high-risk customers with {money(hir)} past revenue and {money(hic or 0)} predicted CLV.",
                     "Highest value at risk: " + ", ".join(f"{s} {c:,} customers / {money(m)}" for s, c, m in seg_hi[:2]) + ".",
                     f"Start win-back with high-risk {seg_hi[0][0]} customers, then {seg_hi[1][0]}.",
                     f"Protect class A stock in Sep–Nov; peak week starts {wk}."]
    return out


# ---------------------------------------------------------------- pages

R1, H1, R2, H2 = 300, 370, 684, 376


def pages(ins: dict[str, list[str]]) -> list[Page]:
    std = [("Year", "dim_date.year"), ("Month", "dim_date.month_name"), ("Country", "dim_country.country")]
    out = []

    p = Page("p01_executive", "Executive Summary").slicers(std)
    p.cards(["Revenue", "Orders", "Customers", "AOV", "Return Rate %", "High Risk Customers"])
    p.add("lineChart", "Revenue by month", 20, R1, 1180, H1, {"Category": ["dim_date.month_start"], "Y": ["[Revenue]", "[Revenue PY]"]})
    p.add("clusteredBarChart", "Top countries by revenue", 1214, R1, 686, H1, {"Category": ["dim_country.country"], "Y": ["[Revenue]"]}, sort=("[Revenue]", "Descending"))
    p.add("donutChart", "Customers by RFM segment", 20, R2, 580, H2, {"Category": ["rfm_segments.segment"], "Y": ["[RFM Customers]"]})
    p.add("tableEx", "Year summary", 614, R2, 586, H2, {"Values": ["dim_date.year", "[Revenue]", "[Orders]", "[Customers]", "[AOV]"]})
    out.append(p.insight(ins["exec"]))

    p = Page("p02_trends", "Revenue Trends").slicers(std)
    p.cards(["Revenue", "Revenue PY", "Revenue YoY %", "Revenue per Trading Day", "Orders"])
    p.add("lineChart", "Revenue vs same month last year", 20, R1, 940, H1, {"Category": ["dim_date.month_start"], "Y": ["[Revenue]", "[Revenue PY]"]})
    p.add("clusteredColumnChart", "Orders by month", 974, R1, 926, H1, {"Category": ["dim_date.month_start"], "Y": ["[Orders]"]})
    p.add("lineChart", "Running total revenue", 20, R2, 580, H2, {"Category": ["dim_date.month_start"], "Y": ["[Revenue Running Total]"]})
    p.add("pivotTable", "Monthly detail", 614, R2, 586, H2, {"Rows": ["dim_date.year_month"], "Values": ["[Revenue]", "[Revenue YoY %]", "[Orders]", "[AOV]"]}, sort=("dim_date.year_month", "Ascending"))
    out.append(p.insight(ins["trends"]))

    p = Page("p03_seasonality", "Seasonality & Peak Weeks").slicers(std)
    p.cards(["Revenue", "Units", "Trading Days", "Revenue per Trading Day"])
    p.add("clusteredColumnChart", "Revenue by week", 20, R1, 1880, H1, {"Category": ["dim_date.week_start"], "Y": ["[Revenue]"]})
    p.add("clusteredColumnChart", "Revenue by month of year", 20, R2, 580, H2, {"Category": ["dim_date.month_name"], "Y": ["[Revenue]"]}, sort=("dim_date.month_name", "Ascending"))
    p.add("clusteredColumnChart", "Revenue by weekday", 614, R2, 586, H2, {"Category": ["dim_date.weekday_name"], "Y": ["[Revenue]"]}, sort=("dim_date.weekday_name", "Ascending"))
    out.append(p.insight(ins["season"]))

    p = Page("p04_country", "Country Performance").slicers(std)
    p.cards(["Countries", "Revenue", "Customers", "Revenue per Customer", "AOV"])
    p.add("clusteredBarChart", "Revenue by country", 20, R1, 620, 760, {"Category": ["dim_country.country"], "Y": ["[Revenue]"]}, sort=("[Revenue]", "Descending"))
    p.add("tableEx", "Country scorecard", 654, R1, 1246, H1, {"Values": ["dim_country.country", "[Revenue]", "[Revenue Share]", "[Orders]", "[Customers]", "[AOV]", "[Return Rate %]"]}, sort=("[Revenue]", "Descending"))
    p.add("scatterChart", "Orders vs AOV by country", 654, R2, 546, H2, {"Category": ["dim_country.country"], "X": ["[Orders]"], "Y": ["[AOV]"], "Size": ["[Revenue]"]})
    out.append(p.insight(ins["country"]))

    p = Page("p05_rfm", "Customer RFM Segments").slicers([("Segment", "rfm_segments.segment"), ("R score", "rfm_segments.r_score"), ("F score", "rfm_segments.f_score")])
    p.cards(["RFM Customers", "Champions %", "Avg Recency Days", "Avg Frequency", "Avg Monetary"])
    p.add("clusteredBarChart", "Customer revenue by segment", 20, R1, 940, H1, {"Category": ["rfm_segments.segment"], "Y": ["[Segment Revenue]"]}, sort=("[Segment Revenue]", "Descending"))
    p.add("donutChart", "Customers by segment", 974, R1, 926, H1, {"Category": ["rfm_segments.segment"], "Y": ["[RFM Customers]"]})
    p.add("tableEx", "Segment profile", 20, R2, 1180, H2, {"Values": ["rfm_segments.segment", "[RFM Customers]", "[Segment Revenue]", "[Avg Recency Days]", "[Avg Frequency]", "[Avg Monetary]"]}, sort=("[Segment Revenue]", "Descending"))
    out.append(p.insight(ins["rfm"]))

    p = Page("p06_cohorts", "Cohort Retention").slicers([("Cohort", "mart_cohort_retention.cohort"), ("Months since first order", "mart_cohort_retention.cohort_age_months")])
    p.cards(["Cohorts", "Cohort Size", "Month 1 Retention %", "Cohort Active"])
    p.add("pivotTable", "Retention % by cohort and month since first order", 20, R1, 1880, H1, {"Rows": ["mart_cohort_retention.cohort"], "Columns": ["mart_cohort_retention.cohort_age_months"], "Values": ["[Retention %]"]})
    p.add("lineChart", "Average retention curve", 20, R2, 580, H2, {"Category": ["mart_cohort_retention.cohort_age_months"], "Y": ["[Retention %]"]})
    p.add("clusteredColumnChart", "New customers per cohort", 614, R2, 586, H2, {"Category": ["mart_cohort_retention.cohort"], "Y": ["[Cohort Size]"]})
    out.append(p.insight(ins["cohort"]))

    p = Page("p07_churn", "Churn Risk").slicers([("Risk band", "churn_scores.risk_band"), ("Segment", "churn_scores.segment")])
    p.cards(["Scored Customers", "High Risk Customers", "High Risk %", "Avg Churn Probability", "Revenue at Risk"])
    p.add("clusteredColumnChart", "Customers by churn probability", 20, R1, 940, H1, {"Category": ["churn_scores.proba_bucket"], "Y": ["[Scored Customers]"]}, sort=("churn_scores.proba_bucket", "Ascending"))
    p.add("donutChart", "Customers by risk band", 974, R1, 926, H1, {"Category": ["churn_scores.risk_band"], "Y": ["[Scored Customers]"]})
    p.add("clusteredBarChart", "Revenue at risk by segment", 20, R2, 580, H2, {"Category": ["churn_scores.segment"], "Y": ["[Revenue at Risk]"]}, sort=("[Revenue at Risk]", "Descending"))
    p.add("tableEx", "Risk band detail", 614, R2, 586, H2, {"Values": ["churn_scores.risk_band", "[Scored Customers]", "[Actual Churn Rate]", "[Avg Churn Probability]"]})
    out.append(p.insight(ins["churn"]))

    p = Page("p08_clv", "Customer Lifetime Value").slicers([("CLV band", "clv_scores.clv_band"), ("Country", "dim_customer.country")])
    p.cards(["CLV Customers", "Avg Predicted CLV", "Median Predicted CLV", "Total Predicted CLV"])
    p.add("clusteredColumnChart", "Customers by predicted CLV band", 20, R1, 940, H1, {"Category": ["clv_scores.clv_band"], "Y": ["[CLV Customers]"]}, sort=("clv_scores.clv_band", "Ascending"))
    p.add("clusteredBarChart", "Predicted CLV by country", 974, R1, 926, H1, {"Category": ["dim_customer.country"], "Y": ["[Total Predicted CLV]"]}, sort=("[Total Predicted CLV]", "Descending"))
    p.add("tableEx", "Top customers by predicted CLV", 20, R2, 1180, H2, {"Values": ["clv_scores.customer_id", "dim_customer.country", "[Total Predicted CLV]"]}, sort=("[Total Predicted CLV]", "Descending"))
    out.append(p.insight(ins["clv"]))

    p = Page("p09_abc", "Product ABC Analysis").slicers([("ABC class", "mart_product_abc.abc_class")])
    p.cards(["ABC Products", "ABC Revenue", "ABC Revenue Share", "Products Sold"])
    p.add("donutChart", "Revenue by ABC class", 20, R1, 620, H1, {"Category": ["mart_product_abc.abc_class"], "Y": ["[ABC Revenue]"]})
    p.add("clusteredColumnChart", "Products by ABC class", 654, R1, 546, H1, {"Category": ["mart_product_abc.abc_class"], "Y": ["[ABC Products]"]})
    p.add("clusteredBarChart", "Top products by revenue", 1214, R1, 686, H1, {"Category": ["dim_product.product"], "Y": ["[ABC Revenue]"]}, sort=("[ABC Revenue]", "Descending"))
    p.add("tableEx", "Product list", 20, R2, 1180, H2, {"Values": ["dim_product.product", "mart_product_abc.abc_class", "[ABC Revenue]", "[ABC Revenue Share]"]}, sort=("[ABC Revenue]", "Descending"))
    out.append(p.insight(ins["abc"]))

    p = Page("p10_basket", "Market Basket").slicers([("Product A", "mart_basket_pairs.product_a"), ("Product B", "mart_basket_pairs.product_b")])
    p.cards(["Product Pairs", "Pair Orders", "Top Pair Orders"])
    p.add("clusteredBarChart", "Top product pairs", 20, R1, 940, 760, {"Category": ["mart_basket_pairs.pair"], "Y": ["[Pair Orders]"]}, sort=("[Pair Orders]", "Descending"))
    p.add("tableEx", "Pairs", 974, R1, 926, H1, {"Values": ["mart_basket_pairs.product_a", "mart_basket_pairs.product_b", "[Pair Orders]"]}, sort=("[Pair Orders]", "Descending"))
    p.add("clusteredColumnChart", "Pair orders by first product", 974, R2, 226, H2, {"Category": ["mart_basket_pairs.product_a"], "Y": ["[Pair Orders]"]}, sort=("[Pair Orders]", "Descending"))
    out.append(p.insight(ins["basket"]))

    p = Page("p11_returns", "Returns & Cancellations").slicers(std)
    p.cards(["Cancelled Invoices", "Return Revenue", "Returned Units", "Return Rate %"])
    p.add("lineChart", "Return revenue by month", 20, R1, 940, H1, {"Category": ["dim_date.month_start"], "Y": ["[Return Revenue]"]})
    p.add("clusteredBarChart", "Return rate by country", 974, R1, 926, H1, {"Category": ["dim_country.country"], "Y": ["[Return Revenue]"]}, sort=("[Return Revenue]", "Descending"))
    p.add("tableEx", "Most cancelled products", 20, R2, 1180, H2, {"Values": ["dim_product.product", "[Return Revenue]", "[Returned Units]", "[Cancelled Invoices]"]}, sort=("[Return Revenue]", "Descending"))
    out.append(p.insight(ins["returns"]))

    p = Page("p12_forecast", "Demand Forecast").slicers([("Product", "dim_product.product")])
    p.cards(["Forecast Products", "Actual Units", "Model Units", "WAPE Model", "WAPE Baseline"])
    p.add("lineChart", "Weekly units: actual vs model vs baseline", 20, R1, 1880, H1, {"Category": ["forecast.week_start"], "Y": ["[Actual Units]", "[Model Units]", "[Baseline Units]"]})
    p.add("tableEx", "Forecast error by product", 20, R2, 1180, H2, {"Values": ["dim_product.product", "[Actual Units]", "[Model Units]", "[WAPE Model]", "[WAPE Baseline]"]}, sort=("[Actual Units]", "Descending"))
    out.append(p.insight(ins["forecast"]))

    p = Page("p13_rescue", "Revenue Rescue Plan").slicers([("Risk band", "churn_scores.risk_band"), ("Segment", "churn_scores.segment")])
    p.cards(["High Risk Customers", "Revenue at Risk", "CLV at Risk", "Champions %", "Return Rate %"])
    p.add("clusteredBarChart", "High-risk customers by segment", 20, R1, 940, H1, {"Category": ["churn_scores.segment"], "Y": ["[High Risk Customers]"]}, sort=("[High Risk Customers]", "Descending"))
    p.add("clusteredBarChart", "Predicted CLV at risk by segment", 974, R1, 926, H1, {"Category": ["churn_scores.segment"], "Y": ["[CLV at Risk]"]}, sort=("[CLV at Risk]", "Descending"))
    p.add("tableEx", "Win-back list by segment", 20, R2, 1180, H2, {"Values": ["churn_scores.segment", "[High Risk Customers]", "[Revenue at Risk]", "[CLV at Risk]", "[Avg Churn Probability]"]}, sort=("[Revenue at Risk]", "Descending"))
    out.append(p.insight(ins["rescue"]))
    return out


def solid(c: str) -> dict:
    return {"solid": {"color": c}}


TXT, MUTED, CARD, PAGE, LINE = "#E2E8F0", "#94A3B8", "#1E293B", "#0F172A", "#334155"
THEME = {
    "name": "RetailPulse Navy",
    "dataColors": ["#2DD4BF", "#FBBF24", "#818CF8", "#F472B6", "#38BDF8", "#A3E635", "#FB923C", "#C084FC", "#5EEAD4", "#FDE68A"],
    "background": CARD, "foreground": TXT, "tableAccent": "#2DD4BF",
    "good": "#2DD4BF", "neutral": "#FBBF24", "bad": "#F87171",
    "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": TXT},
                    "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": MUTED},
                    "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 26, "color": "#2DD4BF"},
                    "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": TXT}},
    "visualStyles": {
        "*": {"*": {
            "background": [{"show": True, "color": solid(CARD), "transparency": 0}],
            "border": [{"show": True, "color": solid(LINE), "radius": 8}],
            "title": [{"fontColor": solid(TXT), "fontFamily": "Segoe UI Semibold", "fontSize": 11}],
            "categoryAxis": [{"labelColor": solid(MUTED), "titleColor": solid(MUTED), "gridlineColor": solid(LINE)}],
            "valueAxis": [{"labelColor": solid(MUTED), "titleColor": solid(MUTED), "gridlineColor": solid(LINE)}],
            "legend": [{"labelColor": solid(TXT)}],
            "labels": [{"color": solid(TXT)}],
            "visualHeader": [{"background": solid(CARD), "foreground": solid(MUTED)}],
        }},
        "page": {"*": {"background": [{"color": solid(PAGE), "transparency": 0}],
                       "outspace": [{"color": solid(PAGE), "transparency": 0}]}},
        "card": {"*": {"labels": [{"color": solid("#2DD4BF"), "fontSize": 26}],
                       "categoryLabels": [{"color": solid(MUTED)}]}},
        "slicer": {"*": {"items": [{"fontColor": solid(TXT), "background": solid(CARD)}],
                         "header": [{"fontColor": solid(TXT)}]}},
        "tableEx": {"*": {"columnHeaders": [{"fontColor": solid("#2DD4BF"), "backColor": solid(PAGE)}],
                          "values": [{"fontColorPrimary": solid(TXT), "backColorPrimary": solid(CARD),
                                      "fontColorSecondary": solid(TXT), "backColorSecondary": solid("#243247")}],
                          "total": [{"fontColor": solid(TXT), "backColor": solid(PAGE)}],
                          "grid": [{"gridHorizontalColor": solid(LINE), "outlineColor": solid(LINE)}]}},
        "pivotTable": {"*": {"columnHeaders": [{"fontColor": solid("#2DD4BF"), "backColor": solid(PAGE)}],
                             "rowHeaders": [{"fontColor": solid(TXT), "backColor": solid(CARD)}],
                             "values": [{"fontColorPrimary": solid(TXT), "backColorPrimary": solid(CARD),
                                         "fontColorSecondary": solid(TXT), "backColorSecondary": solid("#243247")}],
                             "total": [{"fontColor": solid(TXT), "backColor": solid(PAGE)}],
                             "grid": [{"gridHorizontalColor": solid(LINE), "outlineColor": solid(LINE)}]}},
        "textbox": {"*": {"background": [{"show": True, "color": solid(CARD), "transparency": 0}]}},
    },
}


def build_report(con: duckdb.DuckDBPyConnection) -> None:
    rp = DASH / f"{NAME}.Report"
    if rp.exists():
        shutil.rmtree(rp)
    d = rp / "definition"
    wjson(rp / ".platform", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": NAME},
        "config": {"version": "2.0", "logicalId": tag("report")}})
    wjson(rp / "definition.pbir", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    theme = "retailpulse-navy.json"
    wjson(rp / "StaticResources" / "RegisteredResources" / theme, THEME)
    wjson(d / "version.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0"})
    wjson(d / "report.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.2.0/schema.json",
        "layoutOptimization": "None",
        "themeCollection": {"customTheme": {"name": theme, "reportVersionAtImport": "5.55", "type": "RegisteredResources"}},
        "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                              "items": [{"name": theme, "path": theme, "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True}})
    ps = pages(insights(con))
    wjson(d / "pages" / "pages.json", {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.name for p in ps], "activePageName": ps[0].name})
    for p in ps:
        wjson(d / "pages" / p.name / "page.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.3.0/schema.json",
            "name": p.name, "displayName": p.display, "displayOption": "FitToPage", "height": 1080, "width": 1920})
        title = textbox([(p.display, {"fontFamily": "Segoe UI Semibold", "fontSize": "20pt", "color": "#F8FAFC"}),
                         (p.subtitle, {"fontSize": "10pt", "color": "#94A3B8"})])
        title["visualContainerObjects"] = {"background": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#111827'")}}, "transparency": lit("0D")}}],
                                           "border": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit("'#2DD4BF'")}}, "radius": lit("0D")}}]}
        wjson(d / "pages" / p.name / "visuals" / f"{p.name}_title" / "visual.json", {
            "$schema": VC, "name": f"{p.name}_title",
            "position": {"x": 0, "y": 0, "z": 0, "width": 1920, "height": 70, "tabOrder": 0}, "visual": title})
        for i, (vname, x, y, w, h, v) in enumerate(p.visuals, 1):
            wjson(d / "pages" / p.name / "visuals" / vname / "visual.json", {
                "$schema": VC, "name": vname,
                "position": {"x": x, "y": y, "z": i * 1000, "width": w, "height": h, "tabOrder": i * 1000},
                "visual": v})
