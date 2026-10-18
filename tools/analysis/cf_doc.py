"""{date}_cash-flow.md: skeleton, parse, checks and the conclusion (キャッシュフロー 良好/普通/懸念/判定保留).

Every number and every judgement of 企業分析フレームワーク.md 2-4 comes from cf_metrics; the writer only fills
the background of the numbers (1 営業CF マイナスの年, 2 投資の中身, 3 利益と営業CF の差, 7 コメント, 8 引き継ぎ,
9, 10). build recomputes the candidates from the raw, so an edited table in the md cannot change the conclusion.
"""
from __future__ import annotations

from string import Template

import mdparse as M
from cf_metrics import FAIR_RATIO, GOOD_RATIO, WINDOW, fmt_amount
from ff_doc import FIXED_MARK, _check_words, replace_section
from validate import check_fill, check_structure, check_tables

UNKNOWN_BACKGROUND = "不明"
NO_NEGATIVE = "該当なし（営業CF がマイナスの年なし）"
AMOUNT_NOTE = ("注: 金額は百万円（米国株は raw の通貨単位のまま）。FCF = 営業CF + 投資CF。各年の値は 決算短信・EDINET の CSV → "
               "有報 → 財務時系列の表 の順に一次の値を採用し、集計サイトの値（二次）は一次が無い年だけに使う。")


# ---------- tables ----------

def _ratio(value: float | None) -> str:
    return "—（純損失）" if value is None else f"{value:.2f}倍"


def cf_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | 営業CF の時系列が raw に無い |"
    return "\n".join(
        f"| {r['year']} | {fmt_amount(r['cfo'])} | {fmt_amount(r['cfi'])} | {fmt_amount(r['cff'])} | "
        f"{fmt_amount(r['fcf'])} | {fmt_amount(r['net_income'])} | "
        f"{r['source']}{'' if r['primary'] else '（二次を含む）'} |" for r in rows)


def fcf_table_rows(rows: list[dict], window: list[str]) -> str:
    picked = [r for r in rows if r["year"] in window] or rows[-WINDOW:]
    if not picked:
        return "| — | — | — | — | — | — |"
    return "\n".join(
        f"| {r['year']} | {fmt_amount(r['cfo'])} | {fmt_amount(r['cfi'])} | {fmt_amount(r['fcf'])} | "
        f"{fmt_amount(r['capex'])} | {fmt_amount(r['acquisitions'])} |" for r in picked)


def quality_table_rows(rows: list[dict], window: list[str]) -> str:
    picked = [r for r in rows if r["year"] in window]
    if not picked:
        return "| — | — | — | 営業CF と当期純利益が揃った年が無い |"
    return "\n".join(f"| {r['year']} | {fmt_amount(r['cfo'])} | {fmt_amount(r['net_income'])} | "
                     f"{_ratio(r['ratio'])} |" for r in picked)


def wc_table_rows(wc: list[dict]) -> str:
    lines = []
    for w in wc:
        if w["last_year"] is None:
            lines.append(f"| {w['name']} | — | {fmt_amount(w['first'])} | — | —（2時点が取れない） |")
            continue
        growth = "—（期初か期末がゼロ以下）" if w["cagr"] is None else f"{w['cagr']:+.1f}%"
        lines.append(f"| {w['name']} | {w['first_year']}〜{w['last_year']} | {fmt_amount(w['first'])} | "
                     f"{fmt_amount(w['last'])} | {growth} |")
    return "\n".join(lines)


def pattern_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | 営業・投資・財務CF の揃った年が無い | — |"
    return "\n".join(f"| {r['year']} | {r['signs'][0]} | {r['signs'][1]} | {r['signs'][2]} | {r['state']} | "
                     f"{r['rating']} |" for r in rows)


def return_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — |"
    return "\n".join(f"| {r['year']} | {fmt_amount(r['dividends'])} | {fmt_amount(r['buybacks'])} | "
                     f"{fmt_amount(r['total'])} | {fmt_amount(r['fcf'])} | {fmt_amount(r['gap'])} |" for r in rows)


def relation_table_rows(rows: list[dict]) -> str:
    return "\n".join(f"| {r['check']} | {r['step2']} | {r['cash']} | {r['result']} |" for r in rows)


def rating_cell(rating: str | None, basis: str) -> str:
    return f"—（{basis}）" if rating is None else f"{rating}{FIXED_MARK}: {basis}"


def negative_cell(s1: dict) -> str:
    if not s1["negative_years"]:
        return NO_NEGATIVE
    years = "、".join(s1["negative_years"])
    return (f"<!-- FILL:negative-cfo {years} に営業CF がマイナスになった理由を年ごとに1文（brief の CF 計算書・"
            f"事業・特別損益の記述から。例: 大型案件の売上債権の増加、先行投資による営業損失）。分からなければ"
            f"「{UNKNOWN_BACKGROUND}（brief に記載なし）」 -->")


# ---------- skeleton ----------

def step1_summary(s1: dict) -> str:
    if s1["rating"] is None:
        return f"—（{s1['basis']}）"
    return (f"対象 {s1['years']} 年（{s1['first']}〜{s1['last']}）: マイナスの年 "
            f"{'、'.join(s1['negative_years']) or 'なし'}")


def step2_summary(s2: dict) -> str:
    if s2["rating"] is None:
        return f"—（{s2['basis']}）"
    return (f"{s2['window'][0]}〜{s2['window'][-1]} の FCF 累計 {fmt_amount(s2['total'])}、"
            f"プラスの年 {s2['positive_years']}/{WINDOW}")


def step3_summary(s3: dict) -> str:
    if s3["ratio"] is None:
        return f"—（{s3['basis']}）"
    flagged = f"。要確認: {'・'.join(s3['flagged'])}の増加率が売上高を上回る" if s3["flagged"] else ""
    return (f"営業CF対純利益比率 {s3['ratio']:.2f}倍（{s3['method']}。{GOOD_RATIO:.1f}倍以上 良好 / "
            f"{FAIR_RATIO:.1f}倍以上 普通）{flagged}")


def render_skeleton(template: str, values: dict, cands: dict, relation: list[dict]) -> str:
    s1, s2, s3, s4, s5 = (cands[k] for k in ("step1", "step2", "step3", "step4", "step5"))
    rows = cands["rows"]
    filled = dict(values,
                  cf_rows=cf_table_rows(rows), step1_summary=step1_summary(s1),
                  step1_rating=rating_cell(s1["rating"], s1["basis"]), negative_cfo=negative_cell(s1),
                  amount_note=AMOUNT_NOTE,
                  fcf_rows=fcf_table_rows(rows, s2["window"]), step2_summary=step2_summary(s2),
                  growth_check=s2["growth"]["text"] if s2["growth"] else "—（FCF の5年累計を計算できない）",
                  step2_rating=rating_cell(s2["rating"], s2["basis"]),
                  quality_rows=quality_table_rows(rows, s3["window"]),
                  wc_rows=wc_table_rows(s3["working_capital"]), step3_summary=step3_summary(s3),
                  step3_rating=(f"判定不能: {s3['basis']}" if s3["loss"] else rating_cell(s3["rating"], s3["basis"])),
                  pattern_rows=pattern_table_rows(s4["rows"]), step4_rating=rating_cell(s4["rating"], s4["basis"]),
                  return_rows=return_table_rows(s5["rows"]),
                  step5_rating=f"{s5['rating']}{FIXED_MARK}: {s5['basis']}",
                  relation_rows=relation_table_rows(relation))
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
    handoff = _kv(M.section(text, "8."))
    return {
        "negative_cfo": _kv(M.section(text, "1.")).get("営業CF がマイナスの年の背景", ""),
        "investment": _kv(M.section(text, "2.")).get("投資の中身", ""),
        "quality_gap": _kv(M.section(text, "3.")).get("利益と営業CF の差の背景", ""),
        "relation_comment": _kv(M.section(text, "7.")).get("コメント", ""),
        "report_points": handoff.get("レポートで使う要点", ""),
        "capital_policy": handoff.get("会社の資本政策との関係", ""),
        "step2_checks": handoff.get("STEP 2 の他の分析で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "9.")), "gaps": M.bullets(M.section(text, "10.")),
    }


# ---------- checks ----------

def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("1. 営業CF がマイナスの年の背景", p["negative_cfo"]), ("2. 投資の中身", p["investment"]),
            ("3. 利益と営業CF の差の背景", p["quality_gap"]), ("7. コメント", p["relation_comment"]),
            ("8. レポートで使う要点", p["report_points"]), ("8. 会社の資本政策との関係", p["capital_policy"]),
            ("8. STEP 2 の他の分析で確かめること", p["step2_checks"]), ("8. 評価が変わる条件", p["triggers"])]


def validate(text: str, template: str) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    if not p["changes"]:
        issues.append("9. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("10. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def conclusion_section(cands: dict) -> str:
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 手順1 営業CF の安定性 | {cands['step1']['sentence']} |",
        f"| 手順2 FCF の創出力 | {cands['step2']['sentence']} |",
        f"| 手順3 利益の質 | {cands['step3']['sentence']} |",
        f"| 手順4 CF パターン | {cands['step4']['sentence']} |",
        f"| 手順5 株主還元の持続性 | {cands['step5']['sentence']} |",
        f"| 境界に近い比較 | {'。'.join(cands['borderline']) or 'なし'} |",
        f"| キャッシュフロー | **{cands['verdict']}**: {cands['why']} |"])


def apply_conclusion(text: str, cands: dict) -> str:
    return replace_section(text, "6.", conclusion_section(cands))


def flags(parsed: dict, cands: dict) -> dict:
    """Items the completion report lists."""
    unknown = [label for label, value in (("営業CF がマイナスの年の背景", parsed["negative_cfo"]),
                                          ("投資の中身", parsed["investment"]),
                                          ("利益と営業CF の差の背景", parsed["quality_gap"]))
               if value.strip().startswith(UNKNOWN_BACKGROUND)]
    return {"unknown_backgrounds": unknown, "borderline": cands["borderline"],
            "flagged_working_capital": cands["step3"]["flagged"]}
