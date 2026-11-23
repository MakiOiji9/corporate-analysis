"""{date}_investment.md: skeleton, parse, checks and the conclusion (投資の質 良好/普通/懸念/判定保留).

Every number and judgement comes from iv_metrics. The writer names what was invested in each year, the themes
(T1〜T5) and their fit with the industry's changes and policy, the background of each change point, and the
mid-term plan / planned facilities against what was done. build re-reads only those classes from the md and
recomputes everything else, so an edited table cannot change the conclusion.
"""
from __future__ import annotations

import re
from string import Template

import an_fill as AF
import iv_metrics as IV
import mdparse as M
from ff_doc import FIXED_MARK, _check_words, replace_section
from gr_doc import UNIT_NUMBER, _numbers, REFERENCE_NUMBERS
from validate import check_fill, check_structure, check_tables

VERSION = 1
THEMES = 5
THEME_ID = re.compile(r"T([1-5])")
NONE = ("—", "-", "なし", "")


# ---------- tables ----------

def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _p(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _x(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def _mix(mix: dict) -> str:
    return "、".join(f"{k} {v:.0f}%" for k, v in sorted(mix.items(), key=lambda kv: -kv[1])) or "—"


def year_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | — | — | — | — | — |"
    out = []
    for r in rows:
        y = r["year"]
        out.append(f"| {y} | {_m(r['capex'])} | {_p(r['capex_share'])} | {_x(r['capex_to_dep'])} | {_m(r['rnd'])} | "
                   f"{_p(r['rnd_share'])} | {_m(r['acquisition'])} | {_m(r['impairment'])} | {_mix(r['mix'])} | "
                   f"<!-- FILL:content-{y} {y} に何に投資したか（brief の {y} の設備投資等の概要・研究開発活動・企業結合の"
                   "記述から、対象・目的を1文。記載が無ければ「不明（brief に記載なし）」） --> | "
                   f"<!-- FILL:themes-{y} 3章の T1〜T5 のうち {y} の投資に当たるもの（例: T1、T3）。無ければ「—」 --> |")
    return "\n".join(out)


def point_rows(points: list[dict]) -> str:
    if not points:
        return "| — | — | 変化点なし | — |"
    return "\n".join(f"| {p['year']} | {p['kind']} | {p['text']} | <!-- FILL:point-{i} {p['year']} の{p['kind']}の背景を1文"
                     "（brief の有報の記述・中期経営計画から。何に投資したか・なぜか）。記載が無ければ「不明（brief に記載なし）」 --> |"
                     for i, p in enumerate(points, start=1))


POINT_NOTE = ("変化点の条件: 設備投資 ÷ 売上が前3年平均の 1.5倍以上 / 0.5倍以下、セグメント別の構成比が前年から 10pt 以上、"
              "研究開発費 ÷ 売上が前3年平均から 1pt 以上、子会社の取得が売上の 5% 以上か企業結合の注記、設備投資 ÷ 減価償却費が "
              "1倍をまたぐ。新しい投資テーマ（1章の主なテーマに初めて出た ID）は build が 7章の前に足す。")


def plan_rows(plans: list[dict]) -> str:
    return "\n".join(
        f"| {p['year']} の設備計画 → {p['next']} の実績 | <!-- FILL:plan-{p['year']} brief の {p['year']} の「設備の新設、除却等の計画」"
        f"に書かれた主な計画（対象・金額）と、{p['next']} の設備投資等の概要・主要な設備で分かる結果を1文 --> | "
        f"<!-- FILL:plan-{p['year']}-class {' / '.join(IV.PLAN_OUTCOMES)} のどれか1語 --> |" for p in plans)


def _row(name: str, value: str, rating: str) -> str:
    return f"| {name} | {value} | {rating}{FIXED_MARK} |"


def efficiency_rows(c: dict) -> str:
    s5, ratio = c["step5"], c["ratio"] or {}
    eff = (s5.get("efficiency") or {})
    lines = [_row("増分 ROIC・人材の効率（成長性分析の手順5から移した）", eff.get("sentence") or s5.get("sentence", "—"),
                  eff.get("rating") or "不明")]
    top = c["top_segment"]
    if top:
        detail = (f"{top['span']} の設備投資が最も多い {top['segment']}（{top['share']:.1f}%）: 売上 CAGR "
                  f"{_p(top['revenue_cagr'])}、営業利益率の変化 "
                  + (f"{top['margin_change']:+.1f}pt（{top.get('margin_span', '—')}）" if top["margin_change"] is not None
                     else "—"))
        lines.append(_row("投資の多いセグメントの成果", detail, "参考"))
    lines.append(_row("(c) 有形固定資産回転率", c["checks"]["c"]["detail"], c["checks"]["c"]["status"]))
    for note in c["axes"]["efficiency"]["notes"]:
        lines.append(_row("① の補正", note, c["axes"]["efficiency"]["rating"]))
    lines.append(_row("① 投資効率", c["axes"]["efficiency"]["sentence"], c["axes"]["efficiency"]["rating"]))
    lines.append(_row("④ 競合比較（売上に対する成長投資）", c["axes"]["peer"]["sentence"], c["axes"]["peer"]["rating"]))
    notes = s5.get("notes") or []
    if notes or ratio.get("underinvest"):
        lines.append(_row("成長投資の注記", "。".join(notes) or "—", "参考"))
    return "\n".join(lines)


def check_rows(c: dict) -> str:
    lines = [_row(ch["name"], ch["detail"], ch["status"]) for ch in c["checks"].values() if not ch["name"].startswith("(c)")]
    lines.append(_row("⑤ 失敗の履歴（(a)・(b) の悪い方）", "—", c["axes"]["failure"]["rating"]))
    lines.append(_row("⑥ 資金と規律（(d)〜(h) の悪い方。(e)・(g) は注意まで）", "—", c["axes"]["discipline"]["rating"]))
    return "\n".join(lines)


def render_skeleton(template: str, values: dict, c: dict) -> str:
    filled = dict(values, year_rows=year_rows(c["rows"]), point_rows=point_rows(c["points"]), point_note=POINT_NOTE,
                  plan_rows=plan_rows(c["plan_years"]), efficiency_rows=efficiency_rows(c), check_rows=check_rows(c))
    return Template(template).safe_substitute(filled)


# ---------- fields the script writes ----------

def _changes(c: dict, previous: tuple[str, dict] | None) -> str:
    old = previous[1] if previous else {}
    axes = old.get("axes") or {}
    pairs = [(label, (axes.get(k) or {}).get("rating"), c["axes"][k]["rating"])
             for k, label in (("efficiency", "① 投資効率"), ("peer", "④ 競合比較"), ("failure", "⑤ 失敗の履歴"),
                              ("discipline", "⑥ 資金と規律"))]
    pairs.append(("変化点の数", len(old.get("points") or []), len(c["points"])))
    return AF.changes_bullets(previous, pairs)


def auto_fills(c: dict, previous: tuple[str, dict] | None, found: dict, warnings: list[str]) -> dict[str, str | None]:
    extra = []
    if not c["has_texts"]:
        extra.append("data/investments.json（有報の設備投資・研究開発・企業結合の文章）が無い: 何に投資したかは raw の有報の章だけで書いた")
    if c["excluded"]:
        extra.append(c["why"])
    return {"changes": _changes(c, previous), "gaps": AF.gaps_bullets(found, warnings, extra)}


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    out = {}
    for table in M.tables(text):
        if table and table[0][:2] in (["項目", "内容"], ["照合", "内容"]):
            out.update({row[0]: row[1:] for row in table[1:] if row})
    return out


def _plain(cell: str) -> str:
    return cell.replace("*", "").strip()


def parse(text: str) -> dict:
    t1 = M.tables(M.section(text, "1."))
    years = []
    for r in (t1[0][1:] if t1 else []):
        if r and r[0] != "—" and len(r) >= 11:
            years.append({"year": r[0], "content": r[9], "themes_cell": r[10],
                          "themes": [f"T{m}" for m in THEME_ID.findall(r[10])]})
    t3 = M.tables(M.section(text, "3."))
    themes = []
    for r in (t3[0][1:] if t3 else []):
        if len(r) >= 4 and _plain(r[1]) not in NONE:
            themes.append({"id": r[0], "name": _plain(r[1]), "trend": _plain(r[2]), "basis": r[3]})
    s4 = _kv(M.section(text, "4."))
    mtp = s4.get("中期経営計画の重点分野・投資計画", ["", ""])
    plans = [{"label": k, "text": v[0], "class": _plain(v[1]) if len(v) > 1 else ""}
             for k, v in s4.items() if "の設備計画 →" in k]
    t2 = M.tables(M.section(text, "2."))
    points = [{"year": r[0], "kind": r[1], "background": r[3]} for r in (t2[0][1:] if t2 else []) if len(r) >= 4
              and r[0] != "—"]
    handoff = {k: v[0] for k, v in _kv(M.section(text, "8.")).items()}
    return {"years": years, "themes": themes, "mtp_text": mtp[0], "mtp_class": _plain(mtp[1]) if len(mtp) > 1 else "",
            "plans": plans, "points": points, "report_points": handoff.get("レポートで使う要点", ""),
            "triggers": handoff.get("評価が変わる条件", ""),
            "changes": M.bullets(M.section(text, "9.")), "gaps": M.bullets(M.section(text, "10."))}


def year_themes(parsed: dict) -> dict[str, list[str]]:
    """{year: [theme names]} from the 1章 IDs (names from 3章, so a renamed theme keeps its continuity)."""
    names = {t["id"]: t["name"] for t in parsed["themes"]}
    return {y["year"]: [names[i] for i in y["themes"] if i in names] for y in parsed["years"]}


def classes(parsed: dict) -> dict:
    return {"year_themes": year_themes(parsed), "mtp_class": parsed["mtp_class"],
            "outcomes": [p["class"] for p in parsed["plans"]], "trend_classes": [t["trend"] for t in parsed["themes"]]}


# ---------- checks ----------

def _check_classes(p: dict, expected_years: list[str], expected_points: int) -> list[str]:
    issues = []
    if [y["year"] for y in p["years"]] != expected_years:
        issues.append("1章の年度がスクリプトの表と違う。行を足したり消したりしない")
    if len(p["points"]) != expected_points:
        issues.append("2章の変化点の行がスクリプトの抽出と違う。行を足したり消したりしない")
    ids = {t["id"] for t in p["themes"]}
    for y in p["years"]:
        if M.is_blank(y["content"]):
            issues.append(f"1章 {y['year']}: 主な内容が空")
        unknown = [i for i in y["themes"] if i not in ids]
        if unknown:
            issues.append(f"1章 {y['year']}: 3章に無いテーマの ID（{'、'.join(unknown)}）")
        if not y["themes"] and _plain(y["themes_cell"]) not in NONE:
            issues.append(f"1章 {y['year']}: 主なテーマは T1〜T5 の ID か「—」で書く（今: 「{y['themes_cell']}」）")
    for t in p["themes"]:
        if t["trend"] not in IV.TREND_CLASSES:
            issues.append(f"3章 {t['id']}: 潮流との照合は {' / '.join(IV.TREND_CLASSES)} のどれか1語（今: 「{t['trend']}」）")
        if M.is_blank(t["basis"]):
            issues.append(f"3章 {t['id']}: 根拠が空")
    if p["mtp_class"] not in IV.PLAN_CLASSES:
        issues.append(f"4章 中期経営計画: 分類は {' / '.join(IV.PLAN_CLASSES)} のどれか1語（今: 「{p['mtp_class']}」）")
    for plan in p["plans"]:
        if plan["class"] not in IV.PLAN_OUTCOMES:
            issues.append(f"4章 {plan['label']}: 分類は {' / '.join(IV.PLAN_OUTCOMES)} のどれか1語（今: 「{plan['class']}」）")
    for point in p["points"]:
        if M.is_blank(point["background"]):
            issues.append(f"2章 {point['year']} {point['kind']}: 背景が空")
    return issues


def _written(p: dict) -> list[tuple[str, str]]:
    cells = [(f"1章 {y['year']}", y["content"]) for y in p["years"]]
    cells += [(f"2章 {x['year']}", x["background"]) for x in p["points"]]
    cells += [(f"3章 {t['id']}", f"{t['name']} {t['basis']}") for t in p["themes"]]
    cells += [("4章 中期経営計画", p["mtp_text"])] + [(f"4章 {x['label']}", x["text"]) for x in p["plans"]]
    return cells + [("8. レポートで使う要点", p["report_points"]), ("8. 評価が変わる条件", p["triggers"])]


def check_numbers(p: dict, allowed_text: str) -> list[str]:
    allowed = _numbers(allowed_text) | REFERENCE_NUMBERS
    issues = []
    for label, cell in _written(p):
        missing = sorted(n for n in _numbers(cell, UNIT_NUMBER) if n not in allowed)
        if missing:
            issues.append(f"{label}: brief・md の表に無い数値（{'、'.join(f'{n:g}' for n in missing[:6])}）。"
                          "brief にある数値だけを引用する")
    return issues


def validate(text: str, template: str, c: dict, allowed_text: str | None = None) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues
    p = parse(text)
    issues = [f"{label}が空" for label, value in (("8. レポートで使う要点", p["report_points"]),
                                                  ("8. 評価が変わる条件", p["triggers"])) if M.is_blank(value)]
    issues += _check_classes(p, [r["year"] for r in c["rows"]], len(c["points"]))
    if allowed_text is not None:
        issues += check_numbers(p, allowed_text)
    if not p["changes"]:
        issues.append("9. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("10. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def conclusion_section(c: dict) -> str:
    a = c["axes"]
    rows = [("① 投資効率", "efficiency"), ("② 中計との整合", "plan"), ("③ 潮流との整合", "trend"), ("④ 競合比較", "peer"),
            ("⑤ 失敗の履歴", "failure"), ("⑥ 資金と規律", "discipline")]
    lines = ["| 項目 | 内容 |", "|---|---|"]
    lines += [f"| {label} | {a[k]['rating']}: {a[k]['sentence']} |" for label, k in rows]
    lines.append(f"| 投資の質 | **{c['verdict']}**: {c['why']} |")
    return "\n".join(lines)


def _replace_line(text: str, label: str, value: str) -> str:
    return re.sub(rf"^\| {re.escape(label)} \|.*$", f"| {label} | {value} |", text, count=1, flags=re.M)


def apply_conclusion(text: str, c: dict) -> str:
    text = _replace_line(text, "潮流との整合（build が集計）", f"{c['axes']['trend']['rating']}: {c['axes']['trend']['sentence']}")
    text = _replace_line(text, "中計との整合（build が集計）", f"{c['axes']['plan']['rating']}: {c['axes']['plan']['sentence']}")
    text = re.sub(r"\n\n新しい投資テーマ（build が 1章の主なテーマから抽出）: [^\n]*", "", text)  # a rebuild replaces it
    new_themes = [p for p in c["points"] if p["kind"] == "新しい投資テーマ"]
    if new_themes:
        note = "新しい投資テーマ（build が 1章の主なテーマから抽出）: " + "、".join(f"{p['year']} {p['text']}" for p in new_themes)
        text = text.replace(POINT_NOTE, POINT_NOTE + "\n\n" + note, 1)
    return replace_section(text, "7.", conclusion_section(c))
