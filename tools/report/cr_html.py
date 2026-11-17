"""HTML pieces every chapter of the company report shares (cr_render.py, cr_dashboard.py, cr_ch_price.py).

Every piece of text goes through esc(): the reader's-words pass (cr_plain) and then slides.esc, so nothing from the
analyses or the md can inject markup.
"""
from __future__ import annotations

import cr_judge as J
import cr_plain as P
import slides
from slides import table

VERDICT_CLASS = {J.CONSIDER: "v-consider", J.WATCH: "v-watch", J.PASS: "v-pass", J.PENDING: "v-pending"}
SPANS = {"short": "〜3ヶ月", "mid": "6ヶ月〜1年", "long": "3年以上"}
PERIODS = {"short": "短期", "mid": "中期", "long": "長期"}
OK_HTML = {True: '<span class="ok-yes">○ 満たす</span>', False: '<span class="ok-no">× 満たさない</span>',
           None: '<span class="ok-unk">不明</span>'}


def esc(text: object) -> str:
    """slides.esc after the reader's-words pass (an internal term written anywhere still reads plainly)."""
    return slides.esc(P.plain(text) if isinstance(text, str) else text)


def badge(word: str | None) -> str:
    return f'<span class="badge {VERDICT_CLASS.get(word or "", "")}">{esc(word or "—")}</span>'


def section(sid: str, number: str, title: str, lead: str, body: str) -> str:
    lead_html = f'<p class="lead">{esc(lead)}</p>' if lead else ""
    return (f'<section id="{sid}"><div class="wrap"><span class="num">{esc(number)}</span><h2>{esc(title)}</h2>'
            f"{lead_html}{body}</div></section>")


def paragraphs(text: str) -> str:
    return "".join(f"<p>{esc(p.strip())}</p>" for p in text.split("\n\n") if p.strip())


def bullet_list(items: list[str]) -> str:
    if not items:
        return '<p class="muted">なし</p>'
    return '<ul class="plain">' + "".join(f"<li>{esc(i)}</li>" for i in items) + "</ul>"


def details(summary: str, inner: str, sid: str = "") -> str:
    anchor = f' id="{sid}"' if sid else ""
    return f'<details{anchor}><summary>{esc(summary)}</summary><div class="inner">{inner}</div></details>'


def conditions(rows: list[dict]) -> str:
    return table(["確かめたこと", "値", "情報源", "結果"],
                 [[esc(r["condition"]), esc(r["value"]), esc(r["source"]), OK_HTML[r["ok"]]] for r in rows],
                 nowrap=frozenset({3}))


def figure(title: str, chart: str, source: str = "", unit: str = "", note: str = "") -> str:
    """A chart in its box: title, optional unit, the SVG, a one-line 'how to read' note and the source."""
    unit_html = f'<span class="muted">{esc(unit)}</span>' if unit else ""
    note_html = f'<p class="howto">{esc(note)}</p>' if note else ""
    source_html = f'<div class="source">出典: {esc(source)}</div>' if source else ""
    return (f'<figure class="chartbox"><figcaption><b>{esc(title)}</b>{unit_html}</figcaption>{chart}'
            f"{note_html}{source_html}</figure>")
