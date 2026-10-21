"""{date}_brief.md: everything the growth writer needs, in one file.

The numbers and the judgements are already in the md skeleton; the brief carries what explains them
(the company's explanation of the decline years, the risks, the SWOT weaknesses and threats, the plan,
M&A, shareholder returns and the business). The writer reads only this file and the skeleton; raw files,
PDFs and CSVs stay closed.
"""
from __future__ import annotations

import re
from dataclasses import replace

import gr_facts as F
from ff_inputs import Found, excerpt
from gr_metrics import fmt_cagr
from gr_paths import Company
from pf_brief import STATUS_LABEL, _outlook_line, _prose

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("減収・減益の年の材料（md の 2章）", ("decline", "self_pl", "risks")),
    ("会社計画の材料（md の 3章）", ("plan", "targets", "mtp_result")),
    ("成長の背景・質の材料（md の 4章）", ("ma", "self_return", "segment", "policy")),
)
PROSE_ONLY = ("self_pl", "plan", "self_return")  # the numbers are already in the md; keep the notes only
SWOT_QUADRANTS = (("W", "弱み"), ("T", "脅威"))
ONLY_WITH_DECLINES = ("risks",)  # structural causes are looked for only when a year fell
SEGMENT_KEEP = re.compile(r"受注|契約形態|販売実績|生産実績|セグメント")
COVERED_BY_TARGETS = ("資本政策", "株主還元")  # the yuho policy section is skipped when the targets section has these


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    s1 = r.get("step1") or {}
    return [f"- 前回の結果: {date}（成長性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - 手順1 {s1.get('rating') or '—'}（売上 CAGR {s1.get('sales_cagr', '—')}%、EPS CAGR "
            f"{s1.get('eps_cagr', '—')}%）、手順3 {(r.get('step3') or {}).get('rating') or '—'}、"
            f"成長の質 {(r.get('step4') or {}).get('quality') or '—'}"]


def _three_c_lines(three_c: tuple[str, dict] | None) -> list[str]:
    if not three_c:
        return ["- 3C分析: 完成済みの結果が無い（整合性チェックは未実施）"]
    date, r = three_c
    growth = r.get("growth") or {}
    return [f"- 3C分析: {date}（勝てる理由 {r.get('verdict', '—')}）",
            f"  - 市場の成長性 {growth.get('rating', '—')}: {growth.get('reason', '—')}"]


def _swot_lines(swot: tuple[str, dict] | None, declines: bool = True) -> list[str]:
    if not declines:
        return ["- SWOT分析: 減収・減益の年が無い、または2年以内に回復しているため、照合する弱み・脅威は省略"
                "（2章の SWOT との照合は「—（構造要因ではない）」）"]
    if not swot:
        return ["- SWOT分析: 完成済みの結果が無い（2章の SWOT との照合は「SWOT 未実施」と書く）"]
    date, r = swot
    lines = [f"- SWOT分析: {date}（SWOT {r.get('verdict', '—')}）。2章で構造要因と照合する弱み・脅威:"]
    quadrants = r.get("quadrants") or {}
    for key, name in SWOT_QUADRANTS:
        items = quadrants.get(key) or []
        if not items:
            lines.append(f"  - {name}: なし")
        for item in items:
            lines.append(f"  - {item.get('id', key)}（{name}、影響度 {item.get('impact', '—')}）: {item.get('fact', '—')}")
    return lines


def _numbers_lines(cands: dict) -> list[str]:
    s1, s3, s4 = cands["step1"], cands["step3"], cands["step4"]
    lines = [f"- 成長性の候補（build が 2章の分類を入れて確定する）: {cands['verdict']} — {cands['why']}",
             f"- 手順1: {s1['sentence']}", f"- 手順3: {s3['sentence']}", f"- 手順4: {s4['sentence']}"]
    if s4["adjusted"]:
        lines.append(f"  - 質の補正: {s4['adjusted']['sentence']}")
    if cands["declines"]:
        lines.append("- 分類する年（売上高・営業利益・EPS のどれかが前年を下回った年。md の 2章）:")
        for d in cands["declines"]:
            metrics = "、".join(f"{m['name']} {m['recovery']}" + (f"（{m['recovered']}）" if m["recovered"] else "")
                               for m in d["metrics"])
            lines.append(f"  - {d['year']}: {metrics}")
    else:
        lines.append("- 減収・減益の年: なし")
    lines.append(f"- 純利益 CAGR（参考）: {fmt_cagr(s1['net_income'])}")
    lines.append(f"- 今期の進捗（md の 3章。STEP 3 の示唆に使う）: {F.progress_text(cands['progress'])}")
    lines.append(f"- {cands['receivables']}（7章の「STEP 2 の他の分析で確かめること」に使う）")
    if cands["downgraded"]:
        lines.append("- 境界に近いため候補を保守的に1段階下げた理由: " + "、".join(cands["downgraded"]))
    if cands["borderline"]:
        lines.append("- 境界に近い比較（材料の誤差で判定が1段階動きうる。7章の「評価が変わる条件」に使う）: "
                     + "。".join(cands["borderline"]))
    lines.append("- 年度ごとの表・計画の達成率は md の 1・3章にある（同じ表をここには載せない）")
    return lines


def _blocks(body: str) -> list[str]:
    return [b for b in re.split(r"\n\s*\n", body) if b.strip()]


def _segment(body: str) -> str:
    """Only the growth-related parts of the business section: orders, contract types, sales and production."""
    kept = [b for b in _blocks(body) if SEGMENT_KEEP.search(b)]
    return "\n\n".join(kept) or "—（受注・契約形態・販売実績の記載なし）"


def _section(f: Found, company: Company) -> str:
    if f.spec.key in PROSE_ONLY and f.body:
        return excerpt(replace(f, body=_prose(f.body) or "—（表のみ。数値は md の表を見る）"), company)
    if f.spec.key == "segment" and f.body:
        return excerpt(replace(f, body=_segment(f.body)), company)
    return excerpt(f, company)


def _skipped(key: str, found: dict[str, Found], declines: bool) -> str | None:
    """Why a section is left out of the brief, or None."""
    if key in ONLY_WITH_DECLINES and not declines:
        return "（減収・減益の年が無い、または2年以内に回復しているため省略）"
    targets = found["targets"]
    if key == "policy" and targets.status == "ok" and all(w in targets.body for w in COVERED_BY_TARGETS):
        return "（中期経営計画の節と同じ内容のため省略）"
    return None


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, three_c: tuple[str, dict] | None,
                 swot: tuple[str, dict] | None, outlook: dict, warnings: list[str] = ()) -> str:
    out = [f"# 成長性分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（growth.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV を開かない）。数値と判定はスクリプトが md に記入済み。",
           "> 書くのは数値の背景と解釈、減収・減益の年の分類（一時 / 構造 / 不明）だけ。新しい計算をしない。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた・補正した可能性。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    # risks and the SWOT weaknesses / threats are material only for a fall that did not come back in time
    declines = any(d["recovery"] != "回復" for d in cands["declines"])
    out += _previous_lines(previous) + _three_c_lines(three_c) + _swot_lines(swot, declines)
    out.append(_outlook_line(outlook).replace("収益性", "成長性"))
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers_lines(cands)
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            skipped = _skipped(key, found, declines)
            out += ["", f"### {found[key].spec.label}", "", skipped or _section(found[key], company)]
        if number == len(CHAPTERS) + 1:
            sga = F.sga_lines(company)
            out += ["", "### 販管費の内訳（採用費・人件費）", "", "\n".join(sga) if sga else "—（raw に記載なし）"]
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
