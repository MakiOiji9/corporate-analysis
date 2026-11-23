"""{date}_brief.md: everything the investment writer needs, in one file.

The numbers and judgements are in the md skeleton. The brief carries what the reports say the money went to
(each year's 設備投資等の概要・設備の新設計画・研究開発活動・企業結合 from data/investments.json), the mid-term plan
and the business policy, and the materials of the trends (the industry's structural changes and the policy lines of
the market outlook). The writer reads only this file and the skeleton.
"""
from __future__ import annotations

import re
from pathlib import Path

from ff_inputs import Found, excerpt
from pf_brief import STATUS_LABEL

TEXT_LIMITS = {"capex_overview": 700, "planned_facilities": 900, "research_and_development": 900,
               "business_combinations": 700}
SHAREHOLDINGS_LIMIT = 1500
TEXT_LABELS = {"capex_overview": "設備投資等の概要", "planned_facilities": "設備の新設、除却等の計画",
               "research_and_development": "研究開発活動", "business_combinations": "企業結合等関係",
               "shareholdings": "株式の保有状況"}
EMPTY_NOTE = re.compile(r"記載すべき重要な事項はありません|該当事項はありません")
CHAPTERS = (("中期経営計画・経営方針（md の 4章）", ("targets", "measures", "mtp_result", "policy")),
            ("有報の章（最新期。md の 1章の補足・米国株の内容）", ("capex", "rnd", "ma")),
            ("潮流の材料（md の 3章）", ("structural",)))
OUTLOOK_HEADINGS = ("財政・政策・政治", "政策・通商・金利の材料", "企業分析への引き継ぎ")
OUTLOOK_LIMIT = 1500


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "…（以下略）"


def year_texts(invest: dict | None) -> list[str]:
    if not invest or not invest.get("years"):
        return ["- data/investments.json が無い（有報の XBRL→CSV から yuho_investments.py で作る。米国株は下の有報の章を読む）"]
    out = []
    years = invest["years"]
    for i, y in enumerate(years):
        texts = y.get("texts") or {}
        out += ["", f"### {y['period_end'][:7]} 期（有報 {y['doc_id']}、提出 {y.get('filed', '—')}）", ""]
        for key, limit in TEXT_LIMITS.items():
            block = texts.get(key)
            if not block or not block.get("text"):
                continue
            text = block["text"]
            if key == "business_combinations" and (EMPTY_NOTE.search(text[:200]) or "NATextBlock" in block["element"]):
                text = "記載すべき重要な事項なし"
            out.append(f"- **{TEXT_LABELS[key]}**: {_cut(text, limit)}")
        if i == len(years) - 1 and texts.get("shareholdings"):
            out.append(f"- **{TEXT_LABELS['shareholdings']}**（最新期のみ）: "
                       f"{_cut(texts['shareholdings']['text'], SHAREHOLDINGS_LIMIT)}")
    return out


def outlook_lines(root: Path, outlook: dict) -> list[str]:
    if not outlook.get("path"):
        return ["- 地合い: 完成済みの outlook.md が無い（政策の材料なし）"]
    text = (root / outlook["path"]).read_text(encoding="utf-8")
    out = [f"- 出典: {outlook['path']}（{outlook['age_days']} 日前の週{'。古い（参考扱い）' if outlook.get('stale') else ''}）"]
    for heading in OUTLOOK_HEADINGS:
        m = re.search(rf"^###? [\d.]*\s*{re.escape(heading)}[^\n]*\n(.*?)(?=^##|\Z)", text, re.M | re.S)
        if m and m.group(1).strip():
            out += ["", f"**{heading}**", "", _cut(m.group(1), OUTLOOK_LIMIT)]
    return out


def _numbers(c: dict) -> list[str]:
    a = c["axes"]
    lines = [f"- 投資の質の候補（build が執筆者の分類を入れて確定する）: {c['verdict']} — {c['why']}",
             f"- ① 投資効率: {a['efficiency']['rating']} — {a['efficiency']['sentence']}",
             f"- ④ 競合比較: {a['peer']['rating']} — {a['peer']['sentence']}",
             f"- ⑤ 失敗の履歴: {a['failure']['rating']} / ⑥ 資金と規律: {a['discipline']['rating']}（(a)〜(h) は md の 6章）",
             "- ② 中計との整合・③ 潮流との整合は、md の 3・4章の分類から build が集計する"]
    if c["points"]:
        lines.append("- 変化点（md の 2章で背景を書く）:")
        lines += [f"  - {p['year']} {p['kind']}: {p['text']}" for p in c["points"]]
    else:
        lines.append("- 変化点: なし")
    if c["plan_years"]:
        lines.append("- 設備計画の照合（md の 4章）: " + "、".join(f"{p['year']} の計画 → {p['next']}" for p in c["plan_years"]))
    top = c["top_segment"]
    if top:
        lines.append(f"- 設備投資が最も多いセグメント: {top['segment']}（{top['span']}、{top['share']:.1f}%）")
    return lines


def _gaps(found: dict[str, Found]) -> list[str]:
    rows = [f"- {f.spec.label}: {STATUS_LABEL[f.status]}" for f in found.values() if f.status != "ok"]
    return rows or ["- なし"]


def render_brief(company, root: Path, date: str, valid_until: str, found: dict[str, Found], c: dict, invest: dict | None,
                 previous: tuple[str, dict] | None, growth: tuple[str, dict] | None, outlook: dict) -> str:
    out = [f"# 投資の質の分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（investment.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV を開かない）。数値と判定はスクリプトが md に記入済み。",
           "> 書くのは、何に投資したか・投資テーマとその分類・変化点の背景・中計と設備計画の照合・潮流との照合だけ。",
           "", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}"]
    if previous:
        out.append(f"- 前回の結果: {previous[0]}（投資の質 {previous[1].get('verdict', '—')}: "
                   f"{previous[1].get('verdict_reason', '—')}）")
    else:
        out.append("- 前回の結果: なし（初回の分析）")
    out.append(f"- 成長性分析: {growth[0]}（成長性 {growth[1].get('verdict', '—')}）" if growth
               else "- 成長性分析: 完成済みの結果が無い（数値は成長性と同じ計算をこの分析の中で行った）")
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers(c)
    out += ["", "## 2. 年ごとの有報の記述（data/investments.json。md の 1・2・4章）"] + year_texts(invest)
    for number, (title, keys) in enumerate(CHAPTERS, start=3):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            out += ["", f"### {found[key].spec.label}", "", excerpt(found[key], company)]
    out += ["", f"## {len(CHAPTERS) + 3}. 地合いの政策の材料（md の 3章。判定には使わず、潮流との照合の根拠にだけ使う）", ""]
    out += outlook_lines(root, outlook)
    out += ["", f"## {len(CHAPTERS) + 4}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
