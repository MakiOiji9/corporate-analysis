"""{date}_brief.md: everything the safety writer needs, in one file.

The numbers and the judgements are already in the md skeleton; the brief carries what explains them (the notes
of the balance sheet and cash flows, the financial and capital policy, the financial risks, the peers' notes,
the profitability result and the interest-rate rows of the market outlook). The writer reads only this file and
the skeleton; raw files, PDFs, CSVs, the profitability md and outlook.md stay closed.
"""
from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

import mdparse as M
from ff_inputs import Found, excerpt
from sf_metrics import CHECK_PURPOSE, BAD_PURPOSE, money
from sf_paths import Company
from sf_series import JAPAN_TICKER
from sw_brief import _rows_for

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("水準と借入の目的の材料（1章の背景・3章）", ("self_bs", "self_cf", "statements", "summary")),
    ("財務方針・資本政策の材料（5章）", ("capital", "policy", "self_return")),
    ("財務に関わるリスク（5章・7章）", ("risks",)),
    ("競合の材料（1章の同業比較）", ("peer_safety",)),
)
PROSE_ONLY = ("self_bs", "self_cf", "statements", "summary", "peer_safety")  # the numbers are already in the md
EMPTY_HEADING = re.compile(r"^\*\*[^*\n]+\*\*\s*\n(?=\s*(?:\*\*|$))", re.M)  # a bold heading left with no body
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}
OUTLOOK_SECTIONS = (("金利・為替（3.2）", "3.2"), ("金融政策（3.3）", "3.3"))


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    s1 = r.get("step1") or {}
    items = "、".join(f"{i.get('name')} {i.get('rating')}" for i in s1.get("items", [])) or "—"
    return [f"- 前回の結果: {date}（安全性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - 手順1 {items}、手順2 {(r.get('step2') or {}).get('rating') or '—'}、"
            f"手順3 {(r.get('step3') or {}).get('rating') or '—'}"]


def _profitability_lines(result: tuple[str, dict] | None) -> list[str]:
    if not result:
        return ["- 収益性分析: 完成済みの結果が無い（安全性の判定には使わない）"]
    date, r = result
    s3 = r.get("step3") or {}
    lines = [f"- 収益性分析: {date}（収益性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）"]
    if s3.get("latest_leverage") is not None:
        lines.append(f"  - ROE の源泉 {s3.get('source', '—')}、直近の財務レバレッジ {s3['latest_leverage']:.2f} 倍")
    checks = (r.get("handoff") or {}).get("step2_checks")
    if checks:
        lines.append(f"  - STEP 2 で確かめること（収益性分析から）: {checks}")
    return lines


def market_of(company: Company) -> str:
    return "日本" if JAPAN_TICKER.match(company.ticker.upper()) else "米国"


def outlook_lines(root: Path, outlook: dict, market: str) -> list[str]:
    if not outlook.get("path"):
        return ["- 完成済みの outlook.md が無い（金利の局面は 5章に書かない）"]
    text = (root / outlook["path"]).read_text(encoding="utf-8")
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    out = [f"出典: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。{market}の行だけを抜粋。"
           "安全性の判定には使わない（5章の「評価が変わる条件」で金利の局面に触れるときだけ引用する）"]
    for title, number in OUTLOOK_SECTIONS:
        out += ["", f"### {title}", "", _rows_for(M.section(text, number, level=3), market)]
    return out


def _numbers_lines(cands: dict) -> list[str]:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    lines = [f"- 安全性の候補（build が確定する）: {cands['verdict']} — {cands['why']}",
             f"- 手順1: {s1['sentence']}"]
    lines += [f"  - {i['name']}: {i['rating']}（{i['basis']}）" for i in s1["items"]]
    lines += [f"- 手順2: {s2['sentence']}", f"- 手順3: {s3['sentence']}"]
    pending = [y for y in s3["years"] if y["rating"] in (CHECK_PURPOSE, BAD_PURPOSE)]
    if s3["years"]:
        lines.append("- 背景を書く年（有利子負債が増えた年。md の 3章）:")
        lines += [f"  - {y['year']}: +{money(y['increase'])} {s1['unit']}、{y['kind']}" for y in s3["years"]]
    if pending:
        lines.append("  - 要確認・懸念の年は、brief の財務時系列・有報・資本政策の記述から借入の理由を探す")
    if cands["borderline"]:
        lines.append("- 境界に近い比較（材料の誤差で判定が1段階動きうる。5章の「評価が変わる条件」に使う）: "
                     + "。".join(cands["borderline"]))
    lines.append("- 年度ごとの表・競合の指標は md の 1〜3章にある（同じ表をここには載せない）")
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
    if f.spec.key in PROSE_ONLY and f.body:
        return excerpt(replace(f, body=_prose(f.body) or "—（表のみ。数値は md の表を見る）"), company)
    return excerpt(f, company)


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, profitability: tuple[str, dict] | None, outlook: dict,
                 warnings: list[str] = ()) -> str:
    out = [f"# 安全性（財務体力）分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（safety.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV・収益性の md・outlook.md を開かない）。"
           "数値と判定はスクリプトが md に記入済み。",
           "> 書くのは数値の背景と解釈だけ。新しい計算をしない。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた可能性。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += _previous_lines(previous) + _profitability_lines(profitability)
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers_lines(cands)
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", _section(found[key], company)]
    tail = len(CHAPTERS) + 2
    out += ["", f"## {tail}. 地合い（金利・金融政策）", ""] + outlook_lines(company.root, outlook, market_of(company))
    out += ["", f"## {tail + 1}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
