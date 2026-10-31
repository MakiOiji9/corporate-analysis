"""facts.json of the company report: the nine analyses' conclusions, STEP 1・2・3, the three horizons, the price
history, the market outlook and the next review date. Every number and judgement of the report comes from here;
the writer only adds words (cr_doc.py), and the HTML (cr_render.py) is drawn from this and the filled md.
"""
from __future__ import annotations

from pathlib import Path

import cr_judge as J
import cr_prices as CP
import cr_status as S
import mdparse as M
import outlook as O
from sf_series import JAPAN_TICKER, unit_label

MARKETS = {"日本": "japan", "米国": "us"}
STATUS_EARNINGS = "四半期決算"
GAP_LIMIT = 12  # 材料不足の一覧に出す数（重複を除く）


def _get(d: object, *keys: str) -> object:
    for key in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(key)
    return d


def market_of(company: S.Company) -> str:
    return "日本" if JAPAN_TICKER.match(company.ticker.upper()) else "米国"


# ---------------------------------------------------------------- per analysis

def _five_forces(r: dict) -> dict:
    return {"industry": r.get("industry"), "total": r.get("total"),
            "factors": [{"name": f.get("name"), "rating": f.get("rating"), "reason": f.get("reason")}
                        for f in r.get("factors") or []]}


def _three_c(r: dict) -> dict:
    return {"win_reason": r.get("win_reason"), "top_kbf": r.get("top_kbf"),
            "customer": _get(r, "customer", "conclusion"), "competitor": _get(r, "competitor", "rating"),
            "growth": _get(r, "growth", "rating")}


def _moat(r: dict) -> dict:
    return {"durability": r.get("durability"), "effective": r.get("effective_moats") or [],
            "moats": [{"type": m.get("type"), "rating": m.get("rating")} for m in r.get("moats") or []],
            "risks": r.get("risks") or []}


def _swot(r: dict) -> dict:
    quadrants = {key: [{"id": i.get("id"), "fact": i.get("fact"), "impact": i.get("impact")} for i in items]
                 for key, items in (r.get("quadrants") or {}).items()}
    return {"sentence": r.get("sentence"), "top_strength": r.get("top_strength"), "top_threat": r.get("top_threat"),
            "quadrants": quadrants}


def _profitability(r: dict) -> dict:
    return {"roe_average": _get(r, "step1", "average"), "roe_minimum": _get(r, "step1", "minimum"),
            "margin": {k: _get(r, "step2", k) for k in ("year", "self", "avg", "diff", "trend")},
            "source": _get(r, "step3", "source"),
            "roe_rows": [{"year": x.get("year"), "roe": x.get("roe")} for x in r.get("roe_rows") or []]}


def _growth(r: dict) -> dict:
    return {"sales_cagr": _get(r, "step1", "sales_cagr"), "eps_cagr": _get(r, "step1", "eps_cagr"),
            "growth_type": _get(r, "step1", "rating"), "plan": _get(r, "step3", "rating"),
            "plan_average": _get(r, "step3", "average"), "quality": _get(r, "step4", "quality"),
            "progress": r.get("progress"),
            "rows": [{k: x.get(k) for k in ("year", "sales", "operating_income", "net_income", "eps")}
                     for x in r.get("rows") or []]}


def _safety(r: dict) -> dict:
    s1 = r.get("step1") or {}
    return {"items": [{k: i.get(k) for k in ("name", "value", "peer_avg", "rating", "target")}
                      for i in s1.get("items") or []],
            "net_cash": s1.get("net_cash"), "debt_free": s1.get("debt_free"), "trend": _get(r, "step2", "rating")}


def _cash_flow(r: dict) -> dict:
    return {"steps": [{"rating": _get(r, k, "rating"), "sentence": _get(r, k, "sentence")}
                      for k in ("step1", "step2", "step3", "step4", "step5")],
            "ratio": _get(r, "step3", "ratio"),
            "rows": [{k: x.get(k) for k in ("year", "cfo", "cfi", "fcf", "net_income", "ratio")}
                     for x in r.get("cf_rows") or []]}


def _valuation(r: dict) -> dict:
    items = {name: {"rating": _get(r, key, "rating"), "sentence": _get(r, key, "sentence")}
             for key, name in (("per", "PER"), ("pbr", "PBR"), ("peg", "PEG"), ("ev", "EV/EBITDA"))}
    axis = _get(r, "per", "rule", "axis1") or {}
    return {"price": r.get("price"), "items": items, "sheet": r.get("sheet"), "flip_prices": r.get("flip_prices") or [],
            "per_actual": _get(r, "per", "per_actual"), "per_forecast": _get(r, "per", "per_forecast"),
            "pbr": _get(r, "pbr", "pbr"), "per_range": {k: axis.get(k) for k in ("low", "high", "position")},
            "cheap_reason": _get(r, "handoff", "cheap_reason"), "final_check": _get(r, "step3", "final_check")}


DETAILS = {"five_forces": _five_forces, "three_c": _three_c, "moat": _moat, "swot": _swot,
           "profitability": _profitability, "growth": _growth, "safety": _safety, "cash_flow": _cash_flow,
           "valuation": _valuation}


def analysis(step: S.Step, company: S.Company) -> dict:
    found = S.latest(step, company)
    base = {"key": step.key, "label": step.label, "step": step.number, "skill": step.skill}
    if not found:
        return {**base, "date": None, "verdict": None, "reason": "未実施", "points": "", "gaps": [], "md": None,
                "detail": {}}
    date, r = found
    gaps = [g for g in r.get("gaps") or [] if not M.is_blank(g) and g != "なし"]
    return {**base, "date": date, "verdict": r.get(step.verdict_key), "reason": r.get("verdict_reason") or "",
            "points": _get(r, "handoff", "report_points") or "", "gaps": gaps, "md": r.get("md"),
            "detail": DETAILS[step.key](r)}


# ---------------------------------------------------------------- outlook / review

def outlook_rows(root: Path, outlook: dict, market: str) -> dict:
    """{overall, summary, rows: {短期/中期/長期: {judgment, scenario, downside, watch}}} for the company's market."""
    if not outlook.get("path"):
        return {"overall": None, "summary": None, "rows": {}}
    parsed = O.parse((root / outlook["path"]).read_text(encoding="utf-8"))
    key = MARKETS[market]
    rows = {r["period"]: {k: r[k] for k in ("judgment", "scenario", "downside", "watch")}
            for r in parsed["outlook"] if r["market"] == key}
    overall = parsed["judgments"].get(key, {})
    return {"overall": overall.get("judgment"), "summary": overall.get("summary"), "rows": rows}


def next_review(company: S.Company) -> str:
    """The next earnings release as status.md states it (the framework reviews after each one)."""
    status = company.path / "status.md"
    if status.exists():
        for row in M.table_dicts(M.section(status.read_text(encoding="utf-8"), "1.")):
            if STATUS_EARNINGS in row.get("区分", "") and not M.is_blank(row.get("次回更新トリガー")):
                return row["次回更新トリガー"]
    return "次の決算発表の後（日付は IR カレンダーで確認）"


# ---------------------------------------------------------------- judgements

def judgements(found: dict[str, dict], prices: dict, outlook: dict) -> dict:
    v = {k: a["verdict"] for k, a in found.items()}
    margin_diff = _get(found["profitability"], "detail", "margin", "diff")
    s1 = J.step1(v["five_forces"], v["three_c"], v["moat"], v["swot"])
    mismatch = J.mismatches(v["moat"], v["three_c"], v["profitability"], margin_diff)
    s2 = J.step2({"収益性": v["profitability"], "成長性": v["growth"], "安全性": v["safety"],
                  "キャッシュフロー": v["cash_flow"]}, mismatch)
    s3 = v["valuation"]
    long = J.long_term(s1, s2, s3)
    growth = found["growth"]["detail"]
    rows = outlook["rows"]
    mid = J.mid_term(long, growth.get("progress"), _get(rows, "中期", "judgment"), growth.get("plan"), s3)
    position, gap = CP.short_inputs(prices)
    short = J.short_term(long, _get(rows, "短期", "judgment"), position, gap)
    return {"step1": s1, "step2": {**s2, "mismatch": mismatch}, "step3": {"verdict": s3},
            "horizons": {"short": short, "mid": mid, "long": long}}


def gaps(found: dict[str, dict]) -> list[dict]:
    seen, out = set(), []
    for a in found.values():
        for g in a["gaps"]:
            if g not in seen:
                seen.add(g)
                out.append({"label": a["label"], "gap": g})
    return out[:GAP_LIMIT]


def build(root: Path, company: S.Company, today: str, status: dict) -> dict:
    found = {step.key: analysis(step, company) for step in S.STEPS}
    market = market_of(company)
    prices = CP.summarize(company.path)
    outlook = {**status["outlook"], **outlook_rows(root, status["outlook"], market)}
    return {
        "company": company.dirname, "ticker": company.ticker, "name": company.display_name(), "market": market,
        "date": today, "unit": unit_label(company), "price": _get(found["valuation"], "detail", "price") or {},
        "analyses": found, "prices": prices, "outlook": outlook, "review": next_review(company),
        **judgements(found, prices, outlook), "gaps": gaps(found), "steps": status["steps"],
        "stale": [{k: s[k] for k in ("skill", "label", "step", "date", "result", "reason")}
                  for s in status["steps"] if s["result"] != "fresh"],
    }
