"""Price history of a company for the report: ranges, moving averages, the monthly chart series and yearly rows.

Reads companies/{ticker}_{name}/data/prices.csv (tools/collect/stock_prices.py; split-adjusted closes, highs and
lows). Every window is counted back from the latest trading day; a window longer than the stored history is
marked partial (上場来・取得期間) instead of pretending to cover it. Without prices.csv the yearly 最高・最低株価
table collected in raw/ir/*_valuation-data.md is passed through as text (fallback, no chart).
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

import mdparse as M

WINDOWS = (("52週", 365), ("3年", 365 * 3 + 1), ("5年", 365 * 5 + 1), ("10年", 365 * 10 + 2))
MA_DAYS = (("13週", 65), ("26週", 130), ("52週", 260))  # trading days (5 a week)
CHART_MA = "26週"
YEARLY_MAX = 10
FALLBACK_KEY = "株価レンジ"
YEAR_START_SLACK = "01-10"  # a first year starting after this day is a partial year


def load(path: Path) -> list[dict]:
    """[{date, close, high, low}] oldest first; rows without a numeric close are skipped."""
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if not r.get("date"):
                continue
            try:
                close = float(r["close"])
                high = float(r["high"]) if r.get("high") else close
                low = float(r["low"]) if r.get("low") else close
            except (KeyError, TypeError, ValueError):
                continue
            out.append({"date": r["date"], "close": close, "high": max(high, close), "low": min(low, close)})
    return sorted(out, key=lambda r: r["date"])


def position(value: float, low: float, high: float) -> float:
    """Where value sits between low (0%) and high (100%)."""
    return 50.0 if high == low else max(0.0, min(100.0, (value - low) / (high - low) * 100))


def window(rows: list[dict], label: str, days: int) -> dict:
    last = dt.date.fromisoformat(rows[-1]["date"])
    start = (last - dt.timedelta(days=days)).isoformat()
    span = [r for r in rows if r["date"] > start]
    hi = max(span, key=lambda r: r["high"])
    lo = min(span, key=lambda r: r["low"])
    current = rows[-1]["close"]
    return {"label": label, "start": span[0]["date"], "partial": rows[0]["date"] > start,
            "high": hi["high"], "high_date": hi["date"], "low": lo["low"], "low_date": lo["date"],
            "position": round(position(current, lo["low"], hi["high"]), 1),
            "from_high": round((current / hi["high"] - 1) * 100, 1),
            "from_low": round((current / lo["low"] - 1) * 100, 1) if lo["low"] else None}


def moving_average(closes: list[float], n: int) -> float | None:
    return sum(closes[-n:]) / n if len(closes) >= n else None


def averages(rows: list[dict]) -> list[dict]:
    closes = [r["close"] for r in rows]
    out = []
    for label, n in MA_DAYS:
        ma = moving_average(closes, n)
        out.append({"label": label, "value": round(ma, 2) if ma else None,
                    "gap": round((closes[-1] / ma - 1) * 100, 1) if ma else None})
    return out


def monthly(rows: list[dict]) -> dict:
    """Month-end closes and the 26-week moving average at each month end (chart points)."""
    n = dict(MA_DAYS)[CHART_MA]
    closes: list[float] = []
    ends: dict[str, tuple[str, float, float | None]] = {}
    for r in rows:
        closes.append(r["close"])
        ends[r["date"][:7]] = (r["date"], r["close"], moving_average(closes, n))
    points = [ends[m] for m in sorted(ends)]
    return {"close": [[d, c] for d, c, _ in points],
            "ma": [[d, round(ma, 2)] for d, _, ma in points if ma is not None]}


def yearly(rows: list[dict]) -> list[dict]:
    """Calendar-year high, low and year-end close, newest first (a first or latest year may be partial)."""
    years: dict[str, list[dict]] = {}
    for r in rows:
        years.setdefault(r["date"][:4], []).append(r)
    first_year, last_year = rows[0]["date"][:4], rows[-1]["date"][:4]
    out, previous = [], None
    for year in sorted(years):
        span = years[year]
        close = span[-1]["close"]
        partial = year == last_year or (year == first_year and span[0]["date"][5:] > YEAR_START_SLACK)
        out.append({"year": year, "high": max(r["high"] for r in span), "low": min(r["low"] for r in span),
                    "close": close, "change": round((close / previous - 1) * 100, 1) if previous else None,
                    "partial": partial})
        previous = close
    return list(reversed(out))[:YEARLY_MAX]


def fallback(company_path: Path) -> dict | None:
    """The yearly price-range table of the newest valuation-data raw that has one (text as collected)."""
    for path in sorted((company_path / "raw" / "ir").glob("*_valuation-data.md"), reverse=True):
        text = path.read_text(encoding="utf-8")
        for level in (3, 2):
            found = M.section_by_title(text, FALLBACK_KEY, level)
            if found and M.table_dicts(found[1]):
                return {"title": found[0], "rows": M.table_dicts(found[1]), "source": path.name}
    return None


def summarize(company_path: Path) -> dict:
    """Everything the report needs about the price history; source is prices, fallback or none."""
    rows = load(company_path / "data" / "prices.csv")
    if not rows:
        table = fallback(company_path)
        return {"source": "fallback" if table else "none", "fallback": table}
    return {"source": "prices", "path": "data/prices.csv", "first": rows[0]["date"], "last": rows[-1]["date"],
            "current": rows[-1]["close"], "days": len(rows),
            "ranges": [window(rows, label, days) for label, days in WINDOWS],
            "averages": averages(rows), "monthly": monthly(rows), "yearly": yearly(rows)}


def short_inputs(prices: dict) -> tuple[float | None, float | None]:
    """(position in the 52-week range %, gap to the 26-week moving average %) for the short-term verdict."""
    if prices.get("source") != "prices":
        return None, None
    pos = next((w["position"] for w in prices["ranges"] if w["label"] == "52週"), None)
    gap = next((a["gap"] for a in prices["averages"] if a["label"] == CHART_MA), None)
    return pos, gap
