"""Every number and judgement of 企業分析フレームワーク.md STEP 3 (バリュエーション).

  3-1 PER: 手順1 the 特別損益 is >= 10% of the net income -> 調整EPS = 実績EPS × 調整純利益 ÷ 純利益
    (調整純利益 = 純利益 −（特別利益 − 特別損失）× 0.7); 手順2 予想PER (price ÷ forecast EPS); when the growth analysis
    says the company plan is to be discounted (割り引いて扱う) the 実績PER is judged too and the judgement nearer
    to 割高 is taken; 手順3 the common rule (va_rules); 手順4 評価対象外 when the newest year is a loss, the
    forecast EPS is not positive, or the net income fell by 50% or more from the year before (also, conservatively,
    when the newest year has an operating loss: a net profit from outside the business is not a PER basis).
  3-2 PBR: 手順1 the common rule (同業比較の補正は ROE の差); 手順2 適正PBR = 予想ROE（予想EPS ÷ BPS）× 過去5年の
    平均PER（有報の期末PER、無ければ年次の（高値 + 安値）÷ 2）; 20% 以上低い 割安 / ±20% 妥当 / 20% 以上高い 割高,
    and it wins over 手順1; 手順3 PBR < 1 and ROE < 8%: the writer answers whether improvement measures are shown
    (あり / なし / 不明); なし・不明 turn a 割安 into 妥当 (バリュートラップ).
  3-3 PEG: 評価対象外 when PER is 評価対象外, the standard growth is below 5%, or the net income halved in one of the
    last 5 years; growth candidates: the growth analysis' EPS CAGR, the company plan (予想EPS ÷ 実績EPS − 1) and the
    analysts' EPS growth; standard = the lowest, pessimistic = half of it, optimistic = the highest;
    PEG = PER (3-1) ÷ standard growth: <= 1 割安 / 1〜2 妥当 / > 2 割高; 安全域あり when the pessimistic PEG <= 2.
  3-4 EV/EBITDA: EV = 時価総額 + 有利子負債 − 現金, EBITDA = 営業利益 + 減価償却費 (newest year); EBITDA <= 0 ->
    評価対象外; the past range is computed (時価総額 ≈ PER × 純利益, or PBR × 自己資本 in a loss year); the common
    rule; 手順2 a judgement opposite to PER gets the candidate reasons (net cash, heavy depreciation, heavy debt).
  STEP 3: va_rules.score; 手順3 a 割安 becomes 妥当 when a STEP 2 analysis is 懸念 or the SWOT is No.
"""
from __future__ import annotations

import datetime as dt
import json

import an_common as A
import cf_paths as CP
import gr_paths as GP
import pf_paths as PP
import sf_paths as SP
import sw_paths as WP
import va_inputs as I
import va_rules as R
import va_series as V

TAX_RATE = 0.30
SPECIAL_SHARE = 0.10
DROP_SHARE = 0.50
HALVED = 0.50
PEG_MIN_GROWTH = 5.0
PEG_LOW, PEG_HIGH = 1.0, 2.0
PEG_BORDER = 0.1
FAIR_PBR_BAND = 0.20
TRAP_PBR, TRAP_ROE = 1.0, 8.0
HEAVY_DEPRECIATION = 0.5  # depreciation >= half of EBITDA
HEAVY_DEBT = 1.0  # D/E >= 1
PRICE_MAX_AGE = 7  # days between the price's base date and the analysis
MISMATCH = 0.10  # the script's PER / PBR against the one written in 3章
MEASURES = ("あり", "なし", "不明")
DISCOUNT = "割り引いて扱う"
INDICATORS = (("per", "PER"), ("pbr", "PBR"), ("peg", "PEG"), ("ev", "EV/EBITDA"))
STEP2 = (("profitability", PP, "収益性"), ("growth", GP, "成長性"), ("safety", SP, "安全性"),
         ("cash_flow", CP, "キャッシュフロー"))
UPSTREAM = STEP2 + (("swot", WP, "SWOT"),)
CONCERN, SWOT_NO = "懸念", "No"
PRICE_ITEM = ("株価のみ: 株価データ 1章・3章（自社の直近の確定終値と基準日・株式数・株価指標。2章は新しい決算・予想修正が"
              "あるときだけ）と、競合 6章「PER・PBR」（EPS（実績）・EPS（予想）・BPS の列も）を同じ基準日で取り直す"
              f"（基準日が{PRICE_MAX_AGE}日より古い）")
PEER_MISMATCH = 0.10  # a site's shown peer PER / PBR against price ÷ the per-share figure
EBITDA_ITEM = I.SPEC["peer_ebitda"].label


# ---------- formatting ----------

def times(value: float | None) -> str:
    return R.fmt(value)


def yen(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}円" if currency == "円" else f"{value:,.2f}ドル"


def amount(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


# ---------- upstream results ----------

def _result(module, company) -> tuple[str, dict] | None:
    return module.latest_result(module.Company(company.root, company.path))


def growth_result(company) -> tuple[str, dict] | None:
    return _result(GP, company)


def others(company) -> dict:
    """{key: {date, verdict, reason} | None} of the STEP 2 analyses and the SWOT."""
    out = {}
    for key, module, _ in UPSTREAM:
        r = _result(module, company)
        out[key] = {"date": r[0], "verdict": r[1].get("verdict"), "reason": r[1].get("verdict_reason")} if r else None
    return out


# ---------- 3-1 PER ----------

def _row(base: dict, year: str | None) -> dict:
    return next((r for r in base["years"]["rows"] if r["year"] == year), {})


def _previous_row(base: dict, year: str | None) -> dict:
    earlier = [r for r in base["years"]["rows"] if year and r["year"] < year and r["net_income"] is not None]
    return earlier[-1] if earlier else {}


def eps_step(base: dict) -> dict:
    """手順1: the actual EPS and, when the 特別損益 is large, the adjusted one."""
    latest = _row(base, base["latest_year"])
    eps = latest.get("eps")
    source = f"{base['latest_year']} の EPS（財務時系列・決算短信。株式分割を調整）" if eps is not None else ""
    if eps is None and base["per_share"]["eps_actual"]:
        row = base["per_share"]["eps_actual"]
        eps, source = row["value"], f"株価データ 2章「{row['label']}」"
    ni, gain, loss = latest.get("net_income"), latest.get("extra_gain"), latest.get("extra_loss")
    special = (gain or 0.0) - (loss or 0.0)
    share = abs(special) / abs(ni) if ni else None
    out = {"year": base["latest_year"], "eps": eps, "source": source, "net_income": ni, "gain": gain, "loss": loss,
           "share": share, "adjusted": False, "eps_used": eps, "adjusted_net_income": None}
    if gain is None and loss is None:
        reason = "特別損益の記載なし"
    elif ni is None or ni <= 0 or share is None:
        reason = "純利益がプラスでない"
    elif share < SPECIAL_SHARE:
        reason = f"特別損益が純利益の{share * 100:.1f}%で10%未満"
    else:
        reason = None
    if reason or eps is None:
        return {**out, "sentence": f"実績EPS {R.fmt(eps, '', 2)}（{reason or 'EPS が無い'}。調整しない）"}
    adj_ni = ni - special * (1 - TAX_RATE)
    adj = eps * adj_ni / ni
    return {**out, "adjusted": True, "eps_used": adj, "adjusted_net_income": adj_ni,
            "sentence": (f"特別損益（特別利益 {amount(gain)} − 特別損失 {amount(loss)}）が純利益 {amount(ni)} の"
                         f"{share * 100:.1f}%で10%以上のため、調整EPS {adj:.2f}（調整純利益 {amount(adj_ni)}）を使う")}


def _per_history(base: dict) -> list[tuple[str, float | None, float | None]]:
    return [(h["year"], h["per_high"], h["per_low"]) for h in base["history"]]


def _peer_growth(base: dict) -> tuple[float | None, list[float]]:
    peers = base["peers"]
    return peers["own"]["cagr"], [p["cagr"] for p in peers["peers"] if p["cagr"] is not None]


def per_applicability(base: dict) -> str | None:
    """Why PER does not work (評価対象外), or None."""
    latest, prev = _row(base, base["latest_year"]), _previous_row(base, base["latest_year"])
    ni, forecast, op = latest.get("net_income"), base["forecast_eps"], latest.get("operating_income")
    if ni is not None and ni <= 0:
        return f"直近期（{base['latest_year']}）が赤字（純利益 {amount(ni)}）"
    if op is not None and op <= 0:  # a profit from outside the business: the PER says nothing about the business
        return f"直近期（{base['latest_year']}）が営業赤字（営業利益 {amount(op)}）で、純利益が本業の稼ぐ力を表さない"
    if forecast and forecast["value"] <= 0:
        return f"予想EPS が {forecast['value']:.2f} で利益が出ない予想"
    before = prev.get("net_income")
    if ni is not None and before and before > 0 and ni <= before * (1 - DROP_SHARE):
        return f"純利益が前年（{prev['year']}）の {amount(before)} から {amount(ni)} へ50%以上減った"
    return None


def _per_choice(rule_f: dict, rule_a: dict, per_f: float | None, per_a: float | None,
                discount: bool) -> tuple[str, dict, float | None, str]:
    """(which PER, its rule, its value, note)."""
    if per_f is None:
        return "実績PER", rule_a, per_a, "予想EPS が無いため実績PER で判定"
    if not discount or per_a is None:
        note = "予想PER で判定" + ("（会社計画を割り引くが実績PER を計算できない）" if discount else "")
        return "予想PER", rule_f, per_f, note
    rating = R.more_expensive(rule_f["rating"], rule_a["rating"])
    actual = rating != rule_f["rating"] or (rating == rule_a["rating"] and per_a > per_f)
    used, rule, value = ("実績PER", rule_a, per_a) if actual else ("予想PER", rule_f, per_f)
    return used, rule, value, ("成長性分析で会社計画を「割り引いて扱う」ため実績PER も判定し、割高寄りの"
                               f"{used}を採る（予想 {rule_f['rating']} / 実績 {rule_a['rating']}）")


def per_step(base: dict, growth: dict | None) -> dict:
    step1 = eps_step(base)
    price, forecast, eps = base["price"]["price"], base["forecast_eps"], step1["eps_used"]
    per_a = price / eps if price and eps and eps > 0 else None
    per_f = price / forecast["value"] if price and forecast and forecast["value"] > 0 else None
    discount = bool(growth) and (growth.get("step3") or {}).get("rating") == DISCOUNT
    own_growth, peer_growths = _peer_growth(base)
    peers = base["peers"]["peers"]
    forecasts = [p["per_forecast"] for p in peers if p["per_forecast"]]
    # the yearly range is of actual PERs (price ÷ actual EPS): the forecast PER of a growing company is
    # structurally lower, so axis 1 always uses the actual PER; axis 2 compares like with like
    range_value = per_a if per_a is not None else per_f
    axis1 = R.range_zone(range_value, _per_history(base))
    if per_f is not None and len(forecasts) >= R.MIN_PEERS:
        axis2_f = R.peer_zone(per_f, forecasts, own_growth, peer_growths)
    else:
        axis2_f = R.peer_zone(per_a, [p["per_actual"] for p in peers], own_growth, peer_growths)
    axis2_a = R.peer_zone(per_a, [p["per_actual"] for p in peers], own_growth, peer_growths)
    rule_f = {"axis1": axis1, "axis2": axis2_f, **R.combine(axis1, axis2_f)}
    rule_a = {"axis1": axis1, "axis2": axis2_a, **R.combine(axis1, axis2_a)}
    na = per_applicability(base)
    out = {"step1": step1, "price": price, "per_actual": per_a, "per_forecast": per_f, "discount": discount,
           "rule_forecast": rule_f, "rule_actual": rule_a, "na": na}
    if na:
        return {**out, "rating": R.NA, "per_used": None, "eps_for_per": None, "used": "—", "rule": rule_f, "note": "",
                "sentence": f"評価対象外（{na}。PER が機能しない）", "borderline": []}
    used, rule, value, note = _per_choice(rule_f, rule_a, per_f, per_a, discount)
    eps_for_per = price / value if price and value else None
    return {**out, "rating": rule["rating"], "per_used": value, "eps_for_per": eps_for_per, "used": used,
            "rule": rule, "note": note, "sentence": f"{used} {times(value)}: {rule['basis']}（{note}）",
            "borderline": R.borderline("PER", rule)}


# ---------- 3-2 PBR ----------

def _roe_actual(base: dict) -> float | None:
    latest = _row(base, base["latest_year"])
    ni, equity = latest.get("net_income"), latest.get("equity")
    return ni / equity * 100 if ni is not None and equity and equity > 0 else None


def _average_per(base: dict) -> tuple[float | None, str]:
    recent = base["history"][-R.RANGE_YEARS:]
    ends = [h["per_end"] for h in recent if h["per_end"] is not None]
    if len(ends) >= R.MIN_RANGE_YEARS:
        return sum(ends) / len(ends), f"有報の期末PER {len(ends)} 期の平均"
    mids = [(h["per_high"] + h["per_low"]) / 2 for h in recent if h["per_high"] is not None and h["per_low"] is not None]
    if len(mids) >= R.MIN_RANGE_YEARS:
        return sum(mids) / len(mids), f"年次の（高値 + 安値）÷ 2 の {len(mids)} 期平均"
    return None, f"過去5年の PER が{R.MIN_RANGE_YEARS}期分無い"


def fair_pbr(base: dict, pbr: float | None) -> dict:
    bps = (base["per_share"]["bps"] or {}).get("value")
    forecast = base["forecast_eps"]
    if forecast and bps and bps > 0:
        roe, roe_basis = forecast["value"] / bps * 100, "予想EPS ÷ BPS"
    else:
        roe, roe_basis = base["reported"]["roe_forecast"], "株価データ 3章の予想ROE"
    avg, avg_basis = _average_per(base)
    out = {"roe": roe, "roe_basis": roe_basis, "average_per": avg, "average_basis": avg_basis, "fair": None,
           "diff": None, "rating": None}
    if roe is None or roe <= 0 or avg is None or pbr is None:
        missing = "プラスの予想ROE" if roe is None or roe <= 0 else "平均PER" if avg is None else "PBR"
        return {**out, "basis": f"適正PBR を計算できない（{missing}が無い）"}
    fair = roe / 100 * avg
    diff = round(pbr / fair - 1, 6)
    rating = R.LOW if diff <= -FAIR_PBR_BAND else R.HIGH if diff >= FAIR_PBR_BAND else R.FAIR
    return {**out, "fair": fair, "diff": diff, "rating": rating,
            "basis": (f"適正PBR {fair:.2f}倍（予想ROE {roe:.1f}%（{roe_basis}）× 平均PER {avg:.1f}倍（{avg_basis}））"
                      f"に対して現在 {pbr:.2f}倍で {diff * 100:+.0f}%（{rating}）")}


def pbr_step(base: dict, measures: str | None = None) -> dict:
    bps = (base["per_share"]["bps"] or {}).get("value")
    price = base["price"]["price"]
    pbr = price / bps if price and bps and bps > 0 else None
    peers = base["peers"]
    rule = R.common_rule(pbr, [(h["year"], h["pbr_high"], h["pbr_low"]) for h in base["history"]],
                         [p["pbr"] for p in peers["peers"]], peers["own"]["roe"],
                         [p["roe"] for p in peers["peers"] if p["roe"] is not None], "ROE")
    fair = fair_pbr(base, pbr)
    roe = _roe_actual(base)
    roe_check = roe if roe is not None else fair["roe"]
    trap_applies = pbr is not None and pbr < TRAP_PBR and roe_check is not None and roe_check < TRAP_ROE
    if fair["rating"]:
        before = fair["rating"]
        conflict = rule["rating"] in (R.LOW, R.FAIR, R.HIGH) and rule["rating"] != fair["rating"]
        how = "手順2（適正PBR）で判定" + (f"（手順1 の {rule['rating']} と食い違うため手順2を優先）" if conflict else "")
    else:
        before, how = rule["rating"], "手順2を計算できないため手順1で判定"
    rating, trap_note = before, ""
    choice = (measures if measures in MEASURES else "不明") if trap_applies else None
    if trap_applies and before == R.LOW and choice != "あり":
        rating = R.FAIR
        roe_kind = "直近期の実績ROE" if roe is not None else "予想ROE"
        trap_note = (f"。PBR 1倍割れ・{roe_kind} {roe_check:.1f}%で改善策が「{choice}」のため割安とみなさず妥当"
                     "（バリュートラップの疑い）")
    trap = {"applies": trap_applies, "roe": roe_check, "measures": choice, "raised": bool(trap_note)}
    detail = fair["basis"] if fair["rating"] else rule["basis"]
    return {"pbr": pbr, "bps": bps, "rule": rule, "fair": fair, "roe_actual": roe, "before_trap": before,
            "trap": trap, "rating": rating, "sentence": f"PBR {R.fmt(pbr, '倍', 2)}: {how}。{detail}{trap_note}",
            "borderline": R.borderline("PBR", rule) + _fair_border(fair)}


def _fair_border(fair: dict) -> list[str]:
    if fair["diff"] is None or abs(abs(fair["diff"]) - FAIR_PBR_BAND) > R.BORDER_PEER:
        return []
    return [f"PBR: 適正PBR との差 {fair['diff'] * 100:+.0f}% が境界（±{FAIR_PBR_BAND * 100:.0f}%）に近い"]


# ---------- 3-3 PEG ----------

def cyclical_year(base: dict) -> str | None:
    """A year among the last 5 whose net income was half the year before or less."""
    rows = [r for r in base["years"]["rows"] if r["net_income"] is not None][-(R.RANGE_YEARS + 1):]
    for prev, cur in zip(rows, rows[1:]):
        if prev["net_income"] > 0 and cur["net_income"] <= prev["net_income"] * HALVED:
            return cur["year"]
    return None


def growth_candidates(base: dict, per: dict, growth: dict | None) -> list[dict]:
    out = []
    cagr = ((growth or {}).get("step1") or {}).get("eps_cagr")
    if isinstance(cagr, (int, float)):
        out.append({"name": "過去の EPS CAGR（成長性分析）", "value": float(cagr)})
    eps, forecast = per["step1"]["eps_used"], base["forecast_eps"]
    if eps and eps > 0 and forecast and forecast["value"] > 0:
        out.append({"name": "会社計画（予想EPS ÷ 実績EPS − 1）", "value": (forecast["value"] / eps - 1) * 100})
    if base["analyst"]:
        out.append({"name": "アナリスト予想の EPS 成長率", "value": base["analyst"]["value"]})
    return out


def _peg_na(per: dict, standard: float | None, cyclical: str | None) -> str | None:
    if per["rating"] == R.NA:
        return "3-1 で PER が評価対象外"
    if standard is not None and standard < PEG_MIN_GROWTH:
        return f"標準ケースの成長率 {standard:.1f}% が5%未満"
    if cyclical:
        return f"{cyclical} に純利益が前年の半分以下になった（景気敏感で利益の変動が大きい）"
    return None


def peg_step(base: dict, per: dict, growth: dict | None) -> dict:
    cands = growth_candidates(base, per, growth)
    values = [c["value"] for c in cands]
    standard = min(values) if values else None
    cases = {"standard": standard, "pessimistic": standard / 2 if standard is not None else None,
             "optimistic": max(values) if values else None}
    per_value = per["per_used"]
    peg = {k: (per_value / g if per_value and g and g > 0 else None) for k, g in cases.items()}
    out = {"candidates": cands, "cases": cases, "peg": peg, "per": per_value, "margin": False, "borderline": []}
    na = _peg_na(per, standard, cyclical_year(base))
    if na:
        return {**out, "rating": R.NA, "na": na, "sentence": f"評価対象外（{na}）"}
    if standard is None or per_value is None:
        missing = "成長率の候補" if standard is None else "3-1 の PER"
        return {**out, "rating": R.PENDING, "na": None, "sentence": f"判定保留（{missing}が無い）"}
    value = peg["standard"]
    rating = R.LOW if value <= PEG_LOW else R.HIGH if value > PEG_HIGH else R.FAIR
    margin = peg["pessimistic"] is not None and peg["pessimistic"] <= PEG_HIGH
    border = [f"PEG: 標準ケース {value:.2f}倍 が境界（{b:.0f}倍）に近い" for b in (PEG_LOW, PEG_HIGH)
              if abs(value - b) <= PEG_BORDER]
    few = (f"。成長率の候補が{len(cands)}つだけ（{'・'.join(c['name'] for c in cands)}）で、標準ケースはその最小"
           if len(cands) < 3 else "")
    return {**out, "rating": rating, "na": None, "margin": margin, "borderline": border,
            "sentence": (f"PEG（標準）{value:.2f}倍 = PER {per_value:.1f}倍 ÷ 成長率 {standard:.1f}%（{rating}）。"
                         f"悲観ケース {R.fmt(peg['pessimistic'], '倍', 2)}"
                         + ("で2倍以下（安全域あり）" if margin else "で2倍超（安全域なし）") + few)}


# ---------- 3-4 EV/EBITDA ----------

def ev_history(base: dict) -> list[dict]:
    """[{year, high, low, basis}]: EV/EBITDA computed from the yearly PER (or PBR) range."""
    out = []
    for h in base["history"][-R.RANGE_YEARS:]:
        row = _row(base, h["year"])
        op, dep, debt, cash = (row.get(k) for k in ("operating_income", "depreciation", "debt", "cash"))
        if None in (op, dep, debt, cash) or op + dep <= 0:
            continue
        ni, equity = row.get("net_income"), row.get("equity")
        if ni and ni > 0 and h["per_high"] is not None and h["per_low"] is not None:
            caps, basis = (h["per_high"] * ni, h["per_low"] * ni), "PER × 純利益"
        elif equity and equity > 0 and h["pbr_high"] is not None and h["pbr_low"] is not None:
            caps, basis = (h["pbr_high"] * equity, h["pbr_low"] * equity), "PBR × 自己資本"
        else:
            continue
        ebitda = op + dep
        low_ev = caps[1] + debt - cash
        if low_ev <= 0:  # a negative EV is no multiple
            continue
        out.append({"year": h["year"], "high": (caps[0] + debt - cash) / ebitda, "low": low_ev / ebitda,
                    "basis": basis})
    return out


def _divergence(per: dict, ev: dict, latest: dict) -> dict | None:
    pr, er = per["rating"], ev["rating"]
    if (pr, er) not in ((R.HIGH, R.LOW), (R.LOW, R.HIGH)):
        return None
    reasons = []
    if ev["net_cash"] is not None and ev["net_cash"] > 0:
        reasons.append("現金が多い（ネットキャッシュがプラス）")
    dep = latest.get("depreciation")
    if ev["ebitda"] and dep is not None and dep / ev["ebitda"] >= HEAVY_DEPRECIATION:
        reasons.append("減価償却の負担が重い（減価償却費が EBITDA の半分以上）")
    equity = latest.get("equity")
    if latest.get("debt") is not None and equity and equity > 0 and latest["debt"] / equity >= HEAVY_DEBT:
        reasons.append("借入が多い（D/E 1倍以上）")
    lead = ("PER では割高、EV/EBITDA では割安。実態は EV/EBITDA に近いとみる" if pr == R.HIGH
            else "PER では割安、EV/EBITDA では割高。借入を含めた評価として EV/EBITDA を優先してみる")
    return {"pattern": f"PER {pr} / EV/EBITDA {er}", "lead": lead,
            "reasons": reasons or ["数値の上では目立つ要因なし（現金・減価償却・借入のいずれも基準未満）"]}


def ev_step(base: dict, per: dict) -> dict:
    latest = _row(base, base["latest_year"])
    op, dep, debt, cash = (latest.get(k) for k in ("operating_income", "depreciation", "debt", "cash"))
    cap = base["market_cap"]
    ebitda = op + dep if op is not None and dep is not None else None
    ev = cap["value"] + debt - cash if cap and debt is not None and cash is not None else None
    net_cash = cash - debt if cash is not None and debt is not None else None
    out = {"year": base["latest_year"], "market_cap": cap, "debt": debt, "cash": cash, "operating_income": op,
           "depreciation": dep, "ebitda": ebitda, "ev": ev, "net_cash": net_cash, "history": ev_history(base),
           "divergence": None, "borderline": []}
    if ebitda is not None and ebitda <= 0:
        return {**out, "rating": R.NA, "value": None, "rule": None,
                "sentence": f"評価対象外（EBITDA {amount(ebitda)} がプラスでない）"}
    if ev is not None and ev <= 0:
        return {**out, "rating": R.NA, "value": None, "rule": None,
                "sentence": f"評価対象外（現金が時価総額と有利子負債の合計を上回り EV {amount(ev)} がプラスでない）"}
    value = ev / ebitda if ev is not None and ebitda else None
    if value is None:
        missing = [n for n, v in (("時価総額", cap), ("有利子負債", debt), ("現金", cash), ("営業利益", op),
                                  ("減価償却費", dep)) if v is None]
        return {**out, "rating": R.PENDING, "value": None, "rule": None,
                "sentence": f"判定保留（{'・'.join(missing)}が無く EV/EBITDA を計算できない）"}
    own_growth, peer_growths = _peer_growth(base)
    peers = [p["ev_ebitda_calc"] if p["ev_ebitda_calc"] is not None else p["ev_ebitda"] for p in base["peers"]["peers"]]
    rule = R.common_rule(value, [(h["year"], h["high"], h["low"]) for h in out["history"]], peers, own_growth,
                         peer_growths)
    history = [(h["year"], h["high"], h["low"]) for h in out["history"]]
    sensitivity = _share_sensitivity(cap, debt, cash, ebitda, history, peers, own_growth, peer_growths, rule)
    borderline = R.borderline("EV/EBITDA", rule)
    if sensitivity and sensitivity["changes"]:
        borderline.append(f"EV/EBITDA: 株式数の上限（{sensitivity['shares']:,.0f}株）では {sensitivity['value']:.1f}倍で"
                          f"{sensitivity['rating']}（判定が変わる。株式数の確定が必要）")
    note = (f"。株式数が未確定のため上限（{sensitivity['shares']:,.0f}株）でも計算: {sensitivity['value']:.1f}倍で"
            f"{sensitivity['rating']}（{'判定が変わる' if sensitivity['changes'] else '判定は同じ'}）" if sensitivity else "")
    result = {**out, "rating": rule["rating"], "value": value, "rule": rule, "sensitivity": sensitivity,
              "sentence": f"EV/EBITDA {times(value)}: {rule['basis']}（過去レンジは算出値）{note}",
              "borderline": borderline}
    return {**result, "divergence": _divergence(per, result, latest)}


def _share_sensitivity(cap: dict | None, debt: float, cash: float, ebitda: float, history: list, peers: list,
                       own_growth: float | None, peer_growths: list, rule: dict) -> dict | None:
    """EV/EBITDA with the upper bound of an uncertain share count (自己株式を含む), and whether the judgement holds."""
    if not cap or not cap.get("max"):
        return None
    value = (cap["max"] + debt - cash) / ebitda
    upper = R.common_rule(value, history, peers, own_growth, peer_growths)
    return {"shares": cap["max_shares"], "market_cap": cap["max"], "value": value, "rating": upper["rating"],
            "changes": upper["rating"] != rule["rating"]}


# ---------- STEP 3 ----------

def step3(items: dict[str, dict], upstream: dict) -> dict:
    ratings = {name: items[key]["rating"] for key, name in INDICATORS}
    scored = R.score(ratings)
    raw = scored["verdict"]
    concerns = [label for key, _, label in STEP2 if (upstream.get(key) or {}).get("verdict") == CONCERN]
    swot_no = (upstream.get("swot") or {}).get("verdict") == SWOT_NO
    not_done = [label for key, _, label in UPSTREAM if not upstream.get(key)]
    # 手順3 no longer moves the verdict: STEP 2 / SWOT already count those concerns, so raising 割安 to 妥当 here
    # would count them twice. A cheap price with such a concern is noted as 「割安だが理由あり」.
    noted = raw == R.LOW and (bool(concerns) or swot_no)
    reasons = ([f"STEP 2 で{'・'.join(concerns)}が懸念"] if concerns else []) + (["SWOT の結論が No"] if swot_no else [])
    if noted:
        why = f"{scored['basis']}で割安。ただし割安だが理由あり（{'、'.join(reasons)}。手順3）"
    elif raw == R.LOW and not_done:
        why = f"{scored['basis']}。手順3: {'・'.join(not_done)}が未実施のため懸念を確認できない（割安のまま）"
    elif raw == R.LOW:
        why = f"{scored['basis']}。手順3: STEP 2 の懸念・SWOT の No なし"
    else:
        why = scored["basis"]
    return {"ratings": ratings, **scored, "raw_verdict": raw, "verdict": raw, "why": why,
            "final_check": {"concerns": concerns, "swot_no": swot_no, "not_done": not_done, "raised": False,
                            "noted": noted, "applies": raw == R.LOW}}


# ---------- price thresholds ----------

def _boundary_values(rule: dict | None) -> tuple[float, float] | None:
    a1 = rule["axis1"] if rule else None
    if not a1 or a1["low"] is None or a1["high"] is None or a1["high"] <= a1["low"]:
        return None
    span = a1["high"] - a1["low"]
    return a1["low"] + span * (R.LOW_PCT + 0.5) / 100, a1["low"] + span * (R.HIGH_PCT - 0.5) / 100


def flip_prices(per: dict, pbr: dict, peg: dict, currency: str) -> list[str]:
    """The prices at which a judgement moves one step (from the multiples the script used)."""
    out = []
    eps = per["eps_for_per"]
    bounds = _boundary_values(per["rule"]) if per["rating"] != R.NA else None
    if bounds and eps:
        out.append(f"PER: 過去レンジの割安圏（位置{R.LOW_PCT}%以下）になる株価 {yen(bounds[0] * eps, currency)} 以下、"
                   f"割高圏（{R.HIGH_PCT}%以上）になる株価 {yen(bounds[1] * eps, currency)} 以上")
    fair, bps = pbr["fair"]["fair"], pbr["bps"]
    if fair and bps:
        out.append(f"PBR: 適正PBR {fair:.2f}倍 から割安（−{FAIR_PBR_BAND * 100:.0f}%）になる株価 "
                   f"{yen(fair * (1 - FAIR_PBR_BAND) * bps, currency)} 以下、割高（+{FAIR_PBR_BAND * 100:.0f}%）になる株価 "
                   f"{yen(fair * (1 + FAIR_PBR_BAND) * bps, currency)} 以上")
    g = peg["cases"]["standard"]
    if peg["rating"] in (R.LOW, R.FAIR, R.HIGH) and eps and g:
        out.append(f"PEG: 1倍になる株価 {yen(g * PEG_LOW * eps, currency)}、2倍になる株価 {yen(g * PEG_HIGH * eps, currency)}")
    return out


# ---------- everything ----------

def _price_age(base: dict, today: str) -> int | None:
    date = base["price"]["date"]
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(date)).days if date else None


def candidates(company, found: dict, today: str, measures: str | None = None) -> dict:
    base = V.base(company, found)
    growth = growth_result(company)
    g = growth[1] if growth else None
    per = per_step(base, g)
    pbr = pbr_step(base, measures)
    peg = peg_step(base, per, g)
    ev = ev_step(base, per)
    items = {"per": per, "pbr": pbr, "peg": peg, "ev": ev}
    upstream = others(company)
    s3 = step3(items, upstream)
    return {"base": base, **items, "step3": s3, "verdict": s3["verdict"], "why": s3["why"], "upstream": upstream,
            "growth_date": growth[0] if growth else None, "price_age": _price_age(base, today),
            "flip_prices": flip_prices(per, pbr, peg, base["price"]["currency"]),
            "borderline": per["borderline"] + pbr["borderline"] + peg["borderline"] + ev["borderline"]}


def trap_outcomes(company, found: dict, today: str) -> set[str]:
    """The STEP 3 verdicts the writer's answer to the PBR improvement measures can lead to."""
    return {candidates(company, found, today, m)["verdict"] for m in MEASURES}


def collect_requests(company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, a price older than PRICE_MAX_AGE days and a missing peer 12章."""
    unavailable = I.unavailable_items(company)
    extra: list[tuple[str, str]] = []
    age = cands["price_age"]
    if found["price"].status == "ok" and (age is None or age > PRICE_MAX_AGE):
        extra.append(("collect-peers-valuation", PRICE_ITEM))
    if found["peer_ebitda"].status in ("missing", "blank") and \
            not any(I.PEER_EBITDA_UNAVAILABLE in u for u in unavailable):
        extra.append(("collect-peers-valuation", EBITDA_ITEM))
    out = [dict(r, items=list(r["items"])) for r in I.collect_requests(found)]
    for agent, item in extra:
        hit = next((r for r in out if r["agent"] == agent), None)
        if hit is None:
            out.append({"agent": agent, "items": [item]})
        elif item not in hit["items"]:
            hit["items"] = hit["items"] + [item]
    return out


def warnings(cands: dict) -> list[str]:
    """Signs that the numbers were read wrongly, or are old (shown in the brief and prepare's output)."""
    base, out = cands["base"], []
    reported = base["reported"]
    for name, mine, theirs in (("実績PER", cands["per"]["per_actual"], reported["per_actual"]),
                               ("予想PER", cands["per"]["per_forecast"], reported["per_forecast"]),
                               ("PBR", cands["pbr"]["pbr"], reported["pbr"])):
        if mine and theirs and abs(mine / theirs - 1) > MISMATCH:
            out.append(f"{name}: スクリプトの計算 {mine:.2f}倍 と株価データ 3章の {theirs:.2f}倍 が10%超ずれる"
                       "（EPS・BPS・株価の読み違い、または調整EPS・基準日の違い）")
    if base["price"].get("intraday"):
        out.append("株価: 株価データ 1章の値が取引中の値で、確定終値の記載が無い（確定終値で取り直す）")
    age = cands["price_age"]
    if age is None:
        out.append("株価の基準日が株価データ 1章から読めない")
    elif age > PRICE_MAX_AGE:
        out.append(f"株価の基準日 {base['price']['date']} が分析日の{age}日前（{PRICE_MAX_AGE}日より古い）")
    peer_date = base["peers"]["date"]
    if peer_date and base["price"]["date"] and peer_date != base["price"]["date"]:
        out.append(f"競合 6章の基準日 {peer_date} が自社の株価の基準日 {base['price']['date']} と違う")
    # a split adjustment only rescales the older years' EPS: the newest EPS (the only one used here) is unchanged
    price = base["price"]
    if price.get("shares_uncertain"):
        upper = f"上限は自己株式を含む {price['total_shares']:,.0f}株" if price.get("total_shares") else "上限は不明"
        out.append(f"株式数: {price['uncertain_note'] or '株式数が未確認'}。時価総額・EV は {price['shares']:,.0f}株で計算した"
                   f"（{upper}。PER・PBR は1株指標なので影響しない。4章に上限での EV/EBITDA の判定を記入）")
    for p in base["peers"]["peers"]:
        for ratio, label in (("per_actual", "実績PER"), ("per_forecast", "予想PER"), ("pbr", "PBR")):
            shown = p.get(f"{ratio}_shown")
            if ratio in p.get("computed", ()) and shown and abs(p[ratio] / shown - 1) > PEER_MISMATCH:
                out.append(f"競合 {p['name']}: {label} の表示値 {shown:.2f}倍 と 株価 ÷ 1株指標 {p[ratio]:.2f}倍 が10%超ずれる"
                           "（計算値を使った）")
    for o in base["years"]["odd"]:
        out.append(f"EPS: {o['before']}→{o['after']} で株式数が{o['ratio']:.0f}倍変わる（単位の読み違いの可能性。調整しない）")
    if base["market_cap"] is None:
        out.append(f"時価総額を年次の単位（{base['years']['unit']}）にそろえられない（EV/EBITDA を計算しない）")
    return out


def _r(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


def series_digest(cands: dict) -> str:
    """Every number the result rests on: a new price, fiscal year or peer value re-opens the result."""
    base = cands["base"]
    own = [base["price"]["price"], base["price"]["date"], (base["forecast_eps"] or {}).get("value"),
           _r(cands["per"]["step1"]["eps_used"]), _r(cands["pbr"]["bps"])]
    years = [[r["year"], _r(r["net_income"], 0), _r(r["operating_income"], 0), _r(r["depreciation"], 0),
              _r(r["debt"], 0), _r(r["cash"], 0)] for r in base["years"]["rows"][-6:]]
    history = [[h["year"], h["per_high"], h["per_low"], h["pbr_high"], h["pbr_low"], h["per_end"]]
               for h in base["history"]]
    peers = [[p["name"], p["per_actual"], p["per_forecast"], p["pbr"], _r(p["ev_ebitda_calc"]), _r(p["cagr"])]
             for p in base["peers"]["peers"]]
    return A.digest(json.dumps([own, years, history, peers], ensure_ascii=False))
