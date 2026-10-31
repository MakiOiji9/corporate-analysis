"""Company report judgements (企業分析フレームワーク.md STEP 1・2 総合、保有期間ごとの判定).

Pure functions on the conclusions of the nine analyses and a few market / price figures, so every rule is
unit-tested:
  step1()          STEP 1 A/B/C from 1-1〜1-4 (L230-239). 勝てる理由・SWOT が判定保留なら確定しない（暫定 B）.
  step2()          STEP 2 A/B/C by score: 良好 +1・普通 0・懸念 −1 の平均. A ≥ +0.5 with no mismatch; C ≤ −0.25,
                   two or more 懸念, or a serious red flag (red_flags()); otherwise B.
  horizon_score()  短期・中期・長期: each factor scored +1 / 0 / −1 and averaged with the horizon's WEIGHTS
                   (+0.3 以上 投資検討, −0.2 以下 見送り, otherwise ウォッチ). A factor without material is left out
                   and the weights are re-normalised; a 判定保留 analysis counts as 0.
  knockouts()      serious red flags pass every horizon; STEP 1 C passes the long horizon only.
  matrix_reference()  the framework's decision matrix (STEP 1 × 2 × 3), shown next to the long horizon.
  sensitivity()    which single factor moving one step would change a horizon's verdict, and the distance to
                   the thresholds.
Every horizon carries its factor rows {key, label, weight, score, contribution, value, reason, source}; the
report shows the positive contributions as 良い点 and the negative ones as 悪い点.
"""
from __future__ import annotations

PENDING = "判定保留"
CONSIDER, WATCH, PASS = "投資検討", "ウォッチ", "見送り"
LEVELS = (CONSIDER, WATCH, PASS)  # best first
UP, DOWN = 0.3, -0.2  # horizon score thresholds
STEP2_A, STEP2_C = 0.5, -0.25
MATRIX = {  # (row, STEP 3) -> verdict, with the framework's note
    ("A", "割安"): (CONSIDER, ""), ("A", "妥当"): (CONSIDER, "分割購入など"), ("A", "割高"): (WATCH, "下落を待つ"),
    ("B", "割安"): (CONSIDER, "割安の理由を精査"), ("B", "妥当"): (WATCH, ""), ("B", "割高"): (PASS, ""),
}
ATTRACTIVE = ("高", "中")
SCORE = {"良好": 1, "普通": 0, "懸念": -1, "高": 1, "中": 0, "低": -1, "明確": 1, "あいまい": 0, "なし": -1,
         "広い": 1, "狭い": 0, "Yes": 1, "条件付き": 0, "No": -1, "割安": 1, "妥当": 0, "割高": -1,
         "平常": 1, "注意": 0, "警戒": -1, PENDING: 0}
HORIZONS = (("short", "短期", "〜3ヶ月"), ("mid", "中期", "6ヶ月〜1年"), ("long", "長期", "3年以上"))
WEIGHTS = {  # percent; each horizon sums to 100
    "short": {"market": 25, "price": 25, "progress": 20, "valuation": 20, "safety": 10},
    "mid": {"market": 10, "price": 10, "progress": 15, "valuation": 20, "growth": 15, "profitability": 10,
            "cash_flow": 10, "safety": 5, "swot": 5},
    "long": {"market": 5, "valuation": 15, "growth": 10, "profitability": 10, "cash_flow": 10, "safety": 5,
             "five_forces": 10, "three_c": 15, "moat": 15, "swot": 5},
}
FACTOR_LABELS = {"market": "地合い", "price": "株価の位置・勢い", "progress": "直近の決算の進捗",
                 "valuation": "株価の割安さ（STEP 3）", "growth": "成長性", "profitability": "収益性",
                 "cash_flow": "キャッシュフロー", "safety": "安全性", "five_forces": "業界の魅力度（ファイブフォース）",
                 "three_c": "勝てる理由（3C）", "moat": "強みの持続性（モート）", "swot": "強みで脅威に対抗できるか（SWOT）"}


def _row(condition: str, value: object, source: str, ok: bool | None) -> dict:
    return {"condition": condition, "value": "—" if value in (None, "") else str(value), "source": source, "ok": ok}


def _known(value: str | None) -> bool:
    return bool(value) and value != PENDING


def lower(a: str, b: str) -> str:
    """The more cautious of two verdicts."""
    return LEVELS[max(LEVELS.index(a), LEVELS.index(b))]


def score_of(value: str | None) -> float | None:
    """+1 / 0 / −1 for a verdict word (判定保留 is 0), None when there is no result."""
    return float(SCORE[value]) if value in SCORE else None


# ---------------------------------------------------------------- STEP 1 / STEP 2

def step1(attractiveness: str | None, win: str | None, moat: str | None, swot: str | None) -> dict:
    """STEP 1 総合. grade is A/B/C; pending=True means it rests on a 判定保留 (grade is then provisional)."""
    rows = [
        _row("業界の魅力度が中以上", attractiveness, "1-1 ファイブフォース",
             attractiveness in ATTRACTIVE if attractiveness else None),
        _row("勝てる理由が明確", win, "1-2 3C", win == "明確" if _known(win) else None),
        _row("モートが広い", moat, "1-3 モート", moat == "広い" if _known(moat) else None),
        _row("SWOT が Yes", swot, "1-4 SWOT", swot == "Yes" if _known(swot) else None),
    ]
    failed = [r["condition"] for r in rows if r["ok"] is not True]
    if win == "なし" or swot == "No":
        why = "勝てる理由がなし" if win == "なし" else "SWOT が No"
        return {"grade": "C", "pending": False, "why": f"{why}（C の条件）", "failed": failed, "rows": rows}
    missing = [name for name, value in (("勝てる理由", win), ("SWOT", swot)) if not _known(value)]
    if not failed:
        return {"grade": "A", "pending": False, "why": "A の4条件をすべて満たす", "failed": [], "rows": rows}
    why = "A の条件を満たさない: " + "、".join(failed)
    if missing:
        why += f"（{'・'.join(missing)}が判定保留のため STEP 1 は確定しない。A にも C にもしない）"
    return {"grade": "B", "pending": bool(missing), "why": why, "failed": failed, "rows": rows}


def mismatches(moat: str | None, win: str | None, profitability: str | None, margin_diff: float | None) -> list[str]:
    """STEP 1 と STEP 2 の整合性チェック（L410-418）で食い違った項目."""
    found = []
    if moat == "広い" and (profitability == "懸念" or (margin_diff is not None and margin_diff <= 0)):
        found.append("モートが広いのに営業利益率が同業平均以下（または収益性が懸念）")
    if win == "明確" and profitability == "懸念":
        found.append("勝てる理由が明確なのに収益性が懸念")
    return found


def red_flags(cf_steps: list[dict], safety: str | None, safety_trend: str | None) -> list[str]:
    """Serious red flags: they pass every horizon and make STEP 2 C. cf_steps are the cash-flow 手順1〜2."""
    flags = []
    labels = ("営業CF がマイナスの年が続く（キャッシュフロー手順1が懸念）", "FCF の累計がマイナス（キャッシュフロー手順2が懸念）")
    for label, step in zip(labels, cf_steps[:2]):
        if (step or {}).get("rating") == "懸念":
            flags.append(label)
    if safety == "懸念" and safety_trend == "悪化傾向":
        flags.append("安全性が懸念で、しかも悪化傾向")
    return flags


def step2(items: dict[str, str | None], mismatch: list[str], flags: list[str] | tuple = ()) -> dict:
    """STEP 2 総合 by score. items: {収益性, 成長性, 安全性, キャッシュフロー: 良好/普通/懸念/判定保留/None}."""
    rows = [_row(f"{name}", value, f"2-{i} {name}分析", value == "良好" if _known(value) else None)
            for i, (name, value) in enumerate(items.items(), start=1)]
    rows.append(_row("STEP 1 との整合性", "、".join(mismatch) or "食い違いなし", "整合性チェック", not mismatch))
    rows.append(_row("深刻な赤信号が無い", "、".join(flags) or "なし", "キャッシュフロー・安全性", not flags))
    known = [SCORE[v] for v in items.values() if _known(v)]
    concerns = [name for name, v in items.items() if v == "懸念"]
    missing = [name for name, v in items.items() if not _known(v)]
    if not known:
        return {"grade": "B", "pending": True, "score": None, "why": "4項目とも判定保留・未実施", "rows": rows}
    average = sum(known) / len(known)
    base = f"平均点 {average:+.2f}（良好 +1・普通 0・懸念 −1。A は +{STEP2_A} 以上、C は {STEP2_C} 以下）"
    if flags or len(concerns) >= 2 or average <= STEP2_C:
        if flags:
            why = "深刻な赤信号: " + "、".join(flags)
        else:
            why = f"懸念が{len(concerns)}つ" if len(concerns) >= 2 else base
        return {"grade": "C", "pending": False, "score": round(average, 2), "why": f"{why}（C の条件）", "rows": rows}
    if average >= STEP2_A and not mismatch and not missing:
        return {"grade": "A", "pending": False, "score": round(average, 2), "why": base, "rows": rows}
    why = base + ("、整合性の食い違いあり" if mismatch else "")
    if missing:
        why += f"（{'・'.join(missing)}が判定保留・未実施のため確定しない）"
    return {"grade": "B", "pending": bool(missing), "score": round(average, 2), "why": why, "rows": rows}


# ---------------------------------------------------------------- horizons

def _verdict_for(score: float) -> str:
    return CONSIDER if score >= UP else PASS if score <= DOWN else WATCH


def _weighted(weights: dict[str, int], factors: dict[str, dict]) -> tuple[float | None, list[dict]]:
    rows = []
    for key, weight in weights.items():
        f = factors.get(key) or {}
        rows.append({"key": key, "label": FACTOR_LABELS[key], "weight": weight, "score": f.get("score"),
                     "value": f.get("value") or "—", "reason": f.get("reason") or "", "source": f.get("source") or "",
                     "pending": bool(f.get("pending"))})
    used = [r for r in rows if r["score"] is not None]
    total = sum(r["weight"] for r in used)
    if not total:
        return None, [dict(r, contribution=None) for r in rows]
    score = sum(r["weight"] * r["score"] for r in used) / total
    rows = [dict(r, contribution=round(r["weight"] * r["score"] / total, 3) if r["score"] is not None else None)
            for r in rows]
    return round(score, 3), rows


def knockouts(horizon: str, flags: list[str], step1_grade: str | None) -> list[str]:
    out = list(flags)
    if horizon == "long" and step1_grade == "C":
        out.append("STEP 1 が C（勝てる理由がなし、または SWOT が No）")
    return out


def horizon_score(horizon: str, factors: dict[str, dict], flags: list[str] | tuple = (),
                  step1_grade: str | None = None) -> dict:
    """The verdict of one horizon. factors: key -> {score (+1..−1 or None), value, reason, source, pending}."""
    score, rows = _weighted(WEIGHTS[horizon], factors)
    good = sorted((r for r in rows if (r["contribution"] or 0) > 0), key=lambda r: -r["contribution"])
    bad = sorted((r for r in rows if (r["contribution"] or 0) < 0), key=lambda r: r["contribution"])
    stops = knockouts(horizon, list(flags), step1_grade)
    base = {"score": score, "rows": rows, "good": good, "bad": bad, "knockout": stops, "provisional": None,
            "unknown": [r["label"] for r in rows if r["score"] is None]}
    if stops:
        return {**base, "verdict": PASS, "why": f"足切り: {'、'.join(stops)}（点数にかかわらず見送り）"}
    if score is None:
        return {**base, "verdict": PENDING, "why": "判定に使える材料が無い"}
    plus = f"プラス: {'・'.join(r['label'] for r in good[:2])}" if good else "プラスの要素なし"
    minus = f"マイナス: {'・'.join(r['label'] for r in bad[:2])}" if bad else "マイナスの要素なし"
    why = f"重み付けの点数 {score:+.2f}（+{UP} 以上 投資検討、{DOWN} 以下 見送り）。{plus}／{minus}"
    return {**base, "verdict": _verdict_for(score), "why": why}


def sensitivity(horizon: str, factors: dict[str, dict], flags: list[str] | tuple = (),
                step1_grade: str | None = None) -> dict:
    """Distance to the thresholds and the single factors whose one-step move would change the verdict."""
    current = horizon_score(horizon, factors, flags, step1_grade)
    out: dict = {"to_up": None, "to_down": None, "movers": []}
    if current["score"] is None or current["knockout"]:
        return out
    score = current["score"]
    out["to_up"] = round(UP - score, 3) if score < UP else None
    out["to_down"] = round(score - DOWN, 3) if score > DOWN else None
    for key, f in factors.items():
        if key not in WEIGHTS[horizon] or f.get("score") is None:
            continue
        for step, word in ((1, "1段良くなれば"), (-1, "1段悪くなれば")):
            moved = max(-1.0, min(1.0, f["score"] + step))
            if moved == f["score"]:
                continue
            other = horizon_score(horizon, {**factors, key: {**f, "score": moved}}, flags, step1_grade)
            if other["verdict"] != current["verdict"]:
                out["movers"].append({"key": key, "label": FACTOR_LABELS[key], "direction": word,
                                      "verdict": other["verdict"], "score": other["score"]})
    return out


def matrix_reference(s1: dict, s2: dict, s3: str | None) -> dict:
    """The framework's decision matrix on STEP 1 × STEP 2 × STEP 3 (shown as the long horizon's reference)."""
    if "C" in (s1["grade"], s2["grade"]):
        which = "・".join(name for name, s in (("STEP 1", s1), ("STEP 2", s2)) if s["grade"] == "C")
        return {"verdict": PASS, "note": "", "why": f"{which} が C のため見送り（判定マトリクス）"}
    row = "A" if s1["grade"] == "A" and s2["grade"] == "A" else "B"
    if not _known(s3):
        return {"verdict": lower(MATRIX[(row, "妥当")][0], WATCH), "note": "",
                "why": "STEP 3 が判定保留のため、株価の妥当性を確かめられるまではウォッチ以下"}
    verdict, note = MATRIX[(row, s3)]
    pending = "（判定保留を含む暫定）" if s1["pending"] or s2["pending"] else ""
    return {"verdict": verdict, "note": note,
            "why": f"STEP 1・2 が{'とも A' if row == 'A' else ' B を含む'}、STEP 3 が{s3}（判定マトリクス）{pending}"}
