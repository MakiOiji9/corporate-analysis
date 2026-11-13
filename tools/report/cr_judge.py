"""Company report judgements (企業分析フレームワーク.md STEP 1・2 総合、保有期間ごとの判定).

Pure functions on the conclusions of the nine analyses and a few market / price figures, so every rule is
unit-tested:
  step1()          STEP 1 A/B/C from 1-1〜1-4 (L230-239). 勝てる理由・SWOT が判定保留なら確定しない（暫定 B）.
  step2()          STEP 2 A/B/C by score: 良好 +1・普通 0・懸念 −1 の平均. A ≥ +0.5 with no mismatch; C ≤ −0.25,
                   two or more 懸念, or a serious red flag (red_flags()); otherwise B.
  cash_burn()      the cash-flow red flags read from the raw rows when the analysis could not judge its steps 1・2
                   (too few years): operating CF negative in most years, cumulative FCF negative.
  horizon_score()  短期・中期・長期: each factor scored −1..+1 in half steps (cr_factors) and averaged with the
                   horizon's WEIGHTS (+0.25 以上 投資検討, −0.25 以下 見送り, otherwise ウォッチ). A factor without
                   material is left out and the weights are re-normalised; a 判定保留 analysis counts as 0.
  knockouts()      only serious red flags pass a horizon. STEP 1 C is weighed through its analyses' scores and
                   named in the long horizon's reason, not a knockout.
  matrix_reference()  the framework's decision matrix (STEP 1 × 2 × 3), shown next to the long horizon;
  matrix_note()       says why the long horizon's verdict differs from it.
  sensitivity()    which single factor moving one step would change a horizon's verdict, and the distance to
                   the thresholds.
Every horizon carries its factor rows {key, label, weight, score, contribution, value, reason, source}; the
report shows the positive contributions as 良い点 and the negative ones as 悪い点.
"""
from __future__ import annotations

import math

PENDING = "判定保留"
CONSIDER, WATCH, PASS = "投資検討", "ウォッチ", "見送り"
LEVELS = (CONSIDER, WATCH, PASS)  # best first
UP, DOWN = 0.25, -0.25  # horizon score thresholds (symmetric)
BURN_MIN_YEARS = 2  # cash_burn() needs at least this many years to call it a pattern
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
FACTOR_LABELS = {"market": "地合い", "price": "株価のテクニカル（トレンド・勢い・位置）", "progress": "直近の決算の進捗",
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


def cash_burn(rows: list[dict], cf_steps: list[dict]) -> list[str]:
    """The red flags of the cash-flow steps 1・2 read from the raw rows, for the steps the analysis left
    unjudged (fewer years than it needs). A judged step decides by its own rating instead (red_flags())."""
    unjudged = [not (step or {}).get("rating") for step in (list(cf_steps[:2]) + [None, None])[:2]]
    out = []
    cfo = [r["cfo"] for r in rows if r.get("cfo") is not None]
    negative = sum(1 for v in cfo if v < 0)
    if unjudged[0] and len(cfo) >= BURN_MIN_YEARS and negative * 2 > len(cfo):
        out.append(f"営業CF がマイナスの年が多い（{negative}/{len(cfo)}年。年数が短く分析では判定できなかった）")
    fcf = [r["fcf"] for r in rows if r.get("fcf") is not None]
    if unjudged[1] and len(fcf) >= BURN_MIN_YEARS and sum(fcf) < 0:
        out.append(f"FCF の累計がマイナス（{len(fcf)}年。年数が短く分析では判定できなかった）")
    return out


def red_flags(cf_steps: list[dict], safety: str | None, safety_trend: str | None,
              burn: list[str] | tuple = ()) -> list[str]:
    """Serious red flags: they pass every horizon and make STEP 2 C. cf_steps are the cash-flow 手順1〜2;
    burn (cash_burn()) counts only when the balance sheet is not 良好 (otherwise it is a caution)."""
    flags = []
    labels = ("営業CF がマイナスの年が続く（キャッシュフローの「営業CF の安定性」が懸念）",
              "FCF の累計がマイナス（キャッシュフローの「FCF の創出力」が懸念）")
    for label, step in zip(labels, cf_steps[:2]):
        if (step or {}).get("rating") == "懸念":
            flags.append(label)
    if safety != "良好":
        flags.extend(burn)
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


STEP1_C_NOTE = "STEP 1 が C（勝てる理由がなし、または SWOT が No）。事業の強みは点数で減点済みだが、確かめてから判断する"


def knockouts(horizon: str, flags: list[str], step1_grade: str | None = None) -> list[str]:
    """Only serious red flags stop a horizon. step1_grade is kept for the callers; STEP 1 C is weighed instead."""
    return list(flags)


def _notes(horizon: str, step1_grade: str | None, cautions: list[str] | tuple) -> str:
    notes = list(cautions) + ([STEP1_C_NOTE] if horizon == "long" and step1_grade == "C" else [])
    return "。注意: " + "、".join(notes) if notes else ""


def horizon_score(horizon: str, factors: dict[str, dict], flags: list[str] | tuple = (),
                  step1_grade: str | None = None, cautions: list[str] | tuple = ()) -> dict:
    """The verdict of one horizon. factors: key -> {score (+1..−1 or None), value, reason, source, pending}.
    cautions are shown in the reason without stopping the horizon (e.g. cash burn with a strong balance sheet)."""
    score, rows = _weighted(WEIGHTS[horizon], factors)
    good = sorted((r for r in rows if (r["contribution"] or 0) > 0), key=lambda r: -r["contribution"])
    bad = sorted((r for r in rows if (r["contribution"] or 0) < 0), key=lambda r: r["contribution"])
    stops = knockouts(horizon, list(flags), step1_grade)
    base = {"score": score, "rows": rows, "good": good, "bad": bad, "knockout": stops, "provisional": None,
            "cautions": list(cautions), "unknown": [r["label"] for r in rows if r["score"] is None]}
    if stops:
        return {**base, "verdict": PASS, "why": f"足切り: {'、'.join(stops)}（点数にかかわらず見送り）"}
    if score is None:
        return {**base, "verdict": PENDING, "why": "判定に使える材料が無い"}
    plus = f"プラス: {'・'.join(r['label'] for r in good[:2])}" if good else "プラスの要素なし"
    minus = f"マイナス: {'・'.join(r['label'] for r in bad[:2])}" if bad else "マイナスの要素なし"
    near = nearest(score)
    why = (f"重み付けの点数 {score:+.2f}（{UP:+.2f} 以上 投資検討、{DOWN:+.2f} 以下 見送り。{near['text']}）。"
           f"{plus}／{minus}{_notes(horizon, step1_grade, cautions)}")
    return {**base, "verdict": _verdict_for(score), "why": why}


def nearest(score: float | None) -> dict | None:
    """The boundary the score is closest to crossing: {to (the verdict on the other side), gap (score change
    needed; + upward, − downward), text}. A 見送り or 投資検討 has one neighbour, a ウォッチ the nearer of two."""
    if score is None:
        return None
    if score <= DOWN:
        to, gap, rule = WATCH, DOWN - score, f"{DOWN:+.2f} を超えれば{WATCH}"  # must rise above DOWN
    elif score >= UP:
        to, gap, rule = WATCH, -(score - UP), f"{UP:+.2f} を下回れば{WATCH}"  # 投資検討 until it falls below UP
    else:
        up, down = UP - score, score - DOWN
        to, gap, rule = ((CONSIDER, up, f"{UP:+.2f} 以上で{CONSIDER}") if up <= down
                         else (PASS, -down, f"{DOWN:+.2f} 以下で{PASS}"))
    gap = round(gap, 3) + 0.0  # + 0.0 turns −0.0 into 0.0
    return {"to": to, "gap": gap, "text": f"{to}まであと {gap:+.2f}（{rule}）"}


def _next_word(score: float, step: int) -> float:
    """One step of a factor: a whole score moves a whole word; a half or fractional score moves to the next
    whole word in that direction (−0.5 up is 0, not +0.5)."""
    if float(score).is_integer():
        return max(-1.0, min(1.0, score + step))
    return float(math.ceil(score) if step > 0 else math.floor(score))


def sensitivity(horizon: str, factors: dict[str, dict], flags: list[str] | tuple = (),
                step1_grade: str | None = None) -> dict:
    """Distance to the thresholds and the single factors whose one-step move would change the verdict."""
    current = horizon_score(horizon, factors, flags, step1_grade)
    out: dict = {"to_up": None, "to_down": None, "nearest": None, "movers": []}
    if current["score"] is None or current["knockout"]:
        return out
    score = current["score"]
    out["nearest"] = nearest(score)
    out["to_up"] = round(UP - score, 3) if score < UP else None
    out["to_down"] = round(score - DOWN, 3) if score > DOWN else None
    for key, f in factors.items():
        if key not in WEIGHTS[horizon] or f.get("score") is None:
            continue
        for step, word in ((1, "1段良くなれば"), (-1, "1段悪くなれば")):
            moved = _next_word(f["score"], step)
            if moved == f["score"]:
                continue
            other = horizon_score(horizon, {**factors, key: {**f, "score": moved}}, flags, step1_grade)
            if other["verdict"] != current["verdict"]:
                out["movers"].append({"key": key, "label": FACTOR_LABELS[key], "direction": word,
                                      "verdict": other["verdict"], "score": other["score"], "to": moved})
    return out


LADDERS = {  # the factor's words from −1 to +1 (a one-step move reads as a concrete condition)
    **{k: ("懸念", "普通", "良好") for k in ("growth", "profitability", "cash_flow", "safety")},
    "five_forces": ("低", "中", "高"), "three_c": ("なし", "あいまい", "明確"), "moat": ("なし", "狭い", "広い"),
    "swot": ("No", "条件付き", "Yes"), "market": ("警戒", "注意", "平常"), "valuation": ("割高", "妥当", "割安")}
NUMERIC_MOVES = {
    ("price", 1): "株価のテクニカルが上向き（上昇トレンドへの転換・売られすぎからの反発）に変われば",
    ("price", -1): "株価のテクニカルが下向き（下降トレンド・買われすぎ）に変われば",
    ("progress", 1): "次の決算で営業利益の進捗が前年同期の110%以上になれば",
    ("progress", -1): "次の決算で営業利益の進捗が前年同期の90%を下回れば"}


def mover_text(mover: dict, rows: list[dict]) -> str:
    """'成長性が「良好」になれば（今は「普通」）投資検討': the one-step move of sensitivity() as a condition."""
    step = 1 if mover["direction"] == "1段良くなれば" else -1
    text = NUMERIC_MOVES.get((mover["key"], step))
    ladder = LADDERS.get(mover["key"])
    row = next((r for r in rows if r["key"] == mover["key"]), None)
    score, to = (row or {}).get("score"), mover.get("to")
    if text is None and ladder and score is not None and to is not None and not float(score).is_integer() \
            and not (mover["key"] == "valuation" and abs(to) == 1):
        text = f"{mover['label']}が「{ladder[int(to) + 1]}」になれば（今は {score:+.1f} 点）"
    if text is None and ladder and row and row["score"] is not None:
        now = max(-1, min(1, round(row["score"])))
        if -1 <= now + step <= 1:
            text = f"{mover['label']}が「{ladder[now + step + 1]}」になれば（今は「{ladder[now + 1]}」）"
        else:  # a fractional score (valuation's average) already rounds to the end word
            text = f"{mover['label']}が「{ladder[now + 1]}」で揃えば"
    return f"{text or mover['label'] + 'が' + mover['direction']}{mover['verdict']}"


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


def matrix_note(matrix: dict, long: dict) -> str:
    """Why the long horizon's verdict differs from the matrix: the matrix reads three grades, the long horizon
    weighs every factor (the report's verdict is the long horizon's)."""
    if (not matrix.get("verdict") or matrix["verdict"] == long.get("verdict") or long.get("score") is None
            or long.get("knockout")):  # a knockout already says why the long horizon is 見送り
        return ""
    return (f"判定マトリクスは{matrix['verdict']}だが、長期の判定は{long['verdict']}（重み付けの点数 "
            f"{long['score']:+.2f}）。マトリクスは STEP 1・2・3 の3つの総合だけを見るが、長期の判定は各分析の"
            "良い点・悪い点を重みで足し合わせるため、片方の総合が低くても他の強みで補われることがある。"
            "レポートの判定は長期の判定を使う")
