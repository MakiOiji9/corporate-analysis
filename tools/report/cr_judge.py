"""Company report judgements (企業分析フレームワーク.md STEP 1・2 総合、総合判断、保有期間ごとの判定).

Pure functions on the conclusions of the nine analyses, so every rule is unit-tested:
  step1()   STEP 1 A/B/C from 1-1〜1-4 (L230-239). 勝てる理由 判定保留 keeps STEP 1 open (provisional B).
  step2()   STEP 2 A/B/C from 2-1〜2-4 and the consistency check with STEP 1 (L410-428).
  long_term()   3年以上: the decision matrix (L583-589) on STEP 1 × STEP 2 × STEP 3.
  mid_term()    6ヶ月〜1年: the long-term verdict, one level down when the latest quarter lags, the market's
                mid-term outlook is 警戒, or an unreliable plan meets an expensive price.
  short_term()  〜3ヶ月: the long-term verdict, the market's short-term outlook and the price's position.
Short and mid never rank above long (行動指針6: when in doubt take the lower side). A verdict that rests on a
判定保留 is returned as 判定保留 with the provisional verdict next to it.

Every judgement carries rows {condition, value, source, ok} (ok: True / False / None = 不明) that the
report shows as its 根拠 table.
"""
from __future__ import annotations

PENDING = "判定保留"
CONSIDER, WATCH, PASS = "投資検討", "ウォッチ", "見送り"
LEVELS = (CONSIDER, WATCH, PASS)  # best first
MATRIX = {  # (row, STEP 3) -> verdict, with the framework's note
    ("A", "割安"): (CONSIDER, ""), ("A", "妥当"): (CONSIDER, "分割購入など"), ("A", "割高"): (WATCH, "下落を待つ"),
    ("B", "割安"): (CONSIDER, "割安の理由を精査"), ("B", "妥当"): (WATCH, ""), ("B", "割高"): (PASS, ""),
}
TOP_ZONE = 67  # 52週レンジでの位置（%）がこれ以上なら上位1/3（フレームワーク共通ルールの 67〜100%）
MA_GAP_LIMIT = 15.0  # 26週移動平均からの上方乖離（%）の上限
PROGRESS_RATIO = 0.9  # 進捗率が前年同期（無ければ標準ペース）の 90% 未満なら遅れ
ATTRACTIVE = ("高", "中")


def _row(condition: str, value: object, source: str, ok: bool | None) -> dict:
    return {"condition": condition, "value": "—" if value in (None, "") else str(value), "source": source, "ok": ok}


def _known(value: str | None) -> bool:
    return bool(value) and value != PENDING


def lower(a: str, b: str) -> str:
    """The more cautious of two verdicts."""
    return LEVELS[max(LEVELS.index(a), LEVELS.index(b))]


def step_down(verdict: str) -> str:
    return LEVELS[min(LEVELS.index(verdict) + 1, len(LEVELS) - 1)]


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


def step2(items: dict[str, str | None], mismatch: list[str]) -> dict:
    """STEP 2 総合. items: {収益性, 成長性, 安全性, キャッシュフロー: 良好/普通/懸念/判定保留/None}."""
    rows = [_row(f"{name}", value, f"2-{i} {name}分析", value == "良好" if _known(value) else None)
            for i, (name, value) in enumerate(items.items(), start=1)]
    rows.append(_row("STEP 1 との整合性", "、".join(mismatch) or "食い違いなし", "整合性チェック", not mismatch))
    values = list(items.values())
    concerns = [name for name, v in items.items() if v == "懸念"]
    if items.get("キャッシュフロー") == "懸念" or len(concerns) >= 2:
        why = "キャッシュフローが懸念" if items.get("キャッシュフロー") == "懸念" else f"懸念が{len(concerns)}つ"
        return {"grade": "C", "pending": False, "why": f"{why}（C の条件）", "rows": rows}
    missing = [name for name, v in items.items() if not _known(v)]
    good, normal = values.count("良好"), values.count("普通")
    if not missing and not mismatch and (good == 4 or (good == 3 and normal == 1)):
        return {"grade": "A", "pending": False, "why": f"良好 {good}・普通 {normal} で整合性に食い違いなし", "rows": rows}
    why = f"良好 {good}・普通 {normal}・懸念 {len(concerns)}"
    if mismatch:
        why += "、整合性の食い違いあり"
    if missing:
        why += f"（{'・'.join(missing)}が判定保留・未実施のため確定しない）"
    return {"grade": "B", "pending": bool(missing), "why": why, "rows": rows}


# ---------------------------------------------------------------- horizons

def _horizon(verdict: str, pending: bool, why: str, rows: list[dict], note: str = "") -> dict:
    return {"verdict": PENDING if pending else verdict, "provisional": verdict if pending else None,
            "why": why, "note": note, "rows": rows}


def long_term(s1: dict, s2: dict, s3: str | None) -> dict:
    """3年以上: the decision matrix."""
    rows = [_row("STEP 1（事業・競争環境）", s1["grade"] + ("（暫定）" if s1["pending"] else ""), "STEP 1 総合",
                 None if s1["pending"] else s1["grade"] == "A"),
            _row("STEP 2（財務）", s2["grade"] + ("（暫定）" if s2["pending"] else ""), "STEP 2 総合",
                 None if s2["pending"] else s2["grade"] == "A"),
            _row("STEP 3（株価の妥当性）", s3, "STEP 3 バリュエーション",
                 None if not _known(s3) else s3 != "割高")]
    if "C" in (s1["grade"], s2["grade"]):
        which = "・".join(name for name, s in (("STEP 1", s1), ("STEP 2", s2)) if s["grade"] == "C")
        return _horizon(PASS, False, f"{which} が C のため、株価にかかわらず見送り（判定マトリクス）", rows)
    row = "A" if s1["grade"] == "A" and s2["grade"] == "A" else "B"
    pending = s1["pending"] or s2["pending"] or not _known(s3)
    if _known(s3):
        verdict, note = MATRIX[(row, s3)]
        why = f"STEP 1・2 が{'とも A' if row == 'A' else 'B を含む'}、STEP 3 が{s3}（判定マトリクス）"
    else:
        verdict, note = lower(MATRIX[(row, "妥当")][0], WATCH), ""
        why = "STEP 3 が判定保留のため、株価の妥当性を確かめられるまではウォッチ以下"
    if s1["pending"] or s2["pending"]:
        why += "。STEP 1・2 に判定保留があり確定しない"
    return _horizon(verdict, pending, why, rows, note)


def _base(long: dict) -> str:
    return long["provisional"] or long["verdict"]


def _progress_row(progress: dict | None) -> dict:
    item = ((progress or {}).get("items") or {}).get("operating_income") or {}
    rate, prior, quarter = item.get("progress"), item.get("prior_progress"), (progress or {}).get("quarter")
    if rate is None or not quarter:
        return _row("直近四半期の営業利益の進捗が遅れていない", "不明（四半期の進捗が無い）", "成長性分析 progress", None)
    pace, basis = (prior, "前年同期") if prior else (quarter / 4 * 100, "標準ペース")
    value = f"第{quarter}四半期 {rate:.1f}%（{basis} {pace:.1f}%）"
    return _row("直近四半期の営業利益の進捗が遅れていない", value, "成長性分析 progress（決算短信）",
                rate >= pace * PROGRESS_RATIO)


def _outlook_row(period: str, judgment: str | None) -> dict:
    return _row(f"地合いの{period}の判断が警戒でない", judgment, "地合い outlook.md 4章",
                judgment != "警戒" if judgment else None)


def mid_term(long: dict, progress: dict | None, outlook_mid: str | None, plan: str | None, s3: str | None) -> dict:
    """6ヶ月〜1年: one level below the long-term verdict when any check fails or is unknown."""
    plan_ok = True if plan == "信頼できる" else (None if not _known(s3) else s3 != "割高")
    rows = [_row("長期の判定", _base(long), "長期（判定マトリクス）", _base(long) == CONSIDER),
            _progress_row(progress), _outlook_row("中期", outlook_mid),
            _row("会社計画が信頼でき、または株価が割高でない", f"計画 {plan or '—'}、STEP 3 {s3 or '—'}",
                 "成長性分析 手順3・STEP 3", plan_ok)]
    base = _base(long)
    if base == PASS:
        return _horizon(PASS, long["provisional"] is not None, "長期が見送りのため中期も見送り", rows)
    hits = [r["condition"] for r in rows[1:] if r["ok"] is not True]
    verdict = step_down(base) if hits else base
    why = (f"長期の{base}から1段下げた（満たさない・不明: {'、'.join(hits)}）" if hits
           else f"長期の{base}のまま（中期の確認項目をすべて満たす）")
    return _horizon(verdict, long["provisional"] is not None, why, rows)


def short_term(long: dict, outlook_short: str | None, position: float | None, ma_gap: float | None) -> dict:
    """〜3ヶ月: the market's short-term outlook and where the price sits; never above the long-term verdict."""
    pos = int(position + 0.5) if position is not None else None  # whole percent, half up (as the valuation zones)
    rows = [_row("長期の判定", _base(long), "長期（判定マトリクス）", _base(long) == CONSIDER),
            _outlook_row("短期", outlook_short),
            _row(f"株価が52週レンジの上位1/3（{TOP_ZONE}%以上）にない", f"{pos}%" if pos is not None else None,
                 "株価の過去レンジ", pos < TOP_ZONE if pos is not None else None),
            _row(f"株価が26週移動平均を {MA_GAP_LIMIT:.0f}% より大きく上回っていない",
                 f"{ma_gap:+.1f}%" if ma_gap is not None else None, "株価の過去レンジ",
                 ma_gap <= MA_GAP_LIMIT if ma_gap is not None else None)]
    note = "短期は値動きの影響が大きく、根拠は中期・長期より弱い"
    base, pending = _base(long), long["provisional"] is not None
    if base == PASS:
        return _horizon(PASS, pending, "長期が見送りのため短期も見送り", rows, note)
    if outlook_short == "警戒" and pos is not None and pos >= TOP_ZONE:
        return _horizon(PASS, pending, "地合いの短期が警戒で、株価が52週レンジの上位1/3にある", rows, note)
    if base == CONSIDER and all(r["ok"] is True for r in rows[1:]):
        return _horizon(CONSIDER, pending, "長期が投資検討で、地合い・株価の位置・移動平均との乖離に問題がない", rows, note)
    hits = [r["condition"] for r in rows[1:] if r["ok"] is not True]
    why = f"長期が{base}" + (f"、満たさない・不明: {'、'.join(hits)}" if hits else "") + "のためウォッチ"
    return _horizon(lower(base, WATCH), pending, why, rows, note)
