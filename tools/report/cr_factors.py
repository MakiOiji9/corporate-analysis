"""The factors the three horizons are scored on (cr_judge.horizon_score), built from facts.json's material.

Each factor is {score: +1..−1 or None (no material), value, reason, source, pending}:
  analyses   growth, profitability, cash_flow, safety, five_forces, three_c, moat, swot: the verdict word
             (良好/高/明確/広い/Yes +1, 普通/中/あいまい/狭い/条件付き 0, 懸念/低/なし/No −1, 判定保留 0 and pending),
             moved half a step by the analysis' own sub-ratings (subs, cr_facts.SUBS) when they lean the other way:
             a 普通 whose subs average ≥ +0.25 is +0.5 (≤ −0.25: −0.5); a 懸念 whose subs average ≥ 0 is −0.5
             (one narrow concern); a 良好 whose subs average ≤ 0 is +0.5. Needs two known subs; hold keeps −1.
  valuation  the average score of the indicators without the one-sided net-cash ratio (it can only be 割安 or
             妥当); fewer than two scored indicators is 判定保留 (0); the raw STEP 3 verdict when no scores
  market     the outlook's row for the horizon (平常 +1, 注意 0, 警戒 −1)
  price      the technical score of cr_technicals (trend, momentum and position averaged; −1..+1); left out
             without a year of prices (no trend: the position and momentum alone are not a reading)
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


def _factor(score: float | None, value: str, reason: str, source: str, pending: bool = False) -> dict:
    return {"score": score, "value": value, "reason": reason, "source": source, "pending": pending}


def half_step(verdict_score: float, subs: list) -> float:
    """The verdict's score moved half a step toward its sub-ratings when they lean the other way."""
    known = [SUB_SCORE[s] for s in subs if s in SUB_SCORE]
    if len(known) < SUB_MIN:
        return verdict_score
    lean = sum(known) / len(known)
    if verdict_score == 0.0 and abs(lean) >= LEAN:
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
    note = "（一部の項目は材料不足のため保守的に扱った）" if a.get("conservative") and "保守的" not in reason else ""
    score = J.score_of(verdict)
    value = verdict or "未実施"
    if score is not None and verdict != J.PENDING and not hold:
        moved = half_step(score, a.get("subs") or [])
        if moved != score:
            value = f"{verdict}（内訳から {moved:+.1f}）"
            note += f"（内訳の評価が{'良い' if moved > score else '悪い'}側に寄るため {moved:+.1f} 点で数えた）"
            score = moved
    return _factor(score, value, reason + note,
                   f"{a['step']} {a['label']}分析（{a.get('date') or '未実施'}）", verdict == J.PENDING)


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
    common.update(valuation=valuation_factor(found["valuation"]), price=price_factor(prices),
                  progress=progress_factor(found["growth"]))
    return {horizon: {**common, "market": market_factor(outlook, horizon)} for horizon in PERIOD_KEYS}
