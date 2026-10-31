"""{date}_moat.md: skeleton, parse, checks and the conclusion (モート 広い/狭い/なし/判定保留).

企業分析フレームワーク.md 1-3, decided here (not by the writer):
  数字の裏付け (手順2), from the script's margin candidate and the writer's share trend:
    不明: the margin comparison could not be made
    なし: margin at or below the peer average, or share 低下
    強い: margin above the peer average for 7+ years and share 拡大/安定
    弱い: otherwise (fewer years above, or share 横ばい〜微減/不明)
  裏付けなし turns every 該当 of 手順1 into 該当なし (the framework's correction rule).
  モートの強さ (手順4), first match wins:
    なし: no 該当 moat
    なし: 裏付け 不明 — a moat without numbers to back it is not 該当 (1-3「裏付けの無いモートは該当しない」);
          decided on the conservative side and recorded in conservative
    なし: 裏付け なし
    広い: 2+ moats, 裏付け 強い, no factor that may break a moat within 5 years
    狭い: otherwise (1 moat with backing / 2+ with weak backing / a factor within 5 years -> the less favourable)
"""
from __future__ import annotations

from string import Template

import mdparse as M
from ff_doc import (CHANGED_FROM_PREVIOUS, CONFIDENCE, LOW_CONFIDENCE, TIE_BREAK, _check_words, candidate_cell,
                    replace_section)
from mt_metrics import cost_table_rows, margin_table_rows
from validate import check_fill, check_structure, check_tables

MOAT_TYPES = ("ブランド", "スイッチングコスト", "ネットワーク効果", "コスト優位", "規制・特許・許認可")
MOAT_RATINGS = ("該当", "該当なし", "不明")
HIT = "該当"
SHARE_TRENDS = ("拡大", "安定", "横ばい〜微減", "低下", "不明")
SHARE_STRONG = ("拡大", "安定")
TIMINGS = ("5年以内", "5〜10年", "10年超・不明")
NEAR = "5年以内"
NO_RISK = "なし"
PENDING = "判定保留"
MOAT_COLUMNS = 5
RISK_COLUMNS = 5


# ---------- skeleton ----------

def _previous(previous: tuple[str, dict] | None) -> tuple[str, str]:
    """(前回の判定 of the moat types, 前回のシェアの推移)."""
    if not previous:
        return "—（初回）", "—（初回）"
    date, r = previous
    moats = "、".join(f"{m.get('type')} {m.get('rating')}" for m in r.get("moats", [])) or "—"
    share = (r.get("share") or {}).get("trend") or "—"
    return f"{moats}（{date}）", f"{share}（{date}）"


def margin_note(cands: dict) -> str:
    sources = "、".join(cands["sources"]) or "—"
    return (f"注: 自社は {sources}、競合は competitors.md「売上高・営業利益」の実績（会社予想は除く）からスクリプトが計算。"
            f"同業平均は比較した競合の単純平均（対象企業を除く。決算期が6か月以内の年度を同じ年として扱う）。"
            f"スクリプトの判定候補（営業利益率の側）: {candidate_cell(cands['margin'])}")


def render_skeleton(template: str, values: dict, cands: dict, previous: tuple[str, dict] | None) -> str:
    prev_moats, prev_share = _previous(previous)
    filled = dict(values, margin_rows=margin_table_rows(cands["rows"]), margin_note=margin_note(cands),
                  cost_rows=cost_table_rows(cands["costs"]), prev_moats=prev_moats, prev_share=prev_share)
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    return {r.get("項目", ""): r.get("内容", "") for r in M.table_dicts(text)}


def _rows(table: list[list[str]], width: int) -> list[list[str]]:
    return [row + [""] * (width - len(row)) for row in table[1:]]


def parse(text: str) -> dict:
    intro = _kv(M.section(text, "1."))
    moat_tables = M.tables(M.section(text, "2."))
    risk_tables = M.tables(M.section(text, "4."))
    share = _kv(M.section(text, "3.3", level=3))
    handoff = _kv(M.section(text, "6."))
    moats = [{"type": r[0], "rating": r[1].strip(), "basis": r[2], "source": r[3], "confidence": r[4].strip()}
             for r in (_rows(moat_tables[0], MOAT_COLUMNS) if moat_tables else [])]
    risks = [{"factor": r[0], "timing": r[1].strip(), "moat": r[2], "basis": r[3], "source": r[4]}
             for r in (_rows(risk_tables[0], RISK_COLUMNS) if risk_tables else [])]
    durability = (next((r[1] for r in risk_tables[1][1:] if len(r) > 1 and r[0] == "持続の見込み"), "")
                  if len(risk_tables) > 1 else "")
    return {
        "strength": intro.get("確かめる強み", ""), "moats": moats,
        "share": {"trend": share.get("シェアの推移", "").strip(), "reason": share.get("理由", ""),
                  "seen": share.get("見たもの", ""), "source": share.get("情報源", ""),
                  "confidence": share.get("根拠の確度", "").strip()},
        "risks": risks, "durability": durability,
        "strengths": handoff.get("SWOT の強み（S）候補", ""), "threats": handoff.get("SWOT の脅威（T）候補", ""),
        "step2_checks": handoff.get("STEP 2 で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "7.")), "gaps": M.bullets(M.section(text, "8.")),
    }


# ---------- checks ----------

def _confidence_ok(confidence: str, may_be_blank: bool) -> bool:
    return confidence in CONFIDENCE or (may_be_blank and M.is_blank(confidence))


def _check_moats(moats: list[dict]) -> list[str]:
    names = [m["type"] for m in moats]
    if names != list(MOAT_TYPES):
        return [f"2. モートの種類の行は {' / '.join(MOAT_TYPES)} をこの順・この名前で5行（今: {'、'.join(names) or 'なし'}）"]
    issues = []
    for m in moats:
        where = f"2. {m['type']}"
        if m["rating"] not in MOAT_RATINGS:
            issues.append(f"{where}: 判定は {'/'.join(MOAT_RATINGS)} の1語: 「{m['rating']}」")
            continue
        if M.is_blank(m["basis"]):
            issues.append(f"{where}: 根拠が空")
        hit = m["rating"] == HIT
        if hit and M.is_blank(m["source"]):
            issues.append(f"{where}: 「該当」なのに情報源が空（根拠が書けないなら「不明」にする）")
        if not _confidence_ok(m["confidence"], may_be_blank=not hit):
            issues.append(f"{where}: 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{m['confidence']}」")
    return issues


def _check_share(share: dict) -> list[str]:
    if share["trend"] not in SHARE_TRENDS:
        return [f"3.3 シェアの推移は {'/'.join(SHARE_TRENDS)} の1語: 「{share['trend']}」"]
    issues = []
    if M.is_blank(share["reason"]):
        issues.append("3.3 理由が空")
    if M.is_blank(share["seen"]):
        issues.append("3.3 見たものが空")
    if not _confidence_ok(share["confidence"], may_be_blank=share["trend"] == "不明"):
        issues.append(f"3.3 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{share['confidence']}」")
    return issues


def _check_risks(risks: list[dict]) -> list[str]:
    if not risks:
        return ["4. 崩しうる要因の表に行が無い（無ければ1行目を「なし」にする）"]
    if risks[0]["factor"].strip().startswith(NO_RISK):
        issues = [] if len(risks) == 1 else ["4. 「なし」の行は1行だけにする（要因があるなら「なし」の行を消す）"]
        return issues + (["4. なし: 根拠（確認した資料）が空"] if M.is_blank(risks[0]["basis"]) else [])
    issues = []
    for r in risks:
        where = f"4. {r['factor']}"
        if r["timing"] not in TIMINGS:
            issues.append(f"{where}: 時期は {'/'.join(TIMINGS)} の1語: 「{r['timing']}」")
        if M.is_blank(r["basis"]):
            issues.append(f"{where}: 根拠が空")
    return issues


def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("1. 確かめる強み", p["strength"]), ("4. 持続の見込み", p["durability"]),
            ("6. 強み候補", p["strengths"]), ("6. 脅威候補", p["threats"]),
            ("6. STEP 2 で確かめること", p["step2_checks"]), ("6. 評価が変わる条件", p["triggers"])]


def validate(text: str, template: str) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_moats(p["moats"]) + _check_share(p["share"]) + _check_risks(p["risks"])
    if not p["changes"]:
        issues.append("7. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("8. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


def check_reference(parsed: dict, previous: tuple[str, dict] | None) -> list[str]:
    """A judgement that differs from the previous result needs「前回から変更:」."""
    if not previous:
        return []
    _, r = previous
    issues = []
    before = {m.get("type"): m.get("rating") for m in r.get("moats", [])}
    for m in parsed["moats"]:
        prev = before.get(m["type"])
        if prev and m["rating"] != prev and CHANGED_FROM_PREVIOUS not in m["basis"]:
            issues.append(f"2. {m['type']}: 前回「{prev}」から変えたので、根拠に「{CHANGED_FROM_PREVIOUS}:」を書く")
    prev_share = (r.get("share") or {}).get("trend")
    share = parsed["share"]
    if prev_share and share["trend"] != prev_share and CHANGED_FROM_PREVIOUS not in share["reason"]:
        issues.append(f"3.3 シェアの推移: 前回「{prev_share}」から変えたので、理由に「{CHANGED_FROM_PREVIOUS}:」を書く")
    return issues


# ---------- conclusion ----------

def backing(margin: dict, share_trend: str) -> tuple[str, str]:
    """(強い/弱い/なし/不明, why) from the margin candidate and the share trend."""
    rating = margin.get("rating")
    years = f"営業利益率が同業平均を {margin.get('years_above', 0)} 年連続で上回る"
    if rating is None:
        return "不明", "自社と競合の営業利益率を比べられない"
    if rating == "なし":
        return "なし", "営業利益率が直近で同業平均以下"
    if share_trend == "低下":
        return "なし", f"{years}が、シェアが低下"
    if rating == "強い" and share_trend in SHARE_STRONG:
        return "強い", f"{years}（7年以上）、シェアが{share_trend}"
    lacking = [] if rating == "強い" else [f"{years}（7年未満）"]
    if share_trend not in SHARE_STRONG:
        lacking.append(f"シェアの推移が「{share_trend}」")
    return "弱い", "、".join(lacking)


def judge(parsed: dict, margin: dict) -> dict:
    support, support_why = backing(margin, parsed["share"]["trend"])
    claimed = [m["type"] for m in parsed["moats"] if m["rating"] == HIT]
    corrected = support == "なし" and bool(claimed)
    effective = [] if support == "なし" else claimed
    near = [r["factor"] for r in parsed["risks"] if r["timing"] == NEAR]
    conservative: list[str] = []
    if not claimed:
        verdict, why = "なし", "該当するモートが無い"
    elif support == "不明":
        effective = []
        verdict = "なし"
        why = (f"数字の裏付けを確かめる材料が無い（{support_why}）。裏付けの無いモートは該当しないため、"
               f"{'・'.join(claimed)} を該当なしとして判定（材料不足のため保守的に判定）")
        conservative.append("営業利益率の同業比較ができず、裏付け 不明 → 該当なし とみなした")
    elif support == "なし":
        verdict, why = "なし", f"数字の裏付けなし（{support_why}）のため、該当としたモートを「該当なし」に修正"
    elif len(effective) >= 2 and support == "強い" and not near:
        verdict, why = "広い", f"モートが{len(effective)}つ該当、裏付けが強い、5年以内に崩しうる要因なし"
    else:
        lacking = []
        if len(effective) < 2:
            lacking.append("該当するモートが1つ")
        if support != "強い":
            lacking.append("裏付けが弱い")
        if near:
            lacking.append("5年以内に崩しうる要因あり")
        verdict, why = "狭い", "、".join(lacking)
    return {"verdict": verdict, "why": why, "backing": support, "backing_why": support_why,
            "claimed": claimed, "effective": effective, "corrected": corrected, "near_risks": near,
            "conservative": conservative}


def conclusion_section(judged: dict, margin: dict, share_trend: str) -> str:
    if judged["corrected"]:
        moats = f"なし（{'、'.join(judged['claimed'])} を裏付けなしのため「該当なし」に修正）"
    else:
        moats = "、".join(judged["effective"]) or "なし"
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 該当するモート | {moats} |",
        f"| 数字の裏付け | {judged['backing']}: {judged['backing_why']}（営業利益率の候補 {margin.get('rating') or '—'}、"
        f"シェアの推移 {share_trend}） |",
        f"| 5年以内に崩しうる要因 | {'、'.join(judged['near_risks']) or 'なし'} |",
        f"| モートの強さ | **{judged['verdict']}**: {judged['why']} |"])


def apply_conclusion(text: str, judged: dict, margin: dict, share_trend: str) -> str:
    return replace_section(text, "5.", conclusion_section(judged, margin, share_trend))


def flags(parsed: dict) -> dict:
    """Items the completion report lists: tie breaks, reference-only evidence and 不明 judgements."""
    parts = [(m["type"], m["basis"], m["confidence"], m["rating"]) for m in parsed["moats"]]
    share = parsed["share"]
    parts.append(("シェアの推移", share["reason"], share["confidence"], share["trend"]))
    return {"tie_breaks": [name for name, reason, _, _ in parts if TIE_BREAK in reason],
            "low_confidence": [name for name, _, conf, _ in parts if conf == LOW_CONFIDENCE],
            "unknown": [name for name, _, _, rating in parts if rating == "不明"]}
