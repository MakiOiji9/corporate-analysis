"""{date}_brief.md: everything the moat writer needs, in one file.

The writer reads only this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

from dataclasses import replace

from ff_doc import candidate_cell
from ff_inputs import Found, excerpt, header_notes
from mt_paths import Company

# brief chapter: (title, input keys). The comparison numbers come first (chapter 1); every raw section once.
CHAPTERS = (
    ("無形資産: ブランド・価格決定力の材料", ("pricing", "peer_claims")),
    ("無形資産: 規制・特許・許認可の材料", ("ip",)),
    ("スイッチングコストの材料", ("retention", "installed_base", "customer_base", "kpi", "peer_kpi")),
    ("ネットワーク効果・効率的規模の材料（市場の大きさ・参入と撤退）", ("market_size", "entry")),
    ("コスト優位の材料", ("peer_cost", "industry_margin", "segments")),
    ("シェアの推移の材料（5章）", ("share", "peer_share")),
    ("持続性の材料（6章）", ("structural", "risks")),
    ("外部の評価（参考。判定の根拠にはしない）", ("outside_rating",)),
)
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}
FF_FACTORS_SHOWN = ("entry", "substitutes")  # five-forces factors that threaten a moat
# the peers' KPI table is wide (3C compares every column); the moat criteria need these columns only
NARROW_COLUMNS = {"peer_kpi": ("会社", "年度", "継続率", "単価", "第三者評価", "出典")}


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


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def narrow_tables(body: str, keep: tuple[str, ...]) -> str:
    """Keep only the columns whose header contains one of the words (tables with fewer matches stay whole)."""
    out: list[str] = []
    columns: list[int] | None = None
    for line in body.splitlines():
        if not line.lstrip().startswith("|"):
            columns = None
            out.append(line)
            continue
        cells = _cells(line)
        if columns is None:  # header row
            picked = [i for i, h in enumerate(cells) if any(w in h for w in keep)]
            columns = picked if len(picked) >= 2 else list(range(len(cells)))
        out.append("| " + " | ".join(cells[i] if i < len(cells) else "" for i in columns) + " |")
    return "\n".join(out)


def _section(f: Found, company: Company) -> str:
    keep = NARROW_COLUMNS.get(f.spec.key)
    return excerpt(replace(f, body=narrow_tables(f.body, keep)) if keep and f.body else f, company)


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, three_c: tuple[str, dict] | None,
                 five_forces: tuple[str, dict] | None, outlook: dict, warnings: list[str] = ()) -> str:
    out = [f"# モート分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（moat.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV を開かない）。数値は転記だけで、新しい計算をしない。",
           "> 超過収益（ROIC と資本コスト）・価格決定力（粗利率）はスクリプトが計算し、build が源泉の判定・シェアの推移・"
           "持続性と合わせてモートの強さを判定する。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた可能性。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += (_previous_lines(previous) + _three_c_lines(three_c) + _five_forces_lines(five_forces)
            + [_outlook_line(outlook)] + _source_lines(found, company))
    ret, pr = cands["returns"], cands["pricing"]
    out += ["", "## 1. 数字（スクリプトが計算）", "",
            f"- 超過収益（入口）: {ret['rating'] or '不明'}: {ret['basis']}",
            f"  - 堀の幅 {ret['width']}、ROIC と資本コストの差の傾向 {ret['trend']}",
            "  - 超過収益が「なし」なら、源泉が「強」「中」でもモートとはみなされない（数字に表れていないため）。"
            "源泉の判定は、超過収益がどの仕組みから生まれているかを説明できるものだけを「強」「中」にする",
            f"- 価格決定力（粗利率）: {pr['rating'] or '不明'}: {pr['basis']}（ブランドの数値の痕跡に使える）",
            f"- 営業利益率の同業比較（参考）: {candidate_cell(cands['margin'])}",
            f"- シェアの推移（スクリプトの候補。5章の1語をこれより良くするなら根拠を書く）: "
            f"{(cands.get('share_trend') or {}).get('trend', '不明')}: {(cands.get('share_trend') or {}).get('basis', '—')}",
            f"- 自社の数値の出典: {'、'.join(cands['sources']) or '—'}",
            "- 年度ごとの ROIC は md の 2.1、営業利益率の同業比較は 2.2、粗利率は 3.1、コスト構造と競合の単純平均は 3.2 を見る"
            "（同じ表をここには載せない）"]
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", _section(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
