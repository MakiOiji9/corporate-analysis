"""Two value checks on the balance sheet and the kind of business (STEP 3 additions).

- ncr_step (資産ベースのネットキャッシュ比率): (流動資産 + 投資有価証券 × ASSET_HAIRCUT − 負債合計) ÷ 時価総額.
  ≥ CHEAP_NCR 割安 (the balance sheet alone covers the market value), 0〜CHEAP_NCR 妥当, below 0 評価対象外 (a thin
  balance sheet is the safety analysis' concern, not a 割高 here). A missing part is 判定保留, never 0.
- business_type / apply_guide (業態別の PER の目安): the kind of business sets a PER a value investor would still
  accept: ニッチトップ型 (moat 広い・狭い), 優良顧客型 (no customer over SUBCONTRACT %), 中小の不動産, 下請け型
  (one customer ≥ SUBCONTRACT % of sales; only with a net cash ratio ≥ CHEAP_NCR) — GUIDES. The PER at or under the
  guide is 割安, over GUIDE_RICH × the guide 割高, between 妥当; a two-axis rating that is the opposite of it moves one
  step toward it (a third axis: it never decides alone).
"""
from __future__ import annotations

import va_rules as R

ASSET_HAIRCUT = 0.7
CHEAP_NCR = 1.0
NCR_BORDER = 0.1
SUBCONTRACT = 30.0             # % of sales from one customer
SMALL_CAP = 100_000.0          # 百万円 (1,000億円)
GUIDE_RICH = 1.5
NICHE, CUSTOMERS, REAL_ESTATE, SUBCONTRACTOR = "ニッチトップ型", "優良顧客型", "中小の不動産", "下請け型"
GUIDES = {NICHE: 20, CUSTOMERS: 15, REAL_ESTATE: 10, SUBCONTRACTOR: 7}
MOAT_OK = ("広い", "狭い")
REAL_ESTATE_SECTORS = ("不動産業",)


def _fmt(v: float) -> str:
    return f"{v:,.0f}"


def ncr_step(row: dict, cap: dict | None, excluded: str | None) -> dict:
    """{rating, value, asset_net_cash, sentence, borderline}."""
    out = {"value": None, "asset_net_cash": None, "borderline": []}
    if excluded:
        return {**out, "rating": R.NA, "sentence": f"評価対象外（{excluded}）"}
    parts = {"流動資産": row.get("current_assets"), "投資有価証券": row.get("investment_securities"),
             "負債合計": row.get("liabilities"), "時価総額": (cap or {}).get("value")}
    missing = [k for k, v in parts.items() if v is None]
    if missing:
        return {**out, "rating": R.PENDING, "sentence": f"判定保留（{'・'.join(missing)}が無く計算できない。0 とはみなさない）"}
    net = parts["流動資産"] + parts["投資有価証券"] * ASSET_HAIRCUT - parts["負債合計"]
    ratio = net / parts["時価総額"] if parts["時価総額"] else None
    head = (f"資産ベースのネットキャッシュ {_fmt(net)}（流動資産 {_fmt(parts['流動資産'])} ＋ 投資有価証券 "
            f"{_fmt(parts['投資有価証券'])} × {ASSET_HAIRCUT} − 負債合計 {_fmt(parts['負債合計'])}）")
    if ratio is None or net < 0:
        return {**out, "asset_net_cash": net, "value": ratio, "rating": R.NA,
                "sentence": f"評価対象外（{head} がマイナス。財務の厚さは安全性分析で見る）"}
    rating = R.LOW if ratio >= CHEAP_NCR else R.FAIR
    border = ([f"ネットキャッシュ比率: {ratio:.2f}倍が {CHEAP_NCR:.0f}倍に近い"]
              if abs(ratio - CHEAP_NCR) <= NCR_BORDER else [])
    return {"value": ratio, "asset_net_cash": net, "rating": rating, "borderline": border,
            "sentence": f"ネットキャッシュ比率 {ratio:.2f}倍: {head} ÷ 時価総額 {_fmt(parts['時価総額'])}。"
                        f"{CHEAP_NCR:.0f}倍以上で割安、0〜{CHEAP_NCR:.0f}倍で妥当 → {rating}"}


def business_type(moat: str | None, customer: float | None, no_major_customer: bool, sector: str | None,
                  cap: float | None, ncr: float | None) -> dict:
    """{type, guide (PER) or None, basis}: the first rule that applies, top to bottom."""
    if sector in REAL_ESTATE_SECTORS and cap is not None and cap < SMALL_CAP:
        return {"type": REAL_ESTATE, "guide": GUIDES[REAL_ESTATE], "basis": f"業種 {sector}・時価総額 {_fmt(cap)}"}
    if customer is not None and customer >= SUBCONTRACT:
        if ncr is None or ncr < CHEAP_NCR:
            return {"type": f"{SUBCONTRACTOR}（目安の条件を満たさない）", "guide": None,
                    "basis": f"主要な販売先1社が売上の {customer:.1f}%。ネットキャッシュ比率が {CHEAP_NCR:.0f}倍未満"
                             "（または不明）で、下請け型の目安の前提を満たさない"}
        return {"type": SUBCONTRACTOR, "guide": GUIDES[SUBCONTRACTOR],
                "basis": f"主要な販売先1社が売上の {customer:.1f}%（{SUBCONTRACT:.0f}% 以上）、ネットキャッシュ比率 {ncr:.2f}倍"}
    if moat in MOAT_OK:
        return {"type": NICHE, "guide": GUIDES[NICHE], "basis": f"モート {moat}（まねされにくい強みがある）"}
    if customer is not None or no_major_customer:
        share = f"最大の販売先 {customer:.1f}%" if customer is not None else "売上の10%以上の販売先なし"
        return {"type": CUSTOMERS, "guide": GUIDES[CUSTOMERS], "basis": f"{share}（特定の顧客に依存しない）"}
    return {"type": "分類できない", "guide": None, "basis": "モート・主要な販売先の材料が無い"}


def apply_guide(per: dict, guide: dict) -> dict:
    """PER with the business-type guide as a third axis: shown always, moves an opposite rating one step."""
    value, limit = per.get("per_used"), guide.get("guide")
    if per["rating"] not in R.ORDER or value is None or limit is None:
        return {**per, "guide": {**guide, "zone": None}}
    zone = R.LOW if value <= limit else R.HIGH if value > limit * GUIDE_RICH else R.FAIR
    rating = per["rating"]
    note = f"業態の目安（{guide['type']} {limit}倍以下）で{R.ZONE[zone]}"
    if {rating, zone} == {R.LOW, R.HIGH}:
        rating, note = R.FAIR, note + f"。2軸の判定（{per['rating']}）と逆のため妥当"
    return {**per, "rating": rating, "guide": {**guide, "zone": zone}, "sentence": f"{per['sentence']}。{note}"}
