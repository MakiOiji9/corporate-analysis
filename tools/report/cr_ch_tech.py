"""テクニカル分析（切り口別）: the chapter drawn from facts["technical_analysis"] (cr_tech_cache.py).

Per timeframe (daily, weekly): the overall reading and its breakdown, three scenarios with trigger / target /
invalidation, a chart with the pattern drawn on it, the detected patterns with their past record, and one folded
block per aspect with its evidence. The fixed disclaimer is written here, not by the writer."""
from __future__ import annotations

import charts as C
import cr_patterns as P
import cr_tech_views as V
from cr_html import details, esc, section
from slides import table

LEAD = ("日足（1日ごと）と週足（1週ごと）の株価から、トレンド・勢い・値動きの大きさ・出来高・水準・チャートパターンの"
        "切り口ごとに今の状態と見立てを示す。見立てには、そう考える根拠と、見立てが崩れる条件、確度を添える。")
DISCLAIMER = ("ここに示すのは過去の値動きから計算した見立てで、将来の株価を保証するものではなく、確実でもない。"
              "チャートパターンのうち「形成中」のものは、まだ確定していない。過去に同じパターンで見立てが当たった割合も、"
              "これからの結果を保証しない。売買の推奨ではなく、この章の内容は結論の判定の点数には入らない。")
DIR = {P.UP: "上向き", P.DOWN: "下向き", P.FLAT: "中立", None: "判定できない"}
DIR_CLASS = {P.UP: "v-consider", P.DOWN: "v-pass", P.FLAT: "v-watch", None: "v-pending"}
CONF_NOTE = "確度は、切り口の向きがどれだけそろっているかで決めた目安（高・中・低）。当たる確率ではない。"
UNIT = {P.DAILY: "日", P.WEEKLY: "週"}


def _badge(direction: str | None, text: str | None = None) -> str:
    return f'<span class="badge {DIR_CLASS[direction]}">{esc(text or DIR[direction])}</span>'


def _px(v: float | None) -> str:
    return "—" if v is None else P.px(v)


def _history(p: dict) -> str:
    h = p.get("history")
    if not h or not h.get("n"):
        return "この銘柄の過去に同じ形は見つからない"
    rate = f"{h['after']}{h['unit']}後に想定の向きへ進んだのは {h['hit_rate']:.0%}"
    note = "（件数が少ない参考値）" if h.get("ref") else ""
    return f"この銘柄の過去 {h['n']} 回のうち、{rate}。値動きの中央値 {h['median_return']:+.1%}{note}"


def _pattern_table(v: dict) -> str:
    pats = v["patterns"]["patterns"]
    if not pats:
        return '<p class="muted">今の株価に当てはまるチャートパターンは見つからない。</p>'
    rows = []
    for p in pats:
        stable = "感度を変えても現れる" if p.get("stable") else "感度により現れたり消えたりする"
        rows.append([esc(p["name"]), esc(p["status"]), _badge(p["bias"], {"up": "上昇", "down": "下落", "flat": "どちらか"}[p["bias"]]),
                     esc(f"確認ライン {_px(p['trigger'])}／目標 {_px(p['target'])}／失敗となる価格 {_px(p['invalidation'])}"),
                     esc(stable), esc(_history(p))])
    sentences = "".join(f"<li>{esc(p['sentence'])}</li>" for p in pats)
    return (table(["パターン", "状態", "向き", "価格", "見つけやすさ", "この銘柄の過去の実績"], rows)
            + f'<ul class="small">{sentences}</ul>')


def _scenarios(v: dict) -> str:
    sc = v["overall"]["scenarios"]
    leading = sc.get("leading")
    rows = [[esc(s["name"]) + (" （有力）" if s["name"] == leading else ""), esc(s["text"]),
             esc(s["confidence"])] for s in (sc["bull"], sc["base"], sc["bear"])]
    note = (f"今は「{leading}」の確度が相対的に高い。" if leading else "確度が頭ひとつ抜けた見立てはない。")
    return (table(["見立て", "内容（トリガー・目安・崩れる条件）", "確度"], rows, nowrap=frozenset({2}))
            + f'<p class="small muted">{esc(note + CONF_NOTE)}</p>')


def _breakdown(v: dict) -> str:
    o = v["overall"]
    rows = [[esc(b["name"]), _badge(b["direction"]), esc(b["state"])] for b in o["breakdown"]]
    note = f'<p class="small">{esc(o["momentum_note"])}</p>' if o.get("momentum_note") else ""
    return (f'<p><b>総合</b>: {esc(o["headline"])}</p>' + table(["切り口", "向き", "状態"], rows) + note)


def _chart(v: dict) -> str:
    ch, tf = v["chart"], v["timeframe"]
    start = ch["close"][0][0]
    a, b, _ = V.MA[tf]
    unit = UNIT[tf]
    series = [{"label": "終値", "points": ch["close"]}, {"label": f"{a}{unit}線", "points": ch["mas"][str(a)]},
              {"label": f"{b}{unit}線", "points": ch["mas"][str(b)]}]
    legend = [("s0", "終値"), ("s1", f"{a}{unit}線"), ("s2", f"{b}{unit}線")]
    pats = [p for p in v["patterns"]["patterns"] if p["status"] != P.FAILED]
    hlines = []
    lv = v["aspects"]["levels"]
    if lv.get("supports"):
        hlines.append({"label": "支持線", "value": lv["supports"][0]["price"], "cls": "sup"})
    if lv.get("resistances"):
        hlines.append({"label": "抵抗線", "value": lv["resistances"][0]["price"], "cls": "res"})
    if pats:
        p = pats[0]
        pts = [[q["date"], q["price"]] for q in p["pivots"] if q["date"] >= start]
        if len(pts) >= 2:
            series.append({"label": p["name"] + "の山谷", "points": pts, "cls": "zig"})
            legend.append(("zig", p["name"] + "の山谷"))
        for ln in p["lines"]:
            lp = [[q["date"], q["price"]] for q in ln["points"] if q["date"] >= start]
            if len(lp) >= 2:
                series.append({"label": ln["label"], "points": lp, "cls": "neck"})
                legend.append(("neck", ln["label"]))
        if p.get("target") is not None:
            hlines.append({"label": "目標", "value": p["target"], "cls": "ref"})
        if p.get("invalidation") is not None:
            hlines.append({"label": "失敗の線", "value": p["invalidation"], "cls": "stop"})
    seen = set()
    legend_html = '<div class="legend">' + "".join(
        f'<span><i class="sw {c}"></i>{esc(t)}</span>' for c, t in legend if not (c in seen or seen.add(c))) + "</div>"
    title = f"{v['label']}の株価とチャートパターン"
    return (f'<figure class="chartbox"><figcaption><b>{esc(title)}</b>{legend_html}</figcaption>'
            f'{C.line_chart(series, title, 0, hlines=hlines)}'
            f'<div class="source">緑＝支持線、紫＝抵抗線、赤＝パターンが失敗となる価格、灰＝パターンの目標。'
            f'出典: 日々の株価（Yahoo Finance）</div></figure>')


def _aspect(a: dict) -> str:
    items = "".join(f'<li><span class="tag">{esc(e["style"])}</span>{esc(e["text"])}</li>' for e in a["evidence"])
    ev = f'<ul class="tx-ev">{items}</ul>' if items else ""
    head = f'{a["name"]}: {a["state"]}（確度 {a["confidence"]}）'
    inner = f'<p><b>見立て</b>: {esc(a["outlook"])}</p>{ev}'
    return details(head, inner)


def _timeframe(v: dict, sid: str) -> str:
    if not v["ok"]:
        return (f'<div class="sub" id="{sid}"><h3 class="subhead">{esc(v["label"])}</h3>'
                '<p class="muted">株価の本数が足りないため判定しない。</p></div>')
    asp = "".join(_aspect(v["aspects"][k]) for k in V.KEYS)
    body = (_breakdown(v) + _scenarios(v) + _chart(v)
            + '<p class="small"><b>チャートパターン</b></p>' + _pattern_table(v)
            + '<p class="small"><b>切り口ごとの根拠</b>（順張り＝流れに乗る指標、逆張り＝行き過ぎを見る指標）</p>' + asp)
    return (f'<div class="sub" id="{sid}"><h3 class="subhead">{esc(v["label"])}（終値 {esc(_px(v["current"]))}、'
            f'{esc(v["date"])} まで）</h3>{body}</div>')


def chapter(facts: dict, number: str) -> str:
    t = facts.get("technical_analysis") or {}
    disclaimer = f'<div class="callout disclaimer"><p>{esc(DISCLAIMER)}</p></div>'
    if not t.get("ok"):
        return section("tech", number, "テクニカル分析（切り口別）", LEAD,
                       disclaimer + '<p class="muted">日々の株価が足りないため、テクニカル分析は出せない。</p>')
    meta = (f'<p class="small muted">終値の日付: {esc(t["price_asof"])}。分析日時: {esc(t["generated_at"][:16].replace("T", " "))}'
            '（日本時間）。終値の日付が変わらない間は、同じ分析を使い回す。</p>')
    align = f'<p><b>日足と週足の関係</b>: {esc(t["alignment"])}</p>' if t.get("alignment") else ""
    return section("tech", number, "テクニカル分析（切り口別）", LEAD,
                   disclaimer + meta + align + _timeframe(t["daily"], "tech-daily") + _timeframe(t["weekly"], "tech-weekly"))
