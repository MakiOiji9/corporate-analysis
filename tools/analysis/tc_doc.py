"""{date}_three-c.md: skeleton, parse, checks and the conclusion (勝てる理由 明確/あいまい/なし).

Conclusion follows 企業分析フレームワーク.md 1-2 手順4, decided here (not by the writer):
  明確: 最重要KBF で自社が ○ かつ比較した競合が全員 △/×（○・？ が無い）、かつ 競合との比較が 優位
  なし: 勝てる理由が「なし」、または 競合との比較が 劣位
  あいまい: それ以外（競合との比較が 不明 の場合も 明確 にしない）
"""
from __future__ import annotations

import re
from string import Template

import mdparse as M
from ff_doc import (CHANGED_FROM_PREVIOUS, CONFIDENCE, DIFFERS_FROM_CANDIDATE, LOW_CONFIDENCE, TIE_BREAK,
                    _check_words, candidate_cell, replace_section)
from tc_metrics import COMPETITOR_ORDER, GROWTH_ORDER, MAX_PEERS, table_rows
from validate import check_fill, check_structure, check_tables

GROWTH_RATINGS = ("高", "中", "低", "不明")
COMPETITOR_RATINGS = ("優位", "同等", "劣位", "不明")
MARKS = ("○", "△", "×", "？")
UNUSED = "—"
PEER_LABELS = ("競合A", "競合B", "競合C")
KBF_SPLIT = re.compile(r"[、,，]")
KBF_COUNT = (2, 5)
KBF_COLUMNS = 2 + MAX_PEERS + 1  # KBF, 自社, 競合A-C, 根拠
NO_REASON = "なし"


# ---------- skeleton ----------

def previous_cell(previous: tuple[str, dict] | None, key: str) -> str:
    if not previous:
        return "—（初回）"
    date, result = previous
    rating = (result.get(key) or {}).get("rating", "")
    return f"{rating}（{date}）" if rating else f"—（{date} の結果に無い）"


def peer_legend(names: list[str]) -> str:
    return "\n".join(f"- {label}: {names[i]}" if i < len(names)
                     else f"- {label}: {UNUSED}（比較対象なし。列は {UNUSED} にする）"
                     for i, label in enumerate(PEER_LABELS))


def peer_note(competitor: dict) -> str:
    return ("注: 数値は raw の売上高・営業利益と data/ の CSV からスクリプトが計算（各社の最新実績年度。会社予想は除く）。"
            f"シェアは competitors.md「市場シェア」の数値（{UNUSED} は数値なし）。判定候補の根拠: {competitor['basis']}")


def render_skeleton(template: str, values: dict, cands: dict, previous: tuple[str, dict] | None) -> str:
    rows = cands["rows"]
    filled = dict(values, peer_rows=table_rows(rows), peer_note=peer_note(cands["competitor"]),
                  peer_legend=peer_legend([r["name"] for r in rows if not r["self"]]),
                  cand_growth=candidate_cell(cands["growth"]), cand_competitor=candidate_cell(cands["competitor"]),
                  prev_growth=previous_cell(previous, "growth"), prev_competitor=previous_cell(previous, "competitor"))
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    return {r.get("項目", ""): r.get("内容", "") for r in M.table_dicts(text)}


def split_kbf(cell: str) -> list[str]:
    return [k.strip() for k in KBF_SPLIT.split(cell) if not M.is_blank(k)]


def _norm(name: str) -> str:
    return re.sub(r"[\s*]", "", name)


def _company_section(text: str) -> tuple[list[dict], str]:
    """(KBF rows, 結論) of '## 3.': the first table is the KBF comparison, the second the 結論 row."""
    found = M.tables(M.section(text, "3."))
    rows = []
    for row in found[0][1:] if found else []:
        cells = row + [""] * (KBF_COLUMNS - len(row))
        rows.append({"kbf": cells[0], "self": cells[1], "peers": cells[2:2 + MAX_PEERS], "basis": cells[-1]})
    conclusion = next((r[1] for r in found[1][1:] if len(r) > 1 and r[0] == "結論"), "") if len(found) > 1 else ""
    return rows, conclusion


def parse(text: str) -> dict:
    customer = _kv(M.section(text, "1."))
    comp = _kv(M.section(text, "2.2", level=3))
    win = _kv(M.section(text, "4."))
    handoff = _kv(M.section(text, "6."))
    kbf_rows, company_conclusion = _company_section(text)
    return {
        "customer": {"segment": customer.get("主力セグメント", ""), "customers": customer.get("顧客層", ""),
                     "kbf": split_kbf(customer.get("KBF（重要度順）", "")), "kbf_basis": customer.get("KBFの根拠", ""),
                     "seen": customer.get("市場規模と成長率", ""), "source": customer.get("情報源", ""),
                     "confidence": customer.get("根拠の確度", "").strip(), "conclusion": customer.get("結論", "")},
        "growth": {"rating": customer.get("成長性", "").strip(), "reason": customer.get("理由", "")},
        "competitor": {"rating": comp.get("判定", "").strip(), "reason": comp.get("理由", ""),
                       "seen": comp.get("見たもの", ""), "source": comp.get("情報源", ""),
                       "confidence": comp.get("根拠の確度", "").strip(), "conclusion": comp.get("結論", "")},
        "kbf_rows": kbf_rows, "company_conclusion": company_conclusion,
        "win_reason": win.get("勝てる理由", ""), "triggers": win.get("評価が変わる条件", ""),
        "strengths": handoff.get("SWOT の強み（S）候補", ""), "weaknesses": handoff.get("SWOT の弱み（W）候補", ""),
        "moat_checks": handoff.get("モート分析で確かめること", ""),
        "changes": M.bullets(M.section(text, "7.")), "gaps": M.bullets(M.section(text, "8.")),
    }


# ---------- checks ----------

def _check_rating(where: str, rating: str, allowed: tuple[str, ...], reason: str, confidence: str) -> list[str]:
    if rating not in allowed:
        return [f"{where}: 評価は {'/'.join(allowed)} の1語: 「{rating}」"]
    issues = []
    if M.is_blank(reason):
        issues.append(f"{where}: 理由が空")
    if confidence not in CONFIDENCE and not (rating == "不明" and M.is_blank(confidence)):
        issues.append(f"{where}: 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{confidence}」")
    return issues


def _check_kbf_row(row: dict, peer_count: int) -> list[str]:
    where, issues = f"3. {row['kbf']}", []
    if row["self"] not in MARKS:
        issues.append(f"{where}: 自社の列は {'/'.join(MARKS)} の1字: 「{row['self']}」")
    for i, mark in enumerate(row["peers"]):
        if i < peer_count and mark not in MARKS:
            issues.append(f"{where}: {PEER_LABELS[i]} の列は {'/'.join(MARKS)} の1字: 「{mark}」")
        if i >= peer_count and mark != UNUSED:
            issues.append(f"{where}: {PEER_LABELS[i]} は比較対象が無いので {UNUSED}: 「{mark}」")
    if M.is_blank(row["basis"]):
        issues.append(f"{where}: 根拠が空")
    return issues


def _check_kbf(parsed: dict, peer_count: int) -> list[str]:
    kbf, rows = parsed["customer"]["kbf"], parsed["kbf_rows"]
    low, high = KBF_COUNT
    if not low <= len(kbf) <= high:
        return [f"1. KBF は「、」区切りで{low}〜{high}個: {len(kbf)}個"]
    issues = []
    if [_norm(r["kbf"]) for r in rows] != [_norm(k) for k in kbf]:
        issues.append(f"3. KBF 比較表の行は1章の KBF と同じ名前・同じ順番にする（1章: {'、'.join(kbf)} / "
                      f"3章: {'、'.join(r['kbf'] for r in rows) or 'なし'}）")
    return issues + [issue for row in rows for issue in _check_kbf_row(row, peer_count)]


def _required_cells(p: dict) -> list[tuple[str, str]]:
    c = p["customer"]
    return [("1. 主力セグメント", c["segment"]), ("1. 顧客層", c["customers"]), ("1. KBFの根拠", c["kbf_basis"]),
            ("1. 市場規模と成長率", c["seen"]), ("1. 結論", c["conclusion"]),
            ("2.2 見たもの", p["competitor"]["seen"]), ("2.2 結論", p["competitor"]["conclusion"]),
            ("3. 結論", p["company_conclusion"]), ("4. 勝てる理由", p["win_reason"]),
            ("4. 評価が変わる条件", p["triggers"]), ("6. 強み候補", p["strengths"]),
            ("6. 弱み候補", p["weaknesses"]), ("6. モート分析で確かめること", p["moat_checks"])]


def validate(text: str, template: str, peer_count: int) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_rating("1. 成長性", p["growth"]["rating"], GROWTH_RATINGS, p["growth"]["reason"],
                            p["customer"]["confidence"])
    issues += _check_rating("2.2 判定", p["competitor"]["rating"], COMPETITOR_RATINGS, p["competitor"]["reason"],
                            p["competitor"]["confidence"])
    issues += _check_kbf(p, peer_count)
    if not p["changes"]:
        issues.append("7. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("8. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


def _rating_in(cell: str, allowed: tuple[str, ...]) -> str:
    return next((r for r in allowed if cell.strip().startswith(r)), "")


def check_reference(parsed: dict, cands: dict, previous: tuple[str, dict] | None) -> list[str]:
    """Candidate / previous rules, with the candidates and previous result recomputed by the caller."""
    issues = []
    for key, where, order, allowed in (("growth", "1. 成長性", GROWTH_ORDER, GROWTH_RATINGS),
                                       ("competitor", "2.2 判定", COMPETITOR_ORDER, COMPETITOR_RATINGS)):
        rating, reason = parsed[key]["rating"], parsed[key]["reason"]
        cand_rating, fixed = cands[key].get("rating"), cands[key].get("fixed")
        if cand_rating and fixed and rating != cand_rating:
            issues.append(f"{where}: スクリプトの判定候補「{cand_rating}（確定）」と違う評価にはできない")
        elif (cand_rating and rating in order and order[rating] > order[cand_rating]
              and DIFFERS_FROM_CANDIDATE not in reason):
            issues.append(f"{where}: 判定候補「{cand_rating}」より有利な評価なので、理由に「{DIFFERS_FROM_CANDIDATE}:」を書く")
        prev = _rating_in(previous_cell(previous, key), allowed)
        if prev and rating != prev and CHANGED_FROM_PREVIOUS not in reason:
            issues.append(f"{where}: 前回「{prev}」から変えたので、理由に「{CHANGED_FROM_PREVIOUS}:」を書く")
    return issues


# ---------- conclusion ----------

def judge(parsed: dict, peer_count: int) -> dict:
    top = parsed["kbf_rows"][0] if parsed["kbf_rows"] else {"kbf": "", "self": "？", "peers": []}
    peers = top["peers"][:peer_count]
    top_win = top["self"] == "○" and bool(peers) and all(m in ("△", "×") for m in peers)
    comp = parsed["competitor"]["rating"]
    no_reason = parsed["win_reason"].strip().startswith(NO_REASON)
    if no_reason or comp == "劣位":
        verdict, why = "なし", "勝てる理由が書けない" if no_reason else "競合との比較が「劣位」"
    elif top_win and comp == "優位":
        verdict, why = "明確", "最重要KBFで自社が ○（競合に ○・？ なし）、かつ競合との比較が「優位」"
    else:
        lacking = [] if top_win else ["最重要KBFで自社が競合より優れるとは言えない"]
        if comp != "優位":
            lacking.append(f"競合との比較が「{comp}」")
        verdict, why = "あいまい", "、".join(lacking)
    marks = "、".join([f"自社 {top['self']}"] + [f"{PEER_LABELS[i]} {m}" for i, m in enumerate(peers)])
    return {"verdict": verdict, "why": why, "top_kbf": top["kbf"], "top_kbf_win": top_win, "top_kbf_marks": marks}


def conclusion_section(judged: dict, comp_rating: str, cand: dict) -> str:
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 最重要KBF | {judged['top_kbf'] or '—'} |",
        f"| 最重要KBFで自社が競合より優れるか | {'はい' if judged['top_kbf_win'] else 'いいえ'}（{judged['top_kbf_marks']}） |",
        f"| 競合との比較 | {comp_rating}（スクリプトの判定候補: {cand.get('rating') or '—'}） |",
        f"| 勝てる理由 | **{judged['verdict']}**: {judged['why']} |"])


def apply_conclusion(text: str, judged: dict, comp_rating: str, cand: dict) -> str:
    return replace_section(text, "5.", conclusion_section(judged, comp_rating, cand))


def flags(parsed: dict) -> dict:
    """Items the completion report lists: tie breaks, reference-only evidence and ？ in the KBF table."""
    parts = (("成長性", parsed["growth"]["reason"], parsed["customer"]["confidence"]),
             ("競合との比較", parsed["competitor"]["reason"], parsed["competitor"]["confidence"]))
    return {"tie_breaks": [name for name, reason, _ in parts if TIE_BREAK in reason],
            "low_confidence": [name for name, _, conf in parts if conf == LOW_CONFIDENCE],
            "unknown_kbf": [r["kbf"] for r in parsed["kbf_rows"] if r["self"] == "？" or "？" in r["peers"]]}
