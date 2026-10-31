"""{date}_brief.md: everything the valuation writer needs, in one file.

The numbers and the judgements are already in the md skeleton; the brief carries what explains them (the
extraordinary items, the capital policy and shareholder returns, the notes of the price data and the peers),
the upstream conclusions the final check uses (growth, the other STEP 2 analyses, the SWOT) and the market outlook
reference. The writer reads only this file and the skeleton; raw files, PDFs, CSVs and the other analyses stay closed.
"""
from __future__ import annotations

from dataclasses import replace

import va_metrics as X
import va_rules as R
from ff_inputs import Found, excerpt
from sf_brief import _gaps, _prose
from va_paths import Company

# brief chapter: (title, input keys). Every raw section once.
CHAPTERS = (
    ("特別損益の材料（1章の特別損益の中身）", ("special",)),
    ("資本政策・株主還元の材料（2章の改善策の有無・7章）", ("capital", "policy")),
    ("株価データの注記（0章の前提）", ("price", "per_share", "current", "history", "analyst")),
    ("競合の注記（0章の同業比較）", ("peer_valuation", "peer_ebitda")),
)
PROSE_ONLY = ("price", "per_share", "current", "history", "analyst", "peer_valuation", "peer_ebitda")


def _previous_lines(previous: tuple[str, dict] | None) -> list[str]:
    if not previous:
        return ["- 前回の結果: なし（初回の分析）"]
    date, r = previous
    ratings = "、".join(f"{name} {(r.get(key) or {}).get('rating', '—')}" for key, name in X.INDICATORS)
    price = r.get("price") or {}
    return [f"- 前回の結果: {date}（STEP 3 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
            f"  - {ratings}。株価 {price.get('value', '—')}（基準日 {price.get('date', '—')}）"]


def _growth_lines(growth: tuple[str, dict] | None) -> list[str]:
    if not growth:
        return ["- 成長性分析: 完成済みの結果が無い"]
    date, r = growth
    s1, s3 = r.get("step1") or {}, r.get("step3") or {}
    lines = [f"- 成長性分析: {date}（成長性 {r.get('verdict', '—')}: {r.get('verdict_reason', '—')}）",
             f"  - EPS CAGR {s1.get('eps_cagr', '—')}%（PEG の成長率の候補）、会社計画の信頼性 {s3.get('rating', '—')}"
             f"（{s3.get('basis', '—')}。「割り引いて扱う」なら PER は実績PER も判定し保守的な方を採る）"]
    hint = (r.get("handoff") or {}).get("step3_hint")
    if hint:
        lines.append(f"  - STEP 3 への引き継ぎ（成長性分析から）: {hint}")
    return lines


def _upstream_lines(upstream: dict, swot: tuple[str, dict] | None) -> list[str]:
    lines = []
    for key, _, label in X.UPSTREAM:
        r = upstream.get(key)
        lines.append(f"- {label}: " + (f"{r['date']}（{r['verdict']}: {r['reason'] or '—'}）" if r else "未実施"))
    top = (swot[1].get("top_threat") if swot else None) or {}
    if isinstance(top, dict) and top.get("fact"):
        lines.append(f"  - SWOT の最大の脅威（{top.get('id', '—')}、影響度 {top.get('impact', '—')}）: {top['fact']}")
    return lines


def _numbers_lines(cands: dict) -> list[str]:
    lines = [f"- STEP 3 の候補（build が確定する）: {cands['verdict']} — {cands['why']}"]
    lines += [f"- {name}: {cands[key]['rating']} — {cands[key]['sentence']}" for key, name in X.INDICATORS]
    if cands["flip_prices"]:
        lines.append("- 判定が1段階変わる株価（7章にそのまま載る。株価の予測ではない）: " + "。".join(cands["flip_prices"]))
    if cands["borderline"]:
        lines.append("- 境界に近い比較（材料の誤差や株価の小さな動きで判定が1段階動きうる）: " + "。".join(cands["borderline"]))
    writes = ["7章・8章・9章"]
    if cands["ev"]["divergence"]:
        writes.insert(0, "4章 食い違いの背景")
    if cands["pbr"]["trap"]["applies"] and cands["pbr"]["before_trap"] == R.LOW:
        writes.insert(0, "2章 改善策の有無（あり/なし/不明。本 brief 3章の資本政策から）")
    if cands["per"]["step1"]["adjusted"]:
        writes.insert(0, "1章 特別損益の中身（本 brief 2章の特別損益から）")
    lines.append(f"- 書く欄: {'、'.join(writes)}（STEP 3 が割安になりうるときは 5章 割安の理由も）")
    lines.append("- 年度ごとの倍率・競合の倍率は md の 0章にある（同じ表をここには載せない）")
    return lines


def _section(f: Found, company: Company) -> str:
    if not f.body:
        return excerpt(f, company)
    body = _prose(f.body) if f.spec.key in PROSE_ONLY else f.body
    return excerpt(replace(f, body=body or "—（表のみ。数値は md の表を見る）"), company)


def render_brief(company: Company, date: str, valid_until: str, found: dict[str, Found], cands: dict,
                 previous: tuple[str, dict] | None, growth: tuple[str, dict] | None, swot: tuple[str, dict] | None,
                 outlook: dict, warnings: list[str] = ()) -> str:
    price = cands["base"]["price"]
    age = cands["price_age"]
    out = [f"# バリュエーション分析の材料 — {company.display_name()}", "",
           f"**作成日**: {date}（valuation.py prepare が生成。手で直さない）", "",
           "> 執筆はこのファイルと md だけを根拠にする（raw・PDF・CSV・他の分析の md・outlook.md を開かない）。"
           "数値と判定はスクリプトが md に記入済み。",
           "> 書くのは数値の背景と解釈だけ。新しい計算をしない。割安・割高は現時点の位置づけで、株価の予測を書かない。"]
    if warnings:
        out += ["", "## 警告（スクリプトが raw を読み違えた可能性、または材料が古い。執筆の前に確かめ、完了報告に書く）", ""]
        out += [f"- {w}" for w in warnings]
    out += ["", "## 0. 前提", "", f"- 分析日: {date} / 有効期限: {valid_until}",
            f"- 株価: {X.yen(price['price'], price['currency'])}（基準日 {price['date'] or '不明'}、"
            f"分析日の{age if age is not None else '—'}日前）"]
    out += _previous_lines(previous) + _growth_lines(growth) + _upstream_lines(cands["upstream"], swot)
    out.append(f"- 地合い: {outlook['path']}（{outlook['age_days']} 日前の週。参照のみ。判定には使わない）"
               if outlook.get("path") else "- 地合い: 完成済みの outlook.md なし")
    out += ["", "## 1. 数値の要点（スクリプトが計算）", ""] + _numbers_lines(cands)
    seen: set = set()
    for number, (title, keys) in enumerate(CHAPTERS, start=2):
        out += ["", f"## {number}. {title}"]
        for key in keys:
            f = found[key]
            same = f.path is not None and (f.path, f.heading) in seen
            out += ["", f"### {f.spec.label}", "", "（上に載せた節と同じため省略）" if same else _section(f, company)]
            if f.path is not None:
                seen.add((f.path, f.heading))
    out += ["", f"## {len(CHAPTERS) + 2}. 取れていない材料", ""] + _gaps(found)
    return "\n".join(out).rstrip() + "\n"
