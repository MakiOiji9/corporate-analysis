"""facts.json of the company report: the nine analyses' conclusions, STEP 1・2・3, the three horizons, the price
history, the market outlook and the next review date. Every number and judgement of the report comes from here;
the writer only adds words (cr_doc.py), and the HTML (cr_render.py) is drawn from this and the filled md.
"""
from __future__ import annotations

from pathlib import Path

import cr_extras as X
import cr_factors as F
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
    customer = r.get("customer") or {}
    return {"win_reason": r.get("win_reason"), "top_kbf": r.get("top_kbf"),
            "customer": customer.get("conclusion"), "customers": customer.get("customers"),
            "kbf": r.get("kbf") or customer.get("kbf") or [], "market": customer.get("seen"),
            "competitor": _get(r, "competitor", "rating"), "competitor_reason": _get(r, "competitor", "conclusion"),
            "growth": _get(r, "growth", "rating"), "growth_reason": _get(r, "growth", "reason"),
            "kbf_table": [{"kbf": k.get("kbf"), "self": k.get("self"), "peers": k.get("peers") or {},
                           "basis": k.get("basis")} for k in r.get("kbf_table") or []],
            "comparison": [{k: c.get(k) for k in ("name", "self", "year", "sales", "margin", "share", "cagr")}
                           for c in r.get("comparison") or []],
            "strengths": _get(r, "handoff", "strengths"), "weaknesses": _get(r, "handoff", "weaknesses"),
            "company_conclusion": r.get("company_conclusion")}


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
    last = (_get(r, "step2", "rows") or [{}])[-1] or {}
    return {"roe_average": _get(r, "step1", "average"), "roe_minimum": _get(r, "step1", "minimum"),
            "margin": {k: _get(r, "step2", k) for k in ("year", "self", "avg", "diff", "trend")},
            "peer_margins": [{"name": p.get("name"), "margin": p.get("margin")} for p in last.get("peers") or []],
            "source": _get(r, "step3", "source"),
            "roe_rows": [{"year": x.get("year"), "roe": x.get("roe")} for x in r.get("roe_rows") or []]}


def _growth(r: dict) -> dict:
    return {"sales_cagr": _get(r, "step1", "sales_cagr"), "eps_cagr": _get(r, "step1", "eps_cagr"),
            "growth_type": _get(r, "step1", "rating"), "plan": _get(r, "step3", "rating"),
            "plan_average": _get(r, "step3", "average"), "quality": _get(r, "step4", "quality"),
            "quality_sentence": _get(r, "step4", "sentence"), "progress": r.get("progress"), "mtp": r.get("mtp"),
            "cagr": {k: _get(r, "step1", "cagr", k, "value") for k in ("sales", "operating_income", "eps")},
            "cagr_span": [_get(r, "step1", "cagr", "sales", "first"), _get(r, "step1", "cagr", "sales", "last")],
            "rows": [{k: x.get(k) for k in ("year", "sales", "operating_income", "net_income", "eps")}
                     for x in r.get("rows") or []]}


def _safety(r: dict) -> dict:
    s1 = r.get("step1") or {}
    return {"items": [{k: i.get(k) for k in ("name", "value", "peer_avg", "rating", "target")}
                      for i in s1.get("items") or []],
            "net_cash": s1.get("net_cash"), "debt_free": s1.get("debt_free"), "trend": _get(r, "step2", "rating"),
            "peers": [{"name": p.get("name"), "equity_ratio": p.get("equity_ratio")} for p in s1.get("peers") or []]}


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
            "cheap_reason": _get(r, "handoff", "cheap_reason"), "final_check": _get(r, "step3", "final_check"),
            "average": _get(r, "step3", "average"), "raw_verdict": _get(r, "step3", "raw_verdict"),
            "ev_ebitda": _get(r, "ev", "value"), "eps_used": _get(r, "per", "eps", "eps_used"),
            "peers": [{k: p.get(k) for k in ("name", "per_actual", "per_forecast", "pbr", "ev_ebitda_calc", "cagr", "roe")}
                      for p in r.get("peers") or []]}


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
            "conservative": r.get("conservative") or [], "detail": DETAILS[step.key](r)}


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
    flags = J.red_flags(_get(found["cash_flow"], "detail", "steps") or [], v["safety"],
                        _get(found["safety"], "detail", "trend"))
    s2 = J.step2({"収益性": v["profitability"], "成長性": v["growth"], "安全性": v["safety"],
                  "キャッシュフロー": v["cash_flow"]}, mismatch, flags)
    s3 = F.step3_verdict(found["valuation"])
    factors = F.build(found, prices, outlook)
    horizons = {h: {**J.horizon_score(h, factors[h], flags, s1["grade"]),
                    "sensitivity": J.sensitivity(h, factors[h], flags, s1["grade"])} for h in factors}
    final_check = _get(found["valuation"], "detail", "final_check") or {}
    note = "割安だが理由あり（" + "・".join(final_check.get("concerns") or []) + "）" \
        if s3 == "割安" and final_check.get("concerns") else ""
    return {"step1": s1, "step2": {**s2, "mismatch": mismatch, "flags": flags},
            "step3": {"verdict": s3, "note": note}, "horizons": horizons,
            "matrix": J.matrix_reference(s1, s2, s3)}


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
    price = _get(found["valuation"], "detail", "price") or {}
    per_forecast = _get(found["valuation"], "detail", "per_forecast")
    extras = {"dividends": X.dividends(company.path, price.get("value"), per_forecast),
              "peers": X.peer_table(found, company.display_name())}
    return {**extras,
        "company": company.dirname, "ticker": company.ticker, "name": company.display_name(), "market": market,
        "date": today, "unit": unit_label(company), "price": _get(found["valuation"], "detail", "price") or {},
        "analyses": found, "prices": prices, "outlook": outlook, "review": next_review(company),
        **judgements(found, prices, outlook), "gaps": gaps(found), "steps": status["steps"],
        "stale": [{k: s[k] for k in ("skill", "label", "step", "date", "result", "reason")}
                  for s in status["steps"] if s["result"] != "fresh"],
    }
