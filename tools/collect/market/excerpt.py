"""Cut a document text (pdf_text.py output) down to the parts worth summarising.

Multi-page (PDF): the first pages (title / table of contents), then pages matching the
catalog's must_include patterns, then pages ranked by keyword hits, until max_chars.
Single page (HTML): kept whole when it is at most WHOLE_SLACK x max_chars. Otherwise
lines are taken by priority (must_include > keyword > long body paragraph) until
max_chars, a short heading line is kept before each chosen paragraph, and the result
is put back in document order. Short lines without keywords (site navigation) are dropped.

The excerpt starts with a COVERAGE line (which pages are included, out of how many) and
keeps '=====PAGE n=====' markers so the summary can cite pages. PAGE n is the page
number of the PDF file, not the number printed on the page.
"""
from __future__ import annotations

import re
from pathlib import Path

from find_pages import load_pages

PAGE_MARK = "=====PAGE {n}====="
COVERAGE_MARK = "=====COVERAGE: {detail}（PAGE n は PDF のページ番号。印字ページ番号ではない）====="
DEFAULT_MAX_CHARS = 14_000
HEAD_PAGES = 2
HEAD_PAGE_CHARS = 2_500
HEAD_LINES = 3
WHOLE_SLACK = 1.2
BODY_LINE_CHARS = 80  # lines at least this long are body paragraphs, shorter ones headings or navigation
HEADING_CHARS = 120
NEVER = re.compile(r"(?!)")


def _keyword_rx(keywords: list[str]) -> re.Pattern:
    return re.compile("|".join(re.escape(k) for k in keywords)) if keywords else NEVER


def _must_rx(patterns: list[str] | None) -> re.Pattern:
    return re.compile("|".join(f"(?:{p})" for p in patterns)) if patterns else NEVER


def page_ranges(numbers: list[int]) -> str:
    """[1, 2, 5, 6, 7] -> '1-2,5-7'."""
    out, start, prev = [], None, None
    for n in sorted(numbers):
        if start is not None and n == prev + 1:
            prev = n
            continue
        if start is not None:
            out.append(f"{start}-{prev}" if prev > start else str(start))
        start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if prev > start else str(start))
    return ",".join(out)


def _line_rank(line: str, keyword: re.Pattern, must: re.Pattern) -> int | None:
    if must.search(line):
        return 0
    if keyword.search(line):
        return 1
    if len(line) >= BODY_LINE_CHARS:
        return 2
    return None


def _trim_single_page(body: str, keyword: re.Pattern, max_chars: int, must: re.Pattern = NEVER) -> str:
    if len(body) <= max_chars * WHOLE_SLACK:
        return body
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    ranked = sorted((rank, i) for i, line in enumerate(lines)
                    if (rank := 0 if i < HEAD_LINES else _line_rank(line, keyword, must)) is not None)
    keep, used = set(), 0
    for _, i in ranked:
        cost = len(lines[i]) + 1
        if used + cost <= max_chars:
            keep.add(i)
            used += cost
    for i in sorted(keep):  # the heading right above a chosen paragraph, when it still fits
        j = i - 1
        if j >= 0 and j not in keep and len(lines[j]) < HEADING_CHARS and used + len(lines[j]) + 1 <= max_chars:
            keep.add(j)
            used += len(lines[j]) + 1
    return "\n".join(lines[i] for i in sorted(keep))


def build_excerpt(pages: dict[int, str], keywords: list[str], max_chars: int = DEFAULT_MAX_CHARS,
                  must_include: list[str] | None = None) -> str:
    keyword, must = _keyword_rx(keywords), _must_rx(must_include)
    if len(pages) == 1:
        n, body = next(iter(pages.items()))
        trimmed = _trim_single_page(body, keyword, max_chars, must)
        share = min(100, round(100 * len(trimmed) / max(len(body), 1)))
        coverage = COVERAGE_MARK.format(detail=f"1 ページの文書。本文の約 {share}% を収録")
        return f"{coverage}\n{PAGE_MARK.format(n=n)}\n{trimmed}\n"
    chosen: dict[int, str] = {}
    used = 0
    for n in sorted(pages)[:HEAD_PAGES]:
        chosen[n] = pages[n][:HEAD_PAGE_CHARS]
        used += len(chosen[n])
    rest = [n for n in pages if n not in chosen]
    ranked = sorted(rest, key=lambda n: (-len(must.findall(pages[n])), -len(keyword.findall(pages[n])), n))
    for n in ranked:
        if not (must.search(pages[n]) or keyword.search(pages[n])) or used + len(pages[n]) > max_chars:
            continue
        chosen[n] = pages[n]
        used += len(pages[n])
    detail = f"収録ページ {page_ranges(list(chosen))} / 全 {len(pages)} ページ"
    body = "".join(f"{PAGE_MARK.format(n=n)}\n{chosen[n].strip()}\n" for n in sorted(chosen))
    return f"{COVERAGE_MARK.format(detail=detail)}\n{body}"


def write_excerpt(text_path: Path, keywords: list[str], max_chars: int = DEFAULT_MAX_CHARS,
                  must_include: list[str] | None = None) -> Path:
    out = text_path.with_name(text_path.name.replace(".txt", "") + ".excerpt.txt")
    out.write_text(build_excerpt(load_pages(text_path), keywords, max_chars, must_include), encoding="utf-8")
    return out
