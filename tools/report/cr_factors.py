"""The factors the three horizons are scored on (cr_judge.horizon_score), built from facts.json's material.

Each factor is {score: +1..−1 or None (no material), value, reason, source, pending}:
  analyses   growth, profitability, cash_flow, safety, five_forces, three_c, moat, swot: the verdict word
             (良好/高/明確/広い/Yes +1, 普通/中/あいまい/狭い/条件付き 0, 懸念/低/なし/No −1, 判定保留 0 and pending),
             moved half a step by the analysis' own sub-ratings (subs, cr_facts.SUBS) when they lean the other way:
             a 普通 whose subs average > +0.25 is +0.5 (< −0.25: −0.5; not raised with a −1 sub); a 懸念 whose subs average ≥ 0 is −0.5
             (one narrow concern); a 良好 whose subs average ≤ 0 is +0.5. Needs two known subs; hold keeps −1.
             The moat is scored by moat_factor: 広い +1, 狭い +0.5, なし 0 while the excess return is 強い/弱い (a
             moat is rare; the lack of an identified source is not a weakness), −1 without an excess return.
  valuation  the average score of the indicators without the one-sided net-cash ratio (it can only be 割安 or
             妥当); fewer than two scored indicators is 判定保留 (0); the raw STEP 3 verdict when no scores
  market     the outlook's row for the horizon (平常 +1, 注意 0, 警戒 −1)
  price      中期: the technical score of cr_technicals (13・26・52週線 trend, momentum and position averaged; −1..+1);
             left out without a year of prices (no trend: the position and momentum alone are not a reading)
  trend_daily  短期: the daily trend of the technical analysis (付録B, cr_tech_views): 上昇 +1, もみ合い 0, 下降 −1,
             0 when its confidence is 低 (判定ルールの改定 3)
  progress   the latest quarter's operating-income progress against the same quarter a year earlier (or the
             standard pace): ≥110% +1, <90% −1, else 0
"""
from __future__ import annotations

import cr_judge as J
import cr_technicals as T

PERIOD_KEYS = {"short": "短期", "mid": "中期", "long": "長期"}
PROGRESS_UP, PROGRESS_DOWN = 1.1, 0.9
ANALYSIS_KEYS = ("growth", "profitability", "cash_flow", "safety", "five_forces", "three_c", "moat", "swot")
SUB_SCORE = {  # the STEP 2 analyses' step ratings (None, 不明, 対象外 are not counted)
    **dict.fromkeys(("良好", "上回る", "本業由来", "高成長", "信頼できる", "高い", "問題なし", "クリア",
                     "悪化傾向なし", "許容"), 1.0),
    **dict.fromkeys(("普通", "同等", "安定成長", "割り引いて扱う", "要確認", "注意", "特定できず"), 0.0),
    **dict.fromkeys(("懸念", "下回る", "借入依存", "停滞・縮小", "問題あり", "未達", "悪化傾向"), -1.0),
}
SUB_MIN = 2  # known sub-ratings needed to move a verdict
LEAN = 0.25  # a 普通 moves when its subs average this far from 0
HALF = 0.5
ONE_SIDED = "ネットキャッシュ比率"  # valuation indicator that can never be 割高
MIN_INDICATORS = 2


def _factor(score: float | None, value: str, reason: str, source: str, pending: bool = False,
            note: str = "") -> dict:
    """note: how the report counted the factor (a half step, a conservative reading). It is shown on a line of
    its own under the reason, not in brackets inside it."""
    return {"score": score, "value": value, "reason": reason, "source": source, "pending": pending, "note": note}


def _join(*notes: str) -> str:
    return "。".join(n for n in notes if n)


def half_step(verdict_score: float, subs: list) -> float:
    """The verdict's score moved half a step toward its sub-ratings when they lean the other way."""
    known = [SUB_SCORE[s] for s in subs if s in SUB_SCORE]
    if len(known) < SUB_MIN:
        return verdict_score
    lean = sum(known) / len(known)
    # 判定ルールの改定 3: a lean exactly at LEAN does not move (policy 6, the lower of two readings), and a 普通 with a
    # concern among its subs (問題あり etc. −1) is not raised
    if verdict_score == 0.0 and abs(lean) > LEAN and not (lean > 0 and -1.0 in known):
        return HALF if lean > 0 else -HALF
    if verdict_score == -1.0 and lean >= 0:
        return -HALF
    if verdict_score == 1.0 and lean <= 0:
        return HALF
    return verdict_score


def analysis_factor(a: dict, hold: bool = False) -> dict:
    """hold keeps the verdict's own score (a cash-flow concern with cash burn is not softened)."""
    verdict = a.get("verdict")
    reason = a.get("reason") or ""
    # most analyses already end their verdict_reason with this note: add it only when it is missing
    # the conservative list names assumed items, not necessarily the ones that decided the verdict
    note = "一部の項目は材料不足のため保守的に扱った" if a.get("conservative") and "保守的" not in reason else ""
    score = J.score_of(verdict)
    value = verdict or "未実施"
    if score is not None and verdict != J.PENDING and not hold:
        moved = half_step(score, a.get("subs") or [])
        if moved != score:
            value = f"{verdict}（内訳から {moved:+.1f}）"
            note = _join(note, f"内訳の評価が{'良い' if moved > score else '悪い'}側に寄るため {moved:+.1f} 点で数えた")
            factor = _factor(moved, value, reason, f"{a['step']} {a['label']}分析（{a.get('date') or '未実施'}）",
                             False, note)
            return {**factor, "whole": score}  # the verdict word's own score (cr_judge.half_step_dependence)
    return _factor(score, value, reason, f"{a['step']} {a['label']}分析（{a.get('date') or '未実施'}）",
                   verdict == J.PENDING, note)


MOAT_SCORE = {"広い": 1.0, "狭い": 0.5}
EXCESS_RETURN = ("強い", "弱い")  # the moat analysis' 超過収益 ratings that show a return above the cost of capital


def moat_factor(a: dict) -> dict:
    """広い +1 / 狭い +0.5 / なし: 0 while the company earns above its cost of capital (超過収益 強い・弱い; the source
    could not be found, which is the usual case and not a weakness), −1 without that excess return."""
    factor = analysis_factor(a)
    verdict = a.get("verdict")
    if verdict in MOAT_SCORE:
        return {**factor, "score": MOAT_SCORE[verdict]}
    returns = ((a.get("detail") or {}).get("returns") or {}).get("rating")
    if verdict == "なし" and returns in EXCESS_RETURN:
        return {**factor, "score": 0.0, "value": f"なし（超過収益は{returns}。それを守る源泉は特定できない）",
                "note": _join(factor.get("note", ""), "資本コストを上回る利益はあるため、モートが無いことは点数では中立に"
                                                       "数えた。マイナスにするのは超過収益そのものが無いとき")}
    return factor


def step3_verdict(valuation: dict) -> str | None:
    """STEP 3 without the old final-check raise (results built before it was dropped carry raw_verdict)."""
    detail = valuation.get("detail") or {}
    if (detail.get("final_check") or {}).get("raised") and detail.get("raw_verdict"):
        return detail["raw_verdict"]
    return valuation.get("verdict")


def _two_sided(detail: dict) -> tuple[float | None, int | None]:
    """The average of the scored indicators without the one-sided net-cash ratio, and their count (None when
    an old result does not say). Results without per-indicator scores fall back to the analysis' own average."""
    scores = detail.get("scores")
    if not isinstance(scores, dict):
        average = detail.get("average")
        return (None if average is None else float(average)), detail.get("scored")
    used = [float(v) for k, v in scores.items() if k != ONE_SIDED and v is not None]
    return (sum(used) / len(used) if used else None), len(used)


def valuation_factor(valuation: dict) -> dict:
    detail = valuation.get("detail") or {}
    verdict = step3_verdict(valuation)
    source = f"3 バリュエーション分析（{valuation.get('date') or '未実施'}）"
    reason = detail.get("sheet") or valuation.get("reason") or ""
    average, count = _two_sided(detail)
    if count is not None and count < MIN_INDICATORS:
        return _factor(0.0, f"{verdict or '未実施'}（{count}指標だけ。判定保留として 0 点）",
                       reason + f"（採点できた指標が{MIN_INDICATORS}つ未満のため、割安・割高は数えない）", source, True)
    if average is None:
        return _factor(J.score_of(verdict), verdict or "未実施", reason, source, verdict == J.PENDING)
    value = f"{verdict or '未実施'}（{count or ''}指標の平均点 {average:+.2f}）"
    return _factor(max(-1.0, min(1.0, average)), value, reason, source, verdict == J.PENDING)


def market_factor(outlook: dict, horizon: str) -> dict:
    row = (outlook.get("rows") or {}).get(PERIOD_KEYS[horizon]) or {}
    judgment = row.get("judgment")
    return _factor(J.score_of(judgment) if judgment in ("平常", "注意", "警戒") else None, judgment or "不明",
                   row.get("scenario") or "",
                   f"地合いレポート（{outlook.get('week') or '—'} の週）の{PERIOD_KEYS[horizon]}の見通し")


def price_factor(prices: dict) -> dict:
    t = prices.get("technicals") or {}
    if prices.get("source") != "prices" or t.get("score") is None:
        return _factor(None, T.value_text(t), "", "株価のテクニカル")
    if (t.get("trend") or {}).get("score") is None:  # under a year of prices: not a reading yet
        return _factor(None, T.value_text(t) + "（1年分の株価が無く、点数には入れない）", "", "株価のテクニカル")
    return _factor(t["score"], T.value_text(t), T.REASON, "株価のテクニカル（日々の株価）")


TREND_SCORE = {"up": 1.0, "down": -1.0, "flat": 0.0}  # cr_patterns.UP / DOWN / FLAT
LOW_CONFIDENCE = "低"


def daily_trend_factor(prices: dict) -> dict:
    """短期: 付録B の日足の「トレンド」切り口（cr_tech_views.trend）. 上昇 +1 / もみ合い 0 / 下降 −1, and 0 when its
    confidence is 低 (判定ルールの改定 3). Left out without the daily analysis."""
    a = prices.get("daily_trend") or {}
    source = "テクニカル分析（日足のトレンド）"
    if a.get("direction") not in TREND_SCORE:
        return _factor(None, "不明（日足のトレンドを出せない）", "", source)
    conf = a.get("confidence") or LOW_CONFIDENCE
    score = 0.0 if conf == LOW_CONFIDENCE else TREND_SCORE[a["direction"]]
    lines = "、".join(e["text"] for e in a.get("evidence") or [])
    reason = ("確度が低いため 0 点で数えた。" if conf == LOW_CONFIDENCE and a["direction"] != "flat" else "") + lines
    return _factor(score, f"{a.get('state')}（確度 {conf}）", reason, source)


def progress_factor(growth: dict) -> dict:
    progress = (growth.get("detail") or {}).get("progress") or {}
    item = (progress.get("items") or {}).get("operating_income") or {}
    rate, prior, quarter = item.get("progress"), item.get("prior_progress"), progress.get("quarter")
    if rate is None or not quarter:
        return _factor(None, "不明（四半期の進捗が無い）", "", "成長性分析（四半期の進捗）")
    pace, basis = (prior, "前年同期") if prior else (quarter / 4 * 100, "標準ペース")
    ratio = rate / pace if pace else None
    score = None if ratio is None else 1.0 if ratio >= PROGRESS_UP else -1.0 if ratio < PROGRESS_DOWN else 0.0
    value = f"第{quarter}四半期 {rate:.1f}%（{basis} {pace:.1f}%）"
    reason = f"{basis}の {PROGRESS_UP * 100:.0f}% 以上は +1、{PROGRESS_DOWN * 100:.0f}% 未満は −1"
    return _factor(score, value, reason, "成長性分析（決算短信の四半期の進捗）")


def build(found: dict[str, dict], prices: dict, outlook: dict,
          burn: list[str] | tuple = ()) -> dict[str, dict[str, dict]]:
    """horizon -> factor key -> factor. burn (cr_judge.cash_burn) keeps the cash-flow factor's own score."""
    common = {key: analysis_factor(found[key], hold=bool(burn) and key == "cash_flow") for key in ANALYSIS_KEYS}
    common["moat"] = moat_factor(found["moat"])
    common.update(valuation=valuation_factor(found["valuation"]), price=price_factor(prices),
                  trend_daily=daily_trend_factor(prices), progress=progress_factor(found["growth"]))
    return {horizon: {**common, "market": market_factor(outlook, horizon)} for horizon in PERIOD_KEYS}
