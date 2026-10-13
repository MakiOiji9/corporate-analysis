"""{date}_brief.md: everything the SWOT writer needs, in one file.

The writer reads only this file and the skeleton; raw files, PDFs, CSVs, the upstream analysis md files and
outlook.md stay closed. The upstream results (five-forces, 3C, moat) come from their json, the market outlook
from the rows of outlook.md that bear on the company's market.
"""
from __future__ import annotations

import re
from pathlib import Path

import mdparse as M
from ff_inputs import Found, excerpt, header_notes
from sw_paths import Company

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("自社の事業と顧客（強み・弱み、影響度の判断）", ("segment", "customers")),
    ("会社の方針・中期経営計画（強み・弱み、条件付きの対策）",
     ("mtp", "mtp_alt", "mtp_targets", "mtp_actions", "mtp_review", "policy", "strategy")),
    ("事業等のリスク（弱み・脅威）", ("risks",)),
    ("業界の変化（機会・脅威）", ("market_size", "substitutes", "structural")),
)
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}
REASON_LIMIT = 300  # characters of an upstream reason
JAPAN_TICKER = re.compile(r"^\d{3}[0-9A-Z]$")
OUTLOOK_TERMS = ("中期", "長期")
BOTH_MARKETS = "日米"  # outlook.md rows that concern both markets


def _cut(text: str | None, limit: int = REASON_LIMIT) -> str:
    text = (text or "—").replace("\n", " ").strip() or "—"
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    top_s, top_t = r.get("top_strength") or {}, r.get("top_threat") or {}
    return [f"- 前回の結果: {date}（SWOT の結論 {r.get('verdict', '—')}。最大の強み {top_s.get('id', '—')} "
            f"{_cut(top_s.get('fact'), 80)}、最大の脅威 {top_t.get('id', '—')} {_cut(top_t.get('fact'), 80)}）",
            "  - 前回と違う判定にするときは、理由に「前回から変更:」で始まる文を入れる（build が確認する）"]


def _five_forces_lines(five_forces: tuple[str, dict] | None) -> list[str]:
    if not five_forces:
        return ["- ファイブフォース（1-1）: 完成済みの結果が無い"]
    date, r = five_forces
    lines = [f"- ファイブフォース（1-1）: {date}（業界の魅力度 {r.get('attractiveness', '—')}。業界: {r.get('industry', '—')}）"]
    for f in r.get("factors", []):
        mark = "（「強」→ 脅威に必ず記載）" if f.get("rating") == "強" else ""
        lines.append(f"  - {f.get('name')}: {f.get('rating')}{mark} — {_cut(f.get('reason'))}")
    return lines


def _three_c_lines(three_c: tuple[str, dict] | None) -> list[str]:
    if not three_c:
        return ["- 3C分析（1-2）: 完成済みの結果が無い"]
    date, r = three_c
    handoff = r.get("handoff") or {}
    return [f"- 3C分析（1-2）: {date}（勝てる理由 {r.get('verdict', '—')}: {_cut(r.get('verdict_reason'))}）",
            f"  - 勝てる理由の文: {_cut(r.get('win_reason'))}",
            f"  - SWOT の強み候補: {_cut(handoff.get('strengths'))}",
            f"  - SWOT の弱み候補: {_cut(handoff.get('weaknesses'))}"]


def _moat_lines(moat: tuple[str, dict] | None) -> list[str]:
    if not moat:
        return ["- モート分析（1-3）: 完成済みの結果が無い"]
    date, r = moat
    handoff = r.get("handoff") or {}
    risks = "、".join(f"{x.get('factor')}（{x.get('timing')}）" for x in r.get("risks", [])) or "—"
    return [f"- モート分析（1-3）: {date}（モートの強さ {r.get('verdict', '—')}: {_cut(r.get('verdict_reason'))}）",
            f"  - 残ったモート（強みに必ず記載）: {'、'.join(r.get('effective_moats', [])) or 'なし'}",
            f"  - 崩しうる要因: {_cut(risks)}",
            f"  - 持続の見込み: {_cut(r.get('durability'))}",
            f"  - SWOT の強み候補: {_cut(handoff.get('strengths'))}",
            f"  - SWOT の脅威候補: {_cut(handoff.get('threats'))}"]


def _source_lines(found: dict[str, Found], company: Company) -> list[str]:
    paths = sorted({f.path for f in found.values() if f.path is not None}, key=lambda p: p.name)
    lines = [f"  - {company.rel(p)}: {note}" for p in paths if (note := header_notes(p))]
    return ["- raw の情報源と注意（根拠の確度はこれで判断する）:"] + lines if lines else []


# ---------- 地合い ----------

def market_label(company: Company) -> str:
    return "日本" if JAPAN_TICKER.match(company.ticker.upper()) else "米国"


def _table(rows: list[list[str]]) -> str:
    if len(rows) < 2:
        return "（該当する行なし）"
    width = len(rows[0])
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows[1:]]
    return "\n".join(lines)


def _rows_for(text: str, market: str, predicate=lambda row: True) -> str:
    """Header plus the rows of the section's first table whose 市場 column is the market (and the predicate)."""
    tables = M.tables(text)
    if not tables:
        return "（表なし）"
    header, *rows = tables[0]
    col = next((i for i, h in enumerate(header) if h == "市場"), None)
    keep = [r for r in rows if (col is None or col >= len(r) or market in r[col] or r[col].strip() == BOTH_MARKETS)
            and predicate(r)]
    return _table([header] + keep)


def outlook_section(root: Path, outlook: dict, market: str) -> list[str]:
    if not outlook.get("path"):
        return ["- 完成済みの outlook.md が無い（地合いからは機会・脅威を書かない）"]
    text = (root / outlook["path"]).read_text(encoding="utf-8")
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return [f"出典: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。{market}の行だけを抜粋", "",
            "### 総合判断", "", _rows_for(M.section(text, "1."), market), "",
            "### 財政・政策・政治（3.5）", "", _rows_for(M.section(text, "3.5", level=3), market), "",
            "### 中期・長期の展望（4）", "",
            _rows_for(M.section(text, "4."), market, lambda r: bool(r) and r[0] in OUTLOOK_TERMS), "",
            "### リスク要因（5）", "", _rows_for(M.section(text, "5."), market)]


# ---------- brief ----------

def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found],
                 upstream: dict[str, tuple[str, dict] | None], previous: tuple[str, dict] | None,
                 outlook: dict) -> str:
    market = market_label(company)
    out = [f"# SWOT分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（swot.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV・上流の分析 md・outlook.md を開かない）。"
           "数値は転記だけで、新しい計算をしない。",
           "> 必ず記載する項目は md の 1.1、影響度の目安（売上・利益の 20%・5% の金額）は md の 3章にある（ここには載せない）。",
           "", "## 0. 前提（上流の分析の結論）", "", f"- 分析日: {date} / 有効期限: {valid_until} / 市場: {market}"]
    out += (_previous_lines(previous) + _five_forces_lines(upstream["five_forces"])
            + _three_c_lines(upstream["three_c"]) + _moat_lines(upstream["moat"]) + _source_lines(found, company))
    for number, (title, keys) in enumerate(CHAPTERS, start=1):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", excerpt(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 1}. 地合い（機会・脅威）", ""] + outlook_section(company.root, outlook, market)
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
