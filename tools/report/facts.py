"""Collect every number, series, date and document the weekly report shows (-> {week}_facts.json).

Inputs are only what collect-market-info produced: market/data/*.csv (time series), the files
listed in market/LATEST.md (indicator tables, calendars, status) and the policy summaries.
Values are copied or simply computed (changes, year-on-year, rebasing); nothing is judged here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass

import mdparse as M
import store
from state import Paths, previous_outlook

MARKETS = ("japan", "us")
MARKET_LABEL = {"japan": "日本", "us": "米国"}
LABEL_MARKET = {v: k for k, v in MARKET_LABEL.items()}
CALENDAR_DAYS = 84            # timeline: 12 weeks from the report Monday
SPARK_DAYS = 365
CHANGE_DAYS = {"1w": 7, "1m": 30}
DATE_FULL = re.compile(r"(\d{4}-\d{2}-\d{2})")
DATE_MONTH = re.compile(r"(\d{4}-\d{2})")
LATEST_KINDS = {"指標": "indicators", "日程・市場指標": "calendar", "収集ステータス": "status"}


@dataclass(frozen=True)
class KpiSpec:
    sid: str
    label: str
    change: str  # "pct" (prices, FX) or "abs" (rates, spreads, VIX)


@dataclass(frozen=True)
class ChartSpec:
    cid: str
    title: str
    unit: str
    kind: str                           # "line" / "bar"
    years: int
    series: tuple[tuple[str, str], ...]  # (series id, legend label)
    rebase: bool = False


KPIS = (
    KpiSpec("JP_NIKKEI225", "日経平均", "pct"),
    KpiSpec("US_SP500", "S&P500", "pct"),
    KpiSpec("US_NASDAQ", "NASDAQ総合", "pct"),
    KpiSpec("JP_USDJPY", "ドル円", "pct"),
    KpiSpec("JP_JGB10Y", "日本10年債利回り", "abs"),
    KpiSpec("US_10Y", "米国10年債利回り", "abs"),
    KpiSpec("US_VIX", "VIX", "abs"),
    KpiSpec("US_HY_OAS", "米ハイイールド債スプレッド", "abs"),
)

CHARTS = (
    ChartSpec("equity", "株価指数（1年前=100）", "指数", "line", 1,
              (("JP_NIKKEI225", "日経平均"), ("US_SP500", "S&P500"), ("US_NASDAQ", "NASDAQ総合")), rebase=True),
    ChartSpec("policy_rates", "政策金利（5年）", "%", "line", 5,
              (("JP_CALL", "日銀 無担保コールO/N"), ("US_FFR_UPPER", "FF金利 誘導目標上限"))),
    ChartSpec("yields10", "10年国債利回り（2年）", "%", "line", 2,
              (("JP_JGB10Y", "日本10年"), ("US_10Y", "米国10年"))),
    ChartSpec("usdjpy", "ドル円（1年）", "円/ドル", "line", 1, (("JP_USDJPY", "ドル円"),)),
    ChartSpec("jp_prices", "日本の消費者物価（前年同月比、3年）", "%", "line", 3,
              (("JP_CPI_YOY", "総合"), ("JP_CPI_CORE_YOY", "生鮮食品を除く"),
               ("JP_CPI_CORECORE_YOY", "生鮮食品・エネルギーを除く"))),
    ChartSpec("us_prices", "米国の物価（前年同月比、3年）", "%", "line", 3,
              (("US_CPI_YOY", "CPI 総合"), ("US_CORE_CPI_YOY", "CPI コア"), ("US_CORE_PCE_YOY", "PCE コア"))),
    ChartSpec("jp_activity", "日本の景気動向指数（3年）", "指数", "line", 3,
              (("JP_CI_LEADING", "先行指数"), ("JP_CI_COINCIDENT", "一致指数"))),
    ChartSpec("us_payrolls", "米国 非農業部門雇用者数 前月差（2年）", "千人", "bar", 2, (("US_NFP_CHANGE", "前月差"),)),
    ChartSpec("jp_foreign_flow", "海外投資家の売買差引（週次）", "億円", "bar", 1, (("JP_FLOW_FOREIGN", "海外投資家"),)),
    ChartSpec("us_cot", "CFTC E-mini S&P500 非商業部門ネット（週次）", "枚", "bar", 1,
              (("US_COT_ES_NET", "ネット建玉"),)),
)

Points = list[tuple[str, float]]


# ---------------------------------------------------------------- time series

def load_catalogs(paths: Paths) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for market in MARKETS:
        catalog = json.loads((paths.catalog_dir / f"{market}.json").read_text(encoding="utf-8"))
        for entry in catalog.get("series", []):
            out[entry["id"]] = {**entry, "market": market}
    return out


def load_series(paths: Paths) -> dict[str, Points]:
    out: dict[str, Points] = {}
    for market in MARKETS:
        csv_path = paths.data / f"{market}_series.csv"
        if csv_path.exists():
            out.update(store.load_points(csv_path))
    return out


def transformed_points(points: Points, transform: str) -> Points:
    """The catalog transform applied to every point (yoy_pct / diff need history, so early points drop)."""
    if transform == "level":
        return list(points)
    out = []
    for i, (date, _) in enumerate(points):
        value = store.transformed(points, i, transform)
        if value is not None:
            out.append((date, value))
    return out


def since(points: Points, end: str, days: int) -> Points:
    start = (dt.date.fromisoformat(end) - dt.timedelta(days=days)).isoformat()
    return [p for p in points if p[0] >= start]


def weekly(points: Points) -> Points:
    """Last point of each ISO week (keeps daily series light in the HTML)."""
    last: dict[tuple[int, int], tuple[str, float]] = {}
    for date, value in points:
        iso = dt.date.fromisoformat(date).isocalendar()
        last[(iso[0], iso[1])] = (date, value)
    return [last[k] for k in sorted(last)]


def change(points: Points, base_date: str, kind: str) -> dict | None:
    """Latest value against the last point on or before base_date (% for pct, difference for abs)."""
    i = store._at_or_before(points, base_date) if points else None
    if i is None:
        return None
    base_on, base = points[i]
    latest = points[-1][1]
    if kind == "pct":
        if not base:
            return None
        delta = (latest / base - 1) * 100
    else:
        delta = latest - base
    return {"base_date": base_on, "base": base, "delta": delta}


def build_kpis(catalogs: dict[str, dict], series: dict[str, Points]) -> list[dict]:
    kpis = []
    for spec in KPIS:
        entry = catalogs.get(spec.sid, {})
        points = series.get(spec.sid, [])
        kpi = {"id": spec.sid, "label": spec.label, "market": entry.get("market", ""),
               "unit": entry.get("unit", ""), "decimals": entry.get("decimals", 2), "change": spec.change,
               "source": entry.get("source", ""), "date": None, "value": None, "changes": {}, "spark": [],
               "high_1y": None, "low_1y": None}
        if points:
            last_date = points[-1][0]
            year = since(points, last_date, SPARK_DAYS)
            bases = {k: (dt.date.fromisoformat(last_date) - dt.timedelta(days=d)).isoformat()
                     for k, d in CHANGE_DAYS.items()}
            bases["1y"] = store._shift(last_date, years=-1)
            kpi.update(date=last_date, value=points[-1][1], spark=weekly(year),
                       changes={k: change(points, b, spec.change) for k, b in bases.items()},
                       high_1y=list(max(year, key=lambda p: p[1])), low_1y=list(min(year, key=lambda p: p[1])))
        kpis.append(kpi)
    return kpis


def build_indicators(catalogs: dict[str, dict], series: dict[str, Points]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {m: [] for m in MARKETS}
    for sid, entry in catalogs.items():
        summary = store.summarize(series.get(sid, []), entry.get("transform", "level"),
                                  entry.get("frequency", "monthly"))
        row = {"id": sid, "group": entry.get("group", ""), "name": entry["name"], "unit": entry.get("unit", ""),
               "decimals": entry.get("decimals", 1), "source": entry.get("source", ""),
               "date": None, "value": None, "prev_date": None, "prev": None, "year_date": None, "year": None}
        if summary:
            row.update(date=summary.latest_date, value=summary.latest, prev_date=summary.prev_date,
                       prev=summary.prev, year_date=summary.year_date, year=summary.year)
        out[entry["market"]].append(row)
    return out


def chart_lines(spec: ChartSpec, catalogs: dict[str, dict], series: dict[str, Points]) -> list[dict]:
    lines = []
    for sid, label in spec.series:
        entry = catalogs.get(sid, {})
        lines.append({"id": sid, "label": label, "market": entry.get("market", ""),
                      "points": transformed_points(series.get(sid, []), entry.get("transform", "level"))})
    ends = [ln["points"][-1][0] for ln in lines if ln["points"]]
    if not ends:
        return lines
    end = max(ends)
    for ln in lines:
        pts = since(ln["points"], end, spec.years * 366)
        if catalogs.get(ln["id"], {}).get("frequency") == "daily":
            pts = weekly(pts)
        if spec.rebase and pts and pts[0][1]:
            pts = [(d, v / pts[0][1] * 100) for d, v in pts]
        ln["points"] = [(d, round(v, 4)) for d, v in pts]
    return lines


def build_charts(catalogs: dict[str, dict], series: dict[str, Points]) -> list[dict]:
    charts = []
    for spec in CHARTS:
        sources = sorted({catalogs.get(sid, {}).get("source", "") for sid, _ in spec.series} - {""})
        charts.append({"id": spec.cid, "title": spec.title, "unit": spec.unit, "kind": spec.kind,
                       "series": chart_lines(spec, catalogs, series), "sources": sources})
    return charts


# ---------------------------------------------------------------- generated Markdown files

def latest_files(paths: Paths) -> dict[str, dict[str, str]]:
    """{market: {indicators|calendar|status: repo-relative path}} from LATEST.md section 1."""
    out: dict[str, dict[str, str]] = {m: {} for m in MARKETS}
    if not paths.latest.exists():
        return out
    for row in M.table_dicts(M.section(paths.latest.read_text(encoding="utf-8"), "1.")):
        m = re.match(r"^(.+)（(日本|米国)）$", row.get("種類", ""))
        if m and m.group(1) in LATEST_KINDS:
            out[LABEL_MARKET[m.group(2)]][LATEST_KINDS[m.group(1)]] = row.get("ファイル", "")
    return out


def latest_docs(paths: Paths) -> list[dict]:
    """Latest document per watch item, from LATEST.md section 2."""
    if not paths.latest.exists():
        return []
    rows = M.table_dicts(M.section(paths.latest.read_text(encoding="utf-8"), "2."))
    return [{"market": LABEL_MARKET.get(r.get("市場", ""), ""), "layer": r.get("層", ""),
             "watch": r.get("監視項目", ""), "date": r.get("公表日", ""), "title": r.get("文書", ""),
             "path": r.get("要旨ファイル", "")} for r in rows]


def event_span(text: str) -> tuple[str, str, bool] | None:
    """(start, end, exact) for '2026-10-14', '2026-12 予定', '2027-01-09 まで'."""
    full = DATE_FULL.search(text)
    if full:
        return full.group(1), full.group(1), True
    month = DATE_MONTH.search(text)
    if month:
        return f"{month.group(1)}-01", f"{month.group(1)}-31", False
    return None


def calendar_rows(text: str, number: str, market: str, kind: str) -> list[dict]:
    rows = []
    for r in M.table_dicts(M.section(text, number)):
        values = list(r.values())
        if len(values) < 5 or all(M.is_blank(v) for v in values[:3]):
            continue
        rows.append({"date": values[0], "market": market, "event": values[1], "detail": values[2],
                     "source": values[3], "certainty": values[4], "kind": kind})
    return rows


def parse_calendar(text: str, market: str) -> dict[str, list]:
    extras = [{"market": market, "indicator": v[0], "value": v[1], "date": v[2], "source": v[3], "certainty": v[4]}
              for v in (list(r.values()) for r in M.table_dicts(M.section(text, "4.")))
              if len(v) >= 5 and not M.is_blank(v[0])]
    return {"events": calendar_rows(text, "1.", market, "確定") + calendar_rows(text, "2.", market, "検索"),
            "politics": calendar_rows(text, "3.", market, "動き"),
            "extras": extras}


def upcoming(events: list[dict], week: str, days: int = CALENDAR_DAYS) -> list[dict]:
    end = (dt.date.fromisoformat(week) + dt.timedelta(days=days)).isoformat()
    picked = []
    for ev in events:
        span = event_span(ev["date"])
        if span and span[1] >= week and span[0] <= end:
            picked.append((span[0], 0 if span[2] else 1, ev["market"], ev))
    return [p[3] for p in sorted(picked, key=lambda p: p[:3])]


def parse_failed(text: str, market: str) -> list[dict]:
    rows = M.table_dicts(M.section(text, "2."))
    return [{"market": market, "name": r.get("指標", ""), "reason": r.get("理由", "")}
            for r in rows if not M.is_blank(r.get("指標")) and r.get("指標") != "なし"]


def parse_review(text: str) -> list[dict]:
    rows = M.table_dicts(M.section(text, "7."))
    return [{"file": r.get("ファイル", ""), "content": r.get("内容", "")}
            for r in rows if not M.is_blank(r.get("内容")) and r.get("ファイル") != "なし"]


def previous_judgments(paths: Paths, week: str) -> dict | None:
    path = previous_outlook(paths, week)
    if not path:
        return None
    out = {"week": path.name[:10], "path": paths.rel(path)}
    for r in M.table_dicts(M.section(path.read_text(encoding="utf-8"), "1.")):
        market = LABEL_MARKET.get(r.get("市場", ""))
        if market:
            out[market] = r.get("地合い判断", "")
    return out


def read_rel(paths: Paths, rel: str) -> str:
    target = paths.root / rel
    return target.read_text(encoding="utf-8") if rel and target.is_file() else ""


def build_facts(paths: Paths, week: str, session: str, today: str) -> dict:
    catalogs, series = load_catalogs(paths), load_series(paths)
    files = latest_files(paths)
    events, politics, extras, failed, review = [], [], [], [], []
    seen_status: set[str] = set()
    for market in MARKETS:
        cal = parse_calendar(read_rel(paths, files[market].get("calendar", "")), market)
        events += cal["events"]
        politics += cal["politics"]
        extras += cal["extras"]
        failed += parse_failed(read_rel(paths, files[market].get("indicators", "")), market)
        status = files[market].get("status", "")
        if status and status not in seen_status:
            seen_status.add(status)
            review += parse_review(read_rel(paths, status))
    return {
        "week": week,
        "generated": today,
        "session": session,
        "files": files,
        "kpis": build_kpis(catalogs, series),
        "indicators": build_indicators(catalogs, series),
        "charts": build_charts(catalogs, series),
        "events": upcoming(events, week),
        "politics": sorted(politics, key=lambda p: p["date"], reverse=True),
        "extras": extras,
        "docs": latest_docs(paths),
        "series_failed": failed,
        "review_items": review,
        "previous": previous_judgments(paths, week),
    }
