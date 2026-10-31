"""Extra material of the company report: shareholder returns (dividends) and the peer comparison table.

dividends()   1株配当 (the latest full-year result and the newest company forecast) from data/tdnet_facts.csv
              (DividendPerShare / PayoutRatio of the AnnualMember contexts), with the dividend yield on the
              valuation's price and the payout ratio on the forecast EPS (price ÷ forecast PER).
peer_table()  one row per company (the target first, then the peers, then the peers' median) with the forward
              PER, PBR, EV/EBITDA, the 3-year sales CAGR, ROE, the operating margin and the equity ratio, joined by
              name from the valuation, profitability and safety results.
"""
from __future__ import annotations

import csv
import re
import statistics
from pathlib import Path

import freshness as FR

NAME_NOTE = re.compile(r"[（(][^）)]*[）)]|株式会社|\s")
PEER_COLUMNS = (("per_forecast", "PER（予想）", "倍"), ("pbr", "PBR", "倍"), ("ev_ebitda", "EV/EBITDA", "倍"),
                ("cagr", "売上の3年CAGR", "%"), ("roe", "ROE", "%"), ("margin", "営業利益率", "%"),
                ("equity_ratio", "自己資本比率", "%"))


MATCH_PREFIX = 4  # 'シグマクシスHD' and 'シグマクシス・ホールディングス' are the same company


def _key(name: str | None) -> str:
    return NAME_NOTE.sub("", name or "")


def _lookup(mapping: dict[str, float | None], name: str) -> float | None:
    """The value for a peer whose name is written differently in another analysis (shared leading characters)."""
    key = _key(name)
    if key in mapping:
        return mapping[key]
    hits = [v for k, v in mapping.items() if len(key) >= MATCH_PREFIX and k[:MATCH_PREFIX] == key[:MATCH_PREFIX]]
    return hits[0] if len(hits) == 1 else None


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _annual_rows(company_path: Path) -> list[dict]:
    path = company_path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if "AnnualMember" in (r.get("context") or "")]


def _latest(rows: list[dict], filed: dict, element: str, context: str, member: str) -> tuple[float | None, str | None]:
    hits = [r for r in rows if r.get("element") == element and r["context"].startswith(context)
            and member in r["context"] and _num(r.get("value")) is not None]
    if not hits:
        return None, None
    best = max(hits, key=lambda r: (filed.get(r.get("doc_id"), ""), r.get("fiscal_year_end", "")))
    return _num(best["value"]), best.get("fiscal_year_end")


def dividends(company_path: Path, price: float | None, per_forecast: float | None) -> dict:
    rows = _annual_rows(company_path)
    filed = {r.get("doc_id"): FR._filed(r.get("filing_date", "")) or "" for r in rows}
    actual, actual_fy = _latest(rows, filed, "DividendPerShare", "CurrentYearDuration", "ResultMember")
    forecast, forecast_fy = _latest(rows, filed, "DividendPerShare", "CurrentYearDuration", "ForecastMember")
    nxt, nxt_fy = _latest(rows, filed, "DividendPerShare", "NextYearDuration", "ForecastMember")
    if forecast is None or (nxt_fy and forecast_fy and nxt_fy > forecast_fy):
        forecast, forecast_fy = nxt, nxt_fy
    payout_actual, _ = _latest(rows, filed, "PayoutRatio", "CurrentYearDuration", "ResultMember")
    eps_forecast = price / per_forecast if price and per_forecast else None
    return {"actual": actual, "actual_fy": actual_fy, "forecast": forecast, "forecast_fy": forecast_fy,
            "payout_actual": payout_actual,
            "yield": round(forecast / price * 100, 2) if forecast is not None and price else None,
            "payout_forecast": round(forecast / eps_forecast * 100, 1) if forecast is not None and eps_forecast else None,
            "source": "data/tdnet_facts.csv（決算短信）" if rows else None}


def _median(values: list[float | None]) -> float | None:
    known = [v for v in values if v is not None]
    return round(statistics.median(known), 2) if known else None


def peer_table(analyses: dict[str, dict], name: str) -> dict:
    val = analyses["valuation"].get("detail") or {}
    prof = analyses["profitability"].get("detail") or {}
    safety = analyses["safety"].get("detail") or {}
    tc = analyses["three_c"].get("detail") or {}
    margins = {_key(p["name"]): p["margin"] for p in prof.get("peer_margins") or []}
    equity = {_key(p["name"]): p["equity_ratio"] for p in safety.get("peers") or []}
    peers = []
    for p in val.get("peers") or []:
        peers.append({"name": p["name"], "self": False, "per_forecast": p.get("per_forecast") or p.get("per_actual"),
                      "pbr": p.get("pbr"), "ev_ebitda": p.get("ev_ebitda_calc"), "cagr": p.get("cagr"),
                      "roe": p.get("roe"), "margin": _lookup(margins, p["name"]),
                      "equity_ratio": _lookup(equity, p["name"])})
    own_cagr = next((c.get("cagr") for c in tc.get("comparison") or [] if c.get("self")), None)
    own_roe = ((prof.get("roe_rows") or [{}])[-1] or {}).get("roe")
    own_equity = next((i["value"] for i in safety.get("items") or [] if i.get("name") == "自己資本比率"), None)
    own = {"name": name, "self": True, "per_forecast": val.get("per_forecast"), "pbr": val.get("pbr"),
           "ev_ebitda": val.get("ev_ebitda"), "cagr": own_cagr, "roe": own_roe,
           "margin": (prof.get("margin") or {}).get("self"), "equity_ratio": own_equity}
    median = {"name": "同業の中央値", "self": False, **{k: _median([p[k] for p in peers]) for k, _, _ in PEER_COLUMNS}}
    return {"rows": [own] + peers, "median": median if peers else None,
            "columns": [list(c) for c in PEER_COLUMNS]}
