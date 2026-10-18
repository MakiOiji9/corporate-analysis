"""Yearly series behind the cash-flow analysis (企業分析フレームワーク.md 2-4).

Fields: operating / investing / financing CF, sales, net income (attributable to owners of the parent),
trade receivables, inventories, dividends paid, treasury stock purchased, capital expenditure and the
acquisition of subsidiaries. Amounts are in 百万円 (a US company: the raw's currency unit as written).
Outflows (dividends, buybacks, capex, acquisitions) are stored as positive amounts.

The sources, first primary value per year winning (pf_series.merge):
data/tdnet_facts.csv and data/financials.csv, then every table of the raw 有報 (10-K / 424B4 too) and
財務時系列 (the CF statement lines before the 株主還元 table, so 配当金の支払額 wins over 配当総額), then the
決算短信's 配当金総額 as the last fallback for the dividends. The table readers are pf_series' with the CF labels.
"""
from __future__ import annotations

import re

import pf_series as S
from common import read_csv_rows
from ff_inputs import raw_files

FIELDS = ("cfo", "cfi", "cff", "sales", "net_income", "receivables", "inventories", "dividends", "buybacks",
          "capex", "acquisitions")
OUTFLOWS = ("dividends", "buybacks", "capex", "acquisitions")
LABELS = {
    "cfo": ("営業活動によるキャッシュ・フロー", "営業活動によるキャッシュフロー", "営業キャッシュ・フロー", "営業CF"),
    "cfi": ("投資活動によるキャッシュ・フロー", "投資活動によるキャッシュフロー", "投資キャッシュ・フロー", "投資CF"),
    "cff": ("財務活動によるキャッシュ・フロー", "財務活動によるキャッシュフロー", "財務キャッシュ・フロー", "財務CF"),
    "sales": S.LABELS["sales"],
    "net_income": S.LABELS["net_income"],
    "receivables": ("売上債権", "受取手形、売掛金及び契約資産", "受取手形及び売掛金", "売掛金及び契約資産", "売掛金"),
    "inventories": ("棚卸資産", "たな卸資産"),
    "dividends": ("配当金の支払額", "配当金支払額", "配当金の支払"),
    "dividends_declared": ("配当総額", "配当金の総額", "配当金総額"),
    "buybacks": ("自己株式の取得による支出", "自己株式の取得", "自社株買い"),
    "capex": ("有形固定資産の取得による支出", "設備投資額", "設備投資"),
    "acquisitions": ("連結範囲の変更を伴う子会社株式の取得による支出", "連結範囲の変更を伴う子会社株式の取得",
                     "子会社株式取得による支出"),
}
# unlike the profitability reader, the キャッシュ・フロー / 株主還元 / 配当 sections are read
SKIP_SECTION = re.compile(r"予想|計画|四半期|中間|CAGR|提出会社|単体|個別|子会社|セグメント")
YUHO_SECTION = re.compile(r"主要な経営指標|財務|損益|貸借|キャッシュ|設備投資")
CF_FIELDS = S.Fields(LABELS, (), SKIP_SECTION)

CSV_ITEMS = {"cfo": "cfo", "cfi": "cfi", "cff": "cff", "net_sales": "sales", "net_income": "net_income",
             "receivables": "receivables", "inventories": "inventories", "dividends_paid": "dividends",
             "treasury_stock_purchase": "buybacks", "capex_tangible": "capex",
             "acquisition_of_subsidiaries": "acquisitions"}
TDNET_ITEMS = {"CashFlowsFromOperatingActivities": "cfo", "CashFlowsFromInvestingActivities": "cfi",
               "CashFlowsFromFinancingActivities": "cff", "NetSales": "sales",
               "ProfitAttributableToOwnersOfParent": "net_income"}
TDNET_DIVIDEND = "TotalDividendPaidAnnual"  # 配当金総額 of the year (declared, parent-only): the last fallback
TDNET_DIVIDEND_SOURCE = "data/tdnet_facts.csv（決算短信の配当金総額）"


def _dividend_fallback(company) -> list[tuple[str, str, S.Value]]:
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return []
    out = []
    for row in read_csv_rows(path):
        context = row.get("context", "")
        if row.get("element") != TDNET_DIVIDEND or "Annual" not in context or "Result" not in context:
            continue
        fy = (row.get("fiscal_year_end") or "")[:7]
        if not fy or not context.startswith(("CurrentYear", "PriorYear")):
            continue
        try:
            value = float(row.get("value", ""))
        except ValueError:
            continue
        year = fy if context.startswith("CurrentYear") else S._shift_year(fy, -12)
        out.append(("dividends_declared", year, S.Value(value, TDNET_DIVIDEND_SOURCE, True)))
    return out


def _with_declared_dividends(series: S.Series) -> S.Series:
    """配当金の支払額 (cash paid, any table) first; the declared 配当総額 only for a year without it."""
    paid = {**series.get("dividends_declared", {}), **series["dividends"]}
    return {**{f: v for f, v in series.items() if f != "dividends_declared"}, "dividends": dict(sorted(paid.items()))}


def _positive_outflows(series: S.Series) -> S.Series:
    """Outflows as positive amounts ('△91,975' in the CF statement and '91百万円' in 株主還元 mean the same)."""
    return {f: ({y: S.Value(abs(v.value), v.source, v.primary) for y, v in values.items()} if f in OUTFLOWS
                else values) for f, values in series.items()}


def self_series(company) -> S.Series:
    observations = S.from_data(company, CSV_ITEMS, TDNET_ITEMS)
    for kind, include in (("yuho", YUHO_SECTION), ("financials-historical", None)):
        for _, path in raw_files(company, kind):
            observations += S.from_raw_text(path.read_text(encoding="utf-8"), path.name, include, CF_FIELDS)
    observations += _dividend_fallback(company)
    merged = S.merge(observations, FIELDS + ("dividends_declared",))
    return _positive_outflows(_with_declared_dividends(merged))
