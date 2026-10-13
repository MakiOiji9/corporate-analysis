"""{date}_profitability.md: skeleton, parse, checks and the conclusion (収益性 良好/普通/懸念/判定保留).

Every number and every judgement of 企業分析フレームワーク.md 2-1 comes from pf_metrics; the writer only fills
the background of the numbers (3.2 差の背景, 3.3 背景 per year, 3.4 一過性要因, 5 コメント, 6 引き継ぎ, 7, 8).
build recomputes the candidates from the raw, so an edited table in the md cannot change the conclusion.
"""
from __future__ import annotations

from string import Template

import mdparse as M
import mt_metrics as MT
from ff_doc import FIXED_MARK, _check_words, replace_section
from pf_metrics import CHANGE_PT, COMPARE_YEARS, FACTORS, ONE_OFF_SHARE, SAME_PT, _mean, fmt_factor
from validate import check_fill, check_structure, check_tables

UNKNOWN_BACKGROUND = "不明"


# ---------- tables ----------

def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _p(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def roe_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | 自社の ROE・純利益・自己資本の時系列が raw に無い |"
    lines = []
    for r in rows:
        equity = _m(r["avg_equity"]) + ("" if r["averaged"] in (True, None) else "（期末）")
        lines.append(f"| {r['year']} | {_m(r['net_income'])} | {equity} | {_p(r['reported'])} | "
                     f"{_p(r['computed'])} | {r['basis']} {r['roe']:.1f}% | {r['source']} |")
    return "\n".join(lines)


def step1_summary(s1: dict) -> str:
    if s1["rating"] is None:
        return f"—（{s1['basis']}）"
    losses = "、".join(s1["losses"]) or "なし"
    return (f"対象 {s1['years']} 年（{s1['first']}〜{s1['last']}）: 平均 {s1['average']:.1f}%、最低 {s1['minimum']:.1f}%"
            f"（{s1['minimum_year']}）、赤字の年 {losses}、直近3年 {s1['direction']}")


def rating_cell(rating: str | None, basis: str) -> str:
    return f"—（{basis}）" if rating is None else f"{rating}{FIXED_MARK}: {basis}"


def dupont_table_rows(own: list[dict]) -> str:
    if not own:
        return "| — | — | — | — | — | 売上高・当期純利益・総資産・自己資本の揃った年が無い |"
    lines = []
    for r in own:
        notes = ["期首期末平均" if r["averaged"] else "期末残高で計算（前年の残高なし）"]
        if not r["primary"]:
            notes.append("二次情報を含む")
        lines.append(f"| {r['year']} | " + " | ".join(fmt_factor(r[k], k) for k, _ in FACTORS)
                     + f" | {fmt_factor(r['roe'], 'roe')} | {'、'.join(notes)} |")
    return "\n".join(lines)


def _span(years: list[str]) -> str:
    return f"{years[0]}〜{years[-1]}（{len(years)}年）" if years else "—"


def _factor_cells(values: dict) -> str:
    return " | ".join(fmt_factor(values.get(k), k) for k, _ in FACTORS) + f" | {fmt_factor(values.get('roe'), 'roe')}"


def peer_table_rows(name: str, own: list[dict], comparison: dict) -> str:
    if comparison["peers"]:
        own_years, own_values = comparison["years"], comparison["self"]
    else:  # nothing to compare: the target's own recent average, for reference
        recent = own[-COMPARE_YEARS:]
        own_years = [r["year"] for r in recent]
        own_values = {k: _mean([r[k] for r in recent]) for k in [k for k, _ in FACTORS] + ["roe"]}
    lines = [f"| **{name}** | {_span(own_years)} | {_factor_cells(own_values)} | 自社の期間平均 |"]
    for p in comparison["peers"]:
        lines.append(f"| {p['name']} | {_span(p['years'])} | {_factor_cells(p)} | "
                     f"{'一次' if p['primary'] else '二次を含む'} |")
    if comparison["peers"]:
        lines.append(f"| 競合の単純平均 | — | {_factor_cells(comparison['peer_avg'])} | スクリプトが計算（自社を除く） |")
    else:
        lines.append("| 競合 | — | — | — | — | — | competitors.md「収益性の分解」に計算できる競合の行が無い |")
    return "\n".join(lines)


def change_table_rows(changes: list[dict]) -> str:
    if not changes:
        return f"| — | — | — | — | 該当なし（前年から {CHANGE_PT:.0f}pt 以上動いた年なし） |"
    return "\n".join(
        f"| {c['year']} | {c['from']:.1f}% → {c['to']:.1f}% | {c['main']} | {c['moves']} | "
        f"<!-- FILL:bg-{c['year']} この年に{c['main']}が動いた理由を1文（同じ行の営業利益率・特別損益の変化と、"
        f"brief の特別損益の内訳・株主還元・事業の記述から）。分からなければ「{UNKNOWN_BACKGROUND}（brief に記載なし）」 --> |"
        for c in changes)


def one_off_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | 特別損益の記載が raw に無い |"
    return "\n".join(
        f"| {r['year']} | {_m(r['gain'])} | {_m(r['loss'])} | {_m(r['net_income'])} | "
        f"{_p(r['share'])}{'（要確認）' if r['check'] else ''} | {_p(r.get('adjusted_roe'))} |" for r in rows)


def one_off_step1_cell(adjusted: dict | None, s1: dict) -> str:
    if adjusted is None:
        return f"—（要確認の年なし。特別損益の純額は各年とも当期純利益の{ONE_OFF_SHARE:.0f}%未満）"
    same = "変わらない" if adjusted["rating"] == s1["rating"] else f"{s1['rating']} から変わる"
    return (f"{'、'.join(adjusted['years'])} の特別損益を除くと（税効果は考慮しない）: {adjusted['sentence']}。"
            f"手順1の判定は{same}")


def consistency_table_rows(rows: list[dict]) -> str:
    return "\n".join(f"| {r['check']} | {r['step1']} | {r['step2']} | {r['result']} |" for r in rows)


# ---------- skeleton ----------

ROE_NOTE = ("注: ROE（計算）= 当期純利益 ÷ 期首期末平均の自己資本。自己資本は「自己資本」の記載値、無い年は 総資産 × "
            "自己資本比率（純資産は非支配株主持分・新株予約権を含むので使わない）。採用した値は 一次の開示値 → 計算値 → "
            "二次の開示値 の順。（期末）は前年の残高が無く期末残高で計算した年。")


def margin_note(s2: dict) -> str:
    sources = "、".join(s2["sources"]) or "—"
    return (f"注: 自社は {sources}、競合は competitors.md「売上高・営業利益」の実績（会社予想は除く）からスクリプトが計算。"
            f"同業平均は比較した競合の単純平均（決算期が6か月以内の年度を同じ年として扱う）。直近の比較できる年の差が "
            f"±{SAME_PT:.0f}pt 以内なら同等。")


def render_skeleton(template: str, values: dict, cands: dict, consistency: list[dict]) -> str:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    filled = dict(values,
                  roe_rows=roe_table_rows(cands["roe_rows"]), step1_summary=step1_summary(s1),
                  step1_rating=rating_cell(s1["rating"], s1["basis"]), roe_note=ROE_NOTE,
                  margin_rows=MT.margin_table_rows(s2["rows"]), step2_rating=rating_cell(s2["rating"], s2["basis"]),
                  margin_note=margin_note(s2), dupont_rows=dupont_table_rows(cands["dupont"]),
                  peer_rows=peer_table_rows(values["company"], cands["dupont"], s3["comparison"]),
                  step3_rating=f"{s3['source']}{'' if s3['source'] == '不明' else FIXED_MARK}: {s3['basis']}",
                  change_rows=change_table_rows(cands["changes"]), one_off_rows=one_off_table_rows(cands["one_off"]),
                  one_off_step1=one_off_step1_cell(cands["one_off_step1"], s1),
                  consistency_rows=consistency_table_rows(consistency))
    return Template(template).safe_substitute(filled)


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    """項目 / 内容 rows of every such table in the text."""
    out = {}
    for table in M.tables(text):
        if table and table[0][:2] == ["項目", "内容"]:
            out.update({row[0]: row[1] if len(row) > 1 else "" for row in table[1:] if row})
    return out


def parse(text: str) -> dict:
    peer = _kv(M.section(text, "3.2", level=3))
    change_tables = M.tables(M.section(text, "3.3", level=3))
    changes = [{"year": r[0], "main": r[2] if len(r) > 2 else "", "background": r[4] if len(r) > 4 else ""}
               for r in (change_tables[0][1:] if change_tables else []) if r and r[0] != "—"]
    handoff = _kv(M.section(text, "6."))
    return {
        "peer_gap": peer.get("同業との差の背景", ""), "changes_by_year": changes,
        "one_off": _kv(M.section(text, "3.4", level=3)).get("一過性要因の評価", ""),
        "consistency_comment": _kv(M.section(text, "5.")).get("コメント", ""),
        "report_points": handoff.get("レポートで使う要点", ""), "targets": handoff.get("会社の目標・資本政策との関係", ""),
        "step2_checks": handoff.get("STEP 2 の他の分析で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "7.")), "gaps": M.bullets(M.section(text, "8.")),
    }


# ---------- checks ----------

def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("3.2 同業との差の背景", p["peer_gap"]), ("3.4 一過性要因の評価", p["one_off"]),
            ("5. コメント", p["consistency_comment"]), ("6. レポートで使う要点", p["report_points"]),
            ("6. 会社の目標・資本政策との関係", p["targets"]), ("6. STEP 2 の他の分析で確かめること", p["step2_checks"]),
            ("6. 評価が変わる条件", p["triggers"])]


def _check_changes(parsed: dict, expected: list[dict]) -> list[str]:
    got = [c["year"] for c in parsed["changes_by_year"]]
    want = [c["year"] for c in expected]
    if got != want:
        return [f"3.3 の年度がスクリプトの抽出と違う（今: {'、'.join(got) or 'なし'} / 期待: {'、'.join(want) or 'なし'}）。"
                "行を足したり消したりしない"]
    return [f"3.3 {c['year']}: 背景が空" for c in parsed["changes_by_year"] if M.is_blank(c["background"])]


def validate(text: str, template: str, expected_changes: list[dict]) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_changes(p, expected_changes)
    if not p["changes"]:
        issues.append("7. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("8. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def conclusion_section(cands: dict) -> str:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    basis = "" if s3["source"] == "不明" else f"（{s3['basis']}）"  # the 不明 sentence already says why
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 手順1 ROE の水準と安定性 | {s1['sentence']} |",
        f"| 手順2 営業利益率の同業比較 | {s2['sentence']} |",
        f"| 手順3 ROE の源泉 | {s3['sentence']}{basis} |",
        f"| 境界に近い比較 | {'。'.join(cands['borderline']) or 'なし'} |",
        f"| 収益性 | **{cands['verdict']}**: {cands['why']} |"])


def apply_conclusion(text: str, cands: dict) -> str:
    return replace_section(text, "4.", conclusion_section(cands))


def flags(parsed: dict, cands: dict) -> dict:
    """Items the completion report lists."""
    return {"unknown_backgrounds": [c["year"] for c in parsed["changes_by_year"]
                                    if c["background"].strip().startswith(UNKNOWN_BACKGROUND)],
            "one_off_checks": [r["year"] for r in cands["one_off"] if r["check"]],
            "one_off_share_limit": ONE_OFF_SHARE, "borderline": cands["borderline"]}
