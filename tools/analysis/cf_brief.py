"""{date}_brief.md: everything the cash-flow writer needs, in one file.

The numbers and the judgements are already in the md skeleton; the brief carries what explains them (the notes
around the CF tables, capital expenditure, the shareholder-return and capital policy). The writer reads only
this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

import re
from dataclasses import replace

import mdparse as M
from cf_doc import main_causes
from cf_paths import Company
from ff_inputs import Found, excerpt

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("営業CF・投資CF・利益の質の背景の材料（1〜3章）", ("cf_table", "cf_section", "statements", "capex")),
    ("株主還元・資本政策の材料（5・8章）", ("self_return", "capital", "targets", "policy")),
)
PROSE_ONLY = ("cf_table", "cf_section", "statements", "self_return")  # the numbers are in the md; keep the notes
CAPEX_SUBSECTION = "設備投資"
COVERED_BY_CAPITAL = ("資本政策", "株主還元")  # the yuho policy section is skipped when the plan section has these
EMPTY_HEADING = re.compile(r"^\*\*[^*\n]+\*\*\s*\n(?=\s*(?:\*\*|$))", re.M)  # a bold heading left with no body
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    ratings = "、".join(f"手順{i} {(r.get(f'step{i}') or {}).get('rating') or '—'}" for i in range(1, 6))
    return [f"- 前回の結果: {date}（キャッシュフロー {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - {ratings}"]


def _profitability_line(profitability: tuple[str, dict] | None) -> list[str]:
    if not profitability:
        return ["- 収益性分析: 完成済みの結果が無い（7章は未実施）"]
    date, r = profitability
    lines = [f"- 収益性分析: {date}（収益性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）"]
    checks = (r.get("handoff") or {}).get("step2_checks")
    if checks:
        lines.append(f"  - キャッシュフローで確かめること（収益性分析から）: {checks}")
    return lines


OTHER_LABELS = {"growth": ("成長性分析", "成長性"), "safety": ("安全性分析", "安全性")}


def _other_lines(others: dict) -> list[str]:
    lines = []
    for name, (label, word) in OTHER_LABELS.items():
        result = others.get(name)
        if not result:
            lines.append(f"- {label}: 完成済みの結果が無い（7章の該当行は未実施）")
            continue
        date, r = result
        lines.append(f"- {label}: {date}（{word} {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）")
        checks = (r.get("handoff") or {}).get("step2_checks")
        if checks:
            lines.append(f"  - STEP 2 の他の分析で確かめること（{label}から）: {checks}")
    return lines


def _outlook_line(outlook: dict) -> str:
    if not outlook.get("path"):
        return "- 地合い: 完成済みの outlook.md が無い（キャッシュフローの判断には使わない）"
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。キャッシュフローの判断には使わない"


def _numbers_lines(cands: dict) -> list[str]:
    lines = [f"- キャッシュフローの候補（build が確定する）: {cands['verdict']} — {cands['why']}"]
    lines += [f"- 手順{i}: {cands[f'step{i}']['sentence']}" for i in range(1, 6)]
    negative = cands["step1"]["negative_years"]
    if negative:
        lines.append(f"- 背景を書く年（営業CF がマイナス。md の 1章）: {'、'.join(negative)}")
    s3 = cands["step3"]
    if s3["ratio"] is not None:
        lines += [f"- 手順3の補足（md の 3章。引用するだけで計算しない）: 直近の推移 {s3['recent_text']}。"
                  f"基準を下回った年 {s3['below_text']}。{s3['without_oldest_text']}",
                  f"- 純利益と営業CF の差の主因（md の 3章の表）: {main_causes(s3['gap_rows'])}"]
    if s3["flagged"]:
        lines.append(f"- 要確認（md の 3章）: {'・'.join(s3['flagged'])}の増加率が売上高を上回る")
    if cands["borderline"]:
        lines.append("- 境界に近い比較（材料の誤差で判定が1段階動きうる。8章の「評価が変わる条件」に使う）: "
                     + "。".join(cands["borderline"]))
    lines.append("- 年度ごとの表は md の 1〜5章にある（同じ表をここには載せない）")
    return lines


def _prose(body: str) -> str:
    """The body without its tables; sub-headings left with nothing under them are dropped."""
    text = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("|"))
    text = re.sub(r"^#{3,6}\s+(.+)$", r"**\1**", text, flags=re.M)
    previous = None
    while previous != text:
        previous, text = text, EMPTY_HEADING.sub("", re.sub(r"\n{3,}", "\n\n", text))
    return text.strip()


def _section(f: Found, company: Company) -> str:
    if f.spec.key == "capex" and f.body:
        hit = M.section_by_title(f.body, CAPEX_SUBSECTION, level=3)  # only the 設備投資 part, not the staff tables
        if hit and hit[1].strip():
            return excerpt(replace(f, heading=f"{f.heading} / {hit[0]}", body=hit[1]), company)
    if f.spec.key in PROSE_ONLY and f.body:
        return excerpt(replace(f, body=_prose(f.body) or "—（表のみ。数値は md の表を見る）"), company)
    return excerpt(f, company)


def _skipped(key: str, found: dict[str, Found], shown: set[tuple[str, str]]) -> str | None:
    """Why a section is left out: the same raw section already shown, or the yuho policy repeating the plan."""
    f = found[key]
    if f.path is not None and (str(f.path), f.heading) in shown:
        return "（上と同じ raw の節のため省略）"
    capital = found["capital"]
    if key == "policy" and capital.status == "ok" and all(w in capital.body for w in COVERED_BY_CAPITAL):
        return "（中期経営計画の節と同じ内容のため省略）"
    return None


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, profitability: tuple[str, dict] | None, outlook: dict,
                 warnings: list[str] = (), others: dict | None = None) -> str:
    out = [f"# キャッシュフロー分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（cash_flow.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV を開かない）。数値と判定はスクリプトが md に記入済み。",
           "> 書くのは数値の背景と解釈だけ。新しい計算をしない。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた可能性。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += (_previous_lines(previous) + _profitability_line(profitability) + _other_lines(others or {})
            + [_outlook_line(outlook)])
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers_lines(cands)
    shown: set[tuple[str, str]] = set()
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            f = found[key]
            skipped = _skipped(key, found, shown)
            out += ["", f"### {f.spec.label}", "", skipped or _section(f, company)]
            if f.path is not None:
                shown.add((str(f.path), f.heading))
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
