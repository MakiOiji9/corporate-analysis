"""Single-file HTML of the company report, drawn from facts.json (numbers, judgements) and the filled md (words).

Every piece of text goes through esc() (tools/report/slides.py), so nothing from the analyses or the md can inject
markup. Charts are inline SVG from charts.py. One vertical page: conclusion first (three verdict cards and the
3-line summary), then the reasons, STEP 1・2・3, the price history, the thesis, the gaps and a glossary.
"""
from __future__ import annotations

from string import Template

import charts as C
import cr_doc as D
import cr_glossary as G
import cr_judge as J
import cr_legends as L
import cr_plain as P
import cr_sections as X
import cr_technicals as T
import slides
from slides import table


def esc(text: object) -> str:
    """slides.esc after the reader's-words pass (an internal term written anywhere still reads plainly)."""
    return slides.esc(P.plain(text) if isinstance(text, str) else text)

VERDICT_CLASS = {J.CONSIDER: "v-consider", J.WATCH: "v-watch", J.PASS: "v-pass", J.PENDING: "v-pending"}
SPANS = {"short": "〜3ヶ月", "mid": "6ヶ月〜1年", "long": "3年以上"}
PERIODS = {"short": "短期", "mid": "中期", "long": "長期"}
OK_HTML = {True: '<span class="ok-yes">○ 満たす</span>', False: '<span class="ok-no">× 満たさない</span>',
           None: '<span class="ok-unk">不明</span>'}
TOC = (("conclusion", "結論"), ("reasons", "期間ごとの良い点・悪い点"), ("step1", "STEP 1 事業"),
       ("step2", "STEP 2 財務"), ("step3", "STEP 3 株価"), ("price", "株価のレンジ"), ("technical", "売買の目安"),
       ("thesis", "投資の理由"), ("legends", "投資の神の視点"), ("gaps", "材料不足"), ("glossary", "用語集"))
SMALL_CHART_WIDTH = 380
TECH_LEAD = ("日々の株価から計算した今のチャートの状態と、注目する価格の水準。水準は「ここを下回ったら」「ここに近づいたら」と"
             "見るための条件の目安で、株価の予想でも売買の推奨でもない。事業・財務の判定（結論）は変えない。")
LEGEND_LEAD = ("3人の投資哲学をこの会社の分析結果に当てはめた参考の視点。評価はスクリプトが資料の条件で決め、"
               "結論の判定の点数には入らない。本人が実際にこの会社をこう評価したという意味ではない。")
PLAIN_HORIZONS = (("短期", "〜3ヶ月", "地合い・株価のテクニカル（流れ・勢い・位置）・直近の決算の進み具合・割安さを重く見る。値動きの影響が大きく、根拠は弱い。"),
                  ("中期", "6ヶ月〜1年", "割安さと業績の勢い（成長性・決算の進捗）を重く見て、財務と地合いも加える。"),
                  ("長期", "3年以上", "事業の強さ（勝てる理由・モート・業界）を重く見て、財務と割安さを加える。"
                   "フレームワークの判定マトリクスも参考に示す。"))
WEIGHT_NOTE = (f"各要素を +1（良い）・0（中間）・−1（悪い）の点数にし、期間ごとの重みで平均した。"
               f"+{J.UP} 以上で投資検討、{J.DOWN} 以下で見送り、その間はウォッチ。"
               "営業CF のマイナスが続く・FCF の累計がマイナス・安全性の悪化などの深刻な赤信号は、点数にかかわらず見送り。")
DISCLAIMER = ("本レポートは公表資料と収集データをもとに企業分析フレームワークに沿って整理したもので、投資の勧誘・推奨ではありません。"
              "判定は作成日時点の材料による位置づけで、将来の株価を予想するものではありません。最終的な投資判断はご自身で行ってください。")


def badge(word: str | None) -> str:
    return f'<span class="badge {VERDICT_CLASS.get(word or "", "")}">{esc(word or "—")}</span>'


def _section(sid: str, number: str, title: str, lead: str, body: str) -> str:
    lead_html = f'<p class="lead">{esc(lead)}</p>' if lead else ""
    return (f'<section id="{sid}"><div class="wrap"><span class="num">{esc(number)}</span><h2>{esc(title)}</h2>'
            f"{lead_html}{body}</div></section>")


def _paragraphs(text: str) -> str:
    return "".join(f"<p>{esc(p.strip())}</p>" for p in text.split("\n\n") if p.strip())


def _list(items: list[str]) -> str:
    if not items:
        return '<p class="muted">なし</p>'
    return '<ul class="plain">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def _conditions(rows: list[dict]) -> str:
    return table(["確かめたこと", "値", "情報源", "結果"],
                 [[esc(r["condition"]), esc(r["value"]), esc(r["source"]), OK_HTML[r["ok"]]] for r in rows],
                 nowrap=frozenset({3}))


def _details(summary: str, inner: str) -> str:
    return f'<details><summary>{esc(summary)}</summary><div class="inner">{inner}</div></details>'


# ---------------------------------------------------------------- top

def masthead(facts: dict) -> str:
    price, o = facts["price"] or {}, facts["outlook"]
    meta = [("作成日", facts["date"]), ("市場", facts["market"]),
            ("株価", f"{C.fmt(price.get('value'), 0)}{price.get('currency') or ''}（{price.get('date') or '—'} 終値）"),
            ("地合い", f"{o.get('overall') or '—'}（{o.get('week') or '—'} 週）"), ("次回の見直し", facts["review"])]
    items = "".join(f"<span>{esc(k)} <b>{esc(v)}</b></span>" for k, v in meta)
    toc = "".join(f'<a href="#{sid}">{esc(label)}</a>' for sid, label in TOC)
    return (f'<header class="masthead"><div class="wrap"><div class="kicker">企業分析レポート ・ STEP 1〜3</div>'
            f'<h1>{esc(facts["name"])}</h1><div class="meta">{items}</div></div></header>'
            f'<nav class="toc" aria-label="目次"><div class="wrap">{toc}</div></nav>')


def _card(key: str, h: dict) -> str:
    word = h["verdict"]
    score = "—" if h["score"] is None else f'{h["score"]:+.2f}'
    good = "・".join(r["label"].split("（")[0] for r in h["good"][:2]) or "なし"
    bad = "・".join(r["label"].split("（")[0] for r in h["bad"][:2]) or "なし"
    return (f'<div class="vcard {VERDICT_CLASS.get(word, "")}"><div class="period">{esc(PERIODS[key])}'
            f'（{esc(SPANS[key])}）</div><div class="word">{esc(word)}<span class="vscore">{esc(score)}</span></div>'
            f'{X.gauge(h["score"])}{_knockout_line(h)}<p class="why"><span class="ok-yes">＋</span> {esc(good)}<br>'
            f'<span class="ok-no">−</span> {esc(bad)}</p></div>')


def _knockout_line(h: dict) -> str:
    """When a knockout (赤信号・STEP 1 C) decided the verdict, the card says so: the score alone would read otherwise."""
    if not h.get("knockout") or h["score"] is None:
        return ""
    by_score = J._verdict_for(h["score"])
    if by_score == h["verdict"]:
        return ""
    return (f'<p class="small knock">点数だけなら{esc(by_score)}だが、{esc("、".join(h["knockout"]))}のため'
            f'{esc(h["verdict"])}</p>')


def _stale_notice(facts: dict) -> str:
    stale = facts.get("stale") or []
    if not stale:
        return ""
    names = "、".join(f"{s['label']}（{s['date']}）" for s in stale)
    return (f'<div class="notice"><b>注意</b>: {esc(names)} は、分析の後に新しい材料が集まったが作り直していない'
            "（既存の結果で判定した）。理由は「材料不足と使った分析」の節を参照。</div>")


def conclusion(facts: dict, parsed: dict) -> str:
    cards = _stale_notice(facts) + '<div class="verdicts">' + "".join(
        _card(k, facts["horizons"][k]) for k in ("short", "mid", "long")) + "</div>"
    summary = '<ol class="summary">' + "".join(f"<li>{esc(s)}</li>" for s in parsed["summary"]) + "</ol>"
    legend = "".join(f"<dt>{badge(w)}</dt><dd>{esc(t)}</dd>" for w, t in G.VERDICTS.items())
    spans = "".join(f"<p><b>{esc(n)}</b>（{esc(s)}）: {esc(t)}</p>" for n, s, t in PLAIN_HORIZONS)
    reading = (f'<h3>判定の読み方</h3><div class="cols"><div class="panel"><dl class="gloss">{legend}</dl></div>'
               f'<div class="panel small">{spans}<p>{esc(WEIGHT_NOTE)}</p></div></div>')
    about = f'<h3>この会社をひと言で</h3><div class="prose">{_paragraphs(parsed["about"])}</div>'
    return _section("conclusion", "01", "結論", "3つの期間それぞれで、今この会社に投資してよいかを判定した。",
                    cards + summary + about + reading)


def reasons(facts: dict, parsed: dict) -> str:
    body = "".join(X.horizon_block(PERIODS[key], SPANS[key], facts["horizons"][key], _paragraphs(parsed[key]),
                                   facts.get("matrix") if key == "long" else None)
                   for key in ("short", "mid", "long"))
    return _section("reasons", "02", "期間ごとの良い点・悪い点",
                    "期間ごとに重視する要素が違う。点数を押し上げた要素が良い点、押し下げた要素が悪い点"
                    "（点数の決め方は「結論」の「判定の読み方」）。", body)


# ---------------------------------------------------------------- STEP 1-3

def _stepcards(facts: dict, keys: tuple[str, ...]) -> str:
    cards = ""
    for key in keys:
        a = facts["analyses"][key]
        flag = '<span class="cons">材料不足のため慎重に判定</span>' if a.get("conservative") else ""
        cards += (f'<div class="stepcard"><div class="label">{esc(a["step"])} {esc(a["label"])}'
                  f'（{esc(a["date"] or "未実施")}）</div><div class="res">{esc(a["verdict"] or "—")}{flag}</div>'
                  f'<p>{esc(a["reason"])}</p></div>')
    return f'<div class="steps">{cards}</div>'


def _stephead(grade: dict, title: str) -> str:
    label = grade["grade"] + ("（暫定）" if grade["pending"] else "")
    return (f'<div class="stephead"><span class="grade g-{esc(grade["grade"])}">{esc(grade["grade"])}</span>'
            f'<div><h3>{esc(title)}: {esc(label)}</h3><p>{esc(grade["why"])}</p></div></div>')


def step1(facts: dict) -> str:
    d = facts["analyses"]
    ff = d["five_forces"]["detail"]
    forces = table(["要因", "強さ", "理由"], [[esc(f["name"]), esc(f["rating"]), esc(f["reason"])]
                                          for f in ff.get("factors") or []])
    inner = (_conditions(facts["step1"]["rows"]) + f"<h3>業界の5つの力（{esc(ff.get('industry'))}）</h3>" + forces
             + f"<h3>モート（強みの持続性）</h3><p>{esc(d['moat']['detail'].get('durability'))}</p>"
             + _conservative(d["moat"]))
    body = (_stephead(facts["step1"], "STEP 1 総合") + _stepcards(facts, ("five_forces", "three_c", "moat", "swot"))
            + X.three_c_block(d["three_c"]["detail"], d["three_c"]) + X.swot_grid(d["swot"]["detail"], d["swot"])
            + _details("詳しく見る（A の条件・業界の5つの力・モート）", inner))
    return _section("step1", "03", "STEP 1 事業と競争環境", "儲けやすい業界か、選ばれる理由があるか、その強みは続くか。", body)


def _conservative(a: dict) -> str:
    notes = a.get("conservative") or []
    return (f'<p class="small"><b>材料不足のため慎重に判定した点</b>: {esc("。".join(notes))}</p>' if notes else "")


def _year_date(year: str) -> str:
    """'2026-03' -> '2026-03-01' (charts.py places points on ISO dates)."""
    return f"{year[:7]}-01" if len(year) >= 7 else f"{year[:4]}-01-01"


def _points(rows: list[dict], key: str) -> list[list]:
    return [[_year_date(r["year"]), r[key]] for r in rows if r.get(key) is not None and r.get("year")]


def _financial_charts(facts: dict) -> str:
    d, unit = facts["analyses"], facts["unit"]
    rows = d["growth"]["detail"].get("rows") or []
    bars = (("売上高", _points(rows, "sales"), "成長性分析"), ("営業利益", _points(rows, "operating_income"), "成長性分析"),
            ("フリーキャッシュフロー（FCF）", _points(d["cash_flow"]["detail"].get("rows") or [], "fcf"),
             "キャッシュフロー分析"))
    out = '<div class="cols">'
    for title, points, source in bars:
        out += (f'<figure class="chartbox"><figcaption><b>{esc(title)}</b><span class="muted">{esc(unit)}</span>'
                f'</figcaption>{C.bar_chart(points, title)}<div class="source">出典: {esc(source)}（決算短信・有報）</div></figure>')
    roe = _points(d["profitability"]["detail"].get("roe_rows") or [], "roe")
    out += (f'<figure class="chartbox"><figcaption><b>ROE（自己資本利益率）</b><span class="muted">%</span></figcaption>'
            f'{C.line_chart([{"label": "ROE", "points": roe}], "ROE")}<div class="source">出典: 収益性分析</div></figure>')
    return out + "</div>"


def step2(facts: dict) -> str:
    d = facts["analyses"]
    safety = table(["指標", "値", "同業平均", "目安", "評価"],
                   [[esc(i["name"]), esc(C.fmt(i["value"], 1)), esc(C.fmt(i["peer_avg"], 1)), esc(i.get("target")),
                     esc(i["rating"])] for i in d["safety"]["detail"].get("items") or []], right=frozenset({1, 2}))
    cfsteps = _list([f"{s['rating']}: {s['sentence']}" for s in d["cash_flow"]["detail"].get("steps") or []
                     if s["rating"]])
    points = _list([f"{a['label']}: {a['points']}" for k, a in d.items()
                    if k in ("profitability", "growth", "safety", "cash_flow") and a["points"]])
    inner = (_conditions(facts["step2"]["rows"]) + "<h3>各分析の要点</h3>" + points + "<h3>安全性の3指標</h3>" + safety
             + "<h3>キャッシュフローの5つの確認</h3>" + cfsteps)
    body = (_stephead(facts["step2"], "STEP 2 総合") + _stepcards(facts, ("profitability", "growth", "safety", "cash_flow"))
            + _financial_charts(facts) + X.growth_block(facts) + X.dividends_block(facts)
            + _details("詳しく見る（A の条件・各分析の要点・安全性・キャッシュフロー）", inner))
    return _section("step2", "04", "STEP 2 財務", "稼ぐ力・伸びる力・つぶれにくさ・お金の流れを数字で確かめる。", body)


def step3(facts: dict) -> str:
    v = facts["analyses"]["valuation"]
    detail = v["detail"]
    cards = "".join(f'<div class="stepcard"><div class="label">{esc(name)}</div>'
                    f'<div class="res">{esc(item.get("rating") or "—")}</div><p>{esc(item.get("sentence"))}</p></div>'
                    for name, item in (detail.get("items") or {}).items())
    s3 = facts["step3"]
    note = f'<p class="notice">{esc(s3["note"])}</p>' if s3.get("note") else ""
    head = (f'<div class="stephead"><div><h3>STEP 3: {badge(s3["verdict"])}</h3><p>{esc(v["reason"])}</p>'
            f'<p class="muted">{esc(detail.get("sheet"))}</p></div></div>{note}')
    flips = _list(detail.get("flip_prices") or [])
    cheap = (f"<h3>安い理由として説明できること</h3><p>{esc(detail['cheap_reason'])}</p>"
             if detail.get("cheap_reason") else "")
    body = (head + f'<div class="steps">{cards}</div>' + X.peers_block(facts)
            + _details("判定が変わる株価・安い理由", f"<h3>判定が変わる株価</h3>{flips}{cheap}"))
    return _section("step3", "05", "STEP 3 株価の妥当性", "今の株価は、過去の水準と同業他社に比べて安いか高いか。"
                    "割安・割高は現時点の位置づけで、将来の株価の予想ではない。", body)


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


def price_section(facts: dict) -> str:
    p = facts["prices"]
    lead = "過去の高値と安値の間で、今の株価がどこにあるか（0%＝安値、100%＝高値）。位置はレンジの説明で、先行きの予想ではない。"
    if p["source"] != "prices":
        return _fallback(p, lead)
    tracks = '<div class="panel ranges">' + "".join(_track(w) for w in p["ranges"]) + "</div>"
    series = [{"label": "月末の終値", "points": p["monthly"]["close"]},
              {"label": "26週移動平均", "points": p["monthly"]["ma"]}]
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
    body = (f"<h3>今の株価の位置</h3>{tracks}<h3>株価の推移</h3>{chart}"
            f'<p class="small">移動平均: {esc(ma or "—")}</p>'
            + (f'<p class="small">{esc(per_line)}</p>' if per_line else "") + _price_tables(p))
    return _section("price", "06", "株価の過去レンジ", lead, body)


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


def technical_section(facts: dict, parsed: dict) -> str:
    t = D.technicals(facts)
    if not t.get("ok") or t["state"] == T.NO_DATA:
        return _section("technical", "07", "売買の目安（テクニカルの参考）", TECH_LEAD,
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
    return _section("technical", "07", "売買の目安（テクニカルの参考）", TECH_LEAD, body)


# ---------------------------------------------------------------- thesis / gaps / glossary

def thesis(facts: dict, parsed: dict) -> str:
    body = (f'<div class="cols"><div class="panel"><h3>投資の理由（または見送りの理由）</h3>{_paragraphs(parsed["thesis"])}'
            f'</div><div class="panel"><h3>判断が崩れる条件</h3>{_list(parsed["break"])}</div></div>'
            f'<h3>次に確かめること</h3>{_list(parsed["watch"])}'
            f'<p class="small"><b>次回の見直し</b>: {esc(facts["review"])}</p>')
    return _section("thesis", "08", "投資の理由と判断が崩れる条件", "", body)


def _legend_card(v: dict, prose: str) -> str:
    checks = table(["項目", "値", "結果", "情報源"],
                   [[esc(f"{c['id']} {c['item']}"), esc(c["value"]), OK_HTML[c["ok"]], esc(c["source"])]
                    for c in v["checks"]], nowrap=frozenset({2}))
    notes = "".join(f'<p class="small muted">{esc(n)}</p>' for n in v["notes"])
    return (f'<div class="stepcard"><div class="label">{esc(v["name"])}（{esc(v["horizon"])}の見方）</div>'
            f'<div class="res"><span class="badge {L.VERDICT_CLASS.get(v["verdict"], "")}">{esc(v["verdict"])}</span></div>'
            f'<p class="small muted">{esc(v["philosophy"])}</p><p>{esc(v["why"])}</p>{prose}{notes}'
            f'{_details("確かめた項目", checks)}</div>')


def legends(facts: dict, parsed: dict) -> str:
    found = facts.get("legends") or {}
    if not found:
        return ""
    cards = "".join(_legend_card(v, _paragraphs(parsed.get(k) or "")) for k, v in found.items())
    return _section("legends", "09", "投資の神の視点（参考）", LEGEND_LEAD, f'<div class="steps">{cards}</div>')


def _link(facts: dict, md: str | None) -> str:
    if not md:
        return "—"
    prefix = f"companies/{facts['company']}/"
    href = "../" + md[len(prefix):] if md.startswith(prefix) else md
    return f'<a href="{slides.esc(href)}">分析の本文</a>'


def gaps(facts: dict) -> str:
    rows = [[esc(a["step"]), esc(a["label"]), esc(a["date"] or "未実施"), esc(a["verdict"] or "—"), _link(facts, a["md"])]
            for a in facts["analyses"].values()]
    stale = facts.get("stale") or []
    stale_html = ("<h3>作り直していない分析（既存の結果を使用）</h3>"
                  + _list([f"{s['label']}（{s['date']}、{s['result']}）: {s['reason']}" for s in stale]) if stale else "")
    body = (_list([f"{g['label']}: {g['gap']}" for g in facts["gaps"]]) + stale_html
            + "<h3>このレポートが使った分析</h3>"
            + table(["STEP", "分析", "分析日", "結論", "ファイル"], rows, nowrap=frozenset({2})))
    return _section("gaps", "10", "材料不足と使った分析", "判定に影響しうる、まだ確かめられていない点。", body)


def glossary(text: str) -> str:
    terms = G.terms_in(text)
    body = (f'<dl class="gloss">{"".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in terms)}</dl>' if terms
            else '<p class="muted">なし</p>')
    return _section("glossary", "11", "用語集", "このレポートに出てくる言葉の意味。", body)


def render(template: str, facts: dict, parsed: dict, md_text: str) -> str:
    main = X.annotate(conclusion(facts, parsed) + reasons(facts, parsed) + step1(facts) + step2(facts) + step3(facts)
                      + price_section(facts) + technical_section(facts, parsed) + thesis(facts, parsed)
                      + legends(facts, parsed) + gaps(facts))
    body = (masthead(facts) + "<main>" + main
            + glossary(md_text + D.render_brief(facts, "").split(D.WRITING_RULES)[0])
            + f'</main><footer><div class="wrap"><p>{esc(DISCLAIMER)}</p>'
              f'<p>作成: 企業分析レポートの作成スクリプト（{esc(facts["date"])}）</p></div></footer>')
    return Template(template).safe_substitute(title=esc(f"{facts['name']} 企業分析レポート {facts['date']}"), body=body)
