"""Indicators computed from the collected series (-> facts["derived"]).

The writer must not calculate, so every ratio the judgement needs is computed here: real policy
rates, the yield-curve slope, the distance from moving averages, where the HY spread sits in its
history and the earnings yield against the 10-year yield. Inputs are the transformed series
(the catalog transform applied, e.g. CPI as year-on-year %) and the web-searched extras.
"""
from __future__ import annotations

import datetime as dt
import re

import store

Points = list[tuple[str, float]]

EXTRA_MAX_AGE_DAYS = 35        # a searched value older than this is shown but not scored
MA_WINDOWS = (50, 200)         # trading days
PERCENTILE_YEARS = 5
NUMBER = re.compile(r"[-−+]?\d+(?:,\d{3})*(?:\.\d+)?")
DATE_FULL = re.compile(r"(\d{4}-\d{2}-\d{2})")
TEN_YEAR_AVG = re.compile(r"10年平均\s*(\d+(?:\.\d+)?)")
PER_EXTRAS = {"japan": "日経平均 予想PER", "us": "S&P500 予想PER"}
TEN_YEAR = {"japan": "JP_JGB10Y", "us": "US_10Y"}


def parse_number(text: str | None) -> float | None:
    """First number in a cell ('19.0倍' -> 19.0, '−3,747' -> -3747); None for '—'."""
    m = NUMBER.search(text or "")
    if not m:
        return None
    return float(m.group(0).replace("−", "-").replace(",", ""))


def extra_date(text: str | None) -> str | None:
    """The first valid YYYY-MM-DD in a searched cell ('2026-10-21 週' -> '2026-10-21'); None if malformed."""
    m = DATE_FULL.search(text or "")
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1)).isoformat()
    except ValueError:
        return None


def is_old(date: str | None, week: str, max_days: int = EXTRA_MAX_AGE_DAYS) -> bool:
    if not date:
        return True
    return (dt.date.fromisoformat(week) - dt.date.fromisoformat(date)).days > max_days


def last(points: Points) -> tuple[str, float] | None:
    return points[-1] if points else None


def value_before(points: Points, date: str) -> tuple[str, float] | None:
    i = store._at_or_before(points, date)
    return points[i] if i is not None else None


def shifted(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) - dt.timedelta(days=days)).isoformat()


def item(did: str, label: str, market: str, value: float | None, unit: str, date: str | None, formula: str,
         inputs: list[dict], stale: bool = False, decimals: int = 2) -> dict:
    return {"id": did, "label": label, "market": market, "value": value, "unit": unit, "date": date,
            "formula": formula, "inputs": inputs, "stale": stale, "decimals": decimals}


def _input(sid: str, point: tuple[str, float] | None) -> dict:
    return {"id": sid, "date": point[0] if point else None, "value": point[1] if point else None}


def difference(did: str, label: str, market: str, series: dict[str, Points], a: str, b: str,
               formula: str, stale_ids: frozenset[str] = frozenset()) -> dict:
    """Latest a minus latest b (each at its own latest date; both dates are kept). Stale when an input is."""
    pa, pb = last(series.get(a, [])), last(series.get(b, []))
    value = pa[1] - pb[1] if pa and pb else None
    date = max(pa[0], pb[0]) if pa and pb else None
    return item(did, label, market, value, "%ポイント", date, formula, [_input(a, pa), _input(b, pb)],
                stale=bool({a, b} & stale_ids))


def ma_gap(points: Points, window: int) -> tuple[str, float] | None:
    """(date, % distance of the latest close from its `window`-day simple moving average)."""
    if len(points) < window:
        return None
    mean = sum(v for _, v in points[-window:]) / window
    return (points[-1][0], (points[-1][1] / mean - 1) * 100) if mean else None


def percentile(points: Points, years: int = PERCENTILE_YEARS) -> tuple[str, float, float] | None:
    """(date, share of points in the window at or below the latest, years actually covered)."""
    if not points:
        return None
    end = points[-1][0]
    start = store._shift(end, years=-years)
    window = [(d, v) for d, v in points if d >= start]
    covered = (dt.date.fromisoformat(end) - dt.date.fromisoformat(window[0][0])).days / 365.25
    share = sum(1 for _, v in window if v <= points[-1][1]) / len(window) * 100
    return end, share, covered


def find_extra(extras: list[dict], market: str, prefix: str) -> dict | None:
    return next((e for e in extras if e["market"] == market and e["indicator"].startswith(prefix)), None)


def yield_gap(market: str, series: dict[str, Points], extras: list[dict], week: str) -> dict:
    """Earnings yield (100 / forward P/E) minus the 10-year yield."""
    label = f"{'日経平均' if market == 'japan' else 'S&P500'} 益利回り − 10年債利回り"
    extra = find_extra(extras, market, PER_EXTRAS[market])
    per = parse_number(extra["value"]) if extra else None
    per_date = extra_date(extra["date"]) if extra else None
    ten = last(series.get(TEN_YEAR[market], []))
    inputs = [{"id": PER_EXTRAS[market], "date": per_date, "value": per}, _input(TEN_YEAR[market], ten)]
    value = 100 / per - ten[1] if per and ten else None
    return item(f"{'JP' if market == 'japan' else 'US'}_YIELD_GAP", label, market, value, "%ポイント", per_date,
                "100 ÷ 予想PER − 10年債利回り", inputs, stale=per is not None and is_old(per_date, week))


def per_vs_average(extras: list[dict], week: str) -> dict:
    extra = find_extra(extras, "us", PER_EXTRAS["us"])
    per = parse_number(extra["value"]) if extra else None
    m = TEN_YEAR_AVG.search(extra.get("note", "")) if extra else None
    avg = float(m.group(1)) if m else None
    date = extra_date(extra["date"]) if extra else None
    value = per - avg if per is not None and avg is not None else None
    return item("US_PER_VS_10Y_AVG", "S&P500 予想PER − 10年平均", "us", value, "倍", date,
                "予想PER − 10年平均（検索で得た注記）",
                [{"id": "予想PER", "date": date, "value": per}, {"id": "10年平均", "date": date, "value": avg}],
                stale=per is not None and is_old(date, week), decimals=1)


def ma_items(series: dict[str, Points]) -> list[dict]:
    out = []
    for sid, name, market in (("JP_NIKKEI225", "日経平均", "japan"), ("US_SP500", "S&P500", "us")):
        for window in MA_WINDOWS:
            gap = ma_gap(series.get(sid, []), window)
            out.append(item(f"{sid}_MA{window}", f"{name} {window}日移動平均からの乖離", market,
                            gap[1] if gap else None, "%", gap[0] if gap else None,
                            f"終値 ÷ {window}日移動平均 − 1", [_input(sid, last(series.get(sid, [])))], decimals=1))
    return out


RV_DAYS, TRADING_DAYS = 20, 252


def realized_vol(points: Points, days: int = RV_DAYS) -> tuple[str, float] | None:
    """(date, annualised standard deviation of the last `days` daily % changes)."""
    if len(points) <= days:
        return None
    window = points[-days - 1:]
    changes = [(b / a - 1) * 100 for (_, a), (_, b) in zip(window, window[1:]) if a]
    if len(changes) < 2:
        return None
    mean = sum(changes) / len(changes)
    var = sum((c - mean) ** 2 for c in changes) / (len(changes) - 1)
    return points[-1][0], var ** 0.5 * TRADING_DAYS ** 0.5


def rv_items(series: dict[str, Points], stale_ids: frozenset[str] = frozenset()) -> list[dict]:
    out = []
    for sid, name, market in (("JP_NIKKEI225", "日経平均", "japan"), ("US_SP500", "S&P500", "us")):
        rv = realized_vol(series.get(sid, []))
        out.append(item(f"{sid}_RV{RV_DAYS}", f"{name} の値動きの大きさ（{RV_DAYS}日の実現変動率、年率）", market,
                        rv[1] if rv else None, "%", rv[0] if rv else None,
                        f"直近{RV_DAYS}日の日次騰落率の標準偏差 × √{TRADING_DAYS}",
                        [_input(sid, last(series.get(sid, [])))], stale=sid in stale_ids, decimals=1))
    return out


def hy_percentile(series: dict[str, Points]) -> dict:
    found = percentile(series.get("US_HY_OAS", []))
    label = "米HYスプレッドの過去5年での位置"
    if not found:
        return item("US_HY_OAS_PCTL", label, "us", None, "%", None, "直近値以下の日の割合", [], decimals=0)
    date, share, covered = found
    formula = f"直近値以下の日の割合（{covered:.1f}年分のデータ）"
    return item("US_HY_OAS_PCTL", label, "us", share, "%", date, formula,
                [_input("US_HY_OAS", last(series["US_HY_OAS"]))], decimals=0)


def build_derived(series: dict[str, Points], extras: list[dict], week: str,
                  stale_ids: frozenset[str] = frozenset()) -> list[dict]:
    """series: transformed points by series id; stale_ids: series whose latest point is too old
    (facts.is_stale). Missing inputs leave value None (never guessed)."""
    out = [
        difference("JP_REAL_POLICY", "日本 実質政策金利", "japan", series, "JP_CALL", "JP_CPI_CORE_YOY",
                   "無担保コールO/N − CPI 生鮮食品を除く総合（前年比）", stale_ids),
        difference("US_REAL_POLICY", "米国 実質政策金利", "us", series, "US_FFR_UPPER", "US_CORE_PCE_YOY",
                   "FF金利 誘導目標上限 − コアPCE（前年比）", stale_ids),
        difference("JP_SLOPE", "日本 長短金利差（10年−2年）", "japan", series, "JP_JGB10Y", "JP_JGB2Y",
                   "10年国債利回り − 2年国債利回り", stale_ids),
    ]
    out += ma_items(series) + rv_items(series, stale_ids)
    out += [hy_percentile(series), yield_gap("japan", series, extras, week), yield_gap("us", series, extras, week),
            per_vs_average(extras, week)]
    return out
