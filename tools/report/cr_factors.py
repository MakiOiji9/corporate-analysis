"""The factors the three horizons are scored on (cr_judge.horizon_score), built from facts.json's material.

Each factor is {score: +1..−1 or None (no material), value, reason, source, pending}:
  analyses   growth, profitability, cash_flow, safety, five_forces, three_c, moat, swot: the verdict word
             (良好/高/明確/広い/Yes +1, 普通/中/あいまい/狭い/条件付き 0, 懸念/低/なし/No −1, 判定保留 0 and pending)
  valuation  the average score of the four indicators (−1..+1); the raw STEP 3 verdict when no average
  market     the outlook's row for the horizon (平常 +1, 注意 0, 警戒 −1)
  price      the 52-week position (≤33% +1, ≥67% −1, else 0) averaged with the gap to the 26-week moving average
             (beyond ±15% −1, else 0)
  progress   the latest quarter's operating-income progress against the same quarter a year earlier (or the
             standard pace): ≥110% +1, <90% −1, else 0
"""
from __future__ import annotations

import cr_judge as J
import cr_prices as CP

PERIOD_KEYS = {"short": "短期", "mid": "中期", "long": "長期"}
LOW_ZONE, TOP_ZONE = 33, 67
MA_GAP_LIMIT = 15.0
PROGRESS_UP, PROGRESS_DOWN = 1.1, 0.9
ANALYSIS_KEYS = ("growth", "profitability", "cash_flow", "safety", "five_forces", "three_c", "moat", "swot")


def _factor(score: float | None, value: str, reason: str, source: str, pending: bool = False) -> dict:
    return {"score": score, "value": value, "reason": reason, "source": source, "pending": pending}


def analysis_factor(a: dict) -> dict:
    verdict = a.get("verdict")
    note = "（材料不足のため保守的に判定）" if a.get("conservative") else ""
    return _factor(J.score_of(verdict), verdict or "未実施", (a.get("reason") or "") + note,
                   f"{a['step']} {a['label']}分析（{a.get('date') or '未実施'}）", verdict == J.PENDING)


def step3_verdict(valuation: dict) -> str | None:
    """STEP 3 without the old final-check raise (results built before it was dropped carry raw_verdict)."""
    detail = valuation.get("detail") or {}
    if (detail.get("final_check") or {}).get("raised") and detail.get("raw_verdict"):
        return detail["raw_verdict"]
    return valuation.get("verdict")


def valuation_factor(valuation: dict) -> dict:
    detail = valuation.get("detail") or {}
    verdict = step3_verdict(valuation)
    average = detail.get("average")
    score = max(-1.0, min(1.0, float(average))) if average is not None else J.score_of(verdict)
    value = f"{verdict or '未実施'}（4指標の平均点 {average:+.2f}）" if average is not None else (verdict or "未実施")
    return _factor(score, value, detail.get("sheet") or valuation.get("reason") or "",
                   f"3 バリュエーション分析（{valuation.get('date') or '未実施'}）", verdict == J.PENDING)


def market_factor(outlook: dict, horizon: str) -> dict:
    row = (outlook.get("rows") or {}).get(PERIOD_KEYS[horizon]) or {}
    judgment = row.get("judgment")
    return _factor(J.score_of(judgment) if judgment in ("平常", "注意", "警戒") else None, judgment or "不明",
                   row.get("scenario") or "", f"地合い {outlook.get('path') or '—'}（{PERIOD_KEYS[horizon]}の行）")


def price_factor(prices: dict) -> dict:
    position, gap = CP.short_inputs(prices)
    parts = []
    if position is not None:
        parts.append(1.0 if position <= LOW_ZONE else -1.0 if position >= TOP_ZONE else 0.0)
    if gap is not None:
        parts.append(-1.0 if abs(gap) > MA_GAP_LIMIT else 0.0)
    if not parts:
        return _factor(None, "不明（株価の時系列が無い）", "", "株価の過去レンジ")
    value = "、".join(([f"52週レンジの位置 {position:.0f}%"] if position is not None else [])
                     + ([f"26週移動平均との差 {gap:+.1f}%"] if gap is not None else []))
    reason = f"位置 {LOW_ZONE}% 以下は +1、{TOP_ZONE}% 以上は −1。移動平均との差が ±{MA_GAP_LIMIT:.0f}% を超えると −1"
    return _factor(sum(parts) / len(parts), value, reason, "株価の過去レンジ（data/prices.csv）")


def progress_factor(growth: dict) -> dict:
    progress = (growth.get("detail") or {}).get("progress") or {}
    item = (progress.get("items") or {}).get("operating_income") or {}
    rate, prior, quarter = item.get("progress"), item.get("prior_progress"), progress.get("quarter")
    if rate is None or not quarter:
        return _factor(None, "不明（四半期の進捗が無い）", "", "成長性分析 progress")
    pace, basis = (prior, "前年同期") if prior else (quarter / 4 * 100, "標準ペース")
    ratio = rate / pace if pace else None
    score = None if ratio is None else 1.0 if ratio >= PROGRESS_UP else -1.0 if ratio < PROGRESS_DOWN else 0.0
    value = f"第{quarter}四半期 {rate:.1f}%（{basis} {pace:.1f}%）"
    reason = f"{basis}の {PROGRESS_UP * 100:.0f}% 以上は +1、{PROGRESS_DOWN * 100:.0f}% 未満は −1"
    return _factor(score, value, reason, "成長性分析 progress（決算短信）")


def build(found: dict[str, dict], prices: dict, outlook: dict) -> dict[str, dict[str, dict]]:
    """horizon -> factor key -> factor."""
    common = {key: analysis_factor(found[key]) for key in ANALYSIS_KEYS}
    common.update(valuation=valuation_factor(found["valuation"]), price=price_factor(prices),
                  progress=progress_factor(found["growth"]))
    return {horizon: {**common, "market": market_factor(outlook, horizon)} for horizon in PERIOD_KEYS}
