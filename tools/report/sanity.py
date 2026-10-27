"""Plausibility checks on the collected numbers (-> facts["checks"], brief 13., outlook 7.).

Nothing is corrected here; a suspicious value is listed as 要確認 so the writer does not build
a judgement on it without saying so.
"""
from __future__ import annotations

import re

from derived import extra_date, is_old, parse_number

PCE_OVER_CPI = 0.3            # core PCE normally runs below core CPI
PER_RANGE = (8.0, 35.0)       # forward P/E outside this is likely a parsing or source error
GROWTH_LIMIT = 25.0           # |growth %| above this in a searched cell is unusual
GROWTH = re.compile(r"成長率[^0-9+\-−]*([+\-−]?\d+(?:\.\d+)?)\s*%")


def _row(rows: dict[str, dict], sid: str) -> dict | None:
    r = rows.get(sid)
    return r if r and r.get("value") is not None else None


def pce_vs_cpi(indicators: dict[str, list[dict]]) -> list[dict]:
    rows = {r["id"]: r for r in indicators.get("us", [])}
    pce, cpi = _row(rows, "US_CORE_PCE_YOY"), _row(rows, "US_CORE_CPI_YOY")
    if not pce or not cpi or pce["value"] - cpi["value"] < PCE_OVER_CPI:
        return []
    return [{"market": "us", "item": "コアPCE がコアCPI を上回る（通常は逆）",
             "detail": f"コアPCE {pce['value']:.1f}%（{pce['date'][:7]}）／コアCPI {cpi['value']:.1f}%"
                       f"（{cpi['date'][:7]}）。系列の取り違え・改定を確認する"}]


def extra_checks(extras: list[dict], week: str) -> list[dict]:
    out = []
    for e in extras:
        value = parse_number(e["value"])
        if "PER" in e["indicator"] and value is not None and not PER_RANGE[0] <= value <= PER_RANGE[1]:
            out.append({"market": e["market"], "item": f"{e['indicator']} が通常の範囲外",
                        "detail": f"{e['value']}（{PER_RANGE[0]:g}〜{PER_RANGE[1]:g}倍の外）"})
        for m in GROWTH.finditer(f"{e['value']} {e.get('note', '')}"):
            growth = float(m.group(1).replace("−", "-"))
            if abs(growth) > GROWTH_LIMIT:
                out.append({"market": e["market"], "item": f"{e['indicator']} の成長率が極端",
                            "detail": f"{m.group(0)}（検索で得た値。原典で確認する）"})
        if value is not None and is_old(extra_date(e["date"]), week):
            out.append({"market": e["market"], "item": f"{e['indicator']} の時点が古い",
                        "detail": f"{e['date']} 時点（足元の判断・評価の信号には使わない）"})
    return out


def check(facts: dict) -> list[dict]:
    return pce_vs_cpi(facts["indicators"]) + extra_checks(facts["extras"], facts["week"])
