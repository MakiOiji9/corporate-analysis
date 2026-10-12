"""{date}_brief.md: everything the moat writer needs, in one file.

The writer reads only this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

from ff_doc import candidate_cell
from ff_inputs import Found, excerpt, header_notes
from ff_metrics import peer_margin_line
from mt_metrics import cost_table_rows, margin_table_rows
from mt_paths import Company

# brief chapter: (title, input keys). The comparison numbers come first (chapter 1); every raw section once.
CHAPTERS = (
    ("ブランド・価格決定力の材料", ("pricing", "peer_claims")),
    ("スイッチングコスト・ネットワーク効果の材料", ("retention", "customer_base", "kpi", "peer_kpi")),
    ("シェアの推移の材料（3.3）", ("share", "peer_share")),
    ("コスト優位の材料", ("peer_cost", "industry_margin")),
    ("規制・特許・許認可の材料", ("ip",)),
    ("持続性の材料（4章）", ("structural", "risks")),
)
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}
FF_FACTORS_SHOWN = ("entry", "substitutes")  # five-forces factors that threaten a moat


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    moats = "、".join(f"{m.get('type')} {m.get('rating')}" for m in r.get("moats", [])) or "—"
    return [f"- 前回の結果: {date}（モートの強さ {r.get('verdict', '—')}、裏付け {r.get('backing', '—')}、"
            f"シェアの推移 {(r.get('share') or {}).get('trend', '—')}）",
            f"  - 前回の判定: {moats}",
            "  - 前回と違う判定にするときは、根拠・理由に「前回から変更:」で始まる文を入れる（build が確認する）"]


def _three_c_lines(three_c: tuple[str, dict] | None) -> list[str]:
    if not three_c:
        return ["- 3C分析: 完成済みの結果が無い"]
    date, r = three_c
    handoff = r.get("handoff") or {}
    return [f"- 3C分析: {date}（勝てる理由 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - 勝てる理由の文: {r.get('win_reason', '—')}",
            f"  - SWOT の強み候補: {handoff.get('strengths', '—')}",
            f"  - SWOT の弱み候補: {handoff.get('weaknesses', '—')}",
            f"  - モート分析で確かめること: {handoff.get('moat_checks', '—')}"]


def _five_forces_lines(five_forces: tuple[str, dict] | None) -> list[str]:
    if not five_forces:
        return ["- ファイブフォース: 完成済みの結果が無い"]
    date, r = five_forces
    lines = [f"- ファイブフォース: {date}（業界の魅力度 {r.get('attractiveness', '—')}。業界: {r.get('industry', '—')}）"]
    for f in r.get("factors", []):
        if f.get("key") in FF_FACTORS_SHOWN:
            lines.append(f"  - {f.get('name')}: {f.get('rating')} — {f.get('reason', '')}")
    return lines


def _outlook_line(outlook: dict) -> str:
    if not outlook.get("path"):
        return "- 地合い: 完成済みの outlook.md が無い（モートの判断には使わない）"
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。モートの判断には使わない"


def _source_lines(found: dict[str, Found], company: Company) -> list[str]:
    paths = sorted({f.path for f in found.values() if f.path is not None}, key=lambda p: p.name)
    notes = [(p, header_notes(p)) for p in paths]
    lines = [f"  - {company.rel(p)}: {note}" for p, note in notes if note]
    return ["- raw の情報源と注意（根拠の確度はこれで判断する）:"] + lines if lines else []


def _peer_lines(cands: dict) -> list[str]:
    by_peer: dict[str, dict[str, float]] = {}
    for row in cands["rows"]:
        for m in row["peers"]:
            by_peer.setdefault(m["name"], {})[m["year"]] = m["margin"]
    if not by_peer:
        return []
    lines = []
    for name, series in by_peer.items():
        peer = {"name": name, "series": [{"year": y, "margin": v, "forecast": False} for y, v in sorted(series.items())]}
        lines.append(f"- {peer_margin_line(peer)}")
    return ["", "比較に使った競合の営業利益率（実績。スクリプトが計算）:", ""] + lines


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, three_c: tuple[str, dict] | None,
                 five_forces: tuple[str, dict] | None, outlook: dict) -> str:
    out = [f"# モート分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（moat.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルだけを根拠にする（raw・PDF・CSV を開かない）。数値は転記だけで、新しい計算をしない。",
           "> 数字の裏付け（営業利益率の同業比較）はスクリプトが計算し、build がシェアの推移と合わせて判定する。",
           "", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += (_previous_lines(previous) + _three_c_lines(three_c) + _five_forces_lines(five_forces)
            + [_outlook_line(outlook)] + _source_lines(found, company))
    out += ["", "## 1. 数字の裏付け（スクリプトが計算）", "",
            f"- 営業利益率の側の判定候補: {candidate_cell(cands['margin'])}",
            f"- 自社の数値の出典: {'、'.join(cands['sources']) or '—'}", "",
            "| 年度 | 自社 | 同業平均 | 差 | 比較した競合（決算期） |", "|---|---|---|---|---|",
            margin_table_rows(cands["rows"])]
    out += _peer_lines(cands)
    out += ["", "コスト構造（competitors.md「コスト構造」から抜粋。平均はスクリプトが計算）:", "",
            "| 会社 | 年度 | 売上原価率 | 販管費率 | 営業利益率 | 出典 |", "|---|---|---|---|---|---|",
            cost_table_rows(cands["costs"])]
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", excerpt(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
