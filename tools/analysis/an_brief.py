"""Briefs of the same day share their raw sections: a section already in another analysis's brief is written once.

The analyses of one company read many of the same raw sections (有報の事業の内容, 業界の市場規模, 競合の推移…), and
the company report writes them one after another in the same session. dedupe() replaces the body of a '### '
section that is exactly the same as a section of another brief of the same date with a pointer to it, so the
writer reads it once. expand() puts the bodies back, for the build checks that look numbers up in the brief.
Only long sections are shared (a short one costs less to repeat than to look up), and a pointer never points at a
pointer.
"""
from __future__ import annotations

import re
from pathlib import Path

MIN_CHARS = 300
HEADING = re.compile(r"^(#{2,3}) (.+)$", re.M)
MARK = re.compile(r"^<!-- skeleton-sha1: [0-9a-f]{40} -->$", re.M)
POINTER = re.compile(r"^（(\S+_brief\.md) の「### (.+)」と同じ内容のため省略。読んでいなければその節を読む）$", re.M)


def _pointer(rel: str, heading: str) -> str:
    return f"（{rel} の「### {heading}」と同じ内容のため省略。読んでいなければその節を読む）"


def sections(text: str) -> list[tuple[int, int, str, str]]:
    """(start of the body, end of the body, heading, body) of every '### ' section; a body ends at the next
    '## ' or '### ' heading. The skeleton mark is not part of a body."""
    heads = list(HEADING.finditer(text))
    out = []
    for i, h in enumerate(heads):
        if h.group(1) != "###":
            continue
        start = h.end()
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        mark = MARK.search(text, start, end)
        stop = mark.start() if mark else end
        out.append((start, stop, h.group(2).strip(), text[start:stop]))
    return out


def _key(heading: str, body: str) -> tuple[str, str]:
    return heading, body.strip()


def dedupe(text: str, company, kind_dir: Path, date: str) -> str:
    """text with the long sections that another brief of `date` already has replaced by a pointer.
    company: has .rel(path); kind_dir: this analysis's directory (companies/X/analysis/{kind})."""
    index: dict[tuple[str, str], str] = {}
    for other in sorted(kind_dir.parent.glob(f"*/{date}_brief.md")):
        if other.parent == kind_dir:
            continue
        rel = company.rel(other)
        for _, _, heading, body in sections(other.read_text(encoding="utf-8")):
            if not POINTER.search(body):
                index.setdefault(_key(heading, body), rel)
    out, last = [], 0
    for start, end, heading, body in sections(text):
        rel = index.get(_key(heading, body))
        if rel and len(body.strip()) >= MIN_CHARS:
            out += [text[last:start], "\n\n", _pointer(rel, heading), "\n\n"]
            last = end
    return "".join(out) + text[last:] if out else text


def expand(text: str, root: Path) -> str:
    """The pointers replaced by the sections they point at (left as they are when the section is gone)."""
    cache: dict[str, dict[str, str]] = {}

    def body(m: re.Match) -> str:
        rel, heading = m.group(1), m.group(2)
        if rel not in cache:
            path = root / rel
            cache[rel] = ({h: b.strip() for _, _, h, b in sections(path.read_text(encoding="utf-8"))}
                          if path.exists() else {})
        found = cache[rel].get(heading)
        return found if found and not POINTER.search(found) else m.group(0)

    return POINTER.sub(body, text)


def read_brief(path: Path, root: Path) -> str:
    """A brief with its pointers expanded ('' when there is none)."""
    return expand(path.read_text(encoding="utf-8"), root) if path.exists() else ""
