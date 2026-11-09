"""{date}_moat.md: skeleton, parse, checks and the conclusion (モート 広い/狭い/なし/判定保留).

企業分析フレームワーク.md 1-3, decided here (not by the writer):
  超過収益 (手順1) is the script's ROIC rating (mt_returns): 強い / 弱い / なし / 不明.
  源泉 (手順2) are the writer's rows: 強 / 中 / 弱 / 該当なし / 不明; 強 and 中 count as a moat.
  堀の傾向: 縮小 when the ROIC spread narrows or the share falls; 拡大 when the spread widens and the share holds;
    不明 when neither is known; else 安定.
  モートの強さ (手順4), first match wins:
    判定保留: 超過収益 不明 (the ROIC cannot be computed)
    なし: 超過収益 なし — a source the numbers do not show is not a moat (the claimed sources are recorded as corrected)
    判定保留: no 強/中 source while some source is 不明 (excess returns exist but what protects them is not known)
    なし: no 強/中 source
    広い: 超過収益 強い, one 強 or two 強/中 sources, depth 深い/中程度, no factor within 5 years, trend not 縮小
    狭い: otherwise
"""
from __future__ import annotations

from string import Template

import an_fill as F
import mdparse as M
from ff_doc import (CHANGED_FROM_PREVIOUS, CONFIDENCE, LOW_CONFIDENCE, TIE_BREAK, _check_words, candidate_cell,
                    replace_section)
from mt_metrics import cost_table_rows, margin_table_rows
from mt_returns import gross_note, gross_table_rows, roic_note, roic_table_rows
from validate import check_fill, check_structure, check_tables

VERSION = 2  # 2026-11: ROIC gate, six sources rated 強/中/弱; results of version 1 used 該当/該当なし/不明
MOAT_TYPES = ("ブランド", "規制・特許・許認可", "スイッチングコスト", "ネットワーク効果", "コスト優位", "効率的規模")
INTANGIBLE = ("ブランド", "規制・特許・許認可")
MOAT_RATINGS = ("強", "中", "弱", "該当なし", "不明")
HITS = ("強", "中")
UNKNOWN = "不明"
SHARE_TRENDS = ("拡大", "安定", "横ばい〜微減", "低下", "不明")
SHARE_HOLDS = ("拡大", "安定")
TIMINGS = ("5年以内", "5〜10年", "10年超・不明")
CATEGORIES = ("技術", "規制", "顧客行動", "破壊的イノベーション", "内製化", "その他")
DEPTHS = ("深い", "中程度", "浅い", "不明")
DEEP_ENOUGH = ("深い", "中程度")
REACHES = ("あり", "限定的", "なし", "不明")
NEAR = "5年以内"
NO_RISK = "なし"
PENDING = "判定保留"
MOAT_COLUMNS = 6
RISK_COLUMNS = 6


# ---------- skeleton ----------

def _previous(previous: tuple[str, dict] | None) -> tuple[str, str]:
    """(前回の判定 of the moat types, 前回のシェアの推移)."""
    if not previous:
        return "—（初回）", "—（初回）"
    date, r = previous
    moats = "、".join(f"{m.get('type')} {m.get('rating')}" for m in r.get("moats", [])) or "—"
    scale = "" if r.get("version") == VERSION else "。旧基準（該当/該当なし/不明）の判定"
    share = (r.get("share") or {}).get("trend") or "—"
    return f"{moats}（{date}{scale}）", f"{share}（{date}）"


def margin_note(cands: dict) -> str:
    sources = "、".join(cands["sources"]) or "—"
    return (f"注: 自社は {sources}、競合は competitors.md「売上高・営業利益」の実績（会社予想は除く）からスクリプトが計算。"
            f"同業中央値は比較した競合の中央値（対象企業を除く。決算期が6か月以内の年度を同じ年として扱う）。"
            f"超過収益（2.1）を補う参考の指標: {candidate_cell(cands['margin'])}")


def width_basis(ret: dict) -> str:
    if ret["recent_spread"] is None:
        return f"ROIC と資本コストの差が計算できない（{ret['basis']}）"
    ep = ret["economic_profit"]
    profit = f"。経済的利益 {ep['year']} {ep['latest']:,}（{ret['unit']}）" if ep["latest"] is not None else ""
    return (f"直近3年の ROIC と資本コストの差の平均 {ret['recent_spread']:+.1f}pt{profit}。"
            f"目安: +10pt 以上 大 / +3pt 以上 中 / 0超 小 / 0以下 なし（スクリプトが判定）")


def render_skeleton(template: str, values: dict, cands: dict, previous: tuple[str, dict] | None) -> str:
    prev_moats, prev_share = _previous(previous)
    ret, pr = cands["returns"], cands["pricing"]
    filled = dict(values, roic_rows=roic_table_rows(ret), roic_note=roic_note(ret),
                  margin_rows=margin_table_rows(cands["rows"]), margin_note=margin_note(cands),
                  gross_rows=gross_table_rows(pr), gross_note=gross_note(pr), cost_rows=cost_table_rows(cands["costs"]),
                  width=ret["width"], width_basis=width_basis(ret), prev_moats=prev_moats, prev_share=prev_share)
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    return {r.get("項目", ""): r.get("内容", "") for r in M.table_dicts(text)}


def _rows(table: list[list[str]], width: int) -> list[list[str]]:
    return [row + [""] * (width - len(row)) for row in table[1:]]


def _axes(text: str) -> dict[str, dict]:
    rows = {r.get("軸", "").split("（")[0]: r for r in M.table_dicts(M.section(text, "7."))}
    return {key: {"rating": rows.get(name, {}).get("評価", "").strip(), "reason": rows.get(name, {}).get("根拠", "")}
            for key, name in (("width", "幅"), ("depth", "深さ"), ("reach", "拡張性"))}


def _moat(r: list[str]) -> dict:
    mechanism, trace = r[2], r[3]
    return {"type": r[0], "group": "無形資産" if r[0] in INTANGIBLE else r[0], "rating": r[1].strip(),
            "mechanism": mechanism, "trace": trace, "basis": f"{mechanism.strip()} 数値: {trace.strip()}",
            "source": r[4], "confidence": r[5].strip()}


def parse(text: str) -> dict:
    intro = _kv(M.section(text, "1."))
    moat_tables = M.tables(M.section(text, "4."))
    risk_tables = M.tables(M.section(text, "6."))
    share = _kv(M.section(text, "5."))
    handoff = _kv(M.section(text, "9."))
    moats = [_moat(r) for r in (_rows(moat_tables[0], MOAT_COLUMNS) if moat_tables else [])]
    risks = [{"factor": r[0], "category": r[1].strip(), "timing": r[2].strip(), "moat": r[3], "basis": r[4],
              "source": r[5]} for r in (_rows(risk_tables[0], RISK_COLUMNS) if risk_tables else [])]
    durability = (next((r[1] for r in risk_tables[1][1:] if len(r) > 1 and r[0] == "持続の見込み"), "")
                  if len(risk_tables) > 1 else "")
    return {
        "strength": intro.get("確かめる強み", ""), "moats": moats,
        "share": {"trend": share.get("シェアの推移", "").strip(), "reason": share.get("理由", ""),
                  "seen": share.get("見たもの", ""), "source": share.get("情報源", ""),
                  "confidence": share.get("根拠の確度", "").strip()},
        "risks": risks, "durability": durability, "axes": _axes(text),
        "strengths": handoff.get("SWOT の強み（S）候補", ""), "threats": handoff.get("SWOT の脅威（T）候補", ""),
        "step2_checks": handoff.get("STEP 2 で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "10.")), "gaps": M.bullets(M.section(text, "11.")),
    }


# ---------- fields build derives from the writer's rows (an_fill.fill_at_build) ----------

BUILD_KEYS = ("strengths", "threats", "changes", "gaps")


def _changes(p: dict, previous: tuple[str, dict] | None) -> str:
    if not previous:
        return "- 初回の分析"
    old = previous[1]
    if old.get("version") != VERSION:
        return "- 判定の基準を改めた（超過収益の入口・6種の源泉・強/中/弱）ため、前回の判定とは比べない"
    old_moats = {m.get("type"): m.get("rating") for m in old.get("moats") or []}
    pairs = [(m["type"], old_moats.get(m["type"]), m["rating"]) for m in p["moats"]]
    pairs.append(("シェアの推移", (old.get("share") or {}).get("trend"), p["share"]["trend"]))
    return F.changes_bullets(previous, pairs)


def _gaps(p: dict, found: dict, warnings: list[str]) -> str:
    extra = [f"{m['type']}: 不明（根拠が brief に無い）" for m in p["moats"] if m["rating"] == UNKNOWN]
    extra += [f"{m['type']}: 根拠が参考情報だけ" for m in p["moats"] if m["confidence"] == LOW_CONFIDENCE]
    if p["share"]["trend"] == UNKNOWN:
        extra.append("シェアの推移: 不明（業界のシェアの時系列が無い）")
    if p["axes"]["depth"]["rating"] == UNKNOWN:
        extra.append("深さ: 不明（模倣に要る時間・投資の材料が無い）")
    return F.gaps_bullets(found, warnings, extra)


def build_fills(text: str, found: dict, previous: tuple[str, dict] | None, warnings: list[str]) -> dict[str, str]:
    """9章 SWOT の強み・脅威の候補 (the 強/中 sources of 4章, the 5年以内・5〜10年 factors of 6章), 10章 and 11章."""
    p = parse(text)
    hits = [f"{m['type']}（{m['rating']}。{m['mechanism'].strip()}）" for m in p["moats"] if m["rating"] in HITS]
    risks = [] if p["risks"] and p["risks"][0]["factor"].strip().startswith(NO_RISK) else p["risks"]
    soon = [f"{r['factor'].strip()}（{r['timing']}。影響するモート: {r['moat'].strip() or '—'}）"
            for r in risks if r["timing"] in TIMINGS[:2]]
    return {"strengths": "／".join(hits) or NO_RISK, "threats": "／".join(soon) or NO_RISK,
            "changes": _changes(p, previous), "gaps": _gaps(p, found, warnings)}


# ---------- checks ----------

def _confidence_ok(confidence: str, may_be_blank: bool) -> bool:
    return confidence in CONFIDENCE or (may_be_blank and M.is_blank(confidence))


def _check_moat(m: dict) -> list[str]:
    where = f"4. {m['type']}"
    if m["rating"] not in MOAT_RATINGS:
        return [f"{where}: 判定は {'/'.join(MOAT_RATINGS)} の1語: 「{m['rating']}」"]
    issues = []
    hit = m["rating"] in HITS
    if M.is_blank(m["mechanism"]) and (hit or M.is_blank(m["trace"])):
        issues.append(f"{where}: 仕組みが空" if hit else f"{where}: 仕組み・数値の痕跡が両方空（確認した資料を書く）")
    if hit and M.is_blank(m["trace"]):
        issues.append(f"{where}: 「{m['rating']}」なのに数値の痕跡が空（数値が無いなら「弱」以下にする）")
    if hit and M.is_blank(m["source"]):
        issues.append(f"{where}: 「{m['rating']}」なのに情報源が空（根拠が書けないなら「不明」にする）")
    if not _confidence_ok(m["confidence"], may_be_blank=not hit):
        issues.append(f"{where}: 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{m['confidence']}」")
    return issues


def _check_moats(moats: list[dict]) -> list[str]:
    names = [m["type"] for m in moats]
    if names != list(MOAT_TYPES):
        return [f"4. モートの種類の行は {' / '.join(MOAT_TYPES)} をこの順・この名前で6行（今: {'、'.join(names) or 'なし'}）"]
    return [issue for m in moats for issue in _check_moat(m)]


def _check_share(share: dict) -> list[str]:
    if share["trend"] not in SHARE_TRENDS:
        return [f"5. シェアの推移は {'/'.join(SHARE_TRENDS)} の1語: 「{share['trend']}」"]
    issues = []
    if M.is_blank(share["reason"]):
        issues.append("5. 理由が空")
    if M.is_blank(share["seen"]):
        issues.append("5. 見たものが空")
    if not _confidence_ok(share["confidence"], may_be_blank=share["trend"] == UNKNOWN):
        issues.append(f"5. 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{share['confidence']}」")
    return issues


def _check_risks(risks: list[dict]) -> list[str]:
    if not risks:
        return ["6. 崩しうる要因の表に行が無い（無ければ1行目を「なし」にする）"]
    if risks[0]["factor"].strip().startswith(NO_RISK):
        issues = [] if len(risks) == 1 else ["6. 「なし」の行は1行だけにする（要因があるなら「なし」の行を消す）"]
        return issues + (["6. なし: 根拠（確認した資料）が空"] if M.is_blank(risks[0]["basis"]) else [])
    issues = []
    for r in risks:
        where = f"6. {r['factor']}"
        if r["category"] not in CATEGORIES:
            issues.append(f"{where}: 分類は {'/'.join(CATEGORIES)} の1語: 「{r['category']}」")
        if r["timing"] not in TIMINGS:
            issues.append(f"{where}: 時期は {'/'.join(TIMINGS)} の1語: 「{r['timing']}」")
        if M.is_blank(r["basis"]):
            issues.append(f"{where}: 根拠が空")
    return issues


def _check_axes(axes: dict) -> list[str]:
    issues = []
    for key, name, words in (("depth", "深さ", DEPTHS), ("reach", "拡張性", REACHES)):
        if axes[key]["rating"] not in words:
            issues.append(f"7. {name}の評価は {'/'.join(words)} の1語: 「{axes[key]['rating']}」")
        elif M.is_blank(axes[key]["reason"]):
            issues.append(f"7. {name}の根拠が空")
    return issues


def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("1. 確かめる強み", p["strength"]), ("6. 持続の見込み", p["durability"]),
            ("9. 強み候補", p["strengths"]), ("9. 脅威候補", p["threats"]),
            ("9. STEP 2 で確かめること", p["step2_checks"]), ("9. 評価が変わる条件", p["triggers"])]


def validate(text: str, template: str) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_moats(p["moats"]) + _check_share(p["share"]) + _check_risks(p["risks"]) + _check_axes(p["axes"])
    if not p["changes"]:
        issues.append("10. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("11. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


def check_reference(parsed: dict, previous: tuple[str, dict] | None) -> list[str]:
    """A judgement that differs from the previous result needs「前回から変更:」. Results judged on the old scale
    (version 1) are not compared."""
    if not previous or previous[1].get("version") != VERSION:
        return []
    _, r = previous
    issues = []
    before = {m.get("type"): m.get("rating") for m in r.get("moats", [])}
    for m in parsed["moats"]:
        prev = before.get(m["type"])
        if prev and m["rating"] != prev and CHANGED_FROM_PREVIOUS not in m["mechanism"]:
            issues.append(f"4. {m['type']}: 前回「{prev}」から変えたので、仕組みに「{CHANGED_FROM_PREVIOUS}:」を書く")
    prev_share = (r.get("share") or {}).get("trend")
    share = parsed["share"]
    if prev_share and share["trend"] != prev_share and CHANGED_FROM_PREVIOUS not in share["reason"]:
        issues.append(f"5. シェアの推移: 前回「{prev_share}」から変えたので、理由に「{CHANGED_FROM_PREVIOUS}:」を書く")
    return issues


# ---------- conclusion ----------

def moat_trend(spread_trend: str, share_trend: str) -> str:
    if spread_trend == "縮小" or share_trend == "低下":
        return "縮小"
    if spread_trend == "拡大" and share_trend in SHARE_HOLDS:
        return "拡大"
    if spread_trend == "不明" and share_trend == UNKNOWN:
        return "不明"
    return "安定"


def _wide_lacking(returns: str, hits: list[dict], depth: str, near: list[str], trend: str) -> list[str]:
    lacking = []
    if returns != "強い":
        lacking.append(f"超過収益が{returns}")
    if not (any(m["rating"] == "強" for m in hits) or len(hits) >= 2):
        lacking.append("「強」のモートが無く「中」が1つだけ")
    if depth not in DEEP_ENOUGH:
        lacking.append(f"深さが{depth}")
    if near:
        lacking.append("5年以内に崩しうる要因あり")
    if trend == "縮小":
        lacking.append("堀の傾向が縮小")
    return lacking


def judge(parsed: dict, returns: dict) -> dict:
    support = returns.get("rating") or UNKNOWN
    hits = [m for m in parsed["moats"] if m["rating"] in HITS]
    claimed = [m["type"] for m in hits]
    unknown = [m["type"] for m in parsed["moats"] if m["rating"] == UNKNOWN]
    near = [r["factor"] for r in parsed["risks"] if r["timing"] == NEAR]
    trend = moat_trend(returns.get("trend", "不明"), parsed["share"]["trend"])
    depth = parsed["axes"]["depth"]["rating"]
    effective, corrected = claimed, False
    if support == UNKNOWN:
        verdict, why, effective = PENDING, f"超過収益を確かめられない（{returns.get('basis', '')}）", []
    elif support == "なし":
        verdict, effective, corrected = "なし", [], bool(claimed)
        why = "超過収益が無い（ROIC が資本コストを上回っていない）" + (
            f"。{'・'.join(claimed)} は数字に表れていないため、モートとはみなさない" if claimed else "")
    elif not claimed and unknown:
        verdict = PENDING
        why = f"超過収益はある（{support}）が、それを守る源泉を確かめる材料が無い（不明: {'・'.join(unknown)}）"
    elif not claimed:
        verdict, why = "なし", (f"超過収益はある（{support}）が、それを守る「強」「中」の源泉が無い"
                                f"（業態に共通する収益性や一時的な要因の可能性）")
    else:
        lacking = _wide_lacking(support, hits, depth, near, trend)
        verdict = "狭い" if lacking else "広い"
        why = "、".join(lacking) if lacking else (
            f"超過収益が強い、{'・'.join(claimed)} が該当、深さ{depth}、5年以内に崩しうる要因なし、堀の傾向{trend}")
    return {"verdict": verdict, "why": why, "backing": support, "backing_why": returns.get("basis", ""),
            "claimed": claimed, "effective": effective, "corrected": corrected, "near_risks": near,
            "trend": trend, "depth": depth, "unknown_sources": unknown, "conservative": []}


def conclusion_section(judged: dict, returns: dict, share_trend: str) -> str:
    if judged["corrected"]:
        moats = f"なし（{'、'.join(judged['claimed'])} は超過収益に表れていないため除いた）"
    else:
        moats = "、".join(judged["effective"]) or "なし"
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 超過収益 | {judged['backing']}: {judged['backing_why']} |",
        f"| 該当するモート | {moats} |",
        f"| 5年以内に崩しうる要因 | {'、'.join(judged['near_risks']) or 'なし'} |",
        f"| 堀の傾向 | {judged['trend']}（ROIC と資本コストの差の傾向 {returns.get('trend', '不明')}、シェアの推移 {share_trend}） |",
        f"| モートの強さ | **{judged['verdict']}**: {judged['why']} |"])


def apply_conclusion(text: str, judged: dict, returns: dict, share_trend: str) -> str:
    return replace_section(text, "8.", conclusion_section(judged, returns, share_trend))


def flags(parsed: dict) -> dict:
    """Items the completion report lists: tie breaks, reference-only evidence and 不明 judgements."""
    parts = [(m["type"], m["basis"], m["confidence"], m["rating"]) for m in parsed["moats"]]
    share = parsed["share"]
    parts.append(("シェアの推移", share["reason"], share["confidence"], share["trend"]))
    depth = parsed["axes"]["depth"]
    parts.append(("深さ", depth["reason"], "", depth["rating"]))
    return {"tie_breaks": [name for name, reason, _, _ in parts if TIE_BREAK in reason],
            "low_confidence": [name for name, _, conf, _ in parts if conf == LOW_CONFIDENCE],
            "unknown": [name for name, _, _, rating in parts if rating == UNKNOWN]}
