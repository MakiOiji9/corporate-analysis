"""Small Markdown readers for the generated raw files and outlook.md (headings, tables, bullets)."""
from __future__ import annotations

import re

DASH = "—"
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
SEPARATOR = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")  # same as tools/collect/market/validate.SEPARATOR


def section(text: str, number: str, level: int = 2) -> str:
    """Body under the heading '## {number}...' (e.g. '1.' or '3.2') up to the next heading of
    the same or a higher level. Empty string if missing."""
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            depth, title = len(m.group(1)), m.group(2).strip()
            if inside and depth <= level:
                break
            if not inside and depth == level and title.startswith(number):
                inside = True
                continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def section_by_title(text: str, keyword: str, level: int = 2) -> tuple[str, str] | None:
    """(heading, body) of the first heading at `level` that contains keyword."""
    for m in re.finditer(rf"^{'#' * level}\s+(.*)$", text, re.M):
        title = m.group(1).strip()
        if keyword in title:
            return title, section(text, title, level)
    return None


def split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def tables(text: str) -> list[list[list[str]]]:
    """Every Markdown table in text as a list of rows (header first, separator dropped)."""
    found: list[list[list[str]]] = []
    current: list[list[str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            if not SEPARATOR.match(stripped):
                current.append(split_row(stripped))
        elif current:
            found.append(current)
            current = []
    if current:
        found.append(current)
    return found


def table_dicts(text: str) -> list[dict[str, str]]:
    """Rows of the first table in text keyed by its header cells."""
    found = tables(text)
    if not found:
        return []
    header, *rows = found[0]
    return [dict(zip(header, row + [""] * (len(header) - len(row)))) for row in rows]


def bullets(text: str) -> list[str]:
    """Top-level '- ' / '* ' / '1. ' items; indented continuation lines are joined to the item."""
    items: list[str] = []
    for line in text.splitlines():
        m = re.match(r"^(?:[-*]|\d+\.)\s+(.*)$", line)
        if m:
            items.append(m.group(1).strip())
        elif items and line.startswith("  ") and line.strip():
            items[-1] += " " + line.strip()
    return items


def is_blank(value: str | None) -> bool:
    return not value or value.strip() in ("", DASH, "-")
