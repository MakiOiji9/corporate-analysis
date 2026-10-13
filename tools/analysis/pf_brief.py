"""{date}_brief.md: everything the profitability writer needs, in one file.

The numbers and the judgements are already in the md skeleton; the brief carries what explains them
(extraordinary items, shareholder returns, capital policy, targets, the peers' notes). The writer reads only
this file and the skeleton; raw files, PDFs and CSVs stay closed.
"""
from __future__ import annotations

import re
from dataclasses import replace

from ff_inputs import Found, excerpt
from pf_metrics import CHANGE_PT, ONE_OFF_SHARE
from pf_paths import Company

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("ROE が動いた年・一過性要因の材料（3.3・3.4）", ("special", "self_pl", "self_return")),
    ("会社の目標・資本政策の材料（6章）", ("targets", "capital", "policy")),
    ("競合の材料（3.2 の差の背景）", ("peer_roe", "peer_dupont")),
)
PROSE_ONLY = ("self_pl", "peer_roe", "peer_dupont")  # the numbers are already in the md; keep the notes only
COVERED_BY_TARGETS = ("資本政策", "株主還元")  # the yuho policy section is skipped when the targets section has these
EMPTY_HEADING = re.compile(r"^\*\*[^*\n]+\*\*\s*\n(?=\s*(?:\*\*|$))", re.M)  # a bold heading left with no body
STATUS_LABEL = {"missing": "raw に無い", "blank": "節はあるが空", "thin": "中身が薄い（見つからなかった旨の記載・空の行）",
                "unavailable": "取得を試みたが取れていない（status.md）"}


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    s1 = r.get("step1") or {}
    return [f"- 前回の結果: {date}（収益性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - 手順1 {s1.get('rating') or '—'}（平均 {s1.get('average', '—')}%）、"
            f"手順2 {(r.get('step2') or {}).get('rating') or '—'}、手順3 {(r.get('step3') or {}).get('source') or '—'}"]


def _upstream_lines(moat: tuple[str, dict] | None, three_c: tuple[str, dict] | None) -> list[str]:
    lines = []
    if moat:
        date, r = moat
        lines.append(f"- モート分析: {date}（モート {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）")
        checks = (r.get("handoff") or {}).get("step2_checks")
        if checks:
            lines.append(f"  - STEP 2 で確かめること（モート分析から）: {checks}")
    else:
        lines.append("- モート分析: 完成済みの結果が無い（整合性チェックは未実施）")
    if three_c:
        date, r = three_c
        lines.append(f"- 3C分析: {date}（勝てる理由 {r.get('verdict', '—')}: {r.get('win_reason', '—')}）")
    else:
        lines.append("- 3C分析: 完成済みの結果が無い（整合性チェックは未実施）")
    return lines


def _outlook_line(outlook: dict) -> str:
    if not outlook.get("path"):
        return "- 地合い: 完成済みの outlook.md が無い（収益性の判断には使わない）"
    stale = "。古い（参考扱い）" if outlook.get("stale") else ""
    return f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週{stale}）。収益性の判断には使わない"


def _numbers_lines(cands: dict) -> list[str]:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    lines = [f"- 収益性の候補（build が確定する）: {cands['verdict']} — {cands['why']}",
             f"- 手順1: {s1['sentence']}", f"- 手順2: {s2['sentence']}",
             f"- 手順3: {s3['sentence']}" + ("" if s3["source"] == "不明" else f"（{s3['basis']}）")]
    if cands["changes"]:
        lines.append(f"- 背景を書く年（ROE が前年から {CHANGE_PT:.0f}pt 以上動いた年。md の 3.3）:")
        lines += [f"  - {c['year']}: {c['from']:.1f}% → {c['to']:.1f}%、主因 {c['main']}（{c['moves']}）"
                  for c in cands["changes"]]
    checks = [r for r in cands["one_off"] if r["check"]]
    if checks:
        lines.append(f"- 一過性要因の要確認（特別損益の純額が当期純利益の {ONE_OFF_SHARE:.0f}% 以上。md の 3.4）: "
                     + "、".join(f"{r['year']}（{r['share']:.1f}%）" for r in checks))
    if cands["borderline"]:
        lines.append("- 境界に近い比較（材料の誤差で判定が1段階動きうる。6章の「評価が変わる条件」に使う）: "
                     + "。".join(cands["borderline"]))
    lines.append("- 年度ごとの表・競合の3要素は md の 1〜3章にある（同じ表をここには載せない）")
    return lines


def _prose(body: str) -> str:
    """The body without its tables; sub-headings left with nothing under them are dropped."""
    text = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("|"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"^#{3,6}\s+(.+)$", r"**\1**", text, flags=re.M)
    previous = None
    while previous != text:
        previous, text = text, EMPTY_HEADING.sub("", re.sub(r"\n{3,}", "\n\n", text))
    return text.strip()


def _section(f: Found, company: Company) -> str:
    if f.spec.key in PROSE_ONLY and f.body:
        return excerpt(replace(f, body=_prose(f.body) or "—（表のみ。数値は md の表を見る）"), company)
    return excerpt(f, company)


def _skipped(key: str, found: dict[str, Found]) -> bool:
    """The yuho policy section repeats what the targets section already quotes."""
    targets = found["targets"]
    return key == "policy" and targets.status == "ok" and all(w in targets.body for w in COVERED_BY_TARGETS)


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}{'（必須）' if f.spec.required else ''}"
            for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, moat: tuple[str, dict] | None,
                 three_c: tuple[str, dict] | None, outlook: dict, warnings: list[str] = ()) -> str:
    out = [f"# 収益性（ROE・デュポン分解）分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（profitability.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV を開かない）。数値と判定はスクリプトが md に記入済み。",
           "> 書くのは数値の背景と解釈だけ。新しい計算をしない。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた可能性。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    out += _previous_lines(previous) + _upstream_lines(moat, three_c) + [_outlook_line(outlook)]
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers_lines(cands)
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            if _skipped(key, found):
                out += ["", f"### {found[key].spec.label}", "", "（中期経営計画の節と同じ内容のため省略）"]
                continue
            out += ["", f"### {found[key].spec.label}", "", _section(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
