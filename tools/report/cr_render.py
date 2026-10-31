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
from slides import esc, table

VERDICT_CLASS = {J.CONSIDER: "v-consider", J.WATCH: "v-watch", J.PASS: "v-pass", J.PENDING: "v-pending"}
SPANS = {"short": "〜3ヶ月", "mid": "6ヶ月〜1年", "long": "3年以上"}
PERIODS = {"short": "短期", "mid": "中期", "long": "長期"}
OK_HTML = {True: '<span class="ok-yes">○ 満たす</span>', False: '<span class="ok-no">× 満たさない</span>',
           None: '<span class="ok-unk">不明</span>'}
TOC = (("conclusion", "結論"), ("reasons", "判定の根拠"), ("step1", "STEP 1 事業"), ("step2", "STEP 2 財務"),
       ("step3", "STEP 3 株価"), ("price", "株価のレンジ"), ("thesis", "投資の理由"), ("gaps", "材料不足"),
       ("glossary", "用語集"))
PLAIN_HORIZONS = (("短期", "〜3ヶ月", "地合いと株価の位置（52週レンジ・移動平均）を見る。値動きの影響が大きく、根拠は弱い。"),
                  ("中期", "6ヶ月〜1年", "長期の判定に、直近の決算の進み具合と地合いを加える。"),
                  ("長期", "3年以上", "事業（STEP 1）・財務（STEP 2）・株価（STEP 3）を判定マトリクスで組み合わせる。"
                   "フレームワークの基本の形。"))
DISCLAIMER = ("本レポートは公表資料と収集データをもとに企業分析フレームワークの手順で整理したもので、投資の勧誘・推奨ではありません。"
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
    prov = f'<div class="prov">暫定の目安: {esc(h["provisional"])}</div>' if h["provisional"] else ""
    return (f'<div class="vcard {VERDICT_CLASS.get(word, "")}"><div class="period">{esc(PERIODS[key])}'
            f'（{esc(SPANS[key])}）</div><div class="word">{esc(word)}</div>{prov}<p class="why">{esc(h["why"])}</p></div>')


def conclusion(facts: dict, parsed: dict) -> str:
    cards = '<div class="verdicts">' + "".join(_card(k, facts["horizons"][k]) for k in ("short", "mid", "long")) + "</div>"
    summary = '<ol class="summary">' + "".join(f"<li>{esc(s)}</li>" for s in parsed["summary"]) + "</ol>"
    legend = "".join(f"<dt>{badge(w)}</dt><dd>{esc(t)}</dd>" for w, t in G.VERDICTS.items())
    spans = "".join(f"<p><b>{esc(n)}</b>（{esc(s)}）: {esc(t)}</p>" for n, s, t in PLAIN_HORIZONS)
    reading = (f'<h3>判定の読み方</h3><div class="cols"><div class="panel"><dl class="gloss">{legend}</dl></div>'
               f'<div class="panel small">{spans}<p>短期・中期は長期より良い判定にしない。</p></div></div>')
    about = f'<h3>この会社をひと言で</h3><div class="prose">{_paragraphs(parsed["about"])}</div>'
    return _section("conclusion", "01", "結論", "3つの期間それぞれで、今この会社に投資してよいかを判定した。",
                    cards + summary + about + reading)


def reasons(facts: dict, parsed: dict) -> str:
    body = ""
    for key in ("short", "mid", "long"):
        h = facts["horizons"][key]
        note = f'<p class="small muted">{esc(h["note"])}</p>' if h["note"] else ""
        body += (f'<h3>{esc(PERIODS[key])}（{esc(SPANS[key])}） {badge(h["verdict"])}</h3>'
                 f'<div class="prose">{_paragraphs(parsed[key])}</div>{note}{_conditions(h["rows"])}')
    return _section("reasons", "02", "判定の根拠", "各期間の判定を決めた条件。○は満たす、×は満たさない、不明は材料が無い"
                    "（不明は良い方に読まない）。", body)


# ---------------------------------------------------------------- STEP 1-3

def _stepcards(facts: dict, keys: tuple[str, ...]) -> str:
    cards = ""
    for key in keys:
        a = facts["analyses"][key]
        cards += (f'<div class="stepcard"><div class="label">{esc(a["step"])} {esc(a["label"])}'
                  f'（{esc(a["date"] or "未実施")}）</div><div class="res">{esc(a["verdict"] or "—")}</div>'
                  f'<p>{esc(a["reason"])}</p></div>')
    return f'<div class="steps">{cards}</div>'


def _stephead(grade: dict, title: str) -> str:
    label = grade["grade"] + ("（暫定）" if grade["pending"] else "")
    return (f'<div class="stephead"><span class="grade g-{esc(grade["grade"])}">{esc(grade["grade"])}</span>'
            f'<div><h3>{esc(title)}: {esc(label)}</h3><p>{esc(grade["why"])}</p></div></div>')


def step1(facts: dict) -> str:
    d = facts["analyses"]
    ff, sw = d["five_forces"]["detail"], d["swot"]["detail"]
    forces = table(["要因", "強さ", "理由"], [[esc(f["name"]), esc(f["rating"]), esc(f["reason"])]
                                          for f in ff.get("factors") or []])
    s, t = sw.get("top_strength") or {}, sw.get("top_threat") or {}
    swot = (f'<p><b>最大の強み</b>（{esc(s.get("id"))}、影響 {esc(s.get("impact"))}）: {esc(s.get("fact"))}</p>'
            f'<p><b>最大の脅威</b>（{esc(t.get("id"))}、影響 {esc(t.get("impact"))}）: {esc(t.get("fact"))}</p>'
            f'<p>{esc(sw.get("sentence"))}</p>')
    inner = (_conditions(facts["step1"]["rows"]) + f"<h3>業界の5つの力（{esc(ff.get('industry'))}）</h3>" + forces
             + f"<h3>勝てる理由</h3><p>{esc(d['three_c']['detail'].get('win_reason'))}</p>"
             + f"<h3>モート（強みの持続性）</h3><p>{esc(d['moat']['detail'].get('durability'))}</p>"
             + "<h3>SWOT</h3>" + swot)
    body = (_stephead(facts["step1"], "STEP 1 総合") + _stepcards(facts, ("five_forces", "three_c", "moat", "swot"))
            + _details("詳しく見る（A の条件・5つの力・強みと脅威）", inner))
    return _section("step1", "03", "STEP 1 事業と競争環境", "儲けやすい業界か、選ばれる理由があるか、その強みは続くか。", body)


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
            + _financial_charts(facts) + _details("詳しく見る（A の条件・各分析の要点・安全性・キャッシュフロー）", inner))
    return _section("step2", "04", "STEP 2 財務", "稼ぐ力・伸びる力・つぶれにくさ・お金の流れを数字で確かめる。", body)


def step3(facts: dict) -> str:
    v = facts["analyses"]["valuation"]
    detail = v["detail"]
    cards = "".join(f'<div class="stepcard"><div class="label">{esc(name)}</div>'
                    f'<div class="res">{esc(item.get("rating") or "—")}</div><p>{esc(item.get("sentence"))}</p></div>'
                    for name, item in (detail.get("items") or {}).items())
    head = (f'<div class="stephead"><div><h3>STEP 3: {badge(v["verdict"])}</h3><p>{esc(v["reason"])}</p>'
            f'<p class="muted">{esc(detail.get("sheet"))}</p></div></div>')
    flips = _list(detail.get("flip_prices") or [])
    cheap = (f"<h3>安い理由として説明できること</h3><p>{esc(detail['cheap_reason'])}</p>"
             if detail.get("cheap_reason") else "")
    body = (head + f'<div class="steps">{cards}</div>'
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
             '<div class="source">分割調整済み。出典: Yahoo Finance（data/prices.csv）</div></figure>')
    ma = "、".join(f"{a['label']} {C.fmt(a['value'], 0)}（今の株価との差 {C.fmt(a['gap'], 1, True)}%）"
                  for a in p["averages"] if a["value"])
    per = facts["analyses"]["valuation"]["detail"].get("per_range") or {}
    per_line = (f"PER（株価が利益の何倍か）の過去5期のレンジは {C.fmt(per.get('low'))}〜{C.fmt(per.get('high'))}倍で、"
                f"今はその中の位置 {per.get('position')}%" if per.get("low") is not None else "")
    body = (f"<h3>今の株価の位置</h3>{tracks}<h3>株価の推移</h3>{chart}"
            f'<p class="small">移動平均: {esc(ma or "—")}</p>'
            + (f'<p class="small">{esc(per_line)}</p>' if per_line else "") + _price_tables(p))
    return _section("price", "06", "株価の過去レンジ", lead, body)


# ---------------------------------------------------------------- thesis / gaps / glossary

def thesis(facts: dict, parsed: dict) -> str:
    body = (f'<div class="cols"><div class="panel"><h3>投資の理由（または見送りの理由）</h3>{_paragraphs(parsed["thesis"])}'
            f'</div><div class="panel"><h3>判断が崩れる条件</h3>{_list(parsed["break"])}</div></div>'
            f'<h3>次に確かめること</h3>{_list(parsed["watch"])}'
            f'<p class="small"><b>次回の見直し</b>: {esc(facts["review"])}</p>')
    return _section("thesis", "07", "投資の理由と判断が崩れる条件", "", body)


def _link(facts: dict, md: str | None) -> str:
    if not md:
        return "—"
    prefix = f"companies/{facts['company']}/"
    href = "../" + md[len(prefix):] if md.startswith(prefix) else md
    return f'<a href="{esc(href)}">{esc(md.rsplit("/", 1)[-1])}</a>'


def gaps(facts: dict) -> str:
    rows = [[esc(a["step"]), esc(a["label"]), esc(a["date"] or "未実施"), esc(a["verdict"] or "—"), _link(facts, a["md"])]
            for a in facts["analyses"].values()]
    body = (_list([f"{g['label']}: {g['gap']}" for g in facts["gaps"]]) + "<h3>このレポートが使った分析</h3>"
            + table(["STEP", "分析", "分析日", "結論", "ファイル"], rows, nowrap=frozenset({2})))
    return _section("gaps", "08", "材料不足と使った分析", "判定に影響しうる、まだ確かめられていない点。", body)


def glossary(text: str) -> str:
    terms = G.terms_in(text)
    body = (f'<dl class="gloss">{"".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in terms)}</dl>' if terms
            else '<p class="muted">なし</p>')
    return _section("glossary", "09", "用語集", "このレポートに出てくる言葉の意味。", body)


def render(template: str, facts: dict, parsed: dict, md_text: str) -> str:
    body = (masthead(facts) + "<main>" + conclusion(facts, parsed) + reasons(facts, parsed) + step1(facts)
            + step2(facts) + step3(facts) + price_section(facts) + thesis(facts, parsed) + gaps(facts)
            + glossary(md_text + D.render_brief(facts, "").split(D.WRITING_RULES)[0])
            + f'</main><footer><div class="wrap"><p>{esc(DISCLAIMER)}</p>'
              f'<p>生成: tools/report/company_report.py build（{esc(facts["date"])}）</p></div></footer>')
    return Template(template).safe_substitute(title=esc(f"{facts['name']} 企業分析レポート {facts['date']}"), body=body)
