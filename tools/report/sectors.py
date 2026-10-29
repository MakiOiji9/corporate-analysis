"""Sector moves (-> facts["sectors"], brief 15., outlook 12., the sector slide).

Per sector ETF (catalog entries with "display": "sectors"): the 1-month and 3-month change and
the gap against the market index over the same span. Sectors are ranked by the 1-month gap.
Only the numbers are produced; why a sector moved is not inferred here.
"""
from __future__ import annotations

from derived import Points, last, shifted, value_before

INDEX = {"japan": ("JP_NIKKEI225", "日経平均"), "us": ("US_SP500", "S&P500")}
SPANS = {"m1": 30, "m3": 91}
RANK = 3


GAP_DAYS = 7          # the base point may be at most this much older than the span start (holidays)


def pct_change(points: Points, days: int) -> float | None:
    """% change over `days` ending at the latest point; None when the base point is missing or too old."""
    now = last(points)
    target = shifted(now[0], days) if now else ""
    before = value_before(points, target) if now else None
    if not now or not before or not before[1] or before[0] < shifted(target, GAP_DAYS):
        return None
    return (now[1] / before[1] - 1) * 100


def until(points: Points, date: str) -> Points:
    return [p for p in points if p[0] <= date]


def sector_rows(entries: list[dict], series: dict[str, Points], index_points: Points) -> list[dict]:
    """Every sector is measured over the same span as the index: both end on the earlier latest date."""
    index_change = {k: pct_change(index_points, d) for k, d in SPANS.items()}
    end = last(index_points)[0] if index_points else None
    rows = []
    for e in entries:
        pts = until(series.get(e["id"], []), end) if end else series.get(e["id"], [])
        p = last(pts)
        if end and p and p[0] < shifted(end, GAP_DAYS):
            pts, p = [], None  # the ETF stopped updating; a gap against the index would mix spans
        change = {k: pct_change(pts, d) for k, d in SPANS.items()}
        rel = {k: change[k] - index_change[k] if change[k] is not None and index_change[k] is not None else None
               for k in SPANS}
        rows.append({"id": e["id"], "name": e["name"], "symbol": e.get("params", {}).get("symbol", ""),
                     "date": p[0] if p else None, "close": p[1] if p else None,
                     "m1": change["m1"], "m3": change["m3"], "rel1": rel["m1"], "rel3": rel["m3"],
                     "source": e.get("source", "")})
    return rows


def build_sectors(catalogs: dict[str, dict], series: dict[str, Points]) -> dict[str, dict]:
    """{market: {index, index_m1, index_m3, rows, top, bottom}}; top/bottom are ids by the 1-month gap."""
    out = {}
    for market, (index_id, index_name) in INDEX.items():
        entries = [e for e in catalogs.values() if e.get("market") == market and e.get("display") == "sectors"]
        if not entries:
            continue
        rows = sector_rows(entries, series, series.get(index_id, []))
        ranked = sorted((r for r in rows if r["rel1"] is not None), key=lambda r: r["rel1"], reverse=True)
        out[market] = {"index": index_name,
                       "index_m1": pct_change(series.get(index_id, []), SPANS["m1"]),
                       "index_m3": pct_change(series.get(index_id, []), SPANS["m3"]),
                       "rows": rows, "top": [r["id"] for r in ranked[:RANK]],
                       "bottom": [r["id"] for r in ranked[RANK:][::-1][:RANK]]}  # weakest first, never in top
    return out
