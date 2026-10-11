"""Render markdown tables from companies/<dir>/data/*.csv for pasting into raw/summaries.

Usage:
  render_tables.py financials <company> [--years 10]   # data/financials.csv (year columns)
  render_tables.py forecasts  <company>                # data/tdnet_facts.csv: 期初予想 / 最新予想 / 実績
  render_tables.py quarterly  <company>                # data/tdnet_facts.csv: 四半期累計の実績
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import company_dir, utf8_stdout  # noqa: E402

ITEM_LABELS = {
    "summary.net_sales": "売上高", "cost_of_sales": "売上原価", "sga": "販売費及び一般管理費",
    "operating_income": "営業利益", "summary.ordinary_income": "経常利益",
    "extraordinary_income": "特別利益", "extraordinary_loss": "特別損失",
    "summary.net_income": "親会社株主に帰属する当期純利益", "summary.eps": "EPS（円）",
    "summary.total_assets": "総資産", "summary.net_assets": "純資産",
    "summary.equity_ratio": "自己資本比率（%）", "summary.bps": "BPS（円）",
    "summary.roe": "ROE（%）", "cash_and_deposits": "現金及び預金", "current_assets": "流動資産",
    "current_liabilities": "流動負債", "receivables": "売上債権", "inventories": "棚卸資産",
    "short_term_loans": "短期借入金", "long_term_loans": "長期借入金", "bonds": "社債",
    "summary.cfo": "営業CF", "summary.cfi": "投資CF", "summary.cff": "財務CF",
    "depreciation": "減価償却費", "capex_tangible": "有形固定資産の取得",
    "capex_intangible": "無形固定資産の取得", "acquisition_of_subsidiaries": "子会社株式の取得（連結範囲変更）",
    "dividends_paid": "配当金の支払額", "treasury_stock_purchase": "自己株式の取得",
    "summary.dps": "1株配当（円）", "summary.payout_ratio": "配当性向（%）",
    "summary.per": "PER（倍、期末）", "summary.employees": "従業員数",
}
TDNET_ITEMS = [("NetSales", "売上高"), ("OperatingIncome", "営業利益"),
               ("OrdinaryIncome", "経常利益"), ("ProfitAttributableToOwnersOfParent", "純利益"),
               ("NetIncomePerShare", "EPS（円）")]
FORECAST_CTX = re.compile(r"^(Current|Next)YearDuration_ConsolidatedMember_ForecastMember$")
ANNUAL_RESULT_CTX = "CurrentYearDuration_ConsolidatedMember_ResultMember"
QUARTER_CTX = re.compile(r"^CurrentAccumulatedQ(\d)Duration_ConsolidatedMember_ResultMember$")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"not found: {path}")
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _fmt(value: str) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value or "—"
    return f"{number:,.0f}" if abs(number) >= 1000 or number == int(number) else f"{number:,.2f}"


def financials_table(rows: list[dict], years: int) -> str:
    grid: dict[str, dict[str, str]] = defaultdict(dict)
    for r in rows:
        grid[r["item"]][r["period_end"]] = r["value"]
    periods = sorted({r["period_end"] for r in rows})[-years:]
    lines = ["| 項目（百万円） | " + " | ".join(p[:7] for p in periods) + " |",
             "|---|" + "---|" * len(periods)]
    for item, label in ITEM_LABELS.items():
        if item in grid:
            lines.append(f"| {label} | " + " | ".join(_fmt(grid[item].get(p, "")) for p in periods) + " |")
    return "\n".join(lines)


def _next_fy(fy_end: str) -> str:
    return f"{int(fy_end[:4]) + 1}{fy_end[4:]}" if fy_end else ""


def forecast_records(rows: list[dict]) -> list[dict]:
    """One record per (target FY, kind) with the TDNET_ITEMS values."""
    docs: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        docs[r["doc_id"]].append(r)
    records: dict[tuple, dict] = {}
    for doc_rows in docs.values():
        head = doc_rows[0]
        is_quarterly = any("Accumulated" in r["context"] for r in doc_rows)
        for r in doc_rows:
            match = FORECAST_CTX.match(r["context"])
            if match:
                target = _next_fy(head["fiscal_year_end"]) if match.group(1) == "Next" else head["fiscal_year_end"]
                kind = "期初予想" if match.group(1) == "Next" and not is_quarterly else "期中予想"
            elif r["context"] == ANNUAL_RESULT_CTX and not is_quarterly:
                target, kind = head["fiscal_year_end"], "実績"
            else:
                continue
            rec = records.setdefault((target, kind, head["filing_date"]), {
                "target": target, "kind": kind, "filing_date": head["filing_date"], "doc_id": head["doc_id"]})
            rec[r["element"]] = r["value"]
    return sorted(records.values(), key=lambda x: (x["target"], x["kind"] != "期初予想",
                                                   x["kind"] == "実績", x["filing_date"]))


def forecasts_table(rows: list[dict]) -> str:
    head = "| 対象年度 | 区分 | " + " | ".join(lbl for _, lbl in TDNET_ITEMS) + " | 公表日 | doc_id |"
    lines = [head, "|---|---|" + "---|" * len(TDNET_ITEMS) + "---|---|"]
    for rec in forecast_records(rows):
        vals = " | ".join(_fmt(rec.get(el, "")) for el, _ in TDNET_ITEMS)
        lines.append(f"| {rec['target'][:7]} | {rec['kind']} | {vals} | {rec['filing_date']} | {rec['doc_id']} |")
    return "\n".join(lines)


def quarterly_table(rows: list[dict]) -> str:
    recs: dict[tuple, dict] = {}
    for r in rows:
        match = QUARTER_CTX.match(r["context"])
        if match:
            recs.setdefault((r["fiscal_year_end"], match.group(1)), {})[r["element"]] = r["value"]
    lines = ["| 期 | 四半期（累計） | " + " | ".join(lbl for _, lbl in TDNET_ITEMS) + " |",
             "|---|---|" + "---|" * len(TDNET_ITEMS)]
    for (fy, q), vals in sorted(recs.items()):
        lines.append(f"| {fy[:7]} | Q{q} | " + " | ".join(_fmt(vals.get(el, "")) for el, _ in TDNET_ITEMS) + " |")
    return "\n".join(lines)


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("table", choices=["financials", "forecasts", "quarterly"])
    ap.add_argument("company")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()
    data = company_dir(args.company) / "data"
    if args.table == "financials":
        print(financials_table(_read(data / "financials.csv"), args.years))
    elif args.table == "forecasts":
        print(forecasts_table(_read(data / "tdnet_facts.csv")))
    else:
        print(quarterly_table(_read(data / "tdnet_facts.csv")))


if __name__ == "__main__":
    main()
