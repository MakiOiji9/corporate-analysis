"""Why the share price moved: the market, the sector and the company's own news, and what the chart agrees on.

- returns: 1 month, 3 months and 52 weeks of the stock, the market index (日経平均 / S&P500) and the company's
  sector series (sector_map), all ending on the same day (the market series may stop earlier than the stock's)
- beta: the stock's weekly returns regressed on the index's over the last year; the 3-month move splits into the
  market's part (beta × the index) and the company's own part (the rest)
- big days: the last BIG_LOOKBACK trading days where the price moved BIG_ATR × the usual daily range on
  BIG_VOLUME × the usual volume, each with the disclosures within NEWS_DAYS trading days (news_table)
- consensus: what the technical indicators say together (cr_technicals)
Only numbers and dated facts; why the price moved is the writer's sentence, citing these rows.
"""
from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

SPANS = (("1か月", 30), ("3か月", 91), ("52週", 365))
SPLIT_SPANS = ("3か月", "1か月")
BASE_SLACK = 7       # days a base point may be older than the span start (holidays)
BETA_DAYS, BETA_STEP, BETA_MIN = 365, 5, 20
BIG_LOOKBACK, BIG_ATR, BIG_VOLUME, BIG_SHOWN = 120, 2.0, 1.5, 6
ATR_DAYS, VOLUME_DAYS, NEWS_DAYS = 14, 20, 2
INDEX = {"japan": ("JP_NIKKEI225", "日経平均"), "us": ("US_SP500", "S&P500")}

Points = list[tuple[str, float]]


def load_series(root: Path, market: str, ids: set[str]) -> dict[str, Points]:
    """{series_id: [(date, value)]} from market/data/{market}_series.csv (series_id,date,value,retrieved)."""
    path = root / "market" / "data" / f"{market}_series.csv"
    out: dict[str, Points] = {i: [] for i in ids}
    if not path.exists():
        return out
    with path.open(encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            if r.get("series_id") in ids:
                try:
                    out[r["series_id"]].append((r["date"], float(r["value"])))
                except (TypeError, ValueError):
                    continue
    return {k: sorted(v) for k, v in out.items()}


def _shift(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()


def _at(points: Points, date: str) -> tuple[str, float] | None:
    hits = [p for p in points if p[0] <= date]
    return hits[-1] if hits else None


def _change(points: Points, end: str, days: int) -> float | None:
    now, start = _at(points, end), _shift(end, days)
    base = _at(points, start)
    if not now or not base or not base[1] or base[0] < _shift(start, BASE_SLACK):
        return None
    return round((now[1] / base[1] - 1) * 100, 1)


def beta(rows: list[dict], index: Points) -> float | None:
    """Weekly (every BETA_STEP common trading days) returns of the last year, stock on index."""
    if not index:
        return None
    idx = dict(index)
    end = min(rows[-1]["date"], index[-1][0])
    start = _shift(end, BETA_DAYS)
    common = [(r["date"], r["close"], idx[r["date"]]) for r in rows if start < r["date"] <= end and r["date"] in idx]
    sample = common[::-1][::BETA_STEP][::-1]
    pairs = [(b[1] / a[1] - 1, b[2] / a[2] - 1) for a, b in zip(sample, sample[1:])]
    if len(pairs) < BETA_MIN:
        return None
    ms, mi = sum(p[0] for p in pairs) / len(pairs), sum(p[1] for p in pairs) / len(pairs)
    var = sum((p[1] - mi) ** 2 for p in pairs)
    return round(sum((p[0] - ms) * (p[1] - mi) for p in pairs) / var, 2) if var else None


def _returns(stock: Points, index: Points, sector: Points | None, end: str) -> list[dict]:
    out = []
    for label, days in SPANS:
        s, i = _change(stock, end, days), _change(index, end, days) if index else None
        sec = _change(sector, end, days) if sector else None
        out.append({"label": label, "stock": s, "index": i, "sector": sec,
                    "vs_index": round(s - i, 1) if s is not None and i is not None else None,
                    "vs_sector": round(s - sec, 1) if s is not None and sec is not None else None})
    return out


def _split(returns: list[dict], b: float | None) -> dict | None:
    if b is None:
        return None
    row = next((r for label in SPLIT_SPANS for r in returns
                if r["label"] == label and r["stock"] is not None and r["index"] is not None), None)
    if not row:
        return None
    market = round(b * row["index"], 1)
    return {"span": row["label"], "stock": row["stock"], "market": market, "own": round(row["stock"] - market, 1),
            "beta": b}


def _atr_pct(rows: list[dict], i: int) -> float | None:
    if i <= ATR_DAYS:
        return None
    trs = [max(rows[k]["high"] - rows[k]["low"], abs(rows[k]["high"] - rows[k - 1]["close"]),
               abs(rows[k]["low"] - rows[k - 1]["close"])) for k in range(i - ATR_DAYS, i)]
    return sum(trs) / ATR_DAYS / rows[i - 1]["close"] * 100


def _volume_ratio(rows: list[dict], i: int) -> float | None:
    past = [r["volume"] for r in rows[max(0, i - VOLUME_DAYS):i] if r.get("volume")]
    return round(rows[i]["volume"] / (sum(past) / len(past)), 1) if past and rows[i].get("volume") else None


def big_days(rows: list[dict], index: Points, news: list[dict]) -> list[dict]:
    """Days that moved BIG_ATR × the usual range on BIG_VOLUME × the usual volume, newest first, with their news."""
    idx = dict(index)
    dates = [r["date"] for r in rows]
    out = []
    for i in range(max(1, len(rows) - BIG_LOOKBACK), len(rows)):
        atr, change = _atr_pct(rows, i), (rows[i]["close"] / rows[i - 1]["close"] - 1) * 100
        ratio = _volume_ratio(rows, i)
        if atr is None or abs(change) < BIG_ATR * atr or (ratio is not None and ratio < BIG_VOLUME):
            continue
        lo, hi = dates[max(0, i - NEWS_DAYS)], dates[min(len(dates) - 1, i + NEWS_DAYS)]
        prev = dates[i - 1]
        market = (round((idx[dates[i]] / idx[prev] - 1) * 100, 1) if dates[i] in idx and prev in idx else None)
        out.append({"date": dates[i], "change": round(change, 1), "volume_ratio": ratio, "index_change": market,
                    "news": [{k: n[k] for k in ("date", "kind", "title", "summary")} for n in news
                             if lo <= n["date"] <= hi]})
    return sorted(out, key=lambda d: d["date"], reverse=True)[:BIG_SHOWN]


def consensus(t: dict) -> list[str]:
    """What the chart says, one fact a line (state, the averages it sits above / below, RSI, volume)."""
    out = [f"チャートの状態: {t['state']}"] if t.get("state") else []
    current = t.get("current")
    sides = [f"{label}（{value:,.0f}）の{'上' if current > value else '下'}"
             for label, value in (t.get("averages") or {}).items() if value and current]
    if sides:
        out.append("株価は " + "・".join(sides))
    m = t.get("momentum") or {}
    if m.get("rsi") is not None:
        out.append(f"RSI {m['rsi']:.0f}（{m.get('rsi_word') or '—'}）")
    v = (t.get("volume") or {}).get("value")
    if v:
        out.append(v)
    return out


def evaluate(rows: list[dict], index: Points, sector: Points | None, news: list[dict], technicals: dict,
             index_name: str, sector_name: str | None) -> dict:
    """{ok, end, index_name, sector_name, returns, beta, split, big_days, consensus, notes}."""
    if not rows:
        return {"ok": False, "notes": ["日々の株価が無い"]}
    notes = []
    end = min(rows[-1]["date"], index[-1][0]) if index else rows[-1]["date"]
    if end < rows[-1]["date"]:
        notes.append(f"指数・業種の系列は {end} まで。騰落率の比較はその日までで揃えた")
    if not index:
        notes.append(f"{index_name}の系列が無いため、市場との比較をしていない")
    stock = [(r["date"], r["close"]) for r in rows]
    b = beta(rows, index)
    returns = _returns(stock, index, sector, end)
    return {"ok": True, "end": end, "index_name": index_name, "sector_name": sector_name, "returns": returns,
            "beta": b, "split": _split(returns, b), "big_days": big_days(rows, index, news),
            "consensus": consensus(technicals), "notes": notes}
