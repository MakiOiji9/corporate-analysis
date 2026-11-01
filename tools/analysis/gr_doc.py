"""{date}_growth.md: skeleton, parse, checks and the conclusion (成長性 良好/普通/懸念/判定保留).

Every number and every judgement of 企業分析フレームワーク.md 2-2 comes from gr_metrics; the writer fills the
background of the numbers and classifies each decline year (2章: 会社の説明・分類・SWOT との照合). build
recomputes the candidates from the raw, so an edited table in the md cannot change the conclusion; only the
classification of the decline years is taken from the md.
"""
from __future__ import annotations

from string import Template

import re
import unicodedata

import an_fill as AF
import gr_facts as F
import mdparse as M
from ff_doc import FIXED_MARK, _check_words, replace_section
from gr_metrics import CLASSES, HIGH_EPS, HIGH_SALES, PLAN_HIT, RECOVERY_YEARS, decide, fmt_cagr, yoy
from validate import check_fill, check_structure, check_tables

UNKNOWN = "不明"
TEMPORARY = "一時"


# ---------- tables ----------

def _m(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _eps(value: float | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def growth_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | — | 自社の売上高の時系列が raw に無い |"
    sales, op, eps = yoy(rows, "sales"), yoy(rows, "operating_income"), yoy(rows, "eps")
    lines = []
    for r in rows:
        y = r["year"]
        source = r["source"] + ("" if r["primary"] else "（二次）")
        lines.append(f"| {y} | {_m(r['sales'])} | {_pct(sales.get(y))} | {_m(r['operating_income'])} | "
                     f"{_pct(op.get(y))} | {_eps(r['eps'])} | {_pct(eps.get(y))} | {source} |")
    return "\n".join(lines)


def cagr_summary(s1: dict) -> str:
    if not s1["first"]:
        return "—（売上高の時系列が無い）"
    eps_name = "EPS" if s1["eps_key"] == "eps" else "純利益（EPS の代用）"
    return (f"対象 {s1['years']} 年（{s1['first']}〜{s1['last']}）: 売上 {fmt_cagr(s1['sales'])}、営業利益 "
            f"{fmt_cagr(s1['operating_income'])}、{eps_name} {fmt_cagr(s1['eps'])}、純利益 {fmt_cagr(s1['net_income'])}")


def rating_cell(rating: str | None, basis: str) -> str:
    return f"—（{basis}）" if rating is None else f"{rating}{FIXED_MARK}: {basis}"


def growth_note(notes: list[dict]) -> str:
    split = "".join(f"{n['text']}。" for n in notes)
    return (f"注: CAGR =（最終年 ÷ 初年）^(1 ÷ 年数) − 1。売上高と EPS が揃う直近最大10年で計算する。{split}"
            "初年が赤字の指標は CAGR を計算しない。（二次）は集計サイトの値。")


def _metric_text(m: dict) -> str:
    change = f"{m['change']:+.1f}%" if m["change"] is not None else f"{_eps(m['from'])}→{_eps(m['to'])}"
    return f"{m['name']} {change}"


def _recovery_text(m: dict) -> str:
    if m["recovery"] in ("回復", "遅れて回復"):
        return f"{m['name']} {m['recovery']}（{m['recovered']}）"
    return f"{m['name']} {m['recovery']}"


def decline_table_rows(declines: list[dict]) -> str:
    if not declines:
        return "| — | 該当なし（売上高・営業利益・EPS とも前年を下回った年なし） | — | — | — | — |"
    lines = []
    for d in declines:
        y = d["year"]
        lines.append(
            f"| {y} | {'、'.join(_metric_text(m) for m in d['metrics'])} | "
            f"{'、'.join(_recovery_text(m) for m in d['metrics'])} | "
            f"<!-- FILL:reason-{y} 会社が説明する減少の理由を1文（brief の「減収・減益の年の会社説明」・損益の注記・"
            f"プレスリリースから）。無ければ「{UNKNOWN}（brief に記載なし）」 --> | "
            f"<!-- FILL:class-{y} 一時 / 構造 / 不明 のどれか1語だけ。一時: 景気後退・為替・災害・一過性の損失など要因が"
            f"消えれば戻るもの（その後の回復が「未回復」の年には使えない。「未確認（後の年も減少）」は後の減少年の分類が"
            f"判定を決めるので一時にしてよい）。構造: シェア低下・市場縮小・製品の陳腐化など。"
            f"理由が分からなければ不明 --> | "
            f"<!-- FILL:swot-{y} 構造なら SWOT の弱み・脅威のどの項目（brief の SWOT の ID）に当たるかを1文。一時・不明なら"
            f"「—（構造要因ではない）」。SWOT が未実施なら「SWOT 未実施」 --> |")
    return "\n".join(lines)


def decline_note() -> str:
    return (f"注: 減少した指標・その後の回復はスクリプトが記入（減少前の水準に {RECOVERY_YEARS} 年以内に戻れば回復、"
            "それより後なら遅れて回復、戻る年がまだ無ければ未確認）。分類が「構造」の年が1つでもあれば成長性は懸念、"
            "「不明」の年があり他の条件が良好なら判定保留（build が判定）。")


def _rate(value: float | None) -> str:
    return "—" if value is None else f"{value:.0f}%"


def plan_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | 期初予想と実績の組が raw・短信に無い |"
    return "\n".join(
        f"| {r['year']} | {r['metric']} | {_m(r['forecast'])} | {_m(r['actual'])} | {_rate(r['rate'])}"
        f"{'' if r['rate'] >= PLAN_HIT else '（未達）'} | {_rate(r['sales_rate'])} | "
        f"{r['source']}{'' if r['primary'] else '（二次を含む）'} |" for r in rows)


def quality_table_rows(s4: dict) -> str:
    return "\n".join(f"| {c['name']} | {c['detail']} | {c['status']}{FIXED_MARK if c['status'] != '不明' else ''} |"
                     for c in s4["checks"])


def adjusted_cell(s4: dict, s1: dict) -> str:
    adjusted = s4["adjusted"]
    if adjusted is None:
        return "—（M&A・自社株買いによる補正なし）"
    same = "変わらない" if adjusted["rating"] == s1["rating"] else f"{s1['rating']} から変わる"
    return f"{adjusted['sentence']}。手順1の判定は{same}"


def consistency_table_rows(rows: list[dict]) -> str:
    return "\n".join(f"| {r['check']} | {r['step1']} | {r['step2']} | {r['result']} |" for r in rows)


# ---------- skeleton ----------

def render_skeleton(template: str, values: dict, cands: dict, consistency: list[dict]) -> str:
    s1, s3, s4 = cands["step1"], cands["step3"], cands["step4"]
    filled = dict(values,
                  growth_rows=growth_table_rows(cands["rows"]), cagr_summary=cagr_summary(s1),
                  step1_rating=rating_cell(s1["rating"], s1["basis"]), growth_note=growth_note(cands["split_notes"]),
                  progress=F.progress_text(cands["progress"]),
                  decline_rows=decline_table_rows(cands["declines"]), decline_note=decline_note(),
                  plan_rows=plan_table_rows(s3["rows"]), step3_rating=rating_cell(s3["rating"], s3["basis"]),
                  quality_rows=quality_table_rows(s4), adjusted_step1=adjusted_cell(s4, s1),
                  consistency_rows=consistency_table_rows(consistency))
    return Template(template).safe_substitute(filled)


# ---------- fields the script writes (an_fill.prefill) ----------

def _consistency_comment(consistency: list[dict]) -> str | None:
    results = [r["result"] for r in consistency]
    if any(r.startswith(("不整合", "判断できない")) for r in results):
        return None  # whether the company is losing share is the writer's
    if results and all(r.startswith(("未実施", "対象外")) for r in results):
        return "該当する STEP 1 の結論なし"
    return "整合（売上が市場並み以上に伸びている）"


def _report_points(cands: dict) -> str | None:
    if cands["declines"]:
        return None  # the verdict waits for the writer's classification of the decline years
    verdict, why, _ = final(cands, {})
    s1, s3, s4 = cands["step1"], cands["step3"], cands["step4"]
    return AF.joined([f"成長性は{verdict}（{why}）", s1["sentence"], "減収・減益の年なし", s4["sentence"],
                      f"会社計画は{s3['rating']}" if s3["rating"] else ""])


def _step3_hint(cands: dict) -> str:
    s3 = cands["step3"]
    if s3["rating"] is None:
        return "会社計画が無いため実績の CAGR を基準にする"
    if s3["rating"] == "信頼できる":
        return f"会社計画は信頼できる（{s3['basis']}）。STEP 3 では会社計画の成長率をそのまま使える"
    return f"会社計画は割り引いて扱う（{s3['basis']}）。STEP 3 では実績の CAGR か保守的な成長率を使う"


def _step2_checks(cands: dict) -> str:
    s4 = cands["step4"]
    checks = ["成長に伴う運転資本・設備投資が営業CF・FCF を圧迫していないか（キャッシュフロー）",
              "成長投資の資金を借入に頼っていないか（安全性）"]
    if s4["problems"] or s4["unknown"]:
        checks.insert(0, "利益の伸びが売上の伸びに見合い、利益率が保たれているか（収益性）")
    return "、".join(checks)


def _triggers(cands: dict) -> str:
    rating = cands["step1"]["rating"]
    parts = {"高成長": [f"売上 CAGR が{HIGH_SALES:.0f}%を下回るか EPS CAGR が{HIGH_EPS:.0f}%を下回れば安定成長"],
             "安定成長": [f"売上 CAGR が{HIGH_SALES:.0f}%以上かつ EPS CAGR が{HIGH_EPS:.0f}%以上になれば高成長、"
                       "売上か EPS の CAGR がマイナスになれば停滞・縮小"],
             "停滞・縮小": ["売上・EPS とも CAGR がプラスになれば安定成長"]}.get(rating, [])
    parts.append("減収・減益の年に構造要因が見つかれば懸念")
    border = ["境界に近い比較: " + "、".join(cands["borderline"])] if cands["borderline"] else []
    return AF.joined(["、".join(parts)] + border)


def _changes(cands: dict, previous: tuple[str, dict] | None) -> str:
    old = previous[1] if previous else {}
    o1, o3, o4 = old.get("step1") or {}, old.get("step3") or {}, old.get("step4") or {}
    s1 = cands["step1"]
    pairs = [("成長性", old.get("verdict"), final(cands, {})[0])] if not cands["declines"] else []
    pairs += [("手順1", o1.get("rating"), s1["rating"]),
              ("売上 CAGR（%）", o1.get("sales_cagr"), s1["sales"]["value"]),
              ("EPS CAGR（%）", o1.get("eps_cagr"), s1["eps"]["value"]),
              ("減収・減益の年", "、".join(d["year"] for d in old.get("declines") or []) or "なし",
               "、".join(d["year"] for d in cands["declines"]) or "なし"),
              ("手順3", o3.get("rating"), cands["step3"]["rating"]),
              ("成長の質", o4.get("quality"), cands["step4"]["quality"])]
    return AF.changes_bullets(previous, pairs)


def auto_fills(cands: dict, consistency: list[dict], previous: tuple[str, dict] | None, found: dict,
               warnings: list[str]) -> dict[str, str | None]:
    """The FILL fields that follow from the numbers. The decline years' classification, the drivers and the
    mid-term plan are the writer's; so is the report text while the verdict waits for that classification."""
    return {"structural": None if cands["declines"] else "減収・減益の年なし",
            "consistency": _consistency_comment(consistency), "report-points": _report_points(cands),
            "step3-hint": _step3_hint(cands), "step2-checks": _step2_checks(cands), "triggers": _triggers(cands),
            "changes": _changes(cands, previous), "gaps": AF.gaps_bullets(found, warnings)}


# ---------- parse ----------

def _kv(text: str) -> dict[str, str]:
    out = {}
    for table in M.tables(text):
        if table and table[0][:2] == ["項目", "内容"]:
            out.update({row[0]: row[1] if len(row) > 1 else "" for row in table[1:] if row})
    return out


def _class(cell: str) -> str:
    return cell.replace("*", "").strip()


def parse(text: str) -> dict:
    chapter2 = M.section(text, "2.")
    tables = M.tables(chapter2)
    declines = [{"year": r[0], "reason": r[3] if len(r) > 3 else "", "class": _class(r[4]) if len(r) > 4 else "",
                 "swot": r[5] if len(r) > 5 else ""}
                for r in (tables[0][1:] if tables else []) if r and r[0] != "—"]
    handoff = _kv(M.section(text, "7."))
    return {
        "declines": declines, "structural": _kv(chapter2).get("構造要因の評価", ""),
        "mtp": _kv(M.section(text, "3.")).get("中期経営計画の達成状況", ""),
        "drivers": _kv(M.section(text, "4.")).get("成長の背景", ""),
        "consistency_comment": _kv(M.section(text, "6.")).get("コメント", ""),
        "report_points": handoff.get("レポートで使う要点", ""), "step3_hint": handoff.get("STEP 3 の成長率設定への示唆", ""),
        "step2_checks": handoff.get("STEP 2 の他の分析で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "8.")), "gaps": M.bullets(M.section(text, "9.")),
    }


def classes(parsed: dict) -> dict[str, str]:
    return {d["year"]: d["class"] for d in parsed["declines"]}


# ---------- checks ----------

def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("2. 構造要因の評価", p["structural"]), ("3. 中期経営計画の達成状況", p["mtp"]),
            ("4. 成長の背景", p["drivers"]), ("6. コメント", p["consistency_comment"]),
            ("7. レポートで使う要点", p["report_points"]), ("7. STEP 3 の成長率設定への示唆", p["step3_hint"]),
            ("7. STEP 2 の他の分析で確かめること", p["step2_checks"]), ("7. 評価が変わる条件", p["triggers"])]


def _check_declines(parsed: dict, expected: list[dict]) -> list[str]:
    got = [d["year"] for d in parsed["declines"]]
    want = [d["year"] for d in expected]
    if got != want:
        return [f"2章の年度がスクリプトの抽出と違う（今: {'、'.join(got) or 'なし'} / 期待: {'、'.join(want) or 'なし'}）。"
                "行を足したり消したりしない"]
    recovery = {d["year"]: d["recovery"] for d in expected}
    issues = []
    for d in parsed["declines"]:
        if M.is_blank(d["reason"]):
            issues.append(f"2章 {d['year']}: 会社の説明が空")
        if d["class"] not in CLASSES:
            issues.append(f"2章 {d['year']}: 分類は {' / '.join(CLASSES)} のどれか1語（今: 「{d['class']}」）")
        elif d["class"] == TEMPORARY and recovery[d["year"]] == "未回復":
            issues.append(f"2章 {d['year']}: その後の回復が「未回復」の年は一時に分類できない（構造か不明にする）")
        if M.is_blank(d["swot"]):
            issues.append(f"2章 {d['year']}: SWOT との照合が空")
    return issues


UNIT_NUMBER = re.compile(r"(?<![\dp.第])(\d[\d,]*(?:\.\d+)?)\s*(?:%|％|pt|百万円|百万|億円|千円|円|倍|名|社)")
ANY_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
# framework thresholds the writer may name without quoting them
REFERENCE_NUMBERS = {0.0, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0, 50.0, 80.0, 90.0, 100.0}


def _numbers(text: str, pattern: re.Pattern = ANY_NUMBER) -> set[float]:
    out = set()
    for m in pattern.finditer(unicodedata.normalize("NFKC", text)):  # '１２．５％' is 12.5%
        try:
            out.add(round(float(m.group(1 if pattern.groups else 0).replace(",", "")), 2))
        except ValueError:
            continue
    return out


def _written(p: dict) -> list[tuple[str, str]]:
    cells = [(f"2章 {d['year']}", f"{d['reason']} {d['swot']}") for d in p["declines"]] + _required_cells(p)
    return cells + [("8. 前回からの変更点", " ".join(p["changes"])), ("9. 判定に効く欠損", " ".join(p["gaps"]))]


def check_numbers(p: dict, allowed_text: str) -> list[str]:
    """Numbers with a unit in the writer's cells must appear in the brief or in the script's part of the md:
    the writer quotes, it does not compute or bring numbers from elsewhere."""
    allowed = _numbers(allowed_text) | REFERENCE_NUMBERS
    issues = []
    for label, cell in _written(p):
        missing = sorted(n for n in _numbers(cell, UNIT_NUMBER) if n not in allowed)
        if missing:
            shown = "、".join(f"{n:g}" for n in missing[:6])
            issues.append(f"{label}: brief・md の表に無い数値（{shown}）。brief にある数値だけを引用し、計算したり"
                          "他の資料から持ち込んだりしない")
    return issues


def validate(text: str, template: str, expected_declines: list[dict], allowed_text: str | None = None) -> list[str]:
    """allowed_text: the brief and the freshly rendered skeleton (the numbers the writer may quote); None skips
    the number check."""
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_declines(p, expected_declines)
    if allowed_text is not None:
        issues += check_numbers(p, allowed_text)
    if not p["changes"]:
        issues.append("8. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("9. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def step2_sentence(cands: dict, year_classes: dict[str, str]) -> str:
    if not cands["declines"]:
        return "減収・減益の年なし"
    by_class = {c: [y for y, v in year_classes.items() if v == c] for c in CLASSES}
    parts = [f"{c} {'、'.join(by_class[c])}" for c in CLASSES if by_class[c]]
    structural = "構造要因あり" if by_class["構造"] else "構造要因なし"
    return f"減収・減益の年 {len(cands['declines'])} 年（{' / '.join(parts)}）で{structural}"


def final(cands: dict, year_classes: dict[str, str]) -> tuple[str, str, list[str]]:
    """(verdict, why, the reasons it was moved down for being near a line)."""
    return decide(cands["step1"], cands["declines"], cands["step4"], year_classes)


def conclusion_section(cands: dict, year_classes: dict[str, str]) -> str:
    verdict, why, _ = final(cands, year_classes)
    s1, s3, s4 = cands["step1"], cands["step3"], cands["step4"]
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 手順1 成長の水準 | {s1['sentence']} |",
        f"| 手順2 減収・減益の原因 | {step2_sentence(cands, year_classes)} |",
        f"| 手順3 会社計画の信頼性 | {s3['sentence']} |",
        f"| 手順4 成長の質 | {s4['sentence']}{'。' + s4['adjusted']['sentence'] if s4['adjusted'] else ''} |",
        f"| 境界に近い比較 | {'。'.join(cands['borderline']) or 'なし'} |",
        f"| 成長性 | **{verdict}**: {why} |"])


def apply_conclusion(text: str, cands: dict, year_classes: dict[str, str]) -> str:
    return replace_section(text, "5.", conclusion_section(cands, year_classes))


def flags(parsed: dict) -> dict:
    """Items the completion report lists."""
    by_class = {c: [d["year"] for d in parsed["declines"] if d["class"] == c] for c in CLASSES}
    return {"structural_years": by_class["構造"], "temporary_years": by_class["一時"],
            "unknown_years": by_class["不明"],
            "unknown_reasons": [d["year"] for d in parsed["declines"] if d["reason"].strip().startswith(UNKNOWN)]}
