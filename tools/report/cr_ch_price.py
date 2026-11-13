"""株価の動きとタイミング: the price history (range position, long trend, monthly chart), today's moves against the
market and sector, and the technical levels. Moved out of cr_render.py as one chapter."""
from __future__ import annotations

import charts as C
import cr_doc as D
import cr_technicals as T
from cr_html import OK_HTML, esc
from cr_html import bullet_list as _list
from cr_html import details, section
from cr_html import paragraphs as _paragraphs
from slides import table

SMALL_CHART_WIDTH = 380
TECH_LEAD = ("日々の株価から計算した今のチャートの状態と、注目する価格の水準。水準は「ここを下回ったら」「ここに近づいたら」と"
             "見るための条件の目安で、株価の予想でも売買の推奨でもない。事業・財務の判定（結論）は変えない。")
CHAPTER_LEAD = ("株価が過去のどこにあり、今どう動いているか。長期の流れ・チャートの状態・注目する価格の水準を見る。"
                "いずれも過去と現在の説明で、先行きの予想ではない。")


def _section(sid: str, number: str, title: str, lead: str, body: str) -> str:
    """One part of the chapter (the three parts were chapters of their own; number is no longer shown)."""
    lead_html = f'<p class="small muted">{esc(lead)}</p>' if lead else ""
    return f'<div class="sub" id="{sid}"><h3 class="subhead">{esc(title)}</h3>{lead_html}{body}</div>'


def chapter(facts: dict, parsed: dict, number: str) -> str:
    """株価の動きとタイミング: the range and trend first, the trading levels next, the day-to-day moves folded."""
    moves = moves_section(facts, parsed)
    return section("market", number, "株価の動きとタイミング", CHAPTER_LEAD,
                   price_section(facts) + technical_section(facts, parsed)
                   + details("今の株価の動き（市場・業種との比較、大きく動いた日、局面、業界の追い風）", moves))


def scenarios(facts: dict) -> str:
    """The buy-price scenarios (shown in the strategy chapter)."""
    return _scenarios(facts.get("scenarios") or {})

# ---------------------------------------------------------------- price

def _track(w: dict) -> str:
    pos = w["position"]
    label = esc(w["label"]) + ('<br><span class="muted">（取得期間のみ）</span>' if w["partial"] else "")
    return (f'<div class="range"><div class="lbl">{label}</div><div class="track" role="img" '
            f'aria-label="{esc(w["label"])}のレンジで現在の位置 {pos:.0f}%"><div class="bar"></div>'
            f'<div class="mark" style="left:{pos:.1f}%"></div><div class="at" style="left:{min(max(pos, 8), 92):.1f}%">'
            f'現在 {pos:.0f}%</div><span class="lo">安値 {esc(C.fmt(w["low"], 0))}</span>'
            f'<span class="hi">高値 {esc(C.fmt(w["high"], 0))}</span></div></div>')


def _fallback(p: dict, lead: str) -> str:
    data = p.get("fallback")
    if not data:
        return _section("price", "06", "株価の過去レンジ", lead, '<p class="muted">株価のデータが取得できていない。</p>')
    header = list(data["rows"][0].keys())
    body = (f'<p class="small muted">日々の株価が取得できなかったため、{esc(data["source"])} の'
            f'「{esc(data["title"])}」を載せる。</p>' + table(header, [[esc(r.get(h)) for h in header] for r in data["rows"]]))
    return _section("price", "06", "株価の過去レンジ", lead, body)


def _price_tables(p: dict) -> str:
    ranges = table(["期間", "高値", "日付", "安値", "日付", "現在の位置", "高値から"],
                   [[esc(w["label"]), esc(C.fmt(w["high"], 0)), esc(w["high_date"]), esc(C.fmt(w["low"], 0)),
                     esc(w["low_date"]), f'{w["position"]:.0f}%', f'{esc(C.fmt(w["from_high"], 1, True))}%']
                    for w in p["ranges"]], right=frozenset({1, 3, 5, 6}), nowrap=frozenset({2, 4}))
    years = table(["年", "高値", "安値", "年末（直近）の終値", "前年比"],
                  [[esc(y["year"] + ("（途中）" if y["partial"] else "")), esc(C.fmt(y["high"], 0)),
                    esc(C.fmt(y["low"], 0)), esc(C.fmt(y["close"], 0)),
                    esc(C.fmt(y["change"], 1, True) + "%" if y["change"] is not None else "—")]
                   for y in p["yearly"]], right=frozenset({1, 2, 3, 4}))
    return "<h3>期間ごとの高値・安値</h3>" + ranges + "<h3>年ごとの高値・安値</h3>" + years


TREND_CLASS = {"上昇トレンド": "v-consider", "レンジ": "v-watch", "下降トレンド": "v-pass"}


def _long_trend(trend: dict) -> str:
    """長期の流れ: 上昇トレンド / 下降トレンド / レンジ from the month-end closes, with each window's numbers."""
    if not trend.get("verdict"):
        return ""
    rows = [[esc(label), esc(w["verdict"]), f"{w['annual']:+.1f}%", f"{w['r2']:.2f}", f"{w['max_drawdown']:.0f}%",
             esc(f"{C.fmt(w['band'][0], 0)}〜{C.fmt(w['band'][1], 0)}")] for label, w in trend["windows"].items()]
    return (f'<h3>長期の流れ</h3><p><span class="badge {TREND_CLASS.get(trend["verdict"], "")}">'
            f'{esc(trend["verdict"])}</span> {esc(trend["sentence"])}</p>'
            + (f'<p class="small">{esc(trend["vs_eps"])}</p>' if trend.get("vs_eps") else "")
            + table(["期間", "判定", "傾向線の年率", "あてはまり（R²）", "最大の下落", "月末の終値の8割の幅"], rows,
                    right=frozenset({2, 3, 4}))
            + '<p class="small muted">月末の終値の対数に直線を当てはめた傾き（年率）。あてはまり 0.5 以上で年率 ±5% を超えれば'
              "上昇・下降トレンド、それ以外はレンジ。過去の値動きの説明で、先行きの予想ではない。</p>")


WIND_CLASS = {"追い風": "v-consider", "中立": "v-watch", "向かい風": "v-pass"}


def _winds(w: dict) -> str:
    """業界の追い風・向かい風: the sector's strength and the written facts of the weekly market report."""
    if not w.get("ok"):
        return (f'<h3>業界の追い風・向かい風</h3><p class="small muted">材料なし（{esc(w.get("why") or "")}）</p>'
                if w else "")
    rows = [["株価の相対の強さ", esc(w["strength"]),
             esc(f"6か月 指数との差 {C.fmt(w.get('rel6'), 1, True)}pt・12か月 {C.fmt(w.get('rel12'), 1, True)}pt"),
             "週次の地合いレポート"]]
    rows += [[esc(i["kind"]), esc(i["direction"]), esc(i["basis"]), esc(i["source"])] for i in w["items"]]
    related = ("<p class=\"small\"><b>事業に関係しうる地合いの出来事（点数に入れない）</b></p>"
               + _list(w["related"]) if w.get("related") else "")
    return (f'<h3>業界の追い風・向かい風（{esc(w["market"])}・{esc(w["sector"])}）</h3>'
            f'<p><span class="badge {WIND_CLASS.get(w["verdict"], "")}">{esc(w["verdict"])}</span> '
            f'{esc(w["why"])}（地合いレポート {esc(w["week"])} の週）</p>'
            + table(["見たもの", "方向", "内容", "出典"], rows) + related
            + '<p class="small muted">株価の強さ（強い +1・弱い −1）と、地合いレポートが業種ごとに挙げた事実（追い風 +1・'
              "向かい風 −1）の合計。参考の表示で、判定の点数には入らない。</p>")


def price_section(facts: dict) -> str:
    p = facts["prices"]
    lead = "過去の高値と安値の間で、今の株価がどこにあるか（0%＝安値、100%＝高値）。位置はレンジの説明で、先行きの予想ではない。"
    if p["source"] != "prices":
        return _fallback(p, lead)
    tracks = '<div class="panel ranges">' + "".join(_track(w) for w in p["ranges"]) + "</div>"
    trend = p.get("long_trend") or {}
    series = [{"label": "月末の終値", "points": p["monthly"]["close"]},
              {"label": "26週移動平均", "points": p["monthly"]["ma"]}]
    if trend.get("line"):
        series.append({"label": f"長期の傾向線（{trend['basis']}）", "points": trend["line"]})
    legend = '<div class="legend">' + "".join(f'<span><i class="sw s{i}"></i>{esc(s["label"])}</span>'
                                              for i, s in enumerate(series)) + "</div>"
    chart = (f'<figure class="chartbox"><figcaption><b>株価の推移（{esc(p["first"])}〜{esc(p["last"])}）</b>{legend}'
             f'</figcaption>{C.line_chart(series, "株価の推移", 0)}'
             '<div class="source">分割調整済み。出典: Yahoo Finance（日々の株価）</div></figure>')
    ma = "、".join(f"{a['label']} {C.fmt(a['value'], 0)}（今の株価との差 {C.fmt(a['gap'], 1, True)}%）"
                  for a in p["averages"] if a["value"])
    per = facts["analyses"]["valuation"]["detail"].get("per_range") or {}
    per_line = (f"PER（株価が利益の何倍か）の過去5期のレンジは {C.fmt(per.get('low'))}〜{C.fmt(per.get('high'))}倍で、"
                f"今はその中の位置 {per.get('position')}%" if per.get("low") is not None else "")
    body = (f"<h3>今の株価の位置</h3>{tracks}{_long_trend(trend)}"
            f"<h3>株価の推移</h3>{chart}"
            f'<p class="small">移動平均: {esc(ma or "—")}</p>'
            + (f'<p class="small">{esc(per_line)}</p>' if per_line else "")
            + details("期間ごと・年ごとの高値と安値", _price_tables(p)))
    return _section("price", "06", "株価の過去レンジ", lead, body)


# ---------------------------------------------------------------- moves (今の株価の動き)

MOVES_LEAD = ("今の株価の動きを、市場全体・業種と比べ、大きく動いた日の開示と、チャートの指標と合わせて見る。"
              "動いた理由として挙げるのは日付の合う開示だけで、推測はしない。")
PHASE_CLASS = {"下落局面": "v-pass", "上昇局面": "v-consider", "どちらでもない": "v-watch"}


def _pct_cell(v: float | None) -> str:
    return "—" if v is None else f"{C.fmt(v, 1, True)}%"


def _move_tables(m: dict) -> str:
    rows = [[esc(r["label"]), _pct_cell(r["stock"]), _pct_cell(r["index"]), _pct_cell(r["vs_index"]),
             _pct_cell(r["sector"]), _pct_cell(r["vs_sector"])] for r in m["returns"]]
    out = table(["期間", "株価", esc(m["index_name"]), "市場との差", esc(f"業種（{m.get('sector_name') or '—'}）"),
                 "業種との差"], rows, right=frozenset({1, 2, 3, 4, 5}))
    s = m.get("split")
    if s:
        out += (f'<p><b>地合いの分と会社固有の分（{esc(s["span"])}）</b>: 株価 {_pct_cell(s["stock"])} のうち、'
                f'市場の動きで説明できる分 {_pct_cell(s["market"])}（β {s["beta"]:.2f} × 市場）、'
                f'会社固有の分 {_pct_cell(s["own"])}</p>')
    days = [[esc(d["date"]), _pct_cell(d["change"]), esc(f"{d['volume_ratio']}倍" if d["volume_ratio"] else "—"),
             _pct_cell(d["index_change"]),
             "<br>".join(f'{esc(n["date"])} {esc(n["kind"])}「{esc(n["title"])}」' for n in d["news"])
             or '<span class="muted">前後2営業日に開示なし</span>'] for d in m.get("big_days") or []]
    out += ("<h3>大きく動いた日と開示</h3>" + (table(["日付", "株価", "出来高（ふだんの何倍）", "市場", "前後2営業日の開示"],
                                                 days, right=frozenset({1, 2, 3}), nowrap=frozenset({0}))
                                           if days else '<p class="muted">直近120営業日になし</p>')
            + '<p class="small muted">大きく動いた日＝ふだんの1日の値幅（ATR）の2倍以上動き、出来高がふだんの1.5倍以上の日。</p>')
    out += "<h3>チャートの指標がそろって示していること</h3>" + _list(m.get("consensus") or [])
    return out + "".join(f'<p class="small muted">{esc(n)}</p>' for n in m.get("notes") or [])


def _phase_card(p: dict, prose: str) -> str:
    if not p:
        return ""
    checks = table(["確かめたこと", "値", "結果"], [[esc(c["item"]), esc(c["value"]), OK_HTML[c["ok"]]]
                                                   for c in p["checks"]], nowrap=frozenset({2}))
    return (f'<h3>株価の局面の見方（参考）</h3><p><span class="badge {PHASE_CLASS.get(p["phase"], "")}">'
            f'{esc(p["phase"])}</span> <b>{esc(p["verdict"])}</b></p>{prose}{checks}'
            '<p class="small muted">下落局面では「優良企業が割安になったか」、上昇局面では「業績が伴っているか、期待が先行して'
            "いないか」を見る参考の視点。判定の点数には入らず、売買の推奨でもない。</p>")


def moves_section(facts: dict, parsed: dict) -> str:
    m = facts.get("moves") or {}
    body = _paragraphs(parsed.get("moves") or "")
    body += _move_tables(m) if m.get("ok") else f'<p class="muted">{esc("。".join(m.get("notes") or ["材料なし"]))}</p>'
    body += _phase_card(facts.get("phase") or {}, _paragraphs(parsed.get("phase") or ""))
    body += _winds(facts.get("winds") or {}) + _paragraphs(parsed.get("winds") or "")
    return _section("moves", "07", "今の株価の動き", MOVES_LEAD, body)


# ---------------------------------------------------------------- technical

def _level_box(cls: str, title: str, items: list[dict], note: str = "") -> str:
    rows = "".join(f"<li>{esc(x['label'])} <b>{esc(C.fmt(x['price'], 0))}</b>（{esc(C.fmt(x['gap'], 1, True))}%）</li>"
                   for x in items) or '<li class="muted">—</li>'
    extra = f'<p class="small muted">{esc(note)}</p>' if note else ""
    return f'<div class="tech-box {cls}"><h4>{esc(title)}</h4><ul>{rows}</ul>{extra}</div>'


def _legend_row(items: list[tuple[str, str]]) -> str:
    return '<div class="legend">' + "".join(f'<span><i class="sw {c}"></i>{esc(lab)}</span>' for c, lab in items) + "</div>"


def _tech_charts(t: dict) -> str:
    ch, lv = t["chart"], t["levels"]
    stop = lv.get("stop")
    hlines = ([{"label": "押し目", "value": x["price"], "cls": "sup"} for x in lv["supports"]]
              + [{"label": "利益確定", "value": x["price"], "cls": "res"} for x in lv["resistances"]]
              + ([{"label": "損切り", "value": stop["price"], "cls": "stop"}] if stop else []))
    series = [{"label": "終値", "points": ch["close"]}, {"label": "13週線", "points": ch["ma_short"]},
              {"label": "26週線", "points": ch["ma_mid"]},
              {"label": "ボリンジャーバンド +2σ", "points": ch["bb_upper"], "cls": "band"},
              {"label": "ボリンジャーバンド −2σ", "points": ch["bb_lower"], "cls": "band"}]
    legend = _legend_row([("s0", "終値"), ("s1", "13週線"), ("s2", "26週線"), ("band", "ボリンジャーバンド ±2σ")])
    drawn = {h["cls"] for h in hlines}
    colours = "、".join(text for cls, text in (("sup", "緑の点線＝押し目の目安"), ("res", "紫＝利益確定の目安"),
                                               ("stop", "赤＝損切りの目安")) if cls in drawn)
    price = (f'<figure class="chartbox"><figcaption><b>直近1年の株価と目安の水準</b>{legend}</figcaption>'
             f'{C.line_chart(series, "直近1年の株価と目安の水準", 0, hlines=hlines)}'
             f'<div class="source">{esc(colours + "。" if colours else "")}出典: 日々の株価（Yahoo Finance）</div></figure>')
    # drawn narrow so the text stays readable when two charts share a row
    rsi = C.line_chart([{"label": "RSI(14)", "points": ch["rsi"]}], "RSI", 0, width=SMALL_CHART_WIDTH, height=220,
                       hlines=[{"label": "買われすぎ", "value": T.RSI_HIGH, "cls": "ref"},
                               {"label": "売られすぎ", "value": T.RSI_LOW, "cls": "ref"}])
    macd = C.bar_chart(ch["macd_hist"], "MACD ヒストグラム", 1, width=SMALL_CHART_WIDTH, height=220)
    return (price + f'<div class="cols"><figure class="chartbox"><figcaption><b>RSI（14日）</b></figcaption>{rsi}'
            f'</figure><figure class="chartbox"><figcaption><b>MACD のヒストグラム（MACD − シグナル）</b></figcaption>'
            f'{macd}</figure></div>')


SCENARIO_LEAD = ("買いを検討する価格の候補ごとに、根拠・損切り・利益確定の目安と、その価格で買った場合のリスクを並べた。"
                 "価格はチャートの支持線・抵抗線と株価指標の割安・適正の水準から計算した条件の目安で、"
                 "その価格になるという予想でも、売買の推奨でもない。リスクリワード＝利確1までの上昇幅 ÷ 損切りまでの下落幅。")


def _price_cell(level: dict | None, pct: float | None = None) -> str:
    if not level:
        return "—"
    tail = f"（{C.fmt(pct, 1, True)}%）" if pct is not None else ""
    return f'<b>{esc(C.fmt(level["price"], 0))}</b>{esc(tail)}<br><span class="small muted">{esc(level["label"])}</span>'


def _scenarios(s: dict) -> str:
    if not s.get("ok"):
        return ""
    rows = [[f'<b>{esc(C.fmt(b["price"], 0))}</b><br><span class="small">{esc(b["basis"])}</span>',
             _price_cell(b["stop"], b["down"]), _price_cell(b["target1"], b["up1"]), _price_cell(b["target2"], b["up2"]),
             esc("—" if b["rr"] is None else f'{b["rr"]:.2f}'),
             '<ul class="plain small">' + "".join(f"<li>{esc(r)}</li>" for r in b["risks"]) + "</ul>"]
            for b in s["buys"]]
    holder = s.get("holder") or {}
    hold_rows = ([["利益確定を考える価格", _price_cell(x)] for x in holder.get("take") or []]
                 + [["撤退を考える価格", _price_cell(x)] for x in holder.get("exit") or []])
    return (f'<h3>売買シナリオ（参考）</h3><p class="small">{esc(SCENARIO_LEAD)}</p>'
            + table(["買いを検討する価格（根拠）", "損切り", "利益確定1", "利益確定2", "リスクリワード",
                     "その価格で買った場合のリスク"], rows, right=frozenset({4}))
            + ("<h4>保有している場合の目安</h4>" + table(["目安", "価格"], hold_rows) if hold_rows else ""))


def technical_section(facts: dict, parsed: dict) -> str:
    t = D.technicals(facts)
    if not t.get("ok") or t["state"] == T.NO_DATA:
        return _section("technical", "08", "売買の目安（テクニカルの参考）", TECH_LEAD,
                        f'<p class="muted">{esc(T.NO_DATA)}</p>{_paragraphs(parsed.get("technical") or "")}')
    lv = t["levels"]
    stop = lv.get("stop")
    boxes = ('<div class="tech-grid">' + _level_box("sup", "押し目の目安（下の支持線）", lv["supports"])
             + _level_box("res", "利益確定の目安（上の抵抗線）", lv["resistances"])
             + _level_box("stop", "損切りの目安", [stop] if stop else [], stop["basis"] if stop else "") + "</div>")
    head = (f'<p><b>今の状態</b>: <span class="badge v-watch">{esc(t["state"])}</span>'
            f'　テクニカル点数 {esc(D.score_text(t["score"]))}（短期・中期の判定の「株価のテクニカル」）</p>')
    positioning = facts["prices"].get("positioning") or {}
    rows = [["トレンド", t["trend"]["value"]], ["勢い", t["momentum"]["value"]], ["位置", t["position"]["value"]],
            ["出来高", t["volume"]["value"]], ["シグナル", "、".join(t["signals"]) or "なし"],
            ["需給（信用残・空売り）", "。".join([positioning.get("text") or "—", *(positioning.get("notes") or [])])]]
    note = T.alignment(t, facts["horizons"]["long"]["verdict"])
    body = (head + _paragraphs(parsed.get("technical") or "") + boxes
            + (f'<p class="small"><b>長期の判定との関係</b>: {esc(note)}</p>' if note else "")
            + table(["見たもの", "値"], [[esc(a), esc(b)] for a, b in rows]) + _tech_charts(t))
    return _section("technical", "08", "売買の目安（テクニカルの参考）", TECH_LEAD, body)
