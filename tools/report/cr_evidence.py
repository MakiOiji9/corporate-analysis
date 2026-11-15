"""The 出典 of an analysis claim in the company report (BL-01): the analyses' json carry `evidence` lists
(tools/analysis/provenance.py) and every table that shows a claim renders them the same way.

A document's name links to its public URL (manifest.csv), so a reader on GitHub or Slack can open it; only a
document with no URL falls back to the saved original under sources/ (git-ignored: it opens where it was fetched).
"""
from __future__ import annotations

import html
from urllib.parse import quote, urlparse

from cr_html import esc

VERIFIED = "検証済み"
KEYS = ("status", "reason", "doc_id", "title", "url", "published", "period", "pages", "local_path")
REASONS = {  # provenance.py's reasons in the reader's words
    "Front Matter なし": "出典の記録なし", "Front Matter の形式の誤り": "出典の記録に誤り", "節の出典なし": "該当箇所の記録なし",
    "原本なし": "原本の保存なし", "ページなし": "ページの記録なし", "検索要約": "検索結果の要約のみ"}


def slim(evidence: list[dict] | None) -> list[dict]:
    """The keys the report shows (for facts.json)."""
    return [{k: e.get(k) for k in KEYS} for e in evidence or []]


def _href(e: dict) -> str | None:
    url = e.get("url")
    if url and urlparse(url).scheme in ("http", "https"):
        return html.escape(url)
    return html.escape(quote("../" + e["local_path"])) if e.get("local_path") else None  # a path: no plain()


def item(e: dict) -> str:
    """'✓ 有価証券報告書 第110期 p.42-43' linked to its source, or '未検証（ページの記録なし） 資料名'."""
    name = esc(e.get("title") or e.get("doc_id") or "")
    href = _href(e)
    named = f'<a href="{href}" rel="noopener">{name}</a>' if href and name else name
    if e.get("status") != VERIFIED:
        reason = f"（{REASONS.get(e['reason'], e['reason'])}）" if e.get("reason") else ""
        return f'<span class="ok-unk">{esc(e.get("status") or "")}{esc(reason)}</span>' + (f" {named}" if named else "")
    pages = f" p.{esc(e['pages'])}" if e.get("pages") else ""
    return f'<span class="ok-yes">✓</span> {named}{pages}'


def cell(evidence: list[dict] | None) -> str:
    """Every document of one claim, once each (two sections may cite the same one); '—' when there is none
    (a result built before BL-01, or a claim whose 情報源 names no raw file)."""
    items = list(dict.fromkeys(item(e) for e in evidence or []))
    return "<br>".join(items) if items else "—"
