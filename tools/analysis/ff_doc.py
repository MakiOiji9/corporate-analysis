"""{date}_five-forces.md: skeleton, parse, checks, scoring and the machine-readable result.

Scoring follows 企業分析フレームワーク.md 1-1 手順3: 弱 2 / 中 1 / 強 0 points, 7+ 高 / 4-6 中 / <=3 低.
Repository rule on top: 不明 counts as 中 (1 point) and two or more 不明 lower the result one step.
"""
from __future__ import annotations

import re
from string import Template

import mdparse as M
from outlook import FORBIDDEN
from validate import check_fill, check_structure, check_tables

FACTORS = (("entry", "2.1", "新規参入の脅威"), ("substitutes", "2.2", "代替品の脅威"),
           ("buyers", "2.3", "買い手の交渉力"), ("suppliers", "2.4", "売り手の交渉力"),
           ("rivalry", "2.5", "業界内の競争"))
RATINGS = ("強", "中", "弱", "不明")
POINTS = {"弱": 2, "中": 1, "強": 0, "不明": 1}
LEVELS = ((7, "高"), (4, "中"), (0, "低"))
DOWNGRADE = {"高": "中", "中": "低", "低": "低"}
UNKNOWN_DOWNGRADE = 2
CONFIDENCE = ("一次", "二次", "参考")  # 有報・会社資料・官公庁統計 / 調査会社の記事経由 / ブログ・比較サイト
LOW_CONFIDENCE = "参考"
TIE_BREAK = "迷った"  # the writer picked the less favourable of two ratings (policy 行動指針6)
DIFFERS_FROM_CANDIDATE = "候補と異なる理由"
CHANGED_FROM_PREVIOUS = "前回から変更"
PENDING = "（build が記入）"
FIXED_MARK = "（確定）"
HEADING2 = re.compile(r"^##\s+(\d+)\.", re.M)


# ---------- skeleton ----------

def candidate_cell(cand: dict) -> str:
    if not cand.get("rating"):
        return f"—（{cand.get('basis', '')}）"
    return f"{cand['rating']}{FIXED_MARK if cand.get('fixed') else ''}: {cand.get('basis', '')}"


def previous_cell(previous: tuple[str, dict] | None, key: str) -> str:
    if not previous:
        return "—（初回）"
    date, result = previous
    rating = next((f["rating"] for f in result.get("factors", []) if f.get("key") == key), "")
    return f"{rating}（{date}）" if rating else f"—（{date} の結果に無い）"


def render_skeleton(template: str, values: dict, candidates: dict[str, dict],
                    previous: tuple[str, dict] | None) -> str:
    rows = [f"| {name} | {PENDING} | {PENDING} | {PENDING} |" for _, _, name in FACTORS]
    rows.append(f"| **合計 / 業界の魅力度** | {PENDING} | {PENDING} | {PENDING} |")
    filled = dict(values, score_rows="\n".join(rows), threats=f"- {PENDING}")
    for key, _, _ in FACTORS:
        filled[f"cand_{key}"] = candidate_cell(candidates[key])
        filled[f"prev_{key}"] = previous_cell(previous, key)
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    return {r.get("項目", ""): r.get("内容", "") for r in M.table_dicts(text)}


def _rating_in(cell: str) -> str:
    """Leading rating word of a candidate / previous cell ('' for '—')."""
    m = re.match(r"\s*(強|中|弱|不明)", cell)
    return m.group(1) if m else ""


def parse(text: str) -> dict:
    industry = _kv(M.section(text, "1."))
    factors = []
    for key, number, name in FACTORS:
        row = _kv(M.section(text, number, level=3))
        cand = row.get("スクリプトの判定候補", "")
        reason = row.get("理由", "")
        factors.append({
            "key": key, "name": name, "rating": row.get("評価", "").strip(),
            "seen": row.get("見たもの", ""), "source": row.get("情報源", ""), "reason": reason,
            # None = the row is absent (results made before these rows existed)
            "confidence": row["根拠の確度"].strip() if "根拠の確度" in row else None,
            "triggers": row.get("評価が変わる条件"),
            "tie_break": TIE_BREAK in reason,
            "candidate": _rating_in(cand), "candidate_fixed": FIXED_MARK in cand,
            "previous": _rating_in(row.get("前回の評価", "")),
        })
    return {"industry": industry.get("業界の定義", ""), "industry_source": industry.get("根拠（情報源）", ""),
            "factors": factors, "changes": M.bullets(M.section(text, "5.")), "gaps": M.bullets(M.section(text, "6."))}


# ---------- checks ----------

def _check_factor(f: dict) -> list[str]:
    where = f"{f['name']}"
    if f["rating"] not in RATINGS:
        return [f"{where}: 評価は 強/中/弱/不明 の1語: 「{f['rating']}」"]
    issues = []
    if M.is_blank(f["seen"]):
        issues.append(f"{where}: 見たものが空")
    if M.is_blank(f["source"]) and f["rating"] != "不明":
        issues.append(f"{where}: 情報源が空（根拠が書けないなら評価を「不明」にする）")
    if M.is_blank(f["reason"]):
        issues.append(f"{where}: 理由が空")
    unknown_without_basis = f["rating"] == "不明" and M.is_blank(f["confidence"])
    if f["confidence"] is not None and f["confidence"] not in CONFIDENCE and not unknown_without_basis:
        issues.append(f"{where}: 根拠の確度は {'/'.join(CONFIDENCE)} の1語: 「{f['confidence']}」")
    if f["triggers"] is not None and M.is_blank(f["triggers"]):
        issues.append(f"{where}: 評価が変わる条件が空")
    return issues


def with_reference(parsed: dict, candidates: dict[str, dict], previous: tuple[str, dict] | None) -> dict:
    """Replace the candidate / previous read from the md with the values the scripts compute now."""
    factors = []
    for f in parsed["factors"]:
        cand = candidates.get(f["key"], {})
        factors.append(dict(f, candidate=cand.get("rating") or "", candidate_fixed=bool(cand.get("fixed")),
                            previous=_rating_in(previous_cell(previous, f["key"]))))
    return dict(parsed, factors=factors)


def _check_reference(f: dict) -> list[str]:
    where, issues = f["name"], []
    cand = f["candidate"]
    if cand and f["candidate_fixed"] and f["rating"] != cand:
        issues.append(f"{where}: スクリプトの判定候補「{cand}（確定）」と違う評価にはできない")
    elif cand and POINTS[f["rating"]] > POINTS[cand] and DIFFERS_FROM_CANDIDATE not in f["reason"]:
        issues.append(f"{where}: 判定候補「{cand}」より有利な評価なので、理由に「{DIFFERS_FROM_CANDIDATE}:」を書く")
    if f["previous"] and f["rating"] != f["previous"] and CHANGED_FROM_PREVIOUS not in f["reason"]:
        issues.append(f"{where}: 前回「{f['previous']}」から変えたので、理由に「{CHANGED_FROM_PREVIOUS}:」を書く")
    return issues


def _check_words(text: str) -> list[str]:
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))
    found = sorted({w for w in FORBIDDEN if w in body})
    return [f"推奨・推測の表現が含まれる: {', '.join(found)}"] if found else []


def check_factors(parsed: dict) -> list[str]:
    """Candidate / previous rules. Run on with_reference() output, after validate() passed."""
    return [issue for f in parsed["factors"] for issue in _check_reference(f)]


def validate(text: str, template: str) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    parsed = parse(text)
    if M.is_blank(parsed["industry"]):
        issues.append("1. 業界の定義が空")
    for f in parsed["factors"]:
        issues += _check_factor(f)
    if not parsed["changes"]:
        issues.append("5. 前回からの変更点に箇条書きが無い")
    if not parsed["gaps"]:
        issues.append("6. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- scoring ----------

def score(parsed: dict) -> dict:
    factors = [dict(f, points=POINTS[f["rating"]]) for f in parsed["factors"]]
    total = sum(f["points"] for f in factors)
    raw_level = next(level for floor, level in LEVELS if total >= floor)
    unknown = sum(1 for f in factors if f["rating"] == "不明")
    downgraded = unknown >= UNKNOWN_DOWNGRADE
    return {"factors": factors, "total": total, "attractiveness_by_points": raw_level,
            "attractiveness": DOWNGRADE[raw_level] if downgraded else raw_level,
            "unknown_count": unknown, "downgraded": downgraded,
            "swot_threats": [f["name"] for f in factors if f["rating"] == "強"]}


def _basis(f: dict) -> str:
    seen = f["seen"].replace("|", "／")
    return f"{seen}（{f['source']}）" if not M.is_blank(f["source"]) else seen


def scores_section(scored: dict) -> str:
    rows = ["| 要因 | 評価 | 点数 | 根拠（数値・出典） |", "|---|---|---|---|"]
    rows += [f"| {f['name']} | {f['rating']} | {f['points']} | {_basis(f)} |" for f in scored["factors"]]
    note = (f"不明 {scored['unknown_count']} 件のため 点数の判定「{scored['attractiveness_by_points']}」から1段階下げた"
            if scored["downgraded"] else f"点数による判定（不明 {scored['unknown_count']} 件）")
    rows.append(f"| **合計 / 業界の魅力度** | **{scored['attractiveness']}** | {scored['total']}/10 | {note} |")
    return "\n".join(rows)


def threats_section(scored: dict) -> str:
    if not scored["swot_threats"]:
        return "- なし（「強」の要因なし）"
    by_name = {f["name"]: f for f in scored["factors"]}
    return "\n".join(f"- {name}: {by_name[name]['reason']}" for name in scored["swot_threats"])


def replace_section(text: str, number: str, body: str) -> str:
    """Replace the body of '## {number}.' up to the next level-2 heading."""
    starts = [(m.group(1), m.start(), m.end()) for m in HEADING2.finditer(text)]
    for i, (num, _, head_end) in enumerate(starts):
        if f"{num}." == number:
            newline = text.find("\n", head_end)
            line_end = len(text) if newline < 0 else newline + 1
            stop = starts[i + 1][1] if i + 1 < len(starts) else len(text)
            return text[:line_end] + "\n" + body.rstrip() + "\n\n" + text[stop:]
    raise ValueError(f"heading ## {number} not found")


def apply_scores(text: str, scored: dict) -> str:
    return replace_section(replace_section(text, "3.", scores_section(scored)), "4.", threats_section(scored))
