"""Numbers behind the five-forces criteria and the ratings they imply (the "script candidates").

Only criteria that are pure numbers in 企業分析フレームワーク.md are decided here:
  ③ 買い手: largest single customer share of sales  (<10% 弱 / 10-20% 中 / >=20% 強, 強 is final)
  ④ 売り手: largest year-on-year fall of the gross margin (<2pt 弱 / 2-5pt 中 / >=5pt 強)
The writer may rate less favourably freely; a more favourable rating needs a reason (checked by build).
"""
from __future__ import annotations

import re
from pathlib import Path

import mdparse as M
from common import read_csv_rows
from ff_inputs import Found, raw_files
from ff_paths import Company

PERCENT = re.compile(r"(-?\d+(?:\.\d+)?)\s*%")
YEAR_JA = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月期")
YEAR_SLASH = re.compile(r"^(\d{4})/(\d{1,2})$")
NUMBER = re.compile(r"^-?[\d,]+(?:\.\d+)?$")
NO_MAJOR_CUSTOMER = ("該当なし", "該当事項なし", "記載なし", "記載を省略")
NOT_A_CUSTOMER = re.compile(r"^(合計|計|小計|その他|外部顧客|国内|海外|本邦)")
BUYER_LIMITS = (10.0, 20.0)
SUPPLIER_LIMITS = (2.0, 5.0)
SALES_LABELS = ("売上高", "売上収益", "営業収益")
GROSS_LABELS = ("売上総利益",)
COST_LABELS = ("売上原価",)


def _rate(value: float, limits: tuple[float, float]) -> str:
    low, high = limits
    return "弱" if value < low else "中" if value < high else "強"


def _number(cell: str) -> float | None:
    cell = cell.replace("△", "-").replace("▲", "-").strip()
    return float(cell.replace(",", "")) if NUMBER.match(cell) else None


def _months_apart(a: str, b: str) -> int:
    """'YYYY-MM' fiscal year ends -> months between them."""
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7])


def _year(cell: str) -> str | None:
    cell = cell.strip()
    m = YEAR_JA.search(cell) or YEAR_SLASH.match(cell)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m else None


# ---------- ③ 買い手 ----------

def buyer(found: Found) -> dict:
    """Largest customer share from the 主要な販売先 tables (latest 比率 column of each table)."""
    if found.status != "ok":
        return {"rating": None, "basis": "主要な販売先の記載が無い", "fixed": False, "value": None}
    best: tuple[float, str] | None = None
    for table in M.tables(found.body):
        header, rows = table[0], table[1:]
        cols = [i for i, h in enumerate(header) if "比率" in h or "割合" in h]
        if not cols:
            continue
        for row in rows:
            if not row or NOT_A_CUSTOMER.match(row[0].strip("* ")):
                continue
            m = PERCENT.search(row[cols[-1]]) if cols[-1] < len(row) else None
            if m and (best is None or float(m.group(1)) > best[0]):
                best = (float(m.group(1)), row[0])
    if best is None:
        # a share written as prose ('A社 25.3%') is not readable here; '10%以上' is the disclosure threshold
        prose_has_ratio = any(float(v) != BUYER_LIMITS[0] for v in PERCENT.findall(found.body))
        if any(w in found.body for w in NO_MAJOR_CUSTOMER) and not prose_has_ratio:
            return {"rating": "弱", "basis": "売上高の10%以上を占める販売先の記載なし", "fixed": False, "value": None}
        return {"rating": None, "basis": "主要な販売先の比率を読み取れない", "fixed": False, "value": None}
    value, name = best
    rating = _rate(value, BUYER_LIMITS)
    return {"rating": rating, "value": value, "fixed": rating == "強",
            "basis": f"最大顧客比率 {value:.1f}%（{name}、直近期）。目安: 10%未満 弱 / 10〜20% 中 / 20%以上 強"}


# ---------- ④ 売り手 ----------

def _margins_from_csv(path: Path) -> dict[str, float]:
    by_year: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(path):
        item, period = row.get("item", ""), row.get("period_end", "")[:7]
        if item in ("net_sales", "cost_of_sales") and period:
            try:
                by_year.setdefault(period, {})[item] = float(row.get("value", ""))
            except ValueError:
                continue
    return {y: (v["net_sales"] - v["cost_of_sales"]) / v["net_sales"] * 100
            for y, v in by_year.items() if v.get("net_sales") and "cost_of_sales" in v}


def _margins_from_table(table: list[list[str]]) -> dict[str, float]:
    years = {i: _year(c) for i, c in enumerate(table[0])}
    rows = {r[0].strip(): r for r in table[1:] if r}

    def pick(labels: tuple[str, ...]) -> list[str] | None:
        # amount rows only: '売上高総利益率' / '売上総利益率' are ratios, not amounts
        return next((rows[k] for k in rows if any(k.startswith(lb) for lb in labels) and "率" not in k), None)

    sales, gross, cost = pick(SALES_LABELS), pick(GROSS_LABELS), pick(COST_LABELS)
    out = {}
    for i, year in years.items():
        if not year or sales is None or i >= len(sales):
            continue
        s = _number(sales[i])
        g = _number(gross[i]) if gross is not None and i < len(gross) else None
        if g is None and cost is not None and i < len(cost) and s is not None:
            c = _number(cost[i])
            g = s - c if c is not None else None
        if s and g is not None:
            out[year] = g / s * 100
    return out


def gross_margins(company: Company) -> tuple[dict[str, float], list[str]]:
    """Gross margin (%) by fiscal year end (YYYY-MM): data/financials.csv first, then the P/L tables
    in raw financials-historical and yuho files (newest first). Returns (margins, sources)."""
    margins: dict[str, float] = {}
    sources: list[str] = []
    csv_path = company.path / "data" / "financials.csv"
    from_csv = _margins_from_csv(csv_path)
    if from_csv:
        margins.update(from_csv)
        sources.append(company.rel(csv_path))
    for kind in ("financials-historical", "yuho"):
        for _, path in raw_files(company, kind):
            added = False
            for table in M.tables(path.read_text(encoding="utf-8")):
                for year, value in _margins_from_table(table).items():
                    if year not in margins:
                        margins[year] = value
                        added = True
            if added:
                sources.append(company.rel(path))
    return dict(sorted(margins.items())), sources


def supplier(company: Company) -> dict:
    margins, sources = gross_margins(company)
    series = [{"year": y, "gross_margin": round(v, 1)} for y, v in margins.items()]
    if len(margins) < 2:
        return {"rating": None, "fixed": False, "series": series, "sources": sources, "max_drop": None,
                "basis": "粗利率の時系列が2年分そろわない"}
    years = list(margins)
    pairs = list(zip(years, years[1:]))
    consecutive = [(a, b) for a, b in pairs if _months_apart(a, b) == 12]  # year-on-year only
    gaps = [f"{a}→{b}" for a, b in pairs if _months_apart(a, b) != 12]
    gap_note = f"。年の欠け（比較から除外）: {', '.join(gaps)}" if gaps else ""
    if not consecutive:
        return {"rating": None, "fixed": False, "series": series, "sources": sources, "max_drop": None,
                "basis": f"連続する2年度の粗利率がそろわない{gap_note}"}
    drop, start, end = max((margins[a] - margins[b], a, b) for a, b in consecutive)
    if drop <= 0:
        return {"rating": "弱", "fixed": False, "series": series, "sources": sources, "max_drop": 0.0,
                "basis": f"粗利率は {years[0]}〜{years[-1]} に前年比で低下した年なし{gap_note}"}
    return {"rating": _rate(drop, SUPPLIER_LIMITS), "fixed": False, "series": series, "sources": sources,
            "max_drop": round(drop, 1),
            "basis": (f"粗利率の前年比の最大低下 {drop:.1f}pt（{start} {margins[start]:.1f}% → {end} "
                      f"{margins[end]:.1f}%）。目安: 2pt未満 弱 / 2〜5pt 中 / 5pt以上 強{gap_note}")}


# ---------- ⑤ 業界内の競争（数値の提示のみ） ----------

def _growth_in_table(title: str, table: list[list[str]]) -> list[str]:
    header = table[0]
    col = next((i for i, h in enumerate(header) if "CAGR" in h), None)
    if col is not None:  # one market per row, a CAGR column
        return [f"{row[0]}: {row[col]}" for row in table[1:] if col < len(row) and not M.is_blank(row[col])]
    return [f"{title}: {row[0]} {row[1]}" for row in table[1:]  # key/value table, a CAGR row
            if len(row) > 1 and "CAGR" in row[0] and not M.is_blank(row[1])]


def market_growth(found: Found) -> list[str]:
    """'市場: CAGR' strings from the market-size tables, labelled by their ### sub-heading."""
    if found.status != "ok":
        return []
    out: list[str] = []
    for chunk in re.split(r"^###\s+", found.body, flags=re.M):
        title = chunk.splitlines()[0].strip() if chunk.strip() and not chunk.lstrip().startswith("|") else ""
        for table in M.tables(chunk):
            out += _growth_in_table(title, table)
    return out


def candidates(company: Company, found: dict[str, Found]) -> dict[str, dict]:
    """Script candidate per factor key (entry/substitutes/buyers/suppliers/rivalry)."""
    none = {"rating": None, "fixed": False, "basis": "数値だけで決まる基準なし"}
    growth = market_growth(found["market_size"])
    rivalry = dict(none, basis="数値だけで決まる基準なし。市場の成長率: " + ("; ".join(growth[:4]) or "—"))
    return {"entry": none, "substitutes": none, "buyers": buyer(found["customers"]),
            "suppliers": supplier(company), "rivalry": rivalry}
