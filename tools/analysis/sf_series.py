"""Yearly balance-sheet and cash-flow series behind the safety analysis (企業分析フレームワーク.md 2-3).

Fields: total assets, equity (自己資本), equity ratio, interest-bearing debt (有利子負債, or the sum of its
loan / bond lines), cash and equivalents (or 現金及び預金), current assets and liabilities, the three cash flows,
sales, operating income and net income. Amounts are in 百万円 for a Japanese company and in the unit of the raw
tables for a US one (unit_label); the equity ratio in %.

The reading reuses pf_series (the same tables, unit handling and primary-over-secondary rule) with the safety
Fields: data/financials.csv and data/tdnet_facts.csv first, then the tables of the raw 有報 and 財務時系列 (the
cash-flow sections included), then the target's own rows in competitors.md「安全性の指標」.
The peers: competitors.md「安全性の指標」, with the equity ratio also taken from「収益性の分解」and「ROE・自己資本比率」.
A year with neither a 有利子負債 line nor any loan / bond line has no debt value (it is never assumed to be 0).
"""
from __future__ import annotations

import re

import pf_series as S
from ff_inputs import Found, raw_files
from sf_inputs import PEER_SAFETY_SECTION
from tc_metrics import _is_self

FIELDS = ("total_assets", "equity", "equity_ratio", "debt", "debt_short", "debt_current_long", "debt_long",
          "debt_bonds", "debt_bonds_current", "debt_cp", "cash", "cash_deposits", "current_assets",
          "current_liabilities", "cfo", "cfi", "cff", "sales", "operating_income", "net_income")
DEBT_PARTS = ("debt_short", "debt_current_long", "debt_long", "debt_bonds", "debt_bonds_current", "debt_cp")
LABELS = {
    "total_assets": S.LABELS["total_assets"],
    "equity": S.LABELS["equity"],
    "equity_ratio": S.LABELS["equity_ratio"],
    "debt": ("有利子負債", "有利子負債残高", "有利子負債合計"),
    "debt_short": ("短期借入金",),
    "debt_current_long": ("1年内返済予定の長期借入金", "1年以内返済予定の長期借入金", "一年内返済予定の長期借入金"),
    "debt_long": ("長期借入金",),
    "debt_bonds": ("社債",),
    "debt_bonds_current": ("1年内償還予定の社債", "1年以内償還予定の社債", "一年内償還予定の社債"),
    "debt_cp": ("コマーシャル・ペーパー", "コマーシャルペーパー"),
    "cash": ("現金及び現金同等物", "現金及び現金同等物の期末残高", "現金同等物", "現金等"),
    "cash_deposits": ("現金及び預金",),
    "current_assets": ("流動資産", "流動資産合計"),
    "current_liabilities": ("流動負債", "流動負債合計"),
    "cfo": ("営業CF", "営業活動によるキャッシュ・フロー", "営業キャッシュ・フロー"),
    "cfi": ("投資CF", "投資活動によるキャッシュ・フロー", "投資キャッシュ・フロー"),
    "cff": ("財務CF", "財務活動によるキャッシュ・フロー", "財務キャッシュ・フロー"),
    "sales": S.LABELS["sales"],
    "operating_income": ("営業利益",),
    "net_income": S.LABELS["net_income"],
}
# the profitability skip list without キャッシュ (the cash flows are read here)
SKIP_SECTION = re.compile(r"予想|計画|四半期|中間|CAGR|提出会社|単体|個別|子会社|セグメント|株主還元|配当")
YUHO_SECTION = re.compile(r"主要な経営指標|財務|損益|貸借|キャッシュ")
SAFETY = S.Fields(LABELS, ("equity_ratio",), SKIP_SECTION)

# data/financials.csv items (the 'summary.' prefix is removed before the lookup)
CSV_ITEMS = {"total_assets": "total_assets", "equity_ratio": "equity_ratio", "cash_equivalents": "cash",
             "cash_and_deposits": "cash_deposits", "current_assets": "current_assets",
             "current_liabilities": "current_liabilities", "short_term_loans": "debt_short",
             "current_portion_long_term_loans": "debt_current_long", "long_term_loans": "debt_long",
             "bonds": "debt_bonds", "cfo": "cfo", "cfi": "cfi", "cff": "cff", "net_sales": "sales",
             "operating_income": "operating_income", "net_income": "net_income"}
# edgar.py writes StockholdersEquity (the parent's equity, without the minority interest) as net_assets
US_CSV_ITEMS = {**CSV_ITEMS, "net_assets": "equity"}
TDNET_ITEMS = {"TotalAssets": "total_assets", "OwnersEquity": "equity", "CapitalAdequacyRatio": "equity_ratio",
               "CashAndEquivalentsEndOfPeriod": "cash", "CashFlowsFromOperatingActivities": "cfo",
               "CashFlowsFromInvestingActivities": "cfi", "CashFlowsFromFinancingActivities": "cff",
               "NetSales": "sales", "OperatingIncome": "operating_income",
               "ProfitAttributableToOwnersOfParent": "net_income"}
JAPAN_TICKER = re.compile(r"^\d{3}[0-9A-Z]$")
PEER_COLUMNS = (("company", ("会社",)), ("year", ("年度", "決算期")), ("source", ("出典", "確度")))
PEER_SECTIONS = (("peer_safety", SAFETY, PEER_SAFETY_SECTION), ("peer_dupont", S.PROFITABILITY, "収益性の分解"),
                 ("peer_roe", S.PROFITABILITY, "ROE・自己資本比率"))
NAME_NOTE = re.compile(r"[（(][^）)]*[）)]|株式会社|\s")
UNIT_NOTE = re.compile(r"単位[:：]\s*([^\s（(。、,|]+)")
MAX_PEERS = 5


# ---------- derived fields ----------

def with_debt(series: S.Series) -> S.Series:
    """有利子負債 where only its loan / bond lines are known (their sum). Returns a new Series."""
    debt = dict(series["debt"])
    years = {y for part in DEBT_PARTS for y in series[part]}
    for year in sorted(years - set(debt)):
        parts = [series[part][year] for part in DEBT_PARTS if year in series[part]]
        debt[year] = S.Value(sum(v.value for v in parts), "借入金・社債の内訳の合計",
                             all(v.primary for v in parts))
    return {**series, "debt": dict(sorted(debt.items()))}


def with_cash(series: S.Series) -> S.Series:
    """現金及び現金同等物, else 現金及び預金 (time deposits included). Returns a new Series."""
    cash = dict(series["cash"])
    for year, value in series["cash_deposits"].items():
        if year not in cash:
            cash[year] = S.Value(value.value, f"現金及び預金（{value.source}）", value.primary)
    return {**series, "cash": dict(sorted(cash.items()))}


def finish(series: S.Series) -> S.Series:
    return with_cash(with_debt(S.with_equity(series)))


# ---------- competitors.md tables ----------

def table_rows(found: Found, fields: S.Fields, section: str) -> list[dict]:
    """Rows of a competitors.md table with 会社 and 年度 columns: name, year and the values."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    out = []
    for table in S.M.tables(found.body):
        header = table[0]
        cols = {key: next((i for i, h in enumerate(header) if any(w in h for w in words)), None)
                for key, words in PEER_COLUMNS}
        if cols["company"] is None or cols["year"] is None:
            continue
        names = {i: S.field_of(h, fields) for i, h in enumerate(header)}
        for row in table[1:]:
            year = S.period(row[cols["year"]]) if cols["year"] < len(row) else None
            if not year:
                continue
            source = row[cols["source"]] if cols["source"] is not None and cols["source"] < len(row) else ""
            primary = not S.SECONDARY.search(source)
            parsed = [(name, year, v) for i, name in names.items() if name and i < len(row)
                      if (v := S._parse(name, row[i], S.unit_of(header[i]) or 1.0, fields)) is not None]
            values = {f: S.Value(v, f"competitors「{section}」", primary) for f, _, v in S.derive_equity(parsed)
                      if f in FIELDS}
            out.append({"name": row[cols["company"]].replace("*", "").strip(), "year": year, "values": values})
    return out


def base_name(name: str) -> str:
    """'アルファ社（1111）' and 'アルファ社' are the same company across the competitors.md sections."""
    return NAME_NOTE.sub("", name)


# ---------- series ----------

def _csv_items(company) -> dict[str, str]:
    return CSV_ITEMS if JAPAN_TICKER.match(company.ticker.upper()) else US_CSV_ITEMS


def unit_label(company) -> str:
    """The unit of the target's amounts: 百万円 for a Japanese company (pf_series converts 千円 / 億円); a US
    company's amounts stay in the unit of its raw tables (千米ドル, 百万ドル ...), read from the 財務時系列 header."""
    if JAPAN_TICKER.match(company.ticker.upper()):
        return "百万円"
    for _, path in raw_files(company, "financials-historical"):
        m = UNIT_NOTE.search(path.read_text(encoding="utf-8"))
        if m:
            return m.group(1)
    return "raw の通貨単位"


def self_series(company, found: dict[str, Found] | None = None) -> S.Series:
    observations = S.from_data(company, _csv_items(company), TDNET_ITEMS)
    for kind, include in (("yuho", YUHO_SECTION), ("financials-historical", None)):
        for _, path in raw_files(company, kind):
            observations += S.from_raw_text(path.read_text(encoding="utf-8"), path.name, include, SAFETY)
    if found is not None:
        own = [r for r in table_rows(found["peer_safety"], SAFETY, PEER_SAFETY_SECTION) if _is_self(r["name"], company)]
        observations += [(f, r["year"], v) for r in own for f, v in r["values"].items()]
    return finish(S.merge(observations, FIELDS))


def peer_series(company, found: dict[str, Found]) -> list[dict]:
    """[{name, series}] for up to MAX_PEERS peers, in the order they first appear («安全性の指標» first)."""
    names: dict[str, str] = {}
    observations: dict[str, list] = {}
    for key, fields, section in PEER_SECTIONS:
        for r in table_rows(found[key], fields, section):
            if _is_self(r["name"], company):
                continue
            base = base_name(r["name"])
            names.setdefault(base, r["name"])
            observations.setdefault(base, []).extend((f, r["year"], v) for f, v in r["values"].items())
    return [{"name": names[b], "series": finish(S.merge(obs, FIELDS))}
            for b, obs in list(observations.items())[:MAX_PEERS]]
