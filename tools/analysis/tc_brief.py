"""{date}_brief.md: everything the 3C writer needs, in one file.

The writer reads only this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

from ff_doc import candidate_cell
from ff_inputs import Found, excerpt, main_business, summary_main_business
from ff_metrics import peer_margin_line, peer_margins
from tc_metrics import table_rows
from tc_paths import Company

# brief chapter: (title, input keys)
CHAPTERS = (
    ("顧客（Customer）の材料", ("segment", "customer_base", "customers", "market_size", "kbf")),
    ("競合（Competitor）の材料", ("peer_selection", "peers", "peer_share", "share")),
    ("自社（Company）の材料", ("products", "kpi", "strategy", "peer_claims")),
)
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "unavailable": "取得を試みたが取れていない（status.md）"}
FF_FACTORS_SHOWN = ("buyers", "rivalry")  # five-forces factors that matter for the customer / competitor view


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    return [f"- 前回の結果: {date}（勝てる理由 {r.get('verdict', '—')}、成長性 {(r.get('growth') or {}).get('rating', '—')}、"
            f"競合との比較 {(r.get('competitor') or {}).get('rating', '—')}、KBF {'、'.join(r.get('kbf', [])) or '—'}）",
            f"  - 勝てる理由の文: {r.get('win_reason', '—')}",
            "  - 前回と違う評価にするときは、理由に「前回から変更:」で始まる文を入れる（build が確認する）"]


def _five_forces_lines(five_forces: tuple[str, dict] | None) -> list[str]:
    if not five_forces:
        return ["- ファイブフォース: 完成済みの結果が無い"]
    date, r = five_forces
    lines = [f"- ファイブフォース: {date}（業界の魅力度 {r.get('attractiveness', '—')}、{r.get('total', '—')}/10点）",
             f"  - 業界の定義: {r.get('industry', '—')}（1章の主力セグメントはこれに合わせる）"]
    for f in r.get("factors", []):
        if f.get("key") in FF_FACTORS_SHOWN:
            lines.append(f"  - {f.get('name')}: {f.get('rating')} — {f.get('reason', '')}")
    return lines


def _outlook_line(outlook: dict) -> str:
    if not outlook.get("path"):
        return "- 地合い: 完成済みの outlook.md が無い（3C の判断には使わない）"
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。3C の判断には使わない"


def _peer_lines(found: Found) -> list[str]:
    peers = peer_margins(found)
    if not peers:
        return []
    return ["", "営業利益率の推移（スクリプトが計算。判定はしない）:", ""] + [f"- {peer_margin_line(p)}" for p in peers]


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, five_forces: tuple[str, dict] | None, outlook: dict) -> str:
    out = [f"# 3C分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（three_c.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルだけを根拠にする（raw・PDF・CSV を開かない）。数値は転記だけで、新しい計算をしない。",
           "> 「スクリプトの判定候補」は判断基準のうち数値で決まる部分の判定。これより有利な評価にするときは理由が要る。",
           "", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += _previous_lines(previous) + _five_forces_lines(five_forces) + [_outlook_line(outlook)]
    out += ["", "## 1. 判定候補と比較表（スクリプトが計算）", "",
            f"- 成長性の判定候補: {candidate_cell(cands['growth'])}",
            f"- 競合との比較の判定候補: {candidate_cell(cands['competitor'])}", "",
            "| 企業 | 年度 | 売上高 | 営業利益率 | シェア | 売上高3年CAGR | 出典 |", "|---|---|---|---|---|---|---|",
            table_rows(cands["rows"])]
    out += _peer_lines(found["peers"])
    out += ["", f"- overview.md の主力事業: {main_business(company) or '—'}", "",
            "summaries/business.md「主力事業の定義」:", "", summary_main_business(company) or "—"]
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", excerpt(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
