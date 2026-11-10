"""Price history of a company for the report: ranges, moving averages, the monthly chart series and yearly rows.

Reads companies/{ticker}_{name}/data/prices.csv (tools/collect/stock_prices.py; split-adjusted closes, highs, lows
and volume); cr_technicals.evaluate() of the same rows goes under "technicals". Every window is counted back from the latest trading day; a window longer than the stored history is
marked partial (上場来・取得期間) instead of pretending to cover it. Without prices.csv the yearly 最高・最低株価
table collected in raw/ir/*_valuation-data.md is passed through as text (fallback, no chart).
"""
from __future__ import annotations

import csv
import datetime as dt
import math
from pathlib import Path

import cr_technicals as T
import mdparse as M

WINDOWS = (("52週", 365), ("3年", 365 * 3 + 1), ("5年", 365 * 5 + 1), ("10年", 365 * 10 + 2))
MA_DAYS = (("13週", 65), ("26週", 130), ("52週", 260))  # trading days (5 a week)
CHART_MA = "26週"
YEARLY_MAX = 10
FALLBACK_KEY = "株価レンジ"
YEAR_START_SLACK = "01-10"  # a first year starting after this day is a partial year


def _volume(text: str | None) -> float | None:
    try:
        return float(text) if text else None
    except ValueError:
        return None


def load(path: Path) -> list[dict]:
    """[{date, close, high, low, volume}] oldest first (volume None when missing); rows without a numeric close
    are skipped."""
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
            out.append({"date": r["date"], "close": close, "high": max(high, close), "low": min(low, close),
                        "volume": _volume(r.get("volume"))})
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


# ---------------------------------------------------------------- long-term trend

TREND_WINDOWS = (("10年", 120), ("5年", 60), ("3年", 36))  # months; the longest one with data decides
WINDOW_COVER = 0.9   # a window needs 90% of its months
TREND_R2 = 0.5       # how well a straight line in logs fits before it is called a trend
TREND_RATE = 5.0     # % a year
BAND_PCT = (0.1, 0.9)  # the range band: the 10th〜90th percentile of the month-end closes
EARNINGS_GAP = 5.0   # pt: price growth within this of EPS growth is "in line with earnings"
UP, DOWN, RANGE = "上昇トレンド", "下降トレンド", "レンジ"


def _month_ends(rows: list[dict]) -> list[tuple[str, float]]:
    ends: dict[str, tuple[str, float]] = {}
    for r in rows:
        ends[r["date"][:7]] = (r["date"], r["close"])
    return [ends[m] for m in sorted(ends)]


def _fit(values: list[float]) -> tuple[float, float, float]:
    """(slope a year, intercept, r²) of ln(value) on years since the first month."""
    xs = [i / 12 for i in range(len(values))]
    ys = [math.log(v) for v in values]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx
    r2 = (sxy * sxy / (sxx * syy)) if syy else 0.0
    return slope, my - slope * mx, r2


def _drawdown(values: list[float]) -> float:
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return round(worst * 100, 1)


def _trend_window(points: list[tuple[str, float]]) -> dict:
    values = [v for _, v in points]
    slope, intercept, r2 = _fit(values)
    annual = (math.exp(slope) - 1) * 100
    verdict = (UP if annual >= TREND_RATE else DOWN if annual <= -TREND_RATE else RANGE) if r2 >= TREND_R2 else RANGE
    ordered = sorted(values)
    band = tuple(round(ordered[int(p * (len(ordered) - 1))], 2) for p in BAND_PCT)
    line = [[d, round(math.exp(intercept + slope * i / 12), 2)] for i, (d, _) in enumerate(points)]
    return {"verdict": verdict, "annual": round(annual, 1), "r2": round(r2, 2), "band": band,
            "max_drawdown": _drawdown(values), "start": points[0][0], "line": line}


def long_trend(rows: list[dict]) -> dict:
    """Whether the price has grown or moved sideways over the long run: a straight line through the month-end
    closes in logs over 10 / 5 / 3 years (年率・あてはまり R²), the max drawdown and, for a range, its band. The
    longest window with data decides."""
    points = _month_ends(rows)
    windows = {label: _trend_window(points[-n:]) for label, n in TREND_WINDOWS
               if len(points) >= n * WINDOW_COVER and all(v > 0 for _, v in points[-n:])}
    if not windows:
        return {"verdict": None, "windows": {}, "sentence": "", "basis": None, "line": []}
    basis = next(label for label, _ in TREND_WINDOWS if label in windows)
    w = windows[basis]
    if w["verdict"] == RANGE:
        sentence = (f"{basis}の株価は {w['band'][0]:,.0f}〜{w['band'][1]:,.0f} のレンジ（月末の終値の8割がこの幅。"
                    f"傾向線は年率 {w['annual']:+.1f}%、あてはまり R² {w['r2']:.2f}）")
    else:
        sentence = f"{basis}の株価は年率 {w['annual']:+.1f}% の{w['verdict']}（傾向線のあてはまり R² {w['r2']:.2f}）"
    sentence += f"。この間の最大の下落は {w['max_drawdown']:.0f}%"
    return {"verdict": w["verdict"], "basis": basis, "windows": {k: {x: v for x, v in d.items() if x != "line"}
                                                                for k, d in windows.items()},
            "sentence": sentence, "line": w["line"]}


def versus_earnings(price_rate: float | None, eps_rate: float | None) -> str:
    """Price growth against EPS growth: in line with earnings, re-rated up, or rated down."""
    if price_rate is None or eps_rate is None:
        return ""
    head = f"株価の伸び（年率 {price_rate:+.1f}%）は EPS の伸び（{eps_rate:+.1f}%）"
    if abs(price_rate - eps_rate) <= EARNINGS_GAP:
        return head + "とほぼ同じで、株価は業績に連動している"
    if price_rate > eps_rate:
        return head + "を上回り、業績に加えて評価の見直し（PER の上昇）が株価を押し上げた"
    return head + "を下回り、業績ほどには株価が伸びず市場の評価が下がった（PER の低下）"


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
            "averages": averages(rows), "monthly": monthly(rows), "yearly": yearly(rows),
            "long_trend": long_trend(rows), "technicals": T.evaluate(rows)}
