"""Detect new policy / monetary-policy documents from watch pages and RSS feeds.

A catalog "watch" entry:
  {"key": "pm-speech", "layer": "A", "kind": "summarize" | "list",
   "type": "html_links" | "rss", "url": "...{var}...",
   "link_pattern": regex on the absolute URL, "title_pattern": regex on the link text,
   "follow": {"link_pattern": ..., "title_pattern": ...}   # optional: open the hit and take the PDF
   "max_new": 1}
Catalog-level "vars" resolve placeholders such as the kantei cabinet number:
  {"kantei_cabinet": {"url": "https://www.kantei.go.jp/", "pattern": "/jp/(\\d+)/"}}

Everything here is deterministic; the LLM only summarises the documents found.
"""
from __future__ import annotations

import email.utils
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, replace
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

from common import read_csv_rows, write_csv_atomic

INDEX_FIELDS = ["doc_key", "watch_key", "layer", "title", "published", "url",
                "page_url", "raw_path", "collected", "status"]
ANCHOR = re.compile(r"<a\b[^>]*?href\s*=\s*[\"']([^\"'#]+)[\"'][^>]*>(.*?)</a>", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
REIWA = re.compile(r"令和\s*(\d+|元)\s*年\s*(\d+)\s*月\s*(\d+)\s*日")
SEIREKI = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
URL_DATE = re.compile(r"/(20\d{2})/(\d{2})(\d{2})")
URL_COMPACT_DATE = re.compile(r"(20\d{2})(0[1-9]|1[0-2])([0-2]\d|3[01])[^/]*$")
REIWA_BASE = 2018


@dataclass(frozen=True)
class Candidate:
    watch_key: str
    layer: str
    kind: str
    title: str
    url: str
    published: str
    page_url: str = ""


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(TAG.sub(" ", text))).strip()


def find_date(*texts: str) -> str:
    """First date found in the texts (令和/西暦 in labels, /YYYY/MMDD in URLs, RFC 822)."""
    for text in texts:
        if not text:
            continue
        if m := REIWA.search(text):
            year = REIWA_BASE + (1 if m.group(1) == "元" else int(m.group(1)))
            return f"{year}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if m := SEIREKI.search(text):
            return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
        if m := URL_DATE.search(text) or URL_COMPACT_DATE.search(text):
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        try:
            return email.utils.parsedate_to_datetime(text).date().isoformat()
        except (TypeError, ValueError):
            continue
    return ""


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    out, seen = [], set()
    for href, label in ANCHOR.findall(html):
        url = urljoin(base_url, unescape(href.strip()))
        if url not in seen:
            seen.add(url)
            out.append((url, clean(label)))
    return out


def parse_rss(xml_text: str) -> list[tuple[str, str, str]]:
    """[(link, title, published ISO)] for RSS 2.0 / RDF items."""
    root = ET.fromstring(xml_text.lstrip("﻿").strip())
    out = []
    for item in root.iter():
        if not item.tag.endswith("item"):
            continue
        fields = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in item}
        link = fields.get("link") or item.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about", "")
        date = fields.get("pubDate") or fields.get("date", "")
        out.append((link, clean(fields.get("title", "")), find_date(date) if date else ""))
    return out


def resolve_vars(spec: dict, get) -> tuple[dict, list[str]]:
    """Values for URL placeholders, and errors for the ones that could not be resolved.

    Each var is independent: a failure only breaks the watch entries that use it.
    """
    values, errors = {}, []
    for name, rule in spec.items():
        try:
            html = get(rule["url"]).content.decode("utf-8", errors="replace")
            m = re.search(rule["pattern"], html)
            if not m:
                raise ValueError(f"pattern not found on {rule['url']}")
            values[name] = m.group(1)
        except Exception as exc:  # noqa: BLE001 - reported per var, entries using it fail later
            errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:100]}")
    return values, errors


def _matches(entry: dict, url: str, title: str) -> bool:
    link_ok = re.search(entry["link_pattern"], url) if entry.get("link_pattern") else True
    title_ok = re.search(entry["title_pattern"], title) if entry.get("title_pattern") else True
    return bool(link_ok and title_ok)


def date_from_pattern(pattern: str, text: str) -> str:
    """Catalog date_pattern with named groups y (2 or 4 digits), m and optional d."""
    m = re.search(pattern, text)
    if not m:
        return ""
    parts = m.groupdict()
    year = parts["y"] if len(parts["y"]) == 4 else "20" + parts["y"]
    return f"{year}-{int(parts['m']):02d}-{int(parts.get('d') or 1):02d}"


def list_candidates(entry: dict, get, variables: dict) -> list[Candidate]:
    """All matching documents on the watch page, page order (usually newest first)."""
    url = entry["url"].format(**variables)
    body = get(url).content.decode(entry.get("encoding", "utf-8"), errors="replace")
    kind, layer, key = entry.get("kind", "summarize"), entry.get("layer", ""), entry["key"]
    if entry["type"] == "rss":
        items = [(link, title, date) for link, title, date in parse_rss(body)]
    else:
        items = [(link, title, "") for link, title in extract_links(body, url)]
    out = []
    for link, title, date in items:
        if not _matches(entry, link, title):
            continue
        if entry.get("date_pattern"):
            date = date_from_pattern(entry["date_pattern"], link) or date
        date = date or find_date(title, link)
        if entry.get("use_entry_title"):  # link text is only 'PDF' / '9月' on some pages
            title = f"{entry['title']}（{date or title}）"
        out.append(Candidate(key, layer, kind, title, link, date))
    if out and all(c.published for c in out):  # some pages list oldest first; pick_new needs newest first
        out.sort(key=lambda c: c.published, reverse=True)
    return out


def follow(candidate: Candidate, rules: dict | list[dict], get) -> Candidate | None:
    """Open the candidate page and point url at the main document (e.g. the 本文 PDF).

    rules may be a list to go several pages deep (年度ページ -> 政府案ページ -> ポイント PDF).
    Returns None when a step finds no matching link (e.g. next year's budget page before
    the PDF is posted), so the caller can move on to the next candidate.
    """
    url, published = candidate.url, candidate.published
    for rule in rules if isinstance(rules, list) else [rules]:
        html = get(url).content.decode("utf-8", errors="replace")
        hit = next((link for link, label in extract_links(html, url) if _matches(rule, link, label)), None)
        if hit is None:
            return None
        published = published or find_date(hit, clean(html)[:3000])
        url = hit
    return replace(candidate, url=url, page_url=candidate.url, published=published)


def load_index(index_csv: Path) -> list[dict]:
    return read_csv_rows(index_csv)


def known_urls(rows: list[dict]) -> set[str]:
    return {r["url"] for r in rows} | {r["page_url"] for r in rows if r.get("page_url")}


def pick_new(cands: list[Candidate], known: set[str]) -> list[Candidate]:
    """Candidates newer than the newest one already in the library.

    Watch pages and feeds list newest first, so scanning stops at the first known URL;
    older documents are never picked up later. The caller stops at max_new.
    """
    fresh = []
    for c in cands:
        if c.url in known:
            break
        fresh.append(c)
    return fresh


def make_doc_key(watch_key: str, published: str, collected: str, taken: set[str]) -> str:
    base = f"{watch_key}-{published or collected}"
    key, n = base, 2
    while key in taken:
        key, n = f"{base}-{n}", n + 1
    return key


def save_index(index_csv: Path, rows: list[dict]) -> None:
    write_csv_atomic(index_csv, INDEX_FIELDS, rows)
