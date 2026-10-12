"""{date}_brief.md: everything the writer needs for the five forces, in one file.

The writer reads only this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

from ff_doc import FACTORS, candidate_cell
from ff_inputs import Found, excerpt, main_business, summary_main_business
from ff_metrics import peer_margin_line, peer_margins
from ff_paths import Company

# brief chapter per factor: (factor key, input keys shown under it)
CHAPTER_INPUTS = (
    ("entry", ("entry", "ip")),
    ("substitutes", ("substitutes", "structural")),
    ("buyers", ("customers", "customer_base", "kbf")),
    ("suppliers", ("procurement", "supply")),
    ("rivalry", ("market_size", "share", "industry_margin", "peers", "peer_share")),
)
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "unavailable": "取得を試みたが取れていない（status.md）"}


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, result = previous
    lines = [f"- 前回の結果: {date}（業界の魅力度 {result.get('attractiveness', '—')}、"
             f"{result.get('total', '—')}/10点、業界の定義「{result.get('industry', '—')}」）"]
    lines += [f"  - {f.get('name')}: {f.get('rating')} — {f.get('reason', '')}" for f in result.get("factors", [])]
    lines.append("  - 前回と違う評価にするときは、理由に「前回から変更:」で始まる文を入れる（build が確認する）")
    return lines


def _outlook_line(outlook: dict) -> str:
    """Path only: the outlook is a header reference, not material for the industry structure."""
    if not outlook.get("path"):
        return "- 地合い: 完成済みの outlook.md が無い（業界構造の判断には使わない）"
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。業界構造の判断には使わない"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _supplier_series(cand: dict) -> list[str]:
    series = cand.get("series") or []
    if not series:
        return []
    lines = ["", f"粗利率・営業利益率の時系列（スクリプトが計算。出典: {', '.join(cand.get('sources', []))}）", "",
             "| 年度末 | 粗利率 | 営業利益率 |", "|---|---|---|"]
    return lines + [f"| {s['year']} | {_pct(s['gross_margin'])} | {_pct(s.get('operating_margin'))} |"
                    for s in series]


def _peer_margins(found: Found) -> list[str]:
    peers = peer_margins(found)
    if not peers:
        return []
    source = found.path.name if found.path else "—"
    return ["", f"営業利益率の推移（スクリプトが売上高・営業利益から計算。出典: {source}「{found.heading}」。判定はしない）",
            ""] + [f"- {peer_margin_line(p)}" for p in peers]


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found],
                 candidates: dict[str, dict], previous: tuple[str, dict] | None, outlook: dict) -> str:
    names = {key: name for key, _, name in FACTORS}
    out = [f"# ファイブフォース分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（five_forces.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルだけを根拠にする（raw・PDF・CSV を開かない）。数値は転記だけで、新しい計算をしない。",
           "> 「スクリプトの判定候補」は判断基準のうち数値で決まる部分の判定。これより有利な評価にするときは理由が要る。",
           "", "## 0. 前提", "",
           f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += _previous_lines(previous) + [_outlook_line(outlook)]
    out += ["", "## 1. 業界の定義の材料", "",
            f"- overview.md の主力事業: {main_business(company) or '—'}", "",
            "summaries/business.md「主力事業の定義」:", "", summary_main_business(company) or "—", "",
            excerpt(found["segment"], company)]
    for number, (key, inputs) in enumerate(CHAPTER_INPUTS, start=2):
        cand = candidates[key]
        out += ["", f"## {number}. {names[key]}", "", f"**スクリプトの判定候補**: {candidate_cell(cand)}"]
        if key == "suppliers":
            out += _supplier_series(cand)
        if key == "rivalry":
            out += _peer_margins(found["peers"])
        for input_key in inputs:
            out += ["", f"### {found[input_key].spec.label}", "", excerpt(found[input_key], company)]
    out += ["", "## 7. 参考: 事業等のリスク", "", excerpt(found["risks"], company),
            "", "## 8. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
