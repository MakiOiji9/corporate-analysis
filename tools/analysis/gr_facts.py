"""Facts beside the yearly series that the growth analysis reports but does not judge on.

- split_records: share splits written in status.md「期末後のコーポレートアクション」and the raw files, so an EPS
  adjustment found by gr_series.adjusted_eps can be checked against what the company announced
- current_progress: this fiscal year's cumulative quarter (決算短信 iXBRL in data/tdnet_facts.csv) against the
  same quarter a year before and against the full-year forecast (for STEP 3, not for the 成長性 verdict)
- sga_lines: the SG&A breakdown (採用費・人件費 …) from the newest 有報 / 財務時系列, for the writer's background
- source_hints: originals already in sources/manifest.csv that cover a requested year (passed to collect-company-info)
"""
from __future__ import annotations

import re

import mdparse as M
from common import read_csv_rows
from ff_inputs import raw_files

SPLIT_LINE = re.compile(r"分割")
NOT_SHARE_SPLIT = re.compile(r"会社分割|吸収分割|新設分割|事業分割|分割払|\d{1,2}:\d{2}\s*(?:から|〜|-)")
FISCAL_YEAR = re.compile(r"^\d{4}-\d{2}$")
SPLIT_ONE_TO_N = re.compile(r"1\s*株(?:につき|→|を|に対し)\s*(?:普通株式\s*)?(\d+(?:\.\d+)?)\s*株")
SPLIT_RATIO = re.compile(r"(\d+(?:\.\d+)?)\s*[:：]\s*(\d+(?:\.\d+)?)")
DATE = re.compile(r"(\d{4})\s*[-年/]\s*(\d{1,2})(?:\s*[-月/]\s*(\d{1,2}))?")
QUARTER = re.compile(r"^CurrentAccumulatedQ(\d)Duration_ConsolidatedMember_ResultMember$")
FORECAST_CTX = "CurrentYearDuration_ConsolidatedMember_ForecastMember"
PROGRESS_ITEMS = (("sales", "売上高", "NetSales"), ("operating_income", "営業利益", "OperatingIncome"))
SGA_ROW = re.compile(r"採用費|人件費|給与|役員報酬|賞与|研究開発費|販売費及び一般管理費")
SGA_ITEM = re.compile(r"採用費|人件費|給与|役員報酬|賞与")  # rows only a breakdown table has
SGA_PROSE = re.compile(r"採用費|人件費")
SGA_ROWS_MAX = 8
HINT_TYPES = ("yuho", "tanshin", "presentation", "hanki", "10k", "424b4", "s-1", "20f", "10q", "8k")


# ---------- splits ----------

def _date(line: str) -> str:
    m = DATE.search(line)
    if not m:
        return ""
    year, month, day = m.group(1), int(m.group(2)), m.group(3)
    return f"{year}-{month:02d}" + (f"-{int(day):02d}" if day else "")


def _factor(line: str) -> float | None:
    m = SPLIT_ONE_TO_N.search(line)
    if m:
        return float(m.group(1))
    at = line.find("分割")
    if at < 0:
        return None
    # '株式分割（1:10）' and '1:100分割' both: the ratio within a few characters either side of 分割
    m = SPLIT_RATIO.search(line[max(0, at - 12):at + 16])
    if m and float(m.group(1)) > 0:
        return float(m.group(2)) / float(m.group(1))
    return None


def split_records(company) -> list[dict]:
    """[{factor, date, source}] of the share splits mentioned in status.md and the financial raw files."""
    texts: list[tuple[str, str]] = []
    status = company.path / "status.md"
    if status.exists():
        texts.append(("status.md", status.read_text(encoding="utf-8")))
    for kind in ("financials-historical", "yuho"):
        texts += [(path.name, path.read_text(encoding="utf-8")) for _, path in raw_files(company, kind)]
    out, seen = [], set()
    for source, text in texts:
        for line in text.splitlines():
            if not SPLIT_LINE.search(line) or "併合" in line or NOT_SHARE_SPLIT.search(line):
                continue
            factor = _factor(line)
            if factor and factor > 1 and (factor, _date(line)) not in seen:
                seen.add((factor, _date(line)))
                out.append({"factor": factor, "date": _date(line), "source": source})
    return out


def match_split(split: dict, records: list[dict]) -> dict | None:
    """The announced split whose factor equals the one found in the EPS series (dated ones first)."""
    hits = [r for r in records if abs(r["factor"] - split["factor"]) < 1e-6]
    return max(hits, key=lambda r: (bool(r["date"]), r["date"])) if hits else None


# ---------- this fiscal year's progress ----------

def _float(text: str | None) -> float | None:
    try:
        return float(text or "")
    except ValueError:
        return None


def _change(value: float | None, base: float | None) -> float | None:
    """Change in % from a positive base (a loss base gives no meaningful rate)."""
    return (value / base - 1) * 100 if value is not None and base is not None and base > 0 else None


def _share(part: float | None, whole: float | None) -> float | None:
    """part ÷ whole in % for a positive whole and a non-negative part (progress against a profit)."""
    if part is None or whole is None or whole <= 0 or part < 0:
        return None
    return part / whole * 100


def current_progress(company, series: dict) -> dict | None:
    """The newest cumulative quarter: per item the cumulative value, the same quarter a year before, the year-on-
    year change, the full-year forecast (latest, same filing), its change from last year's actual and the progress
    rate now and a year before. None without quarterly 短信 data."""
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return None
    docs: dict[str, list[dict]] = {}
    for row in read_csv_rows(path):
        docs.setdefault(row.get("doc_id", ""), []).append(row)
    best = None
    for doc_id, rows in docs.items():
        quarters = [int(m.group(1)) for r in rows if (m := QUARTER.match(r.get("context", "")))]
        fy = (rows[0].get("fiscal_year_end") or "")[:7]
        if quarters and FISCAL_YEAR.match(fy):
            key = (fy, max(quarters), rows[0].get("filing_date") or "")  # a corrected filing wins a tie
            if best is None or key > best[0]:
                best = (key, doc_id)
    if best is None:
        return None
    (fy, quarter, _), doc_id = best
    if fy in series.get("sales", {}):  # the full year is already reported: no current-year progress to show
        return None
    rows = docs[doc_id]

    def value(context: str, element: str) -> float | None:
        return next((_float(r.get("value")) for r in rows if r.get("context") == context
                     and r.get("element") == element), None)

    prior_fy = f"{int(fy[:4]) - 1}{fy[4:]}"
    items = {}
    for key, name, element in PROGRESS_ITEMS:
        cum = value(f"CurrentAccumulatedQ{quarter}Duration_ConsolidatedMember_ResultMember", element)
        prior = value(f"PriorAccumulatedQ{quarter}Duration_ConsolidatedMember_ResultMember", element)
        forecast = value(FORECAST_CTX, element)
        last = series.get(key, {}).get(prior_fy)
        last = last.value if last else None
        items[key] = {
            "name": name, "cum": cum, "prior": prior, "forecast": forecast, "last_actual": last,
            "yoy": _change(cum, prior), "forecast_growth": _change(forecast, last),
            "progress": _share(cum, forecast), "prior_progress": _share(prior, last)}
    return {"fy": fy, "quarter": quarter, "filing_date": rows[0].get("filing_date", ""), "items": items}


def _pct(value: float | None, signed: bool = False) -> str:
    if value is None:
        return "—"
    return f"{value:+.1f}%" if signed else f"{value:.1f}%"


def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def progress_text(progress: dict | None) -> str:
    if not progress:
        return "—（決算短信の四半期データなし。米国株・短信 iXBRL の無い会社は対象外）"
    parts = []
    for item in progress["items"].values():
        parts.append(f"{item['name']} {_m(item['cum'])}百万（前年同期比 {_pct(item['yoy'], True)}。通期予想 "
                     f"{_m(item['forecast'])}（前期比 {_pct(item['forecast_growth'], True)}）に対する進捗 "
                     f"{_pct(item['progress'])}、前年同期の進捗 {_pct(item['prior_progress'])}）")
    return (f"{progress['fy']} 期の第{progress['quarter']}四半期累計（{progress['filing_date']} 公表の決算短信）: "
            + "、".join(parts))


# ---------- SG&A ----------

def sga_lines(company) -> list[str]:
    """Rows of the SG&A breakdown tables and the prose lines on recruiting / personnel costs of the newest 有報,
    else of the newest 財務時系列 (as Markdown, with the file name)."""
    for kind in ("yuho", "financials-historical"):
        for _, path in raw_files(company, kind):
            text = path.read_text(encoding="utf-8")
            lines = []
            # the breakdown table (most 採用費・給与… rows), not the P/L that only has the SG&A total
            scored = [(sum(bool(row) and bool(SGA_ITEM.search(row[0])) for row in t[1:]), t) for t in M.tables(text)]
            score, table = max(scored, key=lambda x: x[0], default=(0, None))
            if score and len(table[0]) > 1:
                hits = [row for row in table[1:] if row and SGA_ROW.search(row[0])]
                lines.append("| " + " | ".join(table[0]) + " |")
                lines.append("|" + "---|" * len(table[0]))
                lines += ["| " + " | ".join(row) + " |" for row in hits[:SGA_ROWS_MAX]]
            lines += [line.strip() for line in text.splitlines()
                      if SGA_PROSE.search(line) and not line.lstrip().startswith(("|", "#"))][:3]
            if lines:
                return [f"出典: {path.name}", *lines]
    return []


# ---------- collection hints ----------

def source_hints(company, years: list[str], types: tuple[str, ...] = HINT_TYPES) -> list[str]:
    """Originals in sources/manifest.csv whose period starts with one of the years (YYYY-MM), as 'type period: path'."""
    manifest = company.path / "sources" / "manifest.csv"
    if not manifest.exists():
        return []
    out = []
    for row in read_csv_rows(manifest):
        period = row.get("period") or ""
        if row.get("doc_type") in types and any(period.startswith(y) for y in years):
            out.append(f"{row['doc_type']} {period}: {row.get('local_path', '')}")
    return sorted(set(out))
