"""How to read the price phase (参考の視点, not scored): a fall or a rise, and whether the business backs it.

Phase: a fall (DOWN_FROM_HIGH or more below the 52-week high, or a long-term downtrend) is checked first, then a rise
(UP_FROM_LOW above the 52-week low with the chart in an uptrend, a long-term uptrend, or the top UP_POSITION of the
52-week range). In a fall the question is whether a sound company has become cheap (優良企業の押し目); in a rise,
whether earnings carry it or expectations run ahead (割高・過熱・株価の伸びが EPS の伸びを大きく上回る).
"""
from __future__ import annotations

DOWN, UP, NONE = "下落局面", "上昇局面", "どちらでもない"
DOWN_FROM_HIGH, UP_FROM_LOW, UP_POSITION = -20.0, 30.0, 80.0
CHEAP_PER, RICH_PER = 33, 67          # position in the PER range (%)
HOT_RSI, HOT_MA_GAP, AHEAD_PT = 70.0, 15.0, 5.0
GOOD_GRADES = ("A", "B")

DIP_GOOD = "優良企業の押し目（買い場の候補）"
DIP_TRAP = "値下がりしているが買い場とは言えない（割安だが事業・財務が弱く、バリュートラップの疑い）"
DIP_WEAK = "値下がりしているが買い場とは言えない（事業・財務の弱さ）"
DIP_NOT_CHEAP = "値下がりしているが買い場とは言えない（まだ割安ではない）"
UP_EARNED = "業績を伴う上昇（優良企業の上昇の継続）"
UP_HOPE = "期待先行の上昇（割高・過熱の疑い）"
UP_WEAK = "事業・財務の裏付けが弱い上昇"
NEITHER = "下落局面でも上昇局面でもない"


def _check(item: str, value: str, ok: bool | None) -> dict:
    return {"item": item, "value": value, "ok": ok}


def _num(v: float | None, unit: str = "%", signed: bool = True) -> str:
    return "—" if v is None else (f"{v:+.1f}{unit}" if signed else f"{v:.0f}{unit}")


def _quality(c: dict) -> tuple[bool | None, dict]:
    grades = (c.get("step1"), c.get("step2"))
    ok = None if None in grades else (all(g in GOOD_GRADES for g in grades) and not c.get("flags"))
    value = f"STEP 1 {grades[0] or '—'}・STEP 2 {grades[1] or '—'}" + ("・赤信号あり" if c.get("flags") else "")
    return ok, _check("事業・財務の質（STEP 1・2 が A/B、赤信号なし）", value, ok)


def _cheap(c: dict) -> tuple[bool, dict]:
    pos = c.get("per_position")
    ok = c.get("step3") == "割安" or (pos is not None and pos <= CHEAP_PER)
    return ok, _check("割安（STEP 3 割安、または PER が過去レンジの下側）",
                      f"STEP 3 {c.get('step3') or '—'}・PER の位置 {_num(pos, '%', False)}", ok)


def _phase(c: dict) -> tuple[str, list[dict]]:
    fall = (c.get("from_high") is not None and c["from_high"] <= DOWN_FROM_HIGH) or c.get("trend") == "下降トレンド"
    rise = ((c.get("from_low") is not None and c["from_low"] >= UP_FROM_LOW and "上昇" in (c.get("tech_state") or ""))
            or c.get("trend") == "上昇トレンド" or (c.get("pos52") is not None and c["pos52"] >= UP_POSITION))
    checks = [_check(f"52週高値から {DOWN_FROM_HIGH:.0f}% 以下、または長期の下降トレンド",
                     f"高値から {_num(c.get('from_high'))}・長期 {c.get('trend') or '—'}", fall),
              _check(f"（下落局面でないとき）52週安値から +{UP_FROM_LOW:.0f}% 以上で上昇トレンド、長期の上昇トレンド、"
                     "または52週レンジの上側",
                     f"安値から {_num(c.get('from_low'))}・52週の位置 {_num(c.get('pos52'), '%', False)}", rise)]
    if fall:  # a fall is read first: the rise check does not apply
        checks[1] = {**checks[1], "ok": None, "value": checks[1]["value"] + "（下落局面のため見ない）"}
    return (DOWN if fall else UP if rise else NONE), checks


def evaluate(c: dict) -> dict:
    """{phase, verdict, checks: [{item, value, ok}]}; c is built by cr_facts (see BASE in the tests)."""
    phase, checks = _phase(c)
    quality, q_check = _quality(c)
    if phase == DOWN:
        cheap, c_check = _cheap(c)
        verdict = (DIP_GOOD if quality and cheap else DIP_TRAP if cheap and quality is not True
                   else DIP_WEAK if quality is False else DIP_NOT_CHEAP)
        return {"phase": phase, "verdict": verdict, "checks": checks + [q_check, c_check]}
    if phase == UP:
        pos = c.get("per_position")
        rich = c.get("step3") == "割高" or (pos is not None and pos >= RICH_PER)
        hot = (c.get("rsi") or 0) >= HOT_RSI or (c.get("ma26_gap") or 0) >= HOT_MA_GAP
        price, eps = c.get("price_rate"), c.get("eps_rate")
        ahead = price is not None and eps is not None and price - eps > AHEAD_PT
        verdict = UP_WEAK if quality is not True else UP_HOPE if rich or hot or ahead else UP_EARNED
        return {"phase": phase, "verdict": verdict, "checks": checks + [
            q_check,
            _check("割高（STEP 3 割高、または PER が過去レンジの上側）", f"STEP 3 {c.get('step3') or '—'}・PER の位置 "
                   f"{_num(pos, '%', False)}", rich),
            _check(f"過熱（RSI {HOT_RSI:.0f} 以上、または26週線から +{HOT_MA_GAP:.0f}% 以上）",
                   f"RSI {_num(c.get('rsi'), '', False)}・26週線との差 {_num(c.get('ma26_gap'))}", hot),
            _check(f"株価の伸びが EPS の伸びを {AHEAD_PT:.0f}pt 超えて上回る", f"株価 {_num(price)}・EPS {_num(eps)}", ahead)]}
    return {"phase": phase, "verdict": NEITHER, "checks": checks}
