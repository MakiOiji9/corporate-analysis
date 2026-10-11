"""Cut a document text (pdf_text.py output) down to the parts worth summarising.

Keeps the first pages (title / table of contents) and then the pages whose text
matches the catalog keywords, until max_chars. A single-page HTML text (speeches)
is kept whole when short, otherwise trimmed to keyword paragraphs with one line of
context. The excerpt keeps '=====PAGE n=====' markers so the summary can cite pages.
"""
from __future__ import annotations

import re
from pathlib import Path

from find_pages import load_pages

PAGE_MARK = "=====PAGE {n}====="
DEFAULT_MAX_CHARS = 14_000
HEAD_PAGES = 2
HEAD_PAGE_CHARS = 2_500


def _keyword_rx(keywords: list[str]) -> re.Pattern:
    return re.compile("|".join(re.escape(k) for k in keywords)) if keywords else re.compile(r"(?!)")


def _trim_single_page(body: str, rx: re.Pattern, max_chars: int) -> str:
    if len(body) <= max_chars:
        return body
    lines = [line for line in body.splitlines() if line.strip()]
    keep: set[int] = set(range(min(5, len(lines))))
    for i, line in enumerate(lines):
        if rx.search(line):
            keep.update({i - 1, i, i + 1})
    out, used = [], 0
    for i in sorted(k for k in keep if 0 <= k < len(lines)):
        if used + len(lines[i]) > max_chars:
            break
        out.append(lines[i])
        used += len(lines[i]) + 1
    return "\n".join(out)


def build_excerpt(pages: dict[int, str], keywords: list[str], max_chars: int = DEFAULT_MAX_CHARS) -> str:
    rx = _keyword_rx(keywords)
    if len(pages) == 1:
        n, body = next(iter(pages.items()))
        return f"{PAGE_MARK.format(n=n)}\n{_trim_single_page(body, rx, max_chars)}\n"
    chosen: list[tuple[int, str]] = []
    used = 0
    for n in sorted(pages)[:HEAD_PAGES]:
        body = pages[n][:HEAD_PAGE_CHARS]
        chosen.append((n, body))
        used += len(body)
    ranked = sorted((n for n in pages if n not in dict(chosen)),
                    key=lambda n: -len(rx.findall(pages[n])))
    for n in ranked:
        hits = len(rx.findall(pages[n]))
        if hits == 0 or used + len(pages[n]) > max_chars:
            continue
        chosen.append((n, pages[n]))
        used += len(pages[n])
    return "".join(f"{PAGE_MARK.format(n=n)}\n{body.strip()}\n" for n, body in sorted(chosen))


def write_excerpt(text_path: Path, keywords: list[str], max_chars: int = DEFAULT_MAX_CHARS) -> Path:
    out = text_path.with_name(text_path.name.replace(".txt", "") + ".excerpt.txt")
    out.write_text(build_excerpt(load_pages(text_path), keywords, max_chars), encoding="utf-8")
    return out
