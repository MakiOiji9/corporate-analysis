"""長期の株価の水準: where the price would sit in 3 and 5 years if EPS kept growing at the rate of each case and the
market paid the past five years' average PER for it. A condition, never a forecast; every number comes from facts.json.

  rates()  悲観・基本・楽観 growth rates from valuation's PEG cases (基本 = the lowest growth candidate, 悲観 = half of
           it, 楽観 = the highest candidate capped at OPTIMISTIC_MULT × 基本 and OPTIMISTIC_CAP); without PEG cases, the
           growth analysis' EPS CAGR is 基本
  build()  {ok, reason, eps0, per, per_basis, years, cases: [{name, rate, basis}],
            rows: [{years, case, eps, price, change, annual}], note}
"""
from __future__ import annotations

YEARS = (3, 5)
OPTIMISTIC_MULT = 1.5   # a one-year company plan compounded for five years overshoots: at most 1.5 × the base rate
OPTIMISTIC_CAP = 25.0   # and at most 25% a year
MIN_RATE = 5.0          # PEG treats growth under 5% as 評価対象外: no growth path is drawn either
NOTE = ("今の EPS が各ケースの率で伸び、株価が過去5年の平均PER で評価されると仮定した水準。"
        "売りを考える目安の一つで、株価の予想ではない")


def _detail(facts: dict, key: str) -> dict:
    return ((facts.get("analyses") or {}).get(key) or {}).get("detail") or {}


def rates(facts: dict) -> list[dict] | None:
    cases = _detail(facts, "valuation").get("peg_cases") or {}
    base = cases.get("standard")
    basis = "PEG の標準ケース（成長率の候補の最小）"
    if base is None:
        base = (_detail(facts, "growth").get("cagr") or {}).get("eps")
        basis = "成長性分析の EPS の年平均成長率"
    if base is None:
        return None
    plan = cases.get("optimistic")
    cap = min(base * OPTIMISTIC_MULT, OPTIMISTIC_CAP)
    if plan is None:
        bull, bull_basis = cap, f"基本の {OPTIMISTIC_MULT} 倍（{OPTIMISTIC_CAP:.0f}% まで）"
    elif plan > cap:
        bull, bull_basis = cap, (f"成長率の候補の最大 {plan:.1f}% に上限（基本の {OPTIMISTIC_MULT} 倍・"
                                 f"{OPTIMISTIC_CAP:.0f}% の低い方）をかけた率")
    else:
        bull, bull_basis = plan, "成長率の候補の最大（会社計画など）"
    return [{"name": "悲観", "rate": base / 2, "basis": "基本の半分"},
            {"name": "基本", "rate": base, "basis": basis},
            {"name": "楽観", "rate": max(bull, base), "basis": bull_basis}]


def _empty(reason: str) -> dict:
    return {"ok": False, "reason": reason, "years": list(YEARS), "cases": [], "rows": [], "note": NOTE}


def build(facts: dict) -> dict:
    v = _detail(facts, "valuation")
    eps0 = v.get("eps_used")
    fair = v.get("pbr_fair") or {}
    per = fair.get("average_per")
    if eps0 is None or eps0 <= 0:
        return _empty("EPS がマイナスか取れないため、成長を前提にした水準を出さない")
    if not per or per <= 0:
        return _empty("過去5年の平均PER が取れないため、水準を出さない")
    cases = rates(facts)
    if not cases:
        return _empty("EPS の成長率が取れないため、水準を出さない")
    base = cases[1]["rate"]
    if base < MIN_RATE:
        return _empty(f"EPS の成長率（{base:.1f}%）が {MIN_RATE:.0f}% 未満で、成長を前提にした水準を出さない")
    price = (facts.get("price") or {}).get("value")
    rows = []
    for c in cases:
        for n in YEARS:
            eps = eps0 * (1 + c["rate"] / 100) ** n
            value = eps * per
            rows.append({"years": n, "case": c["name"], "eps": eps, "price": value,
                         "change": (value / price - 1) * 100 if price else None,
                         "annual": ((value / price) ** (1 / n) - 1) * 100 if price else None})
    return {"ok": True, "reason": None, "eps0": eps0, "per": per,
            "per_basis": fair.get("average_basis") or "過去5年の平均PER", "years": list(YEARS),
            "cases": cases, "rows": rows, "note": NOTE}


def level(p: dict, case: str, years: int) -> float | None:
    """The price of one case and horizon, or None when no level is drawn."""
    return next((r["price"] for r in p.get("rows") or [] if r["case"] == case and r["years"] == years), None)


def rate(p: dict, case: str) -> float | None:
    return next((c["rate"] for c in p.get("cases") or [] if c["name"] == case), None)
