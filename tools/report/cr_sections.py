"""HTML parts of the company report beyond the frame in cr_render.py: the horizons' good / bad points, the 3C cards
and tables, the SWOT grid, the growth outlook, the peer table, shareholder returns, and the glossary tooltips.

All text goes through esc() (slides.py); tooltips are added afterwards by annotate(), which only touches text
between tags, so nothing in an attribute or a chart is rewritten.
"""
from __future__ import annotations

import re
from html import escape

import charts as C
import cr_glossary as G
import cr_judge as J
import cr_plain as P
import slides
from slides import table


def esc(text: object) -> str:
    """slides.esc after the reader's-words pass (cr_plain)."""
    return slides.esc(P.plain(text) if isinstance(text, str) else text)

VERDICT_CLASS = {J.CONSIDER: "v-consider", J.WATCH: "v-watch", J.PASS: "v-pass", J.PENDING: "v-pending"}
IMPACT_CLASS = {"大": "imp-hi", "中": "imp-mid", "小": "imp-lo", "不明": "imp-unk"}
QUADRANTS = (("S", "強み", "内部・プラス"), ("W", "弱み", "内部・マイナス"), ("O", "機会", "外部・プラス"),
             ("T", "脅威", "外部・マイナス"))
MARK_CLASS = {"○": "mk-good", "△": "mk-mid", "×": "mk-bad", "？": "mk-unk"}
SKIP_TAGS = ("svg", "dt", "a", "summary", "h1", "h2", "button", "script", "style", "title")
YEN_OKU = 1e8


def badge(word: str | None) -> str:
    return f'<span class="badge {VERDICT_CLASS.get(word or "", "")}">{esc(word or "—")}</span>'


def num(value: float | None, unit: str = "", decimals: int = 1) -> str:
    return "—" if value is None else f"{C.fmt(value, decimals)}{unit}"


# ---------------------------------------------------------------- horizons

def gauge(score: float | None) -> str:
    """A −1..+1 bar with the thresholds (−0.2 / +0.3) and the score's marker."""
    if score is None:
        return '<div class="gauge-none muted small">点数なし</div>'
    pct = (max(-1.0, min(1.0, score)) + 1) / 2 * 100
    down, up = (J.DOWN + 1) / 2 * 100, (J.UP + 1) / 2 * 100
    return (f'<div class="gauge" role="img" aria-label="点数 {score:+.2f}">'
            f'<div class="g-zone g-pass" style="left:0;width:{down:.1f}%"></div>'
            f'<div class="g-zone g-watch" style="left:{down:.1f}%;width:{up - down:.1f}%"></div>'
            f'<div class="g-zone g-consider" style="left:{up:.1f}%;width:{100 - up:.1f}%"></div>'
            f'<div class="g-mark" style="left:{pct:.1f}%"></div>'
            f'<span class="g-l">見送り</span><span class="g-m">ウォッチ</span><span class="g-r">投資検討</span></div>')


def _point(row: dict) -> str:
    pending = "（判定保留を0点）" if row["pending"] else ""
    reason = f'<span class="small muted">。{esc(row["reason"])}</span>' if row["reason"] else ""
    return (f'<li><b>{esc(row["label"])}</b> <span class="muted small">重み {row["weight"]}%・寄与 '
            f'{row["contribution"]:+.2f}{esc(pending)}</span><br>{esc(row["value"])}{reason}</li>')


def _movers(h: dict) -> str:
    s = h.get("sensitivity") or {}
    parts = [f"最も近い境目: {s['nearest']['text']} 点"] if s.get("nearest") else []
    if s.get("to_up") is not None:
        parts.append(f"投資検討まであと {s['to_up']:+.2f} 点")
    if s.get("to_down") is not None:
        parts.append(f"見送りまであと {s['to_down']:.2f} 点")
    movers = [J.mover_text(m, h["rows"]) for m in s.get("movers") or []]
    text = "、".join(parts) or "—"
    text += "。" + ("、".join(movers) if movers else "1つの要素が1段変わっても判定は変わらない")
    return f'<p class="small"><b>判定を動かす要因</b>: {esc(text)}</p>'


def horizon_block(label: str, span: str, h: dict, prose: str, matrix: dict | None) -> str:
    good = "".join(_point(r) for r in h["good"]) or '<li class="muted">なし</li>'
    bad = "".join(_point(r) for r in h["bad"]) or '<li class="muted">なし</li>'
    knock = f'<p class="notice"><b>足切り</b>: {esc("、".join(h["knockout"]))}</p>' if h.get("knockout") else ""
    unknown = (f'<p class="small muted">材料が無く点数から外した要素: {esc("・".join(h["unknown"]))}</p>'
               if h.get("unknown") else "")
    rows = table(["要素", "重み", "点数", "寄与", "値", "情報源"],
                 [[esc(r["label"]), f'{r["weight"]}%', "不明" if r["score"] is None else f'{r["score"]:+.1f}',
                   "—" if r["contribution"] is None else f'{r["contribution"]:+.3f}', esc(r["value"]),
                   esc(r["source"])] for r in h["rows"]], right=frozenset({1, 2, 3}))
    ref = (f'<p class="small"><b>参考: フレームワークの判定マトリクス</b> {badge(matrix["verdict"])} '
           f'{esc(matrix["why"])}</p>' if matrix else "")
    score = "—" if h["score"] is None else f'{h["score"]:+.2f}'
    return (f'<div class="horizon {VERDICT_CLASS.get(h["verdict"], "")}"><div class="h-head"><h3>{esc(label)}'
            f'<span class="muted small">（{esc(span)}）</span></h3>{badge(h["verdict"])}'
            f'<span class="h-score">点数 {score}</span></div>{gauge(h["score"])}{knock}<div class="prose">{prose}</div>'
            f'<div class="cols pn"><div class="plus"><h4>良い点（点数を押し上げた要素）</h4><ul>{good}</ul></div>'
            f'<div class="minus"><h4>悪い点（点数を押し下げた要素）</h4><ul>{bad}</ul></div></div>'
            f'{_movers(h)}{unknown}{ref}'
            f'<details><summary>点数の内訳（{esc(label)}）</summary><div class="inner">{rows}</div></details></div>')


# ---------------------------------------------------------------- 3C / SWOT

LONG_NOTE = re.compile(r"\s*[（(][^（）()]{6,}[）)]")


def short_name(name: str | None) -> str:
    """A company name without the collector's notes ('X（3月期。2022年3月期以降は IFRS を…）' -> 'X')."""
    return LONG_NOTE.sub("", name or "").strip() or (name or "")


def _competitor_conclusion(detail: dict) -> str:
    rating = detail.get("competitor") or "—"
    unknown = any(k.get("self") == "？" for k in detail.get("kbf_table") or [])
    if rating == "同等" and unknown:
        return "同等（選ばれる理由（KBF）を比べる材料が足りず、同程度とみなした。数値の差は上の表のとおり）"
    return rating


def _mark(mark: str | None) -> str:
    return f'<span class="mk {MARK_CLASS.get(mark or "", "")}">{esc(mark or "—")}</span>'


def _three_c_cards(detail: dict) -> str:
    kbf = "".join(f'<li{" class=top" if i == 0 else ""}>{esc(k)}</li>' for i, k in enumerate(detail.get("kbf") or []))
    customer = (f'<div class="c3 c-customer"><div class="c3-h">Customer（顧客・市場）</div>'
                f'<p class="small">{esc(detail.get("customers") or detail.get("customer") or "—")}</p>'
                f'<p class="small"><b>選ぶときに重視すること（KBF。上ほど重要）</b></p><ol class="kbf">{kbf}</ol>'
                f'<p class="small"><b>市場の成長性</b>: {esc(detail.get("growth") or "—")}。'
                f'{esc(detail.get("growth_reason") or "")}</p></div>')
    comp_rows = [[esc(short_name(c["name"])) + (" <b>（対象）</b>" if c.get("self") else ""),
                  esc(num(c["sales"] / YEN_OKU, "億円", 0) if c.get("sales") else "—"),
                  esc(num(c.get("margin"), "%")), esc(num(c.get("cagr"), "%")), esc(num(c.get("share"), "%"))]
                 for c in detail.get("comparison") or []]
    competitor = (f'<div class="c3 c-competitor"><div class="c3-h">Competitor（競合）</div>'
                  + table(["会社", "売上高", "営業利益率", "3年CAGR", "シェア"], comp_rows,
                          right=frozenset({1, 2, 3, 4}))
                  + f'<p class="small"><b>比較の結論</b>: {esc(_competitor_conclusion(detail))}。'
                    f'{esc(detail.get("competitor_reason") or "")}</p></div>')
    company = (f'<div class="c3 c-company"><div class="c3-h">Company（自社）</div>'
               f'<p class="small"><b>強み</b>: {esc(detail.get("strengths") or "—")}</p>'
               f'<p class="small"><b>弱み</b>: {esc(detail.get("weaknesses") or "—")}</p></div>')
    return f'<div class="c3-grid">{customer}{competitor}{company}</div>'


def three_c_block(detail: dict, analysis: dict) -> str:
    if not detail:
        return '<h3>3C分析</h3><p class="muted">3C分析が未実施。</p>'
    peers = list(((detail.get("kbf_table") or [{}])[0] or {}).get("peers", {}).keys())
    kbf_rows = [[esc(k["kbf"]), _mark(k["self"])] + [_mark(k["peers"].get(p)) for p in peers] + [esc(k.get("basis"))]
                for k in detail.get("kbf_table") or []]
    letters = [f"競合{chr(ord('A') + i)}" for i in range(len(peers))]
    legend = "、".join(f"{letter}: {esc(short_name(p))}" for letter, p in zip(letters, peers))
    kbf_table = ((f'<p class="small muted">{legend}</p>' if legend else "")
                 + table(["KBF", "自社"] + letters + ["根拠"], kbf_rows, nowrap=frozenset(range(len(peers) + 2))))
    conservative = "".join(f"<li>{esc(c)}</li>" for c in analysis.get("conservative") or [])
    conclusion = (f'<p><b>勝てる理由</b>: {badge(analysis.get("verdict"))} {esc(analysis.get("reason"))}</p>'
                  + (f'<ul class="plain small">{conservative}</ul>' if conservative else ""))
    return (f'<h3>3C分析（顧客・競合・自社）</h3>{_three_c_cards(detail)}'
            f'<h4>KBF ごとの比較（○ 優れる・△ 同程度・× 劣る・？ 比べる材料なし）</h4>{kbf_table}{conclusion}')


def swot_grid(detail: dict, analysis: dict) -> str:
    if not detail:
        return '<h3>SWOT分析</h3><p class="muted">SWOT分析が未実施。</p>'
    top = {(detail.get("top_strength") or {}).get("id"), (detail.get("top_threat") or {}).get("id")}
    cells = ""
    for key, name, axis in QUADRANTS:
        items = "".join(
            f'<li class="{"top" if i.get("id") in top else ""}"><span class="imp {IMPACT_CLASS.get(i.get("impact"), "")}">'
            f'{esc(i.get("impact") or "—")}</span> <b>{esc(i.get("id"))}</b> {esc(i.get("fact"))}</li>'
            for i in (detail.get("quadrants") or {}).get(key) or []) or '<li class="muted">なし</li>'
        cells += (f'<div class="swq swq-{key}"><div class="swq-h">{esc(name)}<span>{esc(axis)}</span></div>'
                  f'<ul>{items}</ul></div>')
    return (f'<h3>SWOT分析</h3><div class="swot">{cells}</div>'
            f'<p class="small muted">影響度: 大・中・小（枠で囲んだ項目は最大の強み・最大の脅威）</p>'
            f'<p><b>強みで脅威に対抗できるか</b>: {badge(analysis.get("verdict"))} {esc(detail.get("sentence"))}</p>')


# ---------------------------------------------------------------- management and shareholders

def governance_block(facts: dict) -> str:
    """経営と株主: the owner's stake, the president, new shares and the management's targets against results."""
    g, m = facts.get("governance"), facts.get("management")
    if not g and not m:
        return ('<h3>経営と株主</h3><p class="muted">大株主・役員（有価証券報告書）と経営者の目標と実績'
                "（決算説明会資料）を集めていない。</p>")
    out = "<h3>経営と株主</h3>"
    if g:
        owner, p = g.get("owner") or {}, g.get("president") or {}
        members = "、".join(f"{x['name']} {num(x['ratio'], '%')}（{x['why']}）" for x in owner.get("members") or [])
        word = "オーナー企業（創業者・親族の保有が 20% 以上）" if owner.get("is_owner") else "オーナー企業ではない"
        lines = [f"創業者・親族の保有: {num(owner.get('ratio'), '%')}。{word}" + (f"（{members}）" if members else ""),
                 f"社長: {p.get('name') or '—'}（{p.get('title') or '—'}、{p.get('age') or '—'}歳）"]
        if owner.get("is_owner"):
            lines.append("オーナーの持株は経営の意思決定を速くする一方、相続や売却のときに株が市場に出て株価が動くことがある")
        offers = [f"{i['period_end'][:7]} {i['kind']}（{num(i['change_pct'], '%')}）" for i in g.get("issuances") or []]
        lines.append("発行済株式数の増加: " + ("、".join(offers) if offers else "なし")
                     + ("。5年以内に公募増資・第三者割当あり（キャッシュフローの評価は最大でも普通）"
                        if g.get("offering_within_5y") else ""))
        out += _ul(lines) + f'<p class="source">出典: 有価証券報告書（{esc(g.get("as_of") or "—")} 期、提出 {esc(g.get("filed") or "—")}）</p>'
    if m:
        avg = "、".join(f"{k} {v:.1f}%" for k, v in (m.get("average") or {}).items()) or "—"
        rows = [[esc(r["year"]), esc(r["kind"]), esc(r["item"]), esc(r["target"]), esc(r["actual"]),
                 esc(num(r["rate"], "%"))] for r in m["rows"]]
        out += (f"<h4>経営者の目標と実績（言行一致）</h4><p class=\"small\">達成率の平均: {esc(avg)}</p>"
                + (table(["年度", "目標の種類", "項目", "目標", "実績", "達成率"], rows, right=frozenset({3, 4, 5}))
                   if rows else '<p class="muted">目標と実績の表が無い</p>')
                + _ul([f"{x['date']} {x['summary']}" for x in m.get("messages") or []])
                + f'<p class="source">出典: 決算説明会資料・社長メッセージ（{esc(m["file"])} 収集）</p>')
    return out


def _ul(items: list[str]) -> str:
    return '<ul class="plain small">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>" if items else ""


# ---------------------------------------------------------------- growth / peers / dividends

def growth_block(facts: dict) -> str:
    g = facts["analyses"]["growth"].get("detail") or {}
    tc = facts["analyses"]["three_c"].get("detail") or {}
    items = (g.get("progress") or {}).get("items") or {}
    plan = [[esc(i.get("name")), esc(num(i.get("last_actual"), "", 0)), esc(num(i.get("forecast"), "", 0)),
             esc(num(i.get("forecast_growth"), "%")), esc(num(i.get("progress"), "%")),
             esc(num(i.get("prior_progress"), "%"))] for i in items.values()]
    cagr = g.get("cagr") or {}
    span = "〜".join(s for s in g.get("cagr_span") or [] if s)
    lines = [f"過去の年平均成長率（{span}）: 売上 {num(cagr.get('sales'), '%')}・営業利益 "
             f"{num(cagr.get('operating_income'), '%')}・EPS {num(cagr.get('eps'), '%')}（{g.get('growth_type') or '—'}）",
             f"会社計画の信頼性: {g.get('plan') or '—'}（過去の達成率の平均 {num(g.get('plan_average'), '%', 0)}）",
             f"成長の質: {g.get('quality_sentence') or g.get('quality') or '—'}",
             f"市場の成長性（3C）: {tc.get('growth') or '—'}。{tc.get('market') or ''}",
             f"中期経営計画: {g.get('mtp') or '—'}"]
    plan_table = (f'<h4>今期の会社計画と進み具合（{esc(facts["unit"])}）</h4>'
                  + table(["項目", "前期の実績", "今期の会社予想", "予想の伸び", "進捗率", "前年同期の進捗率"], plan,
                          right=frozenset({1, 2, 3, 4, 5})) if plan else "")
    return ('<h3>成長の見通し</h3><ul class="plain">' + "".join(f"<li>{esc(x)}</li>" for x in lines) + "</ul>"
            + plan_table)


def peers_block(facts: dict) -> str:
    peers = facts.get("peers") or {}
    rows = peers.get("rows") or []
    if len(rows) <= 1:
        return ""
    cols = peers.get("columns") or []
    body = []
    summary = [peers[k] for k in ("mean", "median") if peers.get(k)]  # the average beside the median
    for r in rows + summary:
        name = esc(short_name(r["name"])) + (" <b>（対象）</b>" if r.get("self") else "")
        cls = "self-row" if r.get("self") else ("median-row" if r in summary else "")
        body.append([f'<span class="{cls}">{name}</span>'] + [esc(num(r.get(k), u, 1)) for k, _, u in cols])
    return ('<h3>同業比較</h3>' + table(["会社"] + [label for _, label, _ in cols], body,
                                       right=frozenset(range(1, len(cols) + 1)))
            + '<p class="source">出典: バリュエーション・収益性・安全性分析（同業の数値は競合資料。— は材料なし）</p>')


def dividends_block(facts: dict) -> str:
    d = facts.get("dividends") or {}
    if not d.get("source"):
        return '<h3>株主還元</h3><p class="muted">配当の資料（決算短信・有価証券報告書）が集まっていない。</p>'
    steps = (facts["analyses"]["cash_flow"].get("detail") or {}).get("steps") or []
    cf5 = steps[4] if len(steps) > 4 else {}
    basis = d.get("yield_basis") or "予想"
    rows = [["1株配当（実績）", esc(num(d.get("actual"), "円")), esc((d.get("actual_fy") or "—")[:7] + " 期")],
            ["1株配当（会社予想）", esc(num(d.get("forecast"), "円")), esc((d.get("forecast_fy") or "—")[:7] + " 期")
             if d.get("forecast") is not None else "会社予想を集めていない"],
            [f"配当利回り（{basis}配当 ÷ 株価）", esc(num(d.get("yield"), "%", 2)), "株価はバリュエーションの基準日"],
            ["配当性向（予想配当 ÷ 予想EPS）", esc(num(d.get("payout_forecast"), "%")),
             f"実績の配当性向 {esc(num(d.get('payout_actual'), '%'))}"]]
    return ("<h3>株主還元</h3>" + table(["項目", "値", "補足"], rows, right=frozenset({1}))
            + f'<p class="small">還元と FCF: {esc((cf5 or {}).get("sentence") or "—")}</p>'
            + f'<p class="source">出典: {esc(d["source"])}・キャッシュフロー分析（株主還元の持続性）</p>')


# ---------------------------------------------------------------- tooltips

def _term_pattern() -> tuple[re.Pattern, dict[str, str]]:
    words = {}
    for term, desc in G.TERMS.items():
        for w in (term, *G.ALIASES.get(term, ())):
            words[w] = desc
    parts = []
    for w in sorted(words, key=len, reverse=True):
        e = re.escape(escape(w))
        parts.append(rf"(?<![A-Za-z]){e}(?![A-Za-z])" if w.isascii() else e)
    return re.compile("|".join(parts)), {escape(w): d for w, d in words.items()}


TERM_RE, TERM_TIPS = _term_pattern()
TAG = re.compile(r"(<[^>]+>)")
TAG_NAME = re.compile(r"</?([a-zA-Z0-9]+)")


def annotate(html: str) -> str:
    """Wrap the first appearance of each glossary term per <section> in a focusable tooltip span. Only text between
    tags is touched; text inside SKIP_TAGS (charts, headings, links, the glossary's own terms) is left alone."""
    out, seen, skip = [], set(), []

    def wrap(m: re.Match) -> str:
        word = m.group(0)
        tip = TERM_TIPS.get(word)
        if not tip or tip in seen:
            return word
        seen.add(tip)
        return f'<span class="term" tabindex="0" data-tip="{escape(tip, quote=True)}">{word}</span>'

    for token in TAG.split(html):
        if token.startswith("<"):
            name = TAG_NAME.match(token)
            tag = name.group(1).lower() if name else ""
            if tag == "section" and not token.startswith("</"):
                seen.clear()
            if tag in SKIP_TAGS and not token.endswith("/>"):
                if not token.startswith("</"):
                    skip.append(tag)
                elif skip and skip[-1] == tag:
                    skip.pop()
            out.append(token)
        elif skip or not token.strip():
            out.append(token)
        else:
            out.append(TERM_RE.sub(wrap, token))
    return "".join(out)
