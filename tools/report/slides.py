"""Assemble the single-file HTML deck from facts.json (numbers) and the parsed outlook.md (words).

Every piece of text goes through esc(), so nothing from the Markdown or the collected data can
inject markup. Charts come from charts.py as inline SVG.
"""
from __future__ import annotations

import datetime as dt
import re
from html import escape
from string import Template

import charts as C
from brief import cell
from facts import MARKET_LABEL

JUDGMENT_CLASS = {"強気": "j-bull", "中立": "j-neutral", "慎重": "j-cautious", "弱気": "j-bear"}
MARKET_CLASS = {"japan": "japan", "us": "us", "日本": "japan", "米国": "us", "日米": "both"}
CHART_DECIMALS = {"equity": 1, "policy_rates": 2, "yields10": 2, "usdjpy": 2, "jp_prices": 1, "us_prices": 1,
                  "jp_activity": 1, "us_payrolls": 0, "jp_foreign_flow": 0, "us_cot": 0}
HORIZONS = (("短期", "今後1か月", "次回の FOMC・日銀会合まで"), ("中期", "6か月程度", ""), ("長期", "1〜3年", ""))
IMPACT_LANES = (("大", "hi", "影響 大"), ("中", "mid", "影響 中"), ("小", "lo", "影響 小"))
POLICY_EVENT = re.compile(r"FOMC|日銀|金融政策決定会合")
EXACT_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")  # same rule as facts.event_span ("2026-10-14 まで" is exact)
BOLD = re.compile(r"\*\*(.+?)\*\*")
DISCLAIMER = ("本資料は収集した公表データと文書の要旨をもとに地合いを整理したもので、投資の勧誘・推奨ではありません。"
              "将来の株価・為替水準を予想するものではなく、最終的な投資判断はご自身で行ってください。")


# ---------------------------------------------------------------- small parts

def esc(text: object) -> str:
    return BOLD.sub(r"<strong>\1</strong>", escape(str(text if text is not None else "")))


def jdate(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.year}年{d.month}月{d.day}日"


def badge(judgment: str) -> str:
    cls = JUDGMENT_CLASS.get(judgment, "j-none")
    return f'<span class="badge {cls}">{esc(judgment or "—")}</span>'


def tag(market: str) -> str:
    label = MARKET_LABEL.get(market, market)
    return f'<span class="tag {MARKET_CLASS.get(market, "both")}">{esc(label)}</span>'


def legend(series: list[dict]) -> str:
    return '<div class="legend">' + "".join(
        f'<span><i class="sw s{i}"></i>{esc(s["label"])}</span>' for i, s in enumerate(series)) + "</div>"


def figure(chart: dict | None, palette: str) -> str:
    if not chart:
        return C.EMPTY
    decimals = CHART_DECIMALS.get(chart["id"], 1)
    if chart["kind"] == "bar":
        svg = C.bar_chart(chart["series"][0]["points"], chart["title"], decimals)
        head = f'<span class="muted small">{esc(chart["unit"])}</span>'
    else:
        svg = C.line_chart(chart["series"], chart["title"], decimals)
        head = legend(chart["series"])
    src = "、".join(chart["sources"])
    return (f'<figure class="chartbox {palette}"><figcaption><b>{esc(chart["title"])}</b>{head}</figcaption>'
            f'{svg}<div class="source">単位: {esc(chart["unit"])}　出典: {esc(src or "—")}</div></figure>')


def finding(market: str, row: dict | None) -> str:
    row = row or {}
    return (f'<div class="finding {market}"><div class="head">{tag(market)}</div>'
            f'<div class="conclusion">{esc(row.get("conclusion", "—"))}</div>'
            f'<div class="seen">{esc(row.get("seen", "—"))}</div>'
            f'<div class="src">情報源: {esc(row.get("source", "—"))}</div></div>')


def findings(parsed: dict, number: str) -> str:
    topic = parsed["trends"].get(number, {})
    return "".join(finding(m, topic.get(m)) for m in ("japan", "us"))


def table(header: list[str], rows: list[list[str]], right: frozenset[int] = frozenset(),
          nowrap: frozenset[int] = frozenset()) -> str:
    """rows hold ready HTML (already escaped). right: numeric columns; nowrap: dates and tags."""
    def cls(i: int) -> str:
        names = [n for n, cols in (("r", right), ("nw", nowrap)) if i in cols]
        return f' class="{" ".join(names)}"' if names else ""
    head = "".join(f"<th{cls(i)}>{esc(h)}</th>" for i, h in enumerate(header))
    body = "".join("<tr>" + "".join(f"<td{cls(i)}>{c}</td>" for i, c in enumerate(r)) + "</tr>" for r in rows)
    if not rows:
        body = f'<tr><td colspan="{len(header)}" class="muted">データなし</td></tr>'
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def chart_by_id(facts: dict, cid: str) -> dict | None:
    return next((c for c in facts["charts"] if c["id"] == cid), None)


def indicator(facts: dict, sid: str) -> dict | None:
    return next((r for rows in facts["indicators"].values() for r in rows if r["id"] == sid), None)


# ---------------------------------------------------------------- slides

def cover(facts: dict, parsed: dict, toc: list[tuple[str, str]]) -> str:
    week = dt.date.fromisoformat(facts["week"])
    friday = week + dt.timedelta(days=4)
    prev = facts.get("previous") or {}
    cards = []
    for market in ("japan", "us"):
        j = parsed["judgments"].get(market, {})
        before = prev.get(market)
        delta = f"前回（{esc(prev['week'])} 週） {esc(before)} → 今回" if before else "前回の判断なし（初回）"
        cards.append(f'<div class="verdict {market}"><div class="market">{esc(MARKET_LABEL[market])}の地合い</div>'
                     f'{badge(j.get("judgment", ""))}<div class="delta">{delta}</div>'
                     f'<p>{esc(j.get("summary", ""))}</p></div>')
    items = "".join(f'<li><a href="#{sid}"><span>{i:02d}</span><span>{esc(label)}</span></a></li>'
                    for i, (sid, label) in enumerate(toc, start=2))
    return (f'<section class="slide cover" id="s-cover" aria-label="表紙"><div class="inner grid wide-left">'
            f'<div><div class="brand">WEEKLY MARKET BRIEF — 日米 地合いレポート</div>'
            f'<h1>{jdate(facts["week"])} 週</h1>'
            f'<div class="period">{week.month}/{week.day}（月）〜 {friday.month}/{friday.day}（金）</div>'
            f'<div class="verdicts">{"".join(cards)}</div>'
            f'<div class="meta">材料: 収集セッション {esc(facts["session"])} ／ 作成日 {esc(facts["generated"])}</div>'
            f'</div><nav aria-label="目次"><ol class="toc">{items}</ol></nav></div></section>')


def key_messages(facts: dict, parsed: dict) -> str:
    items = "".join(f"<li><div>{esc(m)}</div></li>" for m in parsed["key_messages"])
    return f'<ol class="messages">{items}</ol>'


def kpi_chip(k: dict, key: str, label: str) -> str:
    ch = k["changes"].get(key)
    if not ch:
        return f"<span><i>{label}</i>—</span>"
    if k["change"] == "pct":
        return f'<span><i>{label}</i>{C.fmt(ch["delta"], 1, signed=True)}%</span>'
    return f'<span><i>{label}</i>{C.fmt(ch["delta"], max(k["decimals"], 2), signed=True)}</span>'


def kpi_tile(k: dict) -> str:
    value = C.fmt(k["value"], k["decimals"]) if k["value"] is not None else "—"
    chips = kpi_chip(k, "1w", "1週") + kpi_chip(k, "1m", "1か月") + kpi_chip(k, "1y", "1年")
    return (f'<div class="kpi {k["market"]}"><div class="label">{esc(k["label"])}</div>'
            f'<div class="value">{value}<span class="unit">{esc(k["unit"])}</span></div>'
            f'<div class="asof">{esc(k["date"] or "未取得")}</div>'
            f'<div class="chips">{chips}</div>{C.sparkline(k["spark"])}</div>')


def dashboard(facts: dict, parsed: dict) -> str:
    tiles = "".join(kpi_tile(k) for k in facts["kpis"])
    return (f'<div class="kpis">{tiles}</div>'
            f'<p class="small muted">変化: 株価・為替は騰落率、金利・スプレッド・VIX は差（ポイント）。'
            f'小さな線は直近1年（週末値）。</p>{figure(chart_by_id(facts, "equity"), "pal-cmp")}')


def next_meetings(facts: dict) -> str:
    rows = [[esc(e["date"]), tag(e["market"]), esc(e["event"]), esc(e["detail"])]
            for e in facts["events"] if POLICY_EVENT.search(e["event"])][:4]
    return table(["日付", "市場", "イベント", "内容"], rows, nowrap=frozenset({0, 1}))


def monetary(facts: dict, parsed: dict) -> str:
    return (f'<div class="grid wide-left"><div class="stack">{figure(chart_by_id(facts, "policy_rates"), "pal-cmp")}'
            f'<div class="panel"><h3>次回の会合</h3>{next_meetings(facts)}</div></div>'
            f'<div class="stack">{findings(parsed, "3.3")}</div></div>')


def curve_table(facts: dict) -> str:
    rows = []
    for label, sid in (("日本 2年", "JP_JGB2Y"), ("日本 10年", "JP_JGB10Y"), ("日本 30年", "JP_JGB30Y"),
                       ("米国 2年", "US_2Y"), ("米国 10年", "US_10Y")):
        r = indicator(facts, sid)
        if not r:
            continue
        diff = r["value"] - r["year"] if r["value"] is not None and r["year"] is not None else None
        rows.append([esc(label), esc(r["date"] or "—"), C.fmt(r["value"], 2), C.fmt(r["year"], 2),
                     C.fmt(diff, 2, signed=True)])
    return table(["国債利回り（%）", "時点", "現在", "1年前", "差"], rows, right=frozenset({2, 3, 4}),
                 nowrap=frozenset({0, 1}))


def rates(facts: dict, parsed: dict) -> str:
    return (f'<div class="grid cols-2">{figure(chart_by_id(facts, "yields10"), "pal-cmp")}'
            f'{figure(chart_by_id(facts, "usdjpy"), "pal-cmp")}</div>'
            f'<div class="grid cols-2" style="margin-top:20px"><div class="panel">{curve_table(facts)}</div>'
            f'<div class="stack">{findings(parsed, "3.2")}</div></div>')


def indicator_table(facts: dict, market: str, groups: tuple[str, ...]) -> str:
    rows, last_group = [], None
    for r in facts["indicators"][market]:
        if r["group"] not in groups:
            continue
        if r["group"] != last_group:
            last_group = r["group"]
            rows.append([f'<b>{esc(r["group"])}</b>', "", "", "", ""])
        d = r["decimals"]
        date = esc(r["date"] or "—") + ('<div class="muted small">古い</div>' if r.get("stale") else "")
        rows.append([f'{esc(r["name"])} <span class="muted small">{esc(r["unit"])}</span>', date,
                     C.fmt(r["value"], d), C.fmt(r["prev"], d), C.fmt(r["year"], d)])
    return table(["指標", "時点", "値", "前回", "1年前"], rows, right=frozenset({2, 3, 4}), nowrap=frozenset({1}))


def macro(market: str, chart_ids: tuple[tuple[str, str], ...], groups: tuple[str, ...]):
    def render(facts: dict, parsed: dict) -> str:
        figs = "".join(figure(chart_by_id(facts, cid), pal) for cid, pal in chart_ids)
        topic = parsed["trends"].get("3.4", {})
        return (f'<div class="grid wide-left"><div class="stack">{figs}</div><div class="stack">'
                f'{finding(market, topic.get(market))}<div class="panel">'
                f'{indicator_table(facts, market, groups)}</div></div></div>')
    return render


def politics_list(facts: dict, market: str) -> str:
    items = [f'<li><b>{esc(p["date"])}</b> {esc(p["event"])}<div class="muted small">{esc(p["detail"])}</div></li>'
             for p in facts["politics"] if p["market"] == market][:4]
    return f'<ul class="plain">{"".join(items) or "<li class=muted>記録なし</li>"}</ul>'


def docs_list(facts: dict, market: str) -> str:
    items = [f'<li><b>{esc(d["date"])}</b> {esc(d["title"])}</li>'
             for d in facts["docs"] if d["market"] == market and d["layer"][:1] in ("A", "B")]
    return f'<ul class="plain small">{"".join(items) or "<li class=muted>なし</li>"}</ul>'


def fiscal(facts: dict, parsed: dict) -> str:
    topic = parsed["trends"].get("3.5", {})
    cols = [f'<div class="stack">{finding(m, topic.get(m))}'
            f'<div class="panel"><h3>直近の政治・政策の動き</h3>{politics_list(facts, m)}</div>'
            f'<div class="panel"><h3>国家方針・財政の最新文書</h3>{docs_list(facts, m)}</div></div>'
            for m in ("japan", "us")]
    return f'<div class="grid cols-2">{"".join(cols)}</div>'


def flows(facts: dict, parsed: dict) -> str:
    extras = [[tag(e["market"]), esc(e["indicator"]),
               esc(e["value"]) + (f'<div class="muted small">{esc(e["note"])}</div>' if e.get("note") else ""),
               esc(e["date"]), esc(e["certainty"])] for e in facts["extras"]]
    flow_rows = [[esc(r["name"].replace("投資部門別売買 ", "")), esc(r["date"] or "—"), C.fmt(r["value"], 0),
                  C.fmt(r["prev"], 0)] for r in facts["indicators"]["japan"] if r["group"] == "需給"]
    return (f'<div class="grid cols-2"><div class="stack">{findings(parsed, "3.1")}</div>'
            f'<div class="stack">{figure(chart_by_id(facts, "jp_foreign_flow"), "pal-jp")}'
            f'{figure(chart_by_id(facts, "us_cot"), "pal-us")}</div></div>'
            f'<div class="grid cols-2" style="margin-top:20px">'
            f'<div class="panel"><h3>投資部門別売買（億円、週間）</h3>'
            f'{table(["投資部門", "週末", "差引", "前週"], flow_rows, right=frozenset({2, 3}), nowrap=frozenset({1}))}'
            f'</div><div class="panel"><h3>バリュエーション・センチメント（web 検索）</h3>'
            f'{table(["市場", "指標", "値", "時点", "確度"], extras, nowrap=frozenset({0, 4}))}</div></div>')


def week_label(iso: str) -> str:
    start = dt.date.fromisoformat(iso)
    start -= dt.timedelta(days=start.weekday())
    return f"{start.month}/{start.day} の週"


def event_item(e: dict, point: str | None, exact: bool) -> str:
    point_html = f'<div class="pt">{esc(point)}</div>' if point and point != "—" else ""
    return (f'<div class="event"><div class="d">{esc(e["date"][5:] if exact else e["date"])}</div>'
            f'<span class="dot {e["market"]}" title="{esc(MARKET_LABEL.get(e["market"], ""))}"></span>'
            f'<div><div class="t">{esc(e["event"])}</div><div class="x">{esc(e["detail"])}</div>{point_html}'
            f'<div class="c">{esc(e["kind"])}・確度 {esc(e["certainty"])}</div></div></div>')


def calendar(facts: dict, parsed: dict) -> str:
    # outlook.md rows went through brief.cell(), so normalise the facts side the same way before joining
    points = {(e["date"], e["event"]): e["point"] for e in parsed["events"]}
    groups: dict[str, list[str]] = {}
    for e in facts["events"]:
        exact = bool(EXACT_DATE.match(e["date"]))
        label = week_label(e["date"][:10]) if exact else f'{e["date"][:7]}（日付未確定）'
        point = points.get((cell(e["date"]), cell(e["event"])))
        groups.setdefault(label, []).append(event_item(e, point, exact))
    weeks = "".join(f'<div class="week"><h3>{esc(k)}</h3>{"".join(v)}</div>' for k, v in groups.items())
    return (f'<p class="small muted">{tag("japan")} 日本　{tag("us")} 米国　'
            f'— 黄色の線は今週の注目点（outlook.md の 6.）</p><div class="weeks">{weeks or "<p>日程なし</p>"}</div>')


def horizon_view(market: str, r: dict) -> str:
    return (f'<article class="view {market}"><header>{tag(market)}{badge(r.get("judgment", ""))}</header>'
            f'<div class="scenario">{esc(r.get("scenario", "—"))}</div><dl>'
            f'<dt>上振れ</dt><dd>{esc(r.get("upside", "—"))}</dd>'
            f'<dt>下振れ</dt><dd>{esc(r.get("downside", "—"))}</dd>'
            f'<dt>確認</dt><dd>{esc(r.get("watch", "—"))}</dd></dl></article>')


def horizons(facts: dict, parsed: dict) -> str:
    by_key = {(r["period"], r["market"]): r for r in parsed["outlook"]}
    return "".join(f'<div class="horizon"><div class="when"><h3>{period}</h3><p>{span}</p><p>{note}</p></div>'
                   + "".join(horizon_view(m, by_key.get((period, m), {})) for m in ("japan", "us")) + "</div>"
                   for period, span, note in HORIZONS)


def risk_map(facts: dict, parsed: dict) -> str:
    lanes = []
    for impact, cls, label in IMPACT_LANES:
        cards = [f'<div class="risk">{tag(r["market"])}<div class="t">{esc(r["risk"])}</div>'
                 f'<div class="x">兆候: {esc(r["signal"])}</div><div class="s">根拠: {esc(r["basis"])}</div></div>'
                 for r in parsed["risks"] if r["impact"] == impact]
        lanes.append(f'<div class="lane {cls}"><h3>{label}</h3>'
                     f'{"".join(cards) or "<p class=empty-lane>該当なし</p>"}</div>')
    return f'<div class="riskmap">{"".join(lanes)}</div>'


def limits(facts: dict, parsed: dict) -> str:
    limit_items = "".join(f"<li>{esc(x)}</li>" for x in parsed["limits"])
    files = sorted({p for m in facts["files"].values() for p in m.values() if p})
    sources = sorted({s for c in facts["charts"] for s in c["sources"]})
    file_items = "".join(f"<li>{esc(p)}</li>" for p in files)
    return (f'<div class="grid cols-2"><div class="panel"><h3>データの限界</h3><ul class="plain">{limit_items}</ul>'
            f'<p class="small muted" style="margin-top:10px">収集時の要確認事項: {len(facts["review_items"])} 件'
            f'（各セッションの status.md の「7. 要確認事項」）</p></div>'
            f'<div class="panel"><h3>出典・材料</h3><ul class="plain small">'
            f'<li>時系列: {esc("、".join(sources))}（market/data/*.csv）</li>{file_items}'
            f'<li>政策文書の要旨 {len(facts["docs"])} 件（market/policy/*/raw/）</li>'
            f'<li>判断の根拠: market/report/{esc(facts["week"])}_outlook.md</li></ul></div></div>'
            f'<div class="disclaimer">{esc(DISCLAIMER)}</div>')


SLIDES = (
    ("s-messages", "キーメッセージ", "KEY MESSAGES", "今週押さえるべきこと", key_messages),
    ("s-dashboard", "マーケット", "DASHBOARD", "主要マーケットの現在地", dashboard),
    ("s-monetary", "金融政策", "MONETARY POLICY", "日銀と FRB の金融政策", monetary),
    ("s-rates", "金利・為替", "RATES & FX", "金利と為替", rates),
    ("s-japan", "日本マクロ", "JAPAN MACRO", "日本経済：物価・雇用・景気",
     macro("japan", (("jp_prices", "pal-jp"), ("jp_activity", "pal-jp")),
           ("物価", "雇用・賃金", "景気・生産", "企業マインド"))),
    ("s-us", "米国マクロ", "US MACRO", "米国経済：物価・雇用・景気",
     macro("us", (("us_prices", "pal-us"), ("us_payrolls", "pal-us")), ("物価", "雇用", "景気"))),
    ("s-fiscal", "財政・政治", "FISCAL & POLITICS", "財政・政策・政治", fiscal),
    ("s-flows", "需給", "FLOWS & VALUATION", "需給・バリュエーション", flows),
    ("s-calendar", "日程", "CALENDAR", "今後12週のイベント", calendar),
    ("s-outlook", "展望", "OUTLOOK", "短期・中期・長期の展望", horizons),
    ("s-risks", "リスク", "RISK MAP", "リスクマップ", risk_map),
    ("s-limits", "データと出典", "DATA & SOURCES", "データの限界と出典", limits),
)


def render(facts: dict, parsed: dict, template_text: str) -> str:
    toc = [(sid, nav) for sid, nav, *_ in SLIDES]
    sections = [cover(facts, parsed, toc)]
    for i, (sid, _nav, kicker, title, fn) in enumerate(SLIDES, start=2):
        alt = " alt" if i % 2 == 0 else ""
        sections.append(f'<section class="slide{alt}" id="{sid}" aria-labelledby="{sid}-h"><div class="inner">'
                        f'<div class="kicker"><span class="no">{i:02d}</span>{kicker}</div>'
                        f'<h2 id="{sid}-h">{esc(title)}</h2>{fn(facts, parsed)}</div></section>')
    nav = "".join(f'<a href="#{sid}" aria-label="{esc(label)}"><span>{esc(label)}</span></a>'
                  for sid, label in [("s-cover", "表紙")] + toc)
    # values are inserted once and never re-scanned, so a "$" in the content is safe
    return Template(template_text).safe_substitute(
        title=esc(f"日米地合いレポート {facts['week']} 週"), dots=nav, slides="\n".join(sections),
        total=f"{len(sections):02d}")
