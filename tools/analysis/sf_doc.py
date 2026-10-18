"""{date}_safety.md: skeleton, parse, checks and the conclusion (安全性 良好/普通/懸念/判定保留).

Every number and every judgement of 企業分析フレームワーク.md 2-3 comes from sf_metrics; the writer only fills
the background of the numbers (1 水準の背景, 3 背景 per year, 5 引き継ぎ, 6, 7).
build recomputes the candidates from the raw, so an edited table in the md cannot change the conclusion.
"""
from __future__ import annotations

from string import Template

import mdparse as M
from ff_doc import FIXED_MARK, _check_words, replace_section
from sf_metrics import CLEAR, DEBT_MATERIAL, MATCH_MONTHS, NAMES, UNKNOWN, fmt, money
from validate import check_fill, check_structure, check_tables

UNKNOWN_BACKGROUND = "不明"


# ---------- tables ----------

def level_table_rows(s1: dict) -> str:
    rows = []
    for i in s1["items"]:
        peer = fmt(i["key"], i["peer_avg"]) if i["peer_avg"] is not None else "—（比較できる競合なし）"
        mark = FIXED_MARK if i["rating"] != UNKNOWN else ""
        rows.append(f"| {i['name']} | {fmt(i['key'], i['value'])} | {i['target']} | {peer} | "
                    f"{i['rating']}{mark}: {i['basis']} |")
    free = "実質無借金（D/E をクリアとみなす）" if s1["debt_free"] else "プラスでない、または有利子負債が不明"
    rows.append(f"| ネットキャッシュ（{s1['unit']}） | {money(s1['net_cash'])} | プラスなら実質無借金 | — | {free} |")
    return "\n".join(rows)


def _cells(row: dict) -> str:
    return " | ".join(fmt(k, row[k]) for k in ("equity_ratio", "de", "current_ratio"))


def peer_table_rows(name: str, s1: dict) -> str:
    own = s1["own"]
    lines = [f"| **{name}** | {s1['year']} | {_cells(own) if own else '— | — | —'} | "
             f"{money(own['net_cash']) if own else '—'} | 自社 |"]
    for p in s1["peers"]:
        lines.append(f"| {p['name']} | {p['year']} | {_cells(p)} | {money(p['net_cash'])} | "
                     f"{'一次' if p['primary'] else '二次を含む'} |")
    if s1["peers"]:
        avg = s1["peer_avg"]
        lines.append(f"| 競合の単純平均 | — | {' | '.join(fmt(k, avg[k]) for k in NAMES)} | — | "
                     "スクリプトが計算（自社を除く。値のある競合だけ） |")
    else:
        lines.append(f"| 競合 | — | — | — | — | — | 自社の直近期（±{MATCH_MONTHS}か月）に合う競合の行が無い |")
    return "\n".join(lines)


def trend_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | — | — | — | 総資産・自己資本・流動資産の時系列が raw に無い |"
    return "\n".join(
        f"| {r['year']} | {money(r['total_assets'])} | {money(r['equity'])} | {fmt('equity_ratio', r['equity_ratio'])} | "
        f"{money(r['debt'])} | {fmt('de', r['de'])} | {fmt('current_ratio', r['current_ratio'])} | "
        f"{money(r['cash'])} | {money(r['net_cash'])} |" for r in rows[-10:])


def purpose_table_rows(s3: dict) -> str:
    if not s3["years"]:
        reason = ("有利子負債の推移が取れない" if s3["rating"] == UNKNOWN
                  else f"有利子負債が総資産の{DEBT_MATERIAL * 100:.0f}%以上増えた年なし")
        return f"| — | — | — | — | — | — | — | — | 該当なし（{reason}） |"
    return "\n".join(
        f"| {y['year']} | {money(y['increase'])}（{money(y['from'])}→{money(y['to'])}） | {money(y['cfo'])} | "
        f"{money(y['cfi'])} | {money(y['cff'])} | {money(y['net_income'])} | {y['after'] or '—'} | "
        f"{y['kind']}（{y['rating']}） | <!-- FILL:bg-{y['year']} この年に借り入れた理由を1文（brief の財務時系列・"
        f"有報・資本政策の記述、設備投資・M&A の内容から）。分からなければ「{UNKNOWN_BACKGROUND}（brief に記載なし）」 --> |"
        for y in s3["years"])


def rating_cell(rating: str, basis: str) -> str:
    return f"—（{basis}）" if rating == UNKNOWN else f"{rating}{FIXED_MARK}: {basis}"


def step1_cell(s1: dict) -> str:
    c = s1["counts"]
    return (f"クリア {c[CLEAR]}・未達 {c['未達']}・不明 {c[UNKNOWN]}{FIXED_MARK}"
            + ("（ネットキャッシュがプラスで実質無借金）" if s1["debt_free"] else ""))


def level_note(s1: dict) -> str:
    excluded = ("業種が銀行・保険・証券・不動産・リースなどのため、目安は使わず同業平均だけと比べる。"
                if s1["excluded"] else "")
    return (f"注: {excluded}自己資本比率 = 自己資本 ÷ 総資産、D/E レシオ = 有利子負債 ÷ 自己資本、流動比率 = 流動資産 ÷ "
            "流動負債、ネットキャッシュ = 現金及び現金同等物（無ければ現金及び預金）− 有利子負債。いずれも期末残高。"
            "自己資本は「自己資本」の記載値、無い年は 総資産 × 自己資本比率（純資産は使わない）。有利子負債は「有利子負債」"
            "の行、無ければ借入金・社債の内訳の合計（リース債務は含まない）で、どちらも無い年は不明（0 とみなさない）。"
            "目安を下回っても同業平均と同等以上（自己資本比率 −2pt、流動比率 −5pt、D/E ×1.05 以内）ならクリア。"
            f"同業平均は決算期が自社の直近期から{MATCH_MONTHS}か月以内の競合の単純平均。")


def render_skeleton(template: str, values: dict, cands: dict) -> str:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    filled = dict(values, unit=s1["unit"], level_rows=level_table_rows(s1),
                  peer_rows=peer_table_rows(values["company"], s1),
                  step1_rating=step1_cell(s1), level_note=level_note(s1),
                  trend_rows=trend_table_rows(cands["rows"]), step2_rating=rating_cell(s2["rating"], s2["basis"]),
                  purpose_rows=purpose_table_rows(s3), step3_rating=rating_cell(s3["rating"], s3["basis"]))
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
    purpose_tables = M.tables(M.section(text, "3."))
    years = [{"year": r[0], "kind": r[7] if len(r) > 7 else "", "background": r[8] if len(r) > 8 else ""}
             for r in (purpose_tables[0][1:] if purpose_tables else []) if r and r[0] != "—"]
    handoff = _kv(M.section(text, "5."))
    return {
        "level_background": _kv(M.section(text, "1.")).get("水準の背景", ""), "purpose_by_year": years,
        "report_points": handoff.get("レポートで使う要点", ""), "policy": handoff.get("財務方針・資本政策との関係", ""),
        "step2_checks": handoff.get("STEP 2 の他の分析で確かめること", ""), "triggers": handoff.get("評価が変わる条件", ""),
        "changes": M.bullets(M.section(text, "6.")), "gaps": M.bullets(M.section(text, "7.")),
    }


# ---------- checks ----------

def _required_cells(p: dict) -> list[tuple[str, str]]:
    return [("1. 水準の背景", p["level_background"]), ("5. レポートで使う要点", p["report_points"]),
            ("5. 財務方針・資本政策との関係", p["policy"]), ("5. STEP 2 の他の分析で確かめること", p["step2_checks"]),
            ("5. 評価が変わる条件", p["triggers"])]


def _check_years(parsed: dict, expected: list[dict]) -> list[str]:
    got = [y["year"] for y in parsed["purpose_by_year"]]
    want = [y["year"] for y in expected]
    if got != want:
        return [f"3章の年度がスクリプトの抽出と違う（今: {'、'.join(got) or 'なし'} / 期待: {'、'.join(want) or 'なし'}）。"
                "行を足したり消したりしない"]
    return [f"3章 {y['year']}: 背景が空" for y in parsed["purpose_by_year"] if M.is_blank(y["background"])]


def validate(text: str, template: str, expected_years: list[dict]) -> list[str]:
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    p = parse(text)
    issues = [f"{label}が空" for label, value in _required_cells(p) if M.is_blank(value)]
    issues += _check_years(p, expected_years)
    if not p["changes"]:
        issues.append("6. 前回からの変更点に箇条書きが無い")
    if not p["gaps"]:
        issues.append("7. 判定に効く欠損に箇条書きが無い（無ければ「- なし」）")
    return issues + _check_words(text)


# ---------- conclusion ----------

def conclusion_section(cands: dict) -> str:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    return "\n".join([
        "| 項目 | 内容 |", "|---|---|",
        f"| 手順1 現状の水準 | {s1['sentence']} |",
        f"| 手順2 推移 | {s2['sentence']} |",
        f"| 手順3 借入の目的 | {s3['sentence']} |",
        f"| 境界に近い比較 | {'。'.join(cands['borderline']) or 'なし'} |",
        f"| 安全性 | **{cands['verdict']}**: {cands['why']} |"])


def apply_conclusion(text: str, cands: dict) -> str:
    return replace_section(text, "4.", conclusion_section(cands))


def flags(parsed: dict, cands: dict) -> dict:
    """Items the completion report lists."""
    return {"unknown_backgrounds": [y["year"] for y in parsed["purpose_by_year"]
                                    if y["background"].strip().startswith(UNKNOWN_BACKGROUND)],
            "debt_years": [y["year"] for y in cands["step3"]["years"]], "borderline": cands["borderline"]}
