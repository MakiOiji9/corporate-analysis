"""Yearly series behind the profitability analysis (企業分析フレームワーク.md 2-1).

Fields: sales, net income (attributable to owners of the parent), total assets, equity (自己資本), equity ratio,
reported ROE and the extraordinary items. Amounts are in 百万円, ratios in %.

The target: data/financials.csv (EDINET XBRL) and data/tdnet_facts.csv (決算短信) first, then the tables of the
raw 有報 and 財務時系列 (both table orientations; the unit is read from the column / row label, the section
text or the file header: 千円 / 百万円 / 億円), then the target's own rows in competitors.md「収益性の分解」.
A primary value (有報・短信・XBRL) wins over a secondary one (IRBANK などの集計サイト) for the same year.
The peers: competitors.md「収益性の分解」(one row per company and year).
Forecasts, quarters, the parent-only figures and segment / subsidiary tables are never read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import mdparse as M
from common import read_csv_rows
from ff_inputs import Found, raw_files
from ff_metrics import FORECAST, _yen
from tc_metrics import _is_self

FIELDS = ("sales", "net_income", "total_assets", "equity", "equity_ratio", "roe", "extra_gain", "extra_loss")
PERCENT_FIELDS = ("equity_ratio", "roe")
# row / column labels per field, most specific first (the first label found in a table wins)
LABELS = {
    "sales": ("売上高", "売上収益", "営業収益"),
    "net_income": ("親会社株主に帰属する当期純利益", "親会社の所有者に帰属する当期利益", "親会社所有者に帰属する当期利益",
                   "当期純利益", "当期利益", "純利益"),
    "total_assets": ("総資産", "総資産額", "資産合計"),
    "equity": ("自己資本", "親会社の所有者に帰属する持分", "親会社所有者帰属持分"),
    "equity_ratio": ("自己資本比率", "親会社所有者帰属持分比率", "親会社の所有者に帰属する持分比率"),
    "roe": ("ROE", "自己資本利益率", "自己資本当期純利益率", "親会社所有者帰属持分当期利益率"),
    "extra_gain": ("特別利益", "特別利益合計"),
    "extra_loss": ("特別損失", "特別損失合計"),
}
# an amount label with one of these is a ratio, a per-share figure, a breakdown or another profit line
AMOUNT_EXCLUDE = ("率", "1株", "一株", "非支配", "包括", "税金等調整前", "調整後", "前期比", "増減", "回転", ":", "：")
RATIO_EXCLUDE = ("前期比", "増減", ":", "：")
UNIT_TO_MILLION = {"千円": 1e-3, "百万円": 1.0, "億円": 100.0}
UNIT_IN_TEXT = re.compile(r"単位[^。\n|]{0,12}?(千円|百万円|億円)|(千円|百万円|億円)単位")
UNIT_IN_LABEL = re.compile(r"[（(]\s*(千円|百万円|億円)")
EXPLICIT_UNIT = re.compile(r"(兆|億|百万|千|万)円")
LEADING_NUMBER = re.compile(r"^[△▲\-−]?\d[\d,]*(?:\.\d+)?")
NOT_ACTUAL = re.compile(r"予|見込|見通し|\dE\b|四半期|中間|累計")  # forecast / quarter columns
LABEL_END = "（( 　"  # a label matches when the name is followed by nothing or a bracket
FIRST_NUMBER = re.compile(r"[△▲\-−]?\d+(?:\.\d+)?")
PERIOD = re.compile(r"^(\d{4})\s*[/年]\s*(\d{1,2})(?!\d)")
SECTION = re.compile(r"^(#{2,3})\s+(.+)$", re.M)
SKIP_SECTION = re.compile(r"予想|計画|四半期|CAGR|提出会社|単体|個別|子会社|セグメント|株主還元|キャッシュ|配当")
YUHO_SECTION = re.compile(r"主要な経営指標|財務|損益|貸借|特別")
SECONDARY = re.compile(r"IRBANK|二次|株探|kabutan|集計サイト")
PEER_SECTION = "収益性の分解"
PAREN_NEGATIVE = re.compile(r"^\((\d[\d,]*(?:\.\d+)?)\)")  # US filings: '(164,402)' is -164,402

# data/financials.csv items (with or without the 'summary.' prefix)
CSV_ITEMS = {"net_sales": "sales", "net_income": "net_income", "total_assets": "total_assets",
             "equity_ratio": "equity_ratio", "roe": "roe", "extraordinary_income": "extra_gain",
             "extraordinary_loss": "extra_loss"}
# data/tdnet_facts.csv elements (consolidated results)
TDNET_ITEMS = {"NetSales": "sales", "ProfitAttributableToOwnersOfParent": "net_income", "TotalAssets": "total_assets",
               "OwnersEquity": "equity", "CapitalAdequacyRatio": "equity_ratio",
               "NetIncomeToShareholdersEquityRatio": "roe"}


@dataclass(frozen=True)
class Value:
    value: float
    source: str
    primary: bool


@dataclass(frozen=True)
class Fields:
    """What one analysis reads from the tables: the labels per field (most specific first), the ratio fields and
    the section titles to skip. The table readers default to the profitability fields."""
    labels: dict[str, tuple[str, ...]]
    percent: tuple[str, ...]
    skip: re.Pattern


PROFITABILITY = Fields(LABELS, PERCENT_FIELDS, SKIP_SECTION)


Series = dict[str, dict[str, Value]]  # field -> fiscal year end (YYYY-MM) -> value


# ---------- cells ----------

def period(cell: str) -> str | None:
    """'2026/03' / '2026年3月期' / '2026年3月末' -> '2026-03'; forecasts are not periods."""
    text = cell.replace("*", "").strip()
    if FORECAST.search(text) or NOT_ACTUAL.search(text):
        return None
    m = PERIOD.match(text)
    return f"{m.group(1)}-{int(m.group(2)):02d}" if m and 1 <= int(m.group(2)) <= 12 else None


def _signed(text: str) -> float:
    negative = text[0] in "△▲-−"
    number = float(text.lstrip("△▲-−").replace(",", ""))
    return -number if negative else number


def amount(cell: str, factor: float) -> float | None:
    """A cell in 百万円. A cell with its own unit ('7.93億円', '23,831百万円') uses it; a bare number
    ('1,748,986（売掛金）', '△98') is multiplied by the table's factor. '計上なし' / '—' -> None."""
    text = PAREN_NEGATIVE.sub(r"-\1", cell.replace("*", "").strip())
    bracketed = UNIT_IN_LABEL.search(text)  # '1,200（百万円）': _yen would drop the bracket as a note
    if bracketed:
        factor = UNIT_TO_MILLION[bracketed.group(1)]
    elif EXPLICIT_UNIT.search(text):
        yen = _yen(text)
        if yen is not None:
            return yen / 1e6
    m = LEADING_NUMBER.match(text)
    return _signed(m.group(0)) * factor if m else None


def percent(cell: str) -> float | None:
    """The first number of the cell: '13.21%' / '18.8%（有報）/ 17.27%（IRBANK）' -> 13.21 / 18.8."""
    m = FIRST_NUMBER.search(cell.replace("*", ""))
    return _signed(m.group(0)) if m else None


def _label(cell: str) -> str:
    return cell.replace("*", "").strip()


def _names(text: str, lb: str) -> bool:
    """'売上高' / '売上高（百万円）' name 売上高; '売上高総利益' / '売上高構成' do not."""
    return text == lb or (text.startswith(lb) and text[len(lb)] in LABEL_END)


def field_of(label: str, fields: Fields = PROFITABILITY) -> str | None:
    """Which field a row / column label holds (ratios are told apart from amounts by their own labels)."""
    text = _label(label)
    for field in fields.percent:
        if any(_names(text, lb) for lb in fields.labels[field]) and not any(w in text for w in RATIO_EXCLUDE):
            return field
    for field, labels in fields.labels.items():
        if field in fields.percent:
            continue
        if any(_names(text, lb) for lb in labels) and not any(w in text for w in AMOUNT_EXCLUDE):
            return field
    return None


def _priority(field: str, label: str, fields: Fields = PROFITABILITY) -> int:
    text = _label(label)
    labels = fields.labels[field]
    return next((i for i, lb in enumerate(labels) if _names(text, lb)), len(labels))


def unit_of(text: str) -> float | None:
    m = UNIT_IN_LABEL.search(text) or UNIT_IN_TEXT.search(text)
    if not m:
        return None
    return UNIT_TO_MILLION[next(g for g in m.groups() if g)]


# ---------- tables ----------

def _best(labels: list[tuple[int, str]], fields: Fields = PROFITABILITY) -> dict[str, int]:
    """field -> index of the most specific label in the table."""
    best: dict[str, tuple[int, int]] = {}
    for index, label in labels:
        field = field_of(label, fields)
        if field and (field not in best or _priority(field, label, fields) < best[field][0]):
            best[field] = (_priority(field, label, fields), index)
    return {field: index for field, (_, index) in best.items()}


def _parse(field: str, cell: str, factor: float, fields: Fields = PROFITABILITY) -> float | None:
    return percent(cell) if field in fields.percent else amount(cell, factor)


def derive_equity(values: list[tuple[str, str, float]]) -> list[tuple[str, str, float]]:
    """The values of one table (or one CSV) plus 自己資本 = 総資産 × 自己資本比率 for the years that give both but
    no equity. Deriving within the source keeps the source order: a derived value from the 有報 still wins over an
    explicit one from a later, weaker source. 純資産 is never used (it includes the minority interest)."""
    by_year: dict[str, dict[str, float]] = {}
    for field, year, value in values:
        by_year.setdefault(year, {}).setdefault(field, value)
    derived = [("equity", year, v["total_assets"] * v["equity_ratio"] / 100) for year, v in by_year.items()
               if "equity" not in v and "total_assets" in v and "equity_ratio" in v]
    return values + derived


def read_table(table: list[list[str]], default_factor: float,
               fields: Fields = PROFITABILITY) -> list[tuple[str, str, float]]:
    """(field, year, value) of a table with years as columns or as rows."""
    header = table[0]
    columns = {i: period(c) for i, c in enumerate(header) if i > 0}
    columns = {i: y for i, y in columns.items() if y}
    out = []
    if len(columns) >= 2:  # years as columns, items as rows
        table_factor = unit_of(header[0]) or default_factor
        rows = {i: row for i, row in enumerate(table[1:]) if row}
        for field, index in _best([(i, row[0]) for i, row in rows.items()], fields).items():
            row = rows[index]
            factor = unit_of(row[0]) or table_factor
            for col, year in columns.items():
                if col < len(row):
                    value = _parse(field, row[col], factor, fields)
                    if value is not None:
                        out.append((field, year, value))
        return derive_equity(out)
    for field, col in _best(list(enumerate(header)), fields).items():  # years as rows, items as columns
        factor = unit_of(header[col]) or default_factor
        for row in table[1:]:
            year = period(row[0]) if row else None
            if year and col < len(row):
                value = _parse(field, row[col], factor, fields)
                if value is not None:
                    out.append((field, year, value))
    return derive_equity(out)


def sections(text: str) -> list[tuple[str, str]]:
    """(titles, body) for every ## / ### heading; titles joins the parent ## title, so a ### under a skipped
    ## section is skipped too. The body stops at the next heading of any level."""
    marks = list(SECTION.finditer(text))
    out, parent = [], ""
    for i, m in enumerate(marks):
        title = m.group(2).strip()
        if len(m.group(1)) == 2:
            parent = title
            titles = title
        else:
            titles = f"{parent} / {title}"
        out.append((titles, text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)]))
    return out


def _prose(body: str) -> str:
    return "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("|"))


def from_raw_text(text: str, source: str, include: re.Pattern | None = None,
                  fields: Fields = PROFITABILITY) -> list[tuple[str, str, Value]]:
    """(field, year, Value) of every table in a raw file, in reading order."""
    first = SECTION.search(text)
    file_factor = unit_of(text[:first.start()] if first else text) or 1.0
    out = []
    for titles, body in sections(text):
        if fields.skip.search(titles) or (include and not include.search(titles)):
            continue
        factor = unit_of(titles) or unit_of(_prose(body)) or file_factor
        primary = not SECONDARY.search(titles)
        label = f"{source}「{titles.split(' / ')[-1][:30]}」"
        for table in M.tables(body):
            for field, year, value in read_table(table, factor, fields):
                out.append((field, year, Value(value, label, primary)))
    return out


# ---------- data/*.csv ----------

def _shift_year(year: str, months: int) -> str:
    total = int(year[:4]) * 12 + int(year[5:7]) - 1 + months
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def from_data(company, csv_items: dict[str, str] = CSV_ITEMS,
              tdnet_items: dict[str, str] = TDNET_ITEMS) -> list[tuple[str, str, Value]]:
    out = []
    path = company.path / "data" / "financials.csv"
    if path.exists():
        values = []
        for row in read_csv_rows(path):
            field = csv_items.get(row.get("item", "").removeprefix("summary."))
            year = (row.get("period_end") or "")[:7]
            try:
                value = float(row.get("value", ""))
            except ValueError:
                continue
            if field and year:
                values.append((field, year, value))
        out += [(f, y, Value(v, "data/financials.csv（EDINET）", True)) for f, y, v in derive_equity(values)]
    return _from_tdnet(company, tdnet_items) + out  # 短信's explicit 自己資本 before the equity derived from a rounded ratio


def _from_tdnet(company, items: dict[str, str] = TDNET_ITEMS) -> list[tuple[str, str, Value]]:
    out = []
    path = company.path / "data" / "tdnet_facts.csv"
    if path.exists():
        for row in read_csv_rows(path):
            context, field = row.get("context", ""), items.get(row.get("element", ""))
            if not field or "Consolidated" not in context or "NonConsolidated" in context or "Result" not in context:
                continue
            fy = (row.get("fiscal_year_end") or "")[:7]
            if not fy or not context.startswith(("CurrentYear", "PriorYear")):
                continue
            year = fy if context.startswith("CurrentYear") else _shift_year(fy, -12)
            try:
                value = float(row.get("value", ""))
            except ValueError:
                continue
            out.append((field, year, Value(value, "data/tdnet_facts.csv（決算短信）", True)))
    return out


# ---------- merge ----------

def merge(observations: list[tuple[str, str, Value]], names: tuple[str, ...] = FIELDS) -> Series:
    """The first primary value per (field, year) wins; a secondary one only fills a gap. Fields not in names
    (自己資本 derived inside a table another analysis reads) are dropped."""
    series: Series = {f: {} for f in names}
    for field, year, value in observations:
        if field not in series:
            continue
        current = series[field].get(year)
        if current is None or (value.primary and not current.primary):
            series[field][year] = value
    return {f: dict(sorted(v.items())) for f, v in series.items()}


def with_equity(series: Series) -> Series:
    """自己資本 where only total assets and the equity ratio are known (純資産 includes the minority interest
    and the stock options, so it is never used as equity). Returns a new Series."""
    equity = dict(series["equity"])
    for year, assets in series["total_assets"].items():
        ratio = series["equity_ratio"].get(year)
        if year not in equity and ratio is not None:
            equity[year] = Value(assets.value * ratio.value / 100, f"総資産 × 自己資本比率（{ratio.source}）",
                                 assets.primary and ratio.primary)
    return {**series, "equity": dict(sorted(equity.items()))}


def self_series(company, peer_found: Found | None = None) -> Series:
    observations = from_data(company)
    for kind, include in (("yuho", YUHO_SECTION), ("financials-historical", None)):
        for _, path in raw_files(company, kind):
            observations += from_raw_text(path.read_text(encoding="utf-8"), path.name, include)
    if peer_found is not None:
        own = [r for r in peer_rows(peer_found) if _is_self(r["name"], company)]
        observations += [(f, r["year"], v) for r in own for f, v in r["values"].items()]
    return with_equity(merge(observations))


# ---------- peers ----------

PEER_COLUMNS = (("company", ("会社",)), ("year", ("年度", "決算期")), ("source", ("出典", "確度")))


def peer_rows(found: Found) -> list[dict]:
    """Rows of competitors.md「収益性の分解」: name, year and the values (amounts in 百万円 unless the cell
    says otherwise)."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    out = []
    for table in M.tables(found.body):
        header = table[0]
        cols = {key: next((i for i, h in enumerate(header) if any(w in h for w in words)), None)
                for key, words in PEER_COLUMNS}
        fields = {i: field_of(h) for i, h in enumerate(header)}
        if cols["company"] is None or cols["year"] is None:
            continue
        for row in table[1:]:
            year = period(row[cols["year"]]) if cols["year"] < len(row) else None
            if not year:
                continue
            source = row[cols["source"]] if cols["source"] is not None and cols["source"] < len(row) else ""
            primary = not SECONDARY.search(source)
            parsed = [(field, year, v) for i, field in fields.items() if field and i < len(row)
                      if (v := _parse(field, row[i], unit_of(header[i]) or 1.0)) is not None]
            values = {f: Value(v, f"competitors「{PEER_SECTION}」", primary) for f, _, v in derive_equity(parsed)}
            out.append({"name": row[cols["company"]].replace("*", "").strip(), "year": year, "values": values})
    return out


def peer_series(company, found: Found) -> list[dict]:
    """[{name, series}] for every peer in「収益性の分解」, in the order they first appear (target excluded)."""
    by_name: dict[str, list[tuple[str, str, Value]]] = {}
    for r in peer_rows(found):
        if _is_self(r["name"], company):
            continue
        by_name.setdefault(r["name"], []).extend((f, r["year"], v) for f, v in r["values"].items())
    return [{"name": name, "series": with_equity(merge(obs))} for name, obs in by_name.items()]
