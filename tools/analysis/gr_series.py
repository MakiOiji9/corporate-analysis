"""Yearly series behind the growth analysis (企業分析フレームワーク.md 2-2).

Fields: sales, operating income, net income (attributable to owners of the parent), EPS, the outflow for
acquiring subsidiaries (連結範囲の変更を伴う) and the share buybacks. Amounts are in 百万 of the reporting
currency (円 / ドル), EPS in the currency per share.

Read order (the first primary value per field and year wins; a secondary one only fills a gap):
data/tdnet_facts.csv (決算短信) → data/financials.csv (EDINET / EDGAR) → the tables of the raw 有報 and
財務時系列 (pf_series' cell and label rules; amounts in parentheses are negative, dollar units are read too).
Forecasts, quarters, the parent-only figures and segment tables are never read into the actuals.

EPS is put on the basis of the newest year: where net income ÷ EPS (the implied share count) jumps by a near
integer factor between two consecutive years, a share split (or a consolidation) is assumed and the earlier
years are divided by it. Each such step is returned so the md and the warnings can show it.

Also read here: the company plan (期初予想) and the actual per year (tdnet_facts.csv, then the raw「会社計画」
table) and the raw「M&A・連結範囲の変更」table (the acquired company's annual sales).
"""
from __future__ import annotations

import re

import mdparse as M
import pf_series as S
from common import read_csv_rows
from ff_inputs import Found, raw_files
from render_tables import forecast_records

Value = S.Value
Series = dict[str, dict[str, S.Value]]

FIELDS = ("sales", "operating_income", "net_income", "eps", "acquisition", "buyback")
PLAIN_FIELDS = ("eps",)  # per-share figures: never scaled to 百万
LABELS = {
    "sales": S.LABELS["sales"],
    "operating_income": ("営業利益", "営業損益", "事業利益"),
    "net_income": S.LABELS["net_income"],
    "eps": ("EPS", "基本EPS", "1株当たり当期純利益", "1株当たり当期利益", "基本的1株当たり当期利益",
            "1株当たり当期純損益"),
    "acquisition": ("連結範囲の変更を伴う子会社株式の取得", "子会社株式の取得", "子会社株式取得による支出",
                    "事業譲受", "事業の譲受"),
    "buyback": ("自己株式の取得による支出", "自己株式の取得", "自社株買い"),
}
AMOUNT_EXCLUDE = S.AMOUNT_EXCLUDE + ("伴わない",)
EPS_EXCLUDE = ("希薄化", "潜在株式", "調整後", "前期比", "増減", ":", "：")
UNIT_WORDS = "千円|百万円|億円|千米ドル|百万米ドル|千ドル|百万ドル"
UNIT_TO_MILLION = {"千円": 1e-3, "百万円": 1.0, "億円": 100.0, "千米ドル": 1e-3, "千ドル": 1e-3,
                   "百万米ドル": 1.0, "百万ドル": 1.0}
UNIT_IN_LABEL = re.compile(rf"[（(]\s*({UNIT_WORDS})")
UNIT_IN_TEXT = re.compile(rf"単位[^。\n|]{{0,12}}?({UNIT_WORDS})|({UNIT_WORDS})単位")
PARENTHESES = re.compile(r"^\(\s*([\d,]+(?:\.\d+)?)\s*\)")
SKIP_SECTION = re.compile(r"予想|計画|四半期|CAGR|提出会社|単体|個別|セグメント|減収・減益|M&A|配当")
YUHO_SECTION = S.YUHO_SECTION

CSV_ITEMS = {"net_sales": "sales", "operating_income": "operating_income", "net_income": "net_income",
             "eps": "eps", "acquisition_of_subsidiaries": "acquisition", "treasury_stock_purchase": "buyback"}
TDNET_ITEMS = {"NetSales": "sales", "OperatingIncome": "operating_income",
               "ProfitAttributableToOwnersOfParent": "net_income", "NetIncomePerShare": "eps"}

# an implied share count that changes by one of these factors (or its inverse) within SPLIT_TOLERANCE is a split
# (5:4, 3:2 and the integer splits); a larger change is more likely a unit slip and is left alone (warned)
SPLIT_FACTORS = (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 25.0, 50.0, 100.0)
SPLIT_TOLERANCE = 0.05
SPLIT_IMPLAUSIBLE = 150.0


# ---------- cells ----------

def _clean(cell: str) -> str:
    """'**(178,821)**' -> '-178,821' (US statements put losses in parentheses)."""
    text = cell.replace("*", "").strip()
    m = PARENTHESES.match(text)
    return f"-{m.group(1)}{text[m.end():]}" if m else text


def plain(cell: str) -> float | None:
    """A per-share number as written: '36.20' / '(4.28)' / '94.02（分割前）' / '1,234.5'."""
    m = S.LEADING_NUMBER.match(_clean(cell))
    return S._signed(m.group(0)) if m else None


def amount(cell: str, factor: float) -> float | None:
    return S.amount(_clean(cell), factor)


def unit_of(text: str) -> float | None:
    m = UNIT_IN_LABEL.search(text) or UNIT_IN_TEXT.search(text)
    return UNIT_TO_MILLION[next(g for g in m.groups() if g)] if m else None


def field_of(label: str) -> str | None:
    text = S._label(label)
    if any(S._names(text, lb) for lb in LABELS["eps"]) and not any(w in text for w in EPS_EXCLUDE):
        return "eps"
    for field, labels in LABELS.items():
        if field in PLAIN_FIELDS:
            continue
        if any(S._names(text, lb) for lb in labels) and not any(w in text for w in AMOUNT_EXCLUDE):
            return field
    return None


def _priority(field: str, label: str) -> int:
    text = S._label(label)
    return next((i for i, lb in enumerate(LABELS[field]) if S._names(text, lb)), len(LABELS[field]))


def _parse(field: str, cell: str, factor: float) -> float | None:
    return plain(cell) if field in PLAIN_FIELDS else amount(cell, factor)


# ---------- tables ----------

def _best(labels: list[tuple[int, str]]) -> dict[str, int]:
    best: dict[str, tuple[int, int]] = {}
    for index, label in labels:
        field = field_of(label)
        if field and (field not in best or _priority(field, label) < best[field][0]):
            best[field] = (_priority(field, label), index)
    return {field: index for field, (_, index) in best.items()}


def read_table(table: list[list[str]], default_factor: float) -> list[tuple[str, str, float]]:
    """(field, year, value) of a table with years as columns or as rows."""
    header = table[0]
    columns = {i: S.period(c) for i, c in enumerate(header) if i > 0}
    columns = {i: y for i, y in columns.items() if y}
    out = []
    if len(columns) >= 2:  # years as columns, items as rows
        table_factor = unit_of(header[0]) or default_factor
        rows = {i: row for i, row in enumerate(table[1:]) if row}
        for field, index in _best([(i, row[0]) for i, row in rows.items()]).items():
            row = rows[index]
            factor = unit_of(row[0]) or table_factor
            for col, year in columns.items():
                if col < len(row) and (value := _parse(field, row[col], factor)) is not None:
                    out.append((field, year, value))
        return out
    for field, col in _best(list(enumerate(header))).items():  # years as rows, items as columns
        factor = unit_of(header[col]) or default_factor
        for row in table[1:]:
            year = S.period(row[0]) if row else None
            if year and col < len(row) and (value := _parse(field, row[col], factor)) is not None:
                out.append((field, year, value))
    return out


def from_raw_text(text: str, source: str, include: re.Pattern | None = None) -> list[tuple[str, str, Value]]:
    first = S.SECTION.search(text)
    file_factor = unit_of(text[:first.start()] if first else text) or 1.0
    out = []
    for titles, body in S.sections(text):
        if SKIP_SECTION.search(titles) or (include and not include.search(titles)):
            continue
        factor = unit_of(titles) or unit_of(S._prose(body)) or file_factor
        primary = not S.SECONDARY.search(titles)
        label = f"{source}「{titles.split(' / ')[-1][:30]}」"
        for table in M.tables(body):
            for field, year, value in read_table(table, factor):
                out.append((field, year, Value(value, label, primary)))
    return out


# ---------- data/*.csv ----------

def _float(text: str | None) -> float | None:
    try:
        return float(text or "")
    except ValueError:
        return None


def from_tdnet(company) -> list[tuple[str, str, Value]]:
    out: list[tuple[int, tuple[str, str, Value]]] = []
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return out
    for row in read_csv_rows(path):
        context, field = row.get("context", ""), TDNET_ITEMS.get(row.get("element", ""))
        if not field or "Consolidated" not in context or "NonConsolidated" in context or "Result" not in context:
            continue
        fy = (row.get("fiscal_year_end") or "")[:7]
        if not fy or not context.startswith(("CurrentYear", "PriorYear")):
            continue
        value = _float(row.get("value"))
        if value is not None:
            current = context.startswith("CurrentYear")
            year = fy if current else S._shift_year(fy, -12)
            out.append((0 if current else 1, (field, year, Value(value, "data/tdnet_facts.csv（決算短信）", True))))
    # the year's own 短信 first: a later 短信's prior-year column may be restated on a new share basis, and EPS and
    # net income must come from the same filing for the split check
    return [obs for _, obs in sorted(out, key=lambda x: x[0])]


def from_financials(company) -> list[tuple[str, str, Value]]:
    out = []
    path = company.path / "data" / "financials.csv"
    if not path.exists():
        return out
    for row in read_csv_rows(path):
        field = CSV_ITEMS.get(row.get("item", "").removeprefix("summary."))
        year = (row.get("period_end") or "")[:7]
        value = _float(row.get("value"))
        if field and year and value is not None:
            out.append((field, year, Value(value, "data/financials.csv", True)))
    return out


def merge(observations: list[tuple[str, str, Value]]) -> Series:
    series: Series = {f: {} for f in FIELDS}
    for field, year, value in observations:
        current = series[field].get(year)
        if current is None or (value.primary and not current.primary):
            series[field][year] = value
    return {f: dict(sorted(v.items())) for f, v in series.items()}


def self_series(company) -> Series:
    observations = from_tdnet(company) + from_financials(company)
    for kind, include in (("yuho", YUHO_SECTION), ("financials-historical", None)):
        for _, path in raw_files(company, kind):
            observations += from_raw_text(path.read_text(encoding="utf-8"), path.name, include)
    return merge(observations)


# ---------- EPS on one basis ----------

def _split_factor(ratio: float) -> float | None:
    """10.0 for a 1:10 split, 1.5 for a 3:2 split, 0.5 for a 2:1 consolidation, None for an ordinary change of
    the share count (buybacks, small issues)."""
    if ratio <= 0:
        return None
    for factor in SPLIT_FACTORS:
        for target in (factor, 1 / factor):
            if abs(ratio - target) / target <= SPLIT_TOLERANCE:
                return target
    return None


def adjusted_eps(series: Series) -> tuple[dict[str, float], list[dict], list[dict]]:
    """EPS per year on the newest year's basis, the splits found ({after, before, factor}) and the jumps too
    large to be a split ({after, before, ratio}; left unadjusted, likely a unit slip)."""
    eps, ni = series["eps"], series["net_income"]
    # loss years are left out: a loss EPS (or one with participating preferred shares around a turn to profit)
    # implies no usable share count
    years = [y for y in sorted(eps) if y in ni and eps[y].value > 0 and ni[y].value > 0]
    shares = {y: ni[y].value / eps[y].value for y in years}
    splits, odd = [], []
    for prev, cur in zip(years, years[1:]):
        ratio = shares[cur] / shares[prev]
        if max(ratio, 1 / ratio) > SPLIT_IMPLAUSIBLE:
            odd.append({"before": prev, "after": cur, "ratio": ratio})
            continue
        factor = _split_factor(ratio)
        if factor:
            splits.append({"before": prev, "after": cur, "factor": factor})
    adjusted = {}
    for year, value in eps.items():
        divisor = 1.0
        for s in splits:
            if year < s["after"]:  # a loss year between the two profitable years is pre-split too
                divisor *= s["factor"]
        adjusted[year] = value.value / divisor
    return adjusted, splits, odd


# ---------- the company plan ----------

PLAN_METRICS = (("sales", ("売上高", "売上収益", "営業収益")), ("operating_income", ("営業利益",)),
                ("ordinary_income", ("経常利益",)), ("net_income", ("純利益", "当期利益")))
PLAN_TDNET = {"NetSales": "sales", "OperatingIncome": "operating_income", "OrdinaryIncome": "ordinary_income",
              "ProfitAttributableToOwnersOfParent": "net_income"}
YEAR_COLUMN = ("対象年度", "年度", "決算期")


def _plan_year(cell: str) -> str | None:
    return S.period(cell.replace("-", "/"))


def _plan_columns(header: list[str]) -> dict:
    cols = {"year": next((i for i, h in enumerate(header) if any(w in h for w in YEAR_COLUMN)), None),
            "kind": next((i for i, h in enumerate(header) if "区分" in h), None)}
    for metric, words in PLAN_METRICS:
        cols[metric] = next((i for i, h in enumerate(header)
                             if any(w in h for w in words) and "率" not in h and "1株" not in h), None)
    return cols


def plan_from_raw(found: Found) -> list[tuple[str, str, str, Value]]:
    """(year, 'forecast' | 'actual', metric, Value) from the raw「会社計画（期初予想）と実績」table. A row without
    a year continues the year above; only 期初予想 and 実績 rows count (修正予想・期中 are left out)."""
    if found.status not in ("ok", "thin") or not found.body:
        return []
    factor = unit_of(S._prose(found.body)) or unit_of(found.heading) or 1.0
    out = []
    for table in M.tables(found.body):
        cols = _plan_columns(table[0])
        if cols["year"] is None or cols["kind"] is None:
            continue
        year = None
        for row in table[1:]:
            if cols["year"] < len(row) and not M.is_blank(row[cols["year"]]):
                year = _plan_year(row[cols["year"]])
            kind_cell = row[cols["kind"]] if cols["kind"] < len(row) else ""
            kind = "forecast" if "期初" in kind_cell else "actual" if "実績" in kind_cell else None
            if not year or not kind:
                continue
            primary = not S.SECONDARY.search(" ".join(row))
            for metric, _ in PLAN_METRICS:
                i = cols[metric]
                value = amount(row[i], unit_of(table[0][i]) or factor) if i is not None and i < len(row) else None
                if value is not None:
                    out.append((year, kind, metric, Value(value, f"{found.path.name}「{found.heading[:20]}」", primary)))
    return out


def plan_from_tdnet(company) -> list[tuple[str, str, str, Value]]:
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return []
    out, seen = [], set()
    for rec in forecast_records(read_csv_rows(path)):
        kind = {"期初予想": "forecast", "実績": "actual"}.get(rec["kind"])
        key = (rec["target"][:7], kind)
        if not kind or key in seen:  # the first 期初予想 of a year is the initial plan
            continue
        seen.add(key)
        for element, metric in PLAN_TDNET.items():
            value = _float(rec.get(element))
            if value is not None:
                out.append((key[0], kind, metric, Value(value, "data/tdnet_facts.csv（決算短信）", True)))
    return out


def plan_records(company, found: Found) -> dict[str, dict]:
    """year -> {'forecast': {metric: Value}, 'actual': {metric: Value}}; the 短信 data first, the raw table fills."""
    out: dict[str, dict] = {}
    for year, kind, metric, value in plan_from_tdnet(company) + plan_from_raw(found):
        slot = out.setdefault(year, {"forecast": {}, "actual": {}})[kind]
        current = slot.get(metric)
        if current is None or (value.primary and not current.primary):
            slot[metric] = value
    return dict(sorted(out.items()))


# ---------- M&A ----------

MA_SALES_WORDS = ("売上",)
MA_TARGET_WORDS = ("対象", "取得先", "会社")


def ma_rows(found: Found) -> list[dict]:
    """Rows of the raw「M&A・連結範囲の変更」table: year, target and the acquired company's annual sales
    (百万, None when the cell gives none)."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    factor = unit_of(S._prose(found.body)) or 1.0
    out = []
    for table in M.tables(found.body):
        header = table[0]
        year_col = next((i for i, h in enumerate(header) if any(w in h for w in YEAR_COLUMN)), None)
        sales_col = next((i for i, h in enumerate(header) if any(w in h for w in MA_SALES_WORDS)), None)
        target_col = next((i for i, h in enumerate(header) if any(w in h for w in MA_TARGET_WORDS)), None)
        if year_col is None:
            continue
        for row in table[1:]:
            year = S.period(row[year_col]) if year_col < len(row) else None
            if not year:
                continue
            sales = (amount(row[sales_col], unit_of(header[sales_col]) or factor)
                     if sales_col is not None and sales_col < len(row) else None)
            target = row[target_col].replace("*", "").strip() if target_col is not None and target_col < len(row) else "—"
            out.append({"year": year, "target": target, "sales": sales})
    return out
