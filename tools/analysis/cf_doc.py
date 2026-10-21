"""{date}_cash-flow.md: skeleton, parse, checks and the conclusion (キャッシュフロー 良好/普通/懸念/判定保留).

Every number and every judgement of 企業分析フレームワーク.md 2-4 comes from cf_metrics; the writer only fills
the background of the numbers (1 営業CF マイナスの年, 2 投資の中身, 3 利益と営業CF の差, 7 コメント, 8 引き継ぎ,
9, 10). build recomputes the candidates from the raw, so an edited table in the md cannot change the conclusion.
"""
from __future__ import annotations

import re
from string import Template

import mdparse as M
from cf_metrics import FAIR_RATIO, GAP_ITEMS, GOOD_RATIO, WINDOW, fmt_amount
from ff_doc import FIXED_MARK, _check_words, replace_section
from validate import check_fill, check_structure, check_tables

UNKNOWN_BACKGROUND = "不明"
NO_NEGATIVE = "該当なし（営業CF がマイナスの年なし）"
ZERO_FILLED = "0（記載なし）"
NO_BREAKDOWN = "内訳なし（CF 計算書の売上債権の増減額が raw に無い）"
# a number the writer typed: 1,994 / 0.77倍 / 23.6% / 392百万円 (years, page numbers and small counts are skipped)
NUMBER = re.compile(r"(?<![\d.,])[△▲\-−+]?\d[\d,]*(?:\.\d+)?(?![\d,])")
APPROXIMATE = re.compile(r"約\s*\d|(?<![契規])約\s*[一二三四五六七八九十][割分]|\d割|[一二三四五六七八九十]割(?!引)")
SMALL_COUNT = 10
DATE_AFTER = "月日期年"  # 3月 / 31日 / 12月期 / 2期 are dates and periods, not amounts
DATE_BEFORE = ("第", "FY", "Q")
# what the writer fills: the 項目 of the 項目 / 内容 rows and the sections that are bullets only
WRITTEN_ROWS = ("営業CF がマイナスの年の背景", "投資の中身", "利益と営業CF の差の背景", "コメント", "レポートで使う要点",
                "会社の資本政策との関係", "STEP 2 の他の分析で確かめること", "評価が変わる条件")
WRITTEN_SECTIONS = ("9", "10")
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


def _return_cell(r: dict, key: str) -> str:
    """A line counted as 0 because the other one is known (記載なし) is shown as such, not as a missing '—'."""
    return ZERO_FILLED if key in r.get("zero_filled", ()) else fmt_amount(r[key])


def return_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — |"
    return "\n".join(f"| {r['year']} | {_return_cell(r, 'dividends')} | {_return_cell(r, 'buybacks')} | "
                     f"{fmt_amount(r['total'])} | {fmt_amount(r['fcf'])} | {fmt_amount(r['gap'])} |" for r in rows)


def gap_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | — | — |"
    lines = []
    for g in rows:
        if g["items"] is None:
            lines.append(f"| {g['year']} | {fmt_amount(g['gap'])} | — | — | — | — | — | {NO_BREAKDOWN} |")
            continue
        cells = " | ".join(fmt_amount(g["items"][k]) for k, _ in GAP_ITEMS)
        lines.append(f"| {g['year']} | {fmt_amount(g['gap'])} | {cells} | {fmt_amount(g['other'])} | "
                     f"{g['main'] or '—（差を説明する項目なし）'} |")
    return "\n".join(lines)


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
    both = (f"5年平均 {s3['average']:.2f}倍・5年累計 {s3['cumulative']:.2f}倍 のうち低い方を採用"
            if s3["average"] is not None else f"5年累計 {s3['cumulative']:.2f}倍")
    return (f"営業CF対純利益比率 {s3['ratio']:.2f}倍（{both}。{GOOD_RATIO:.1f}倍以上 良好 / "
            f"{FAIR_RATIO:.1f}倍以上 普通）{flagged}")


def main_causes(gap_rows: list[dict]) -> str:
    """The main item of each year with a breakdown, for the 3章 summary and the brief."""
    known = [f"{g['year']} {g['main']}" for g in gap_rows if g["items"] is not None and g["main"]]
    missing = [g["year"] for g in gap_rows if g["items"] is None]
    text = "、".join(known) or "—（内訳のある年なし）"
    return text + (f"（内訳なし: {'、'.join(missing)}）" if missing else "")


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
                  gap_rows=gap_table_rows(s3["gap_rows"]), gap_main=main_causes(s3["gap_rows"]),
                  recent=s3["recent_text"], below=s3["below_text"], without_oldest=s3["without_oldest_text"],
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


def _is_label_number(text: str, start: int, end: int) -> bool:
    """A date, a period or a code rather than an amount: 3月31日, 12月期, 第15期, p.27, FY24, 10-K."""
    before, after = text[max(0, start - 2):start], text[end:end + 1]
    return (after in DATE_AFTER and after != "") or before.endswith(DATE_BEFORE) \
        or (before[-1:].isascii() and before[-1:].isalpha()) or (after.isascii() and after.isalpha()) \
        or after == "-" or before.endswith("p.")


def _numbers(text: str) -> set[str]:
    """Amounts in a text, normalised ('1,994' -> '1994', '△352' / '-352' -> '352', '0.770' -> '0.77')."""
    out = set()
    for m in NUMBER.finditer(text):
        if _is_label_number(text, m.start(), m.end()):
            continue
        raw = m.group(0).lstrip("△▲-−+").replace(",", "")
        out.add(raw.rstrip("0").rstrip(".") if "." in raw else raw)
    return out


def _script_part(text: str) -> str:
    """The md without what the writer wrote (the written rows of the 項目 / 内容 tables and the bodies of 9・10章),
    line by line so that a short written value never cuts numbers out of the script's tables."""
    out, section = [], ""
    for line in text.splitlines():
        heading = re.match(r"^##\s+(\d+)\.", line)
        if heading:
            section = heading.group(1)
            out.append(line)
            continue
        cells = M.split_row(line) if line.lstrip().startswith("|") else []
        if section in WRITTEN_SECTIONS or (cells and cells[0] in WRITTEN_ROWS):
            continue
        out.append(line)
    return "\n".join(out)


def _is_counted(number: str) -> bool:
    """Years, page numbers and small counts (2年, 1文) are not checked."""
    if "." in number:
        return True
    value = int(number)
    return value >= SMALL_COUNT and not 1900 <= value <= 2100


def written_cells(parsed: dict) -> list[tuple[str, str]]:
    """(label, text) of everything the writer wrote."""
    return _required_cells(parsed) + [("9. 前回からの変更点", " ".join(parsed["changes"])),
                                      ("10. 判定に効く欠損", " ".join(parsed["gaps"]))]


def check_numbers(text: str, parsed: dict, brief: str) -> list[str]:
    """A number in a written cell must appear in the script's part of the md or in the brief (the writer quotes,
    never computes); approximations (約〜, 〜割) are refused."""
    cells = written_cells(parsed)
    known = _numbers(_script_part(text)) | _numbers(brief)
    issues = []
    for label, value in cells:
        new = sorted(n for n in _numbers(value) - known if _is_counted(n))
        if new:
            issues.append(f"{label}: md の表・brief に無い数値 {'、'.join(new)}（数値は表と brief から引用し、計算しない）")
        if APPROXIMATE.search(value):
            issues.append(f"{label}: 概数（約〜・〜割）を書かない。表の数値をそのまま引用する")
    return issues


def validate(text: str, template: str, brief: str = "") -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    if not p["changes"]:
        issues.append("9. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("10. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + check_numbers(text, p, brief) + _check_words(text)


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
