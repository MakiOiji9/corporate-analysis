"""Single-file HTML of the company report, drawn from facts.json (numbers, judgements) and the filled md (words).

Every piece of text goes through esc() (cr_html.py), so nothing from the analyses or the md can inject markup.
Charts are inline SVG from charts.py. One vertical page, overview first and details folded:
  01 ひと目でわかる結論 (verdict cards, the nine analyses, the price band, key figures, the 3-line summary)
  02 期間ごとの良い点・悪い点   03 投資判断と行動計画 (thesis, break conditions, buy-price scenarios)
  04 STEP 1 事業   05 STEP 2 財務   06 STEP 3 株価の妥当性   07 株価の動きとタイミング (cr_ch_price.py)
  08 投資の神の視点   09 材料不足と使った分析   10 用語集
"""
from __future__ import annotations

from string import Template

import charts as C
import cr_ch_price as CP
import cr_dashboard as DB
import cr_doc as D
import cr_glossary as G
import cr_judge as J
import cr_legends as L
import cr_sections as X
import cr_strategy as ST
import slides
from cr_html import OK_HTML, PERIODS, SPANS, VERDICT_CLASS, badge, esc, figure
from cr_html import bullet_list as _list
from cr_html import conditions as _conditions
from cr_html import details as _details
from cr_html import paragraphs as _paragraphs
from cr_html import section as _section
from slides import table

TOC = (("conclusion", "結論"), ("reasons", "良い点・悪い点"), ("thesis", "行動計画"), ("step1", "STEP 1 事業"),
       ("step2", "STEP 2 財務"), ("step3", "STEP 3 株価"), ("market", "株価の動き"),
       ("legends", "投資の神"), ("gaps", "材料不足"), ("glossary", "用語集"))
LEGEND_LEAD = ("3人の投資哲学をこの会社の分析結果に当てはめた参考の視点。評価はスクリプトが資料の条件で決め、"
               "結論の判定の点数には入らない。本人が実際にこの会社をこう評価したという意味ではない。")
PLAIN_HORIZONS = (("短期", "〜3ヶ月", "地合い・株価のテクニカル（流れ・勢い・位置）・直近の決算の進み具合・割安さを重く見る。値動きの影響が大きく、根拠は弱い。"),
                  ("中期", "6ヶ月〜1年", "割安さと業績の勢い（成長性・決算の進捗）を重く見て、財務と地合いも加える。"),
                  ("長期", "3年以上", "事業の強さ（勝てる理由・モート・業界）を重く見て、財務と割安さを加える。"
                   "フレームワークの判定マトリクスも参考に示す。"))
WEIGHT_NOTE = (f"各要素を +1（良い）・0（中間）・−1（悪い）の点数にし（財務の4分析は中身に応じて ±0.5 もある）、"
               f"期間ごとの重みで平均した。{J.UP:+.2f} 以上で投資検討、{J.DOWN:+.2f} 以下で見送り、その間はウォッチ。"
               "営業CF のマイナスが続く・FCF の累計がマイナス・安全性の悪化などの深刻な赤信号は、点数にかかわらず見送り。")
DISCLAIMER = ("本レポートは公表資料と収集データをもとに企業分析フレームワークに沿って整理したもので、投資の勧誘・推奨ではありません。"
              "判定は作成日時点の材料による位置づけで、将来の株価を予想するものではありません。最終的な投資判断はご自身で行ってください。")
ROIC_NOTE = ("ROIC（使ったお金に対する本業の利益の割合）が資本コストの線より上の年は、元手に見合う以上に稼いだ年。"
             "上回る年が長く続くほど、強みが続いている証拠になる。")
CF_NOTE = "営業CF（本業で実際に入った現金）が純利益より上なら、利益が現金を伴っている。下回る年が続くと利益の質に注意。"
EQUITY_NOTE = "自己資本比率が高いほど借金に頼らず、つぶれにくい。ネットキャッシュ（現金 − 借金）がプラスなら実質無借金。"


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
    out = ""
    stale = facts.get("stale") or []
    if stale:
        names = "、".join(f"{s['label']}（{s['date']}）" for s in stale)
        out += (f'<div class="notice"><b>注意</b>: {esc(names)} は、分析の後に新しい材料が集まったが作り直していない'
                "（既存の結果で判定した）。理由は「材料不足と使った分析」の節を参照。</div>")
    old = [m for m in facts.get("materials") or [] if m["stale"] and m["key"] != "prices"]
    if old:
        names = "、".join(f"{m['label']}（{m['date'] or '無し'}）" for m in old)
        out += (f'<div class="notice"><b>古い材料</b>: {esc(names)} は集め直しても新しくならなかった。'
                "その材料に基づく記述は基準日の時点のもの（「材料不足と使った分析」の「材料の基準日」を参照）。</div>")
    return out


def conclusion(facts: dict, parsed: dict) -> str:
    cards = _stale_notice(facts) + '<div class="verdicts">' + "".join(
        _card(k, facts["horizons"][k]) for k in ("short", "mid", "long")) + "</div>"
    summary = '<ol class="summary">' + "".join(f"<li>{esc(s)}</li>" for s in parsed["summary"]) + "</ol>"
    legend = "".join(f"<dt>{badge(w)}</dt><dd>{esc(t)}</dd>" for w, t in G.VERDICTS.items())
    spans = "".join(f"<p><b>{esc(n)}</b>（{esc(s)}）: {esc(t)}</p>" for n, s, t in PLAIN_HORIZONS)
    reading = (f'<div class="cols"><div class="panel"><dl class="gloss">{legend}</dl></div>'
               f'<div class="panel small">{spans}<p>{esc(WEIGHT_NOTE)}</p></div></div>')
    about = f'<h3>この会社をひと言で</h3><div class="prose">{_paragraphs(parsed["about"])}</div>'
    glance = ('<h3>9つの分析の結論</h3>' + DB.analysis_strip(facts) + DB.key_figures_html(facts)
              + '<h3>今の株価の位置</h3>' + DB.fair_value(facts))
    return _section("conclusion", "01", "ひと目でわかる結論",
                    "3つの期間それぞれで、今この会社に投資してよいかを判定した。詳しい理由は下の章で確かめられる。",
                    cards + ST.action_card(facts) + summary + glance + about
                    + _details("判定の読み方（判定の言葉・期間ごとの重み）", reading))


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
             + _moat_sources(d["moat"]["detail"]) + _conservative(d["moat"]))
    body = (_stephead(facts["step1"], "STEP 1 総合") + _stepcards(facts, ("five_forces", "three_c", "moat", "swot"))
            + _roic_chart(d["moat"]["detail"]) + X.swot_grid(d["swot"]["detail"], d["swot"])
            + _details("勝てる理由（3C）を詳しく見る", X.three_c_block(d["three_c"]["detail"], d["three_c"]))
            + _details("経営と株主", X.governance_block(facts))
            + _details("詳しく見る（A の条件・業界の5つの力・モートの源泉）", inner))
    return _section("step1", "04", "STEP 1 事業と競争環境", "儲けやすい業界か、選ばれる理由があるか、その強みは続くか。", body)


def _roic_chart(moat: dict) -> str:
    returns = moat.get("returns") or {}
    rows = returns.get("rows") or []
    roic = _points(rows, "roic")
    if not roic:
        return ""
    hurdle = returns.get("hurdle")
    hlines = [{"label": "資本コスト", "value": hurdle, "cls": "ref"}] if hurdle is not None else []
    series = [{"label": "自社の ROIC", "points": roic}, {"label": "同業の中央値", "points": _points(rows, "peer_median")}]
    legend = '<div class="legend">' + "".join(f'<span><i class="sw s{i}"></i>{esc(s["label"])}</span>'
                                              for i, s in enumerate(series) if s["points"]) + "</div>"
    return figure("ROIC と資本コスト（強みが利益に表れているか）", legend + C.line_chart(series, "ROIC と資本コスト", 1, hlines=hlines),
                  "モート分析（有報・決算短信から計算）", "%", ROIC_NOTE)


def _moat_sources(moat: dict) -> str:
    rows = [[esc(m.get("type")), esc(m.get("group") or ""), esc(m.get("rating")), esc(m.get("mechanism") or "")]
            for m in moat.get("moats") or []]
    if not rows:
        return ""
    axes = moat.get("axes") or {}
    axis = "、".join(f"{name} {axes[k]}" for k, name in (("width", "幅"), ("depth", "深さ"), ("reach", "拡張性"))
                    if axes.get(k))
    head = f'<p class="small">堀の{esc(axis)}。傾向: {esc(moat.get("trend") or "—")}</p>' if axis else ""
    return "<h4>強みの源泉（6種類）</h4>" + head + table(["源泉", "種類", "強さ", "仕組みと根拠"], rows)


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
    out += figure("ROE（自己資本利益率）", C.line_chart([{"label": "ROE", "points": roe}], "ROE"), "収益性分析", "%")
    cf_rows = d["cash_flow"]["detail"].get("rows") or []
    if _points(cf_rows, "cfo"):
        series = [{"label": "営業CF", "points": _points(cf_rows, "cfo")},
                  {"label": "純利益", "points": _points(cf_rows, "net_income")}]
        legend = '<div class="legend"><span><i class="sw s0"></i>営業CF</span><span><i class="sw s1"></i>純利益</span></div>'
        out += figure("営業CF と純利益（利益が現金を伴うか）", legend + C.line_chart(series, "営業CF と純利益", 0),
                      "キャッシュフロー分析", unit, CF_NOTE)
    s_rows = d["safety"]["detail"].get("rows") or []
    if _points(s_rows, "equity_ratio"):
        out += figure("自己資本比率（つぶれにくさ）",
                      C.line_chart([{"label": "自己資本比率", "points": _points(s_rows, "equity_ratio")}], "自己資本比率"),
                      "安全性分析", "%", EQUITY_NOTE)
    return out + "</div>"


def _dupont(prof: dict) -> str:
    rows = [[esc(r["year"]), esc(C.fmt(r.get("margin"), 1)), esc(C.fmt(r.get("turnover"), 2)),
             esc(C.fmt(r.get("leverage"), 2)), esc(C.fmt(r.get("roe"), 1))] for r in (prof.get("dupont") or [])[-6:]]
    if not rows:
        return ""
    return ("<h3>ROE の分解（どこで稼いでいるか）</h3>"
            '<p class="small muted">ROE ＝ 売上高純利益率 × 総資産回転率 × 財務レバレッジ。利益率が高ければ本業の強さ、'
            "レバレッジが高ければ借入の効果。</p>"
            + table(["年度", "純利益率（%）", "総資産回転率（回）", "財務レバレッジ（倍）", "ROE（%）"], rows,
                    right=frozenset({1, 2, 3, 4})))


def step2(facts: dict) -> str:
    d = facts["analyses"]
    safety = table(["指標", "値", "同業平均", "目安", "評価"],
                   [[esc(i["name"]), esc(C.fmt(i["value"], 1)), esc(C.fmt(i["peer_avg"], 1)), esc(i.get("target")),
                     esc(i["rating"])] for i in d["safety"]["detail"].get("items") or []], right=frozenset({1, 2}))
    cfsteps = _list([f"{s['rating']}: {s['sentence']}" for s in d["cash_flow"]["detail"].get("steps") or []
                     if s["rating"]])
    points = _list([f"{a['label']}: {a['points']}" for k, a in d.items()
                    if k in ("profitability", "growth", "safety", "cash_flow") and a["points"]])
    inner = (_conditions(facts["step2"]["rows"]) + "<h3>各分析の要点</h3>" + points + _dupont(d["profitability"]["detail"])
             + "<h3>安全性の3指標</h3>" + safety + "<h3>キャッシュフローの5つの確認</h3>" + cfsteps)
    body = (_stephead(facts["step2"], "STEP 2 総合") + _stepcards(facts, ("profitability", "growth", "safety", "cash_flow"))
            + _financial_charts(facts) + _details("成長の見通しと会社計画の達成率", X.growth_block(facts))
            + _details("株主還元（配当・自社株買い）", X.dividends_block(facts))
            + _details("詳しく見る（A の条件・各分析の要点・ROE の分解・安全性・キャッシュフロー）", inner))
    return _section("step2", "05", "STEP 2 財務", "稼ぐ力・伸びる力・つぶれにくさ・お金の流れを数字で確かめる。", body)


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
    return _section("step3", "06", "STEP 3 株価の妥当性", "今の株価は、過去の水準と同業他社に比べて安いか高いか。"
                    "割安・割高は現時点の位置づけで、将来の株価の予想ではない。", body)


# ---------------------------------------------------------------- thesis / gaps / glossary

def thesis(facts: dict, parsed: dict) -> str:
    body = (f'<div class="cols"><div class="panel"><h3>投資の理由（または見送りの理由）</h3>{_paragraphs(parsed["thesis"])}'
            f'</div><div class="panel"><h3>判断が崩れる条件</h3>{_list(parsed["break"])}</div></div>'
            + ST.html(facts, []) + f'<h3>次に確かめること</h3>{_list(parsed["watch"])}'
            + _details("チャートから見た買いの候補の価格（損切り・利益確定・リスクリワード）", CP.scenarios(facts)))
    return _section("thesis", "03", "投資判断と行動計画",
                    "結論を踏まえて、何を根拠に、どんな条件で判断を変えるか。価格は条件の目安で、予想や推奨ではない。", body)


def _legend_card(v: dict, prose: str, action: str = "") -> str:
    checks = table(["項目", "値", "結果", "情報源"],
                   [[esc(f"{c['id']} {c['item']}"), esc(c["value"]), OK_HTML[c["ok"]], esc(c["source"])]
                    for c in v["checks"]], nowrap=frozenset({2}))
    notes = "".join(f'<p class="small muted">{esc(n)}</p>' for n in v["notes"])
    act = f'<p class="legend-act"><b>この考え方なら</b>: {esc(action)}</p>' if action else ""
    return (f'<div class="stepcard"><div class="label">{esc(v["name"])}（{esc(v["horizon"])}の見方）</div>'
            f'<div class="res"><span class="badge {L.VERDICT_CLASS.get(v["verdict"], "")}">{esc(v["verdict"])}</span></div>'
            f'{act}<p class="small muted">{esc(v["philosophy"])}</p><p>{esc(v["why"])}</p>{prose}{notes}'
            f'{_details("確かめた項目", checks)}</div>')


def legends(facts: dict, parsed: dict) -> str:
    found = facts.get("legends") or {}
    if not found:
        return ""
    actions = ST.legend_actions(facts)["actions"]
    cards = "".join(_legend_card(v, _paragraphs(parsed.get(k) or ""), actions.get(k, "")) for k, v in found.items())
    return _section("legends", "08", "投資の神の視点（参考）", LEGEND_LEAD,
                    ST.legend_summary(facts) + f'<div class="steps">{cards}</div>')


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
    materials = facts.get("materials") or []
    material_html = ("<h3>材料の基準日</h3>" + table(
        ["材料", "基準日", "状態"],
        [[esc(m["label"]), esc(m["date"] or "無し"),
          '<span class="ok-no">古い（' + esc(m["why"]) + "）</span>" if m["stale"] else '<span class="ok-yes">新しい</span>']
         for m in materials], nowrap=frozenset({1})) if materials else "")
    body = (_list([f"{g['label']}: {g['gap']}" for g in facts["gaps"]]) + stale_html + material_html
            + "<h3>このレポートが使った分析</h3>"
            + table(["STEP", "分析", "分析日", "結論", "ファイル"], rows, nowrap=frozenset({2})))
    return _section("gaps", "09", "材料不足と使った分析", "判定に影響しうる、まだ確かめられていない点。", body)


def glossary(text: str) -> str:
    terms = G.terms_in(text)
    body = (f'<dl class="gloss">{"".join(f"<dt>{esc(t)}</dt><dd>{esc(d)}</dd>" for t, d in terms)}</dl>' if terms
            else '<p class="muted">なし</p>')
    return _section("glossary", "10", "用語集", "このレポートに出てくる言葉の意味。", body)


def render(template: str, facts: dict, parsed: dict, md_text: str) -> str:
    main = X.annotate(conclusion(facts, parsed) + reasons(facts, parsed) + thesis(facts, parsed) + step1(facts)
                      + step2(facts) + step3(facts) + CP.chapter(facts, parsed, "07") + legends(facts, parsed)
                      + gaps(facts))
    body = (masthead(facts) + "<main>" + main
            + glossary(md_text + D.render_brief(facts, "").split(D.WRITING_RULES)[0])
            + f'</main><footer><div class="wrap"><p>{esc(DISCLAIMER)}</p>'
              f'<p>作成: 企業分析レポートの作成スクリプト（{esc(facts["date"])}）</p></div></footer>')
    return Template(template).safe_substitute(title=esc(f"{facts['name']} 企業分析レポート {facts['date']}"), body=body)
