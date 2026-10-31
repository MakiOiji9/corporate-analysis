"""The company report's writing side: brief.md (what the writer reads), the md skeleton, and the checks build runs.

The skeleton is .ai/templates/company-report/report.md with the conclusion table filled by the script; the writer
replaces only the <!-- FILL:... --> markers. build re-renders the conclusion table from facts.json and rejects an
md whose table, headings or verdict words differ, which still has FILL markers, or which uses the words the
policy forbids (recommendations, guesses, price targets).
"""
from __future__ import annotations

from string import Template

import charts as C
import cr_judge as J
import mdparse as M
import outlook as O
from validate import check_fill, check_structure, check_tables

HORIZONS = (("short", "短期（〜3ヶ月）"), ("mid", "中期（6ヶ月〜1年）"), ("long", "長期（3年以上）"))
TEXT_KEYS = (("about", "2."), ("short", "3.1"), ("mid", "3.2"), ("long", "3.3"),
             ("thesis", "4.1"), ("break", "4.2"), ("watch", "4.3"))
LIST_KEYS = ("break", "watch")
LIMITS = {"about": 200, "short": 300, "mid": 300, "long": 350, "thesis": 200}
SUMMARY_TITLE, SUMMARY_LINES, SUMMARY_LIMIT = "3行まとめ", 3, 60
LIST_RANGE = (2, 4)
OK_MARK = {True: "○", False: "×", None: "不明"}
WRITING_RULES = "## 7. 書き方"  # the brief's last section; its term list is not the report's text (glossary)


def cell(text: object) -> str:
    return str(text if text not in (None, "") else "—").replace("|", "／").replace("\n", " ")


def verdict_label(h: dict) -> str:
    return f"{J.PENDING}（暫定: {h['provisional']}）" if h.get("provisional") else h["verdict"]


def score_text(score: float | None) -> str:
    return "—" if score is None else f"{score:+.2f}"


def short_label(label: str) -> str:
    """'株価の割安さ（STEP 3）' -> '株価の割安さ' (what a sentence about the factor names)."""
    return label.split("（")[0]


def horizon_rows(facts: dict) -> str:
    rows = []
    for key, label in HORIZONS:
        h = facts["horizons"][key]
        rows.append(f"| {label} | {verdict_label(h)} | {score_text(h['score'])} | {cell(h['why'])} |")
    return "\n".join(rows)


# ---------------------------------------------------------------- brief

def _table(header: list[str], rows: list[list[object]]) -> list[str]:
    body = ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + (
        body or ["| " + " | ".join("—" for _ in header) + " |"])


def _condition_table(rows: list[dict]) -> list[str]:
    return _table(["条件", "値", "情報源", "満たす"],
                  [[r["condition"], r["value"], r["source"], OK_MARK[r["ok"]]] for r in rows])


def _analyses(facts: dict) -> list[str]:
    d = facts["analyses"]
    lines = ["## 2. 各分析の結論", ""]
    lines += _table(["STEP", "分析", "分析日", "結論", "理由", "ファイル"],
                    [[a["step"], a["label"], a["date"], a["verdict"], a["reason"], a["md"]] for a in d.values()])
    lines += [f"\n- **{a['label']}の要点**: {a['points']}" for a in d.values() if a["points"]]
    ff, tc, sw = d["five_forces"]["detail"], d["three_c"]["detail"], d["swot"]["detail"]
    lines += ["", "### 事業・競争環境の補足", "",
              f"- 業界: {ff.get('industry') or '—'}。5要因: "
              + "、".join(f"{f['name']} {f['rating']}" for f in ff.get("factors") or []),
              f"- 勝てる理由: {tc.get('win_reason') or '—'}（顧客: {tc.get('customer') or '—'}）",
              f"- モート: {d['moat']['detail'].get('durability') or '—'}",
              f"- SWOT: {sw.get('sentence') or '—'}"]
    v = d["valuation"]["detail"]
    lines += ["", "### 株価の妥当性の補足", ""]
    lines += [f"- {name}: {cell(item.get('rating'))}。{item.get('sentence') or '—'}"
              for name, item in (v.get("items") or {}).items()]
    lines += [f"- 判定が変わる株価: {p}" for p in v.get("flip_prices") or []]
    if v.get("cheap_reason"):
        lines.append(f"- 安い理由として説明できること: {v['cheap_reason']}")
    div = facts.get("dividends") or {}
    if div.get("source"):
        lines += ["", "### 株主還元", "",
                  f"- 1株配当: 実績 {div.get('actual')}円、会社予想 {div.get('forecast')}円。配当利回り "
                  f"{div.get('yield')}%、配当性向（予想）{div.get('payout_forecast')}%"]
    med = (facts.get("peers") or {}).get("median") or {}
    if med:
        lines += ["", "### 同業の中央値（同業比較の表）", "",
                  "- " + "、".join(f"{label} {med.get(key)}" for key, label, _ in (facts["peers"].get("columns") or [])
                                   if med.get(key) is not None)]
    return lines


def _horizons(facts: dict) -> list[str]:
    lines = ["## 3. 期間ごとの判定（スクリプトが決めた。変えない）", ""]
    for name, key in (("STEP 1 総合", "step1"), ("STEP 2 総合", "step2")):
        s = facts[key]
        lines += [f"### {name}: {s['grade']}{'（暫定。判定保留を含む）' if s['pending'] else ''}", "",
                  f"理由: {s['why']}", ""] + _condition_table(s["rows"]) + [""]
    note = f"（{facts['step3']['note']}）" if facts["step3"].get("note") else ""
    lines += [f"### STEP 3: {facts['step3']['verdict'] or '—'}{note}", ""]
    for key, label in HORIZONS:
        lines += _horizon_lines(facts, key, label)
    m = facts.get("matrix") or {}
    lines += ["### 長期の参考: フレームワークの判定マトリクス", "",
              f"- {m.get('verdict', '—')}{'（' + m['note'] + '）' if m.get('note') else ''}。{m.get('why', '')}", ""]
    return lines


def _points(rows: list[dict]) -> list[str]:
    return [f"- {r['label']}（重み {r['weight']}%、点数 {r['score']:+.1f}、寄与 {r['contribution']:+.3f}）: {r['value']}。"
            f"{r['reason']}（{r['source']}）" for r in rows]


def _horizon_lines(facts: dict, key: str, label: str) -> list[str]:
    h = facts["horizons"][key]
    lines = [f"### {label}: {verdict_label(h)}（点数 {score_text(h['score'])}）", "", f"理由: {h['why']}", ""]
    lines += _table(["要素", "重み", "点数", "寄与", "値", "情報源"],
                    [[r["label"] + ("（判定保留）" if r["pending"] else ""), f"{r['weight']}%",
                      "不明" if r["score"] is None else f"{r['score']:+.1f}",
                      "—" if r["contribution"] is None else f"{r['contribution']:+.3f}", r["value"], r["source"]]
                     for r in h["rows"]])
    lines += ["", "良い点（点数を押し上げた要素）:"] + (_points(h["good"]) or ["- なし"])
    lines += ["", "悪い点（点数を押し下げた要素）:"] + (_points(h["bad"]) or ["- なし"])
    s = h.get("sensitivity") or {}
    movers = [f"{m['label']}が{m['direction']} {m['verdict']}" for m in s.get("movers") or []]
    distance = [f"投資検討まであと {s['to_up']:+.2f}" if s.get("to_up") is not None else "",
                f"見送りまであと {s['to_down']:.2f}" if s.get("to_down") is not None else ""]
    lines += ["", "判定を動かす要因: " + ("、".join(d for d in distance if d) or "—")
              + ("。" + "、".join(movers) if movers else "。1段の変化で判定が変わる要素は無い"), ""]
    return lines


def _prices(facts: dict) -> list[str]:
    p = facts["prices"]
    lines = ["## 4. 株価の過去レンジ", ""]
    if p["source"] != "prices":
        table = p.get("fallback")
        lines.append("- 日々の株価（data/prices.csv）が無い。"
                     + (f"{table['source']} の「{table['title']}」を載せる" if table else "株価のレンジは不明"))
        return lines
    lines += [f"- 期間: {p['first']}〜{p['last']}（{p['days']} 営業日、分割調整済み）。現在 {C.fmt(p['current'], 0)}", ""]
    lines += _table(["期間", "高値（日付）", "安値（日付）", "現在の位置", "高値から"],
                    [[w["label"] + ("（取得期間のみ）" if w["partial"] else ""),
                      f"{C.fmt(w['high'], 0)}（{w['high_date']}）", f"{C.fmt(w['low'], 0)}（{w['low_date']}）",
                      f"{w['position']:.0f}%", f"{C.fmt(w['from_high'], 1, True)}%"] for w in p["ranges"]])
    lines += ["", "- 移動平均: " + "、".join(
        f"{a['label']} {C.fmt(a['value'], 0)}（乖離 {C.fmt(a['gap'], 1, True)}%）" for a in p["averages"])]
    return lines


def break_candidates(facts: dict) -> list[str]:
    """Numbers-backed conditions the writer can pick for 4.2 (the framework's examples, with today's values)."""
    d = facts["analyses"]
    out = []
    margin = d["profitability"]["detail"].get("margin") or {}
    if margin.get("self") is not None and margin.get("avg") is not None:
        out.append(f"営業利益率が2期連続で同業平均を下回る（{margin.get('year')} は {margin['self']}%、"
                   f"同業平均 {margin['avg']}%）")
    roe = (d["profitability"]["detail"].get("roe_rows") or [])[-1:]
    if roe and roe[0].get("roe") is not None:
        out.append(f"ROE が2期連続で8%を下回る（{roe[0]['year']} は {roe[0]['roe']}%）")
    ratio = d["cash_flow"]["detail"].get("ratio")
    if ratio is not None:
        out.append(f"営業CF対純利益比率（5年平均と累計の低い方）が0.8倍を下回ったまま（今は {ratio}倍。"
                   "キャッシュフロー分析の判定に使った値）")
    g = d["growth"]["detail"]
    if g.get("plan_average") is not None:
        out.append(f"会社計画の達成率が90%を下回る年が続く（過去の平均 {g['plan_average']:.0f}%、{g.get('plan') or '—'}）")
    threat = d["swot"]["detail"].get("top_threat") or {}
    if threat.get("fact"):
        out.append(f"SWOT の最大の脅威（{threat.get('id')}: {threat['fact']}）が業績の数字に表れる")
    return out + [f"株価が判定の変わる水準に動く（{p}）" for p in d["valuation"]["detail"].get("flip_prices") or []]


def _premise(facts: dict) -> list[str]:
    o, price = facts["outlook"], facts["price"] or {}
    lines = ["## 1. 対象と前提", "",
             f"- 市場: {facts['market']}。金額の単位: {facts['unit']}",
             f"- 株価: {price.get('value') or '—'}{price.get('currency') or ''}（{price.get('date') or '—'} 終値。"
             "バリュエーション分析の基準日）",
             f"- 地合い: {o.get('path') or '—'}（{o.get('week') or '—'} 週、{facts['market']}の注意の度合い "
             f"{o.get('overall') or '—'}）" + (f"。要約: {o['summary']}" if o.get("summary") else "")]
    for period in ("短期", "中期", "長期"):
        row = (o.get("rows") or {}).get(period)
        if row:
            lines.append(f"  - {period}: {row['judgment']}。{row['scenario']}（下振れ要因: {row['downside']}）")
    if o.get("stale"):
        lines.append("  - 注意: 地合い判断が35日より古い")
    latest = (facts["analyses"]["growth"]["detail"].get("rows") or [{}])[-1]
    if latest.get("year"):
        lines.append(f"- 主要な数字（{latest['year']}、成長性分析）: 売上高 {C.fmt(latest.get('sales'), 0)}・"
                     f"営業利益 {C.fmt(latest.get('operating_income'), 0)}・純利益 {C.fmt(latest.get('net_income'), 0)}"
                     f"（{facts['unit']}）、EPS {C.fmt(latest.get('eps'), 1)}")
    lines.append(f"- 次回の見直し: {facts['review']}")
    for s in facts.get("stale") or []:
        lines.append(f"- 注意: {s['label']}（{s['date']}）は分析後に材料が変わったが作り直していない（{s['reason']}）。"
                     "4.3 に確かめることとして書く")
    return lines + [""]


def render_brief(facts: dict, md_rel: str) -> str:
    lines = [f"# 企業分析レポートの材料 — {facts['name']}", "",
             f"作成日: {facts['date']}。書く先: {md_rel}（FILL の欄だけ）。判定と数値はこの brief のものを使い、変えない。", ""]
    lines += _premise(facts) + _analyses(facts) + [""] + _horizons(facts) + _prices(facts) + [""]
    lines += ["## 5. 判断が崩れる条件の候補（4.2 の材料）", ""] + [f"- {c}" for c in break_candidates(facts)] + [""]
    lines += ["## 6. 材料不足（4.3 の材料）", ""]
    lines += [f"- {g['label']}: {g['gap']}" for g in facts["gaps"]] or ["- なし"]
    lines += ["", WRITING_RULES, "",
              "- 判定語（投資検討・ウォッチ・見送り・判定保留）は表と同じものを使う。各期間の説明は判定語から書き始める",
              "- 専門用語（ROE・PER・PBR・FCF・モートなど）は初めて出るところで「（＝…）」と言い換える。用語集は HTML に自動で付く",
              "- 使わない語: " + "・".join(O.FORBIDDEN) + "。株価の水準の予想も書かない",
              "- 分析ファイルに無いこと（一般論・推測）を補わない。分からないことは「不明」と書き、良い方に解釈しない"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- skeleton / parse / validate

def render_skeleton(template: str, facts: dict, brief_rel: str) -> str:
    price, o = facts["price"] or {}, facts["outlook"]
    values = {
        "company": facts["name"], "date": facts["date"], "brief": brief_rel,
        "analyses": "、".join(f"{a['label']} {a['date'] or '未実施'}" for a in facts["analyses"].values()),
        "price_date": f"{price.get('date') or '不明'}（{C.fmt(price.get('value'), 0)}{price.get('currency') or ''}）",
        "outlook": (f"{o['path']}（{facts['market']}: {o.get('overall') or '—'}。参照のみ）" if o.get("path")
                    else "—（完成済みの outlook.md なし）"),
        "horizon_rows": horizon_rows(facts), "review": facts["review"],
        **{f"{key}_verdict": verdict_label(facts["horizons"][key]) for key, _ in HORIZONS},
    }
    return Template(template).safe_substitute(values)


def _body(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">")).strip()


def _section(text: str, number: str) -> str:
    return M.section(text, number, level=2 if number.endswith(".") else 3)


def parse(text: str) -> dict:
    out: dict = {"summary": M.bullets(M.section(text, SUMMARY_TITLE, level=3))}
    for key, number in TEXT_KEYS:
        body = _body(_section(text, number))
        out[key] = M.bullets(body) if key in LIST_KEYS else body
    return out


def validate(text: str, template: str, facts: dict) -> tuple[list[str], list[str]]:
    """(issues that block build, warnings to fix when possible)."""
    issues = check_structure(text, template) + check_fill(text) + check_tables(text)
    want = horizon_rows(facts).splitlines()
    got = [line.strip() for line in _section(text, "1.").splitlines()
           if line.startswith("| ") and not line.startswith("| 期間")]
    if got != want:
        issues.append("1章の結論の表がスクリプトの判定と違う（表は変更しない。元に戻す）")
    parsed = parse(text)
    names = dict(TEXT_KEYS)
    if len(parsed["summary"]) != SUMMARY_LINES:
        issues.append(f"3行まとめは箇条書きでちょうど{SUMMARY_LINES}行（今 {len(parsed['summary'])} 行）")
    for key in LIST_KEYS:
        if not LIST_RANGE[0] <= len(parsed[key]) <= LIST_RANGE[1]:
            issues.append(f"{names[key]} は箇条書きで{LIST_RANGE[0]}〜{LIST_RANGE[1]}行（今 {len(parsed[key])} 行）")
    issues += [f"{names[key]} が空" for key in LIMITS if M.is_blank(parsed[key])]
    for key, label in HORIZONS:
        h = facts["horizons"][key]
        if M.is_blank(parsed[key]):
            continue
        if h["verdict"] not in parsed[key]:
            issues.append(f"{label}の説明に判定（{h['verdict']}）が無い（判定語から書き始める）")
        for side, rows in (("良い点", h.get("good") or []), ("悪い点", h.get("bad") or [])):
            names = [short_label(r["label"]) for r in rows]
            if names and not any(n in parsed[key] for n in names):
                issues.append(f"{label}の説明に{side}（{'・'.join(names)} のどれか）が無い（根拠の数値と一緒に書く）")
    issues += O._check_words(_body(text))
    warnings = [f"{names[k]} が {len(parsed[k])} 字（目安 {n} 字以内）" for k, n in LIMITS.items() if len(parsed[k]) > n]
    warnings += [f"3行まとめの{i}行目が {len(s)} 字（目安 {SUMMARY_LIMIT} 字以内）"
                 for i, s in enumerate(parsed["summary"], 1) if len(s) > SUMMARY_LIMIT]
    return issues, warnings
