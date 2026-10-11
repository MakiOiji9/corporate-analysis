"""Mechanical checks that a raw file still follows its template.

- structure: headings and table header rows equal the template's (template ${vars} match anything)
- fill:      no <!-- FILL:... --> marker is left
- tables:    every row has the header's cell count, no empty cell, at least one data row
- words:     no evaluative / recommendation words outside the '>' instruction lines
"""
from __future__ import annotations

import re
from pathlib import Path

FILL = re.compile(r"<!--\s*FILL:(\w+)")
TEMPLATE_VAR = re.compile(r"\\\$\\\{\w+\\\}")
SEPARATOR = re.compile(r"^\|(\s*:?-{3,}:?\s*\|)+\s*$")
FORBIDDEN_WORDS = ("強気", "弱気", "割安", "割高", "買い推奨", "売り推奨", "買うべき", "売るべき",
                   "投資判断", "買い時", "売り時")


def _lines(text: str) -> list[str]:
    return text.splitlines()


def structure(text: str) -> list[str]:
    """Headings and table header rows, in order."""
    lines = _lines(text)
    out = []
    for i, line in enumerate(lines):
        if line.startswith("#"):
            out.append(line.strip())
        elif line.startswith("|") and i + 1 < len(lines) and SEPARATOR.match(lines[i + 1].strip()):
            out.append(line.strip())
    return out


def _pattern(template_line: str) -> re.Pattern:
    return re.compile(TEMPLATE_VAR.sub(".*", re.escape(template_line)) + r"\Z")


def check_structure(text: str, template_text: str) -> list[str]:
    got, want = structure(text), structure(template_text)
    if len(got) != len(want):
        return [f"見出し・表ヘッダーの数がテンプレートと違う（{len(got)} / テンプレート {len(want)}）"]
    return [f"テンプレートと違う: 「{g}」（期待: 「{w}」）"
            for g, w in zip(got, want) if not _pattern(w).match(g)]


def check_fill(text: str) -> list[str]:
    keys = FILL.findall(text)
    return [f"FILL が残っている: {', '.join(keys)}"] if keys else []


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check_tables(text: str) -> list[str]:
    lines, issues = _lines(text), []
    i = 0
    while i < len(lines):
        if lines[i].startswith("|") and i + 1 < len(lines) and SEPARATOR.match(lines[i + 1].strip()):
            header, width, j = lines[i].strip(), len(_cells(lines[i])), i + 2
            rows = 0
            while j < len(lines) and lines[j].startswith("|"):
                cells = _cells(lines[j])
                if len(cells) != width:
                    issues.append(f"列数が合わない行（{len(cells)}/{width}）: {lines[j][:60]}")
                elif any(c == "" for c in cells):
                    issues.append(f"空欄がある行（— と理由を書く）: {lines[j][:60]}")
                rows += 1
                j += 1
            if rows == 0 and not (j < len(lines) and FILL.search(lines[j])):
                issues.append(f"表に行がない: {header[:60]}")
            i = j
        else:
            i += 1
    return issues


def check_words(text: str) -> list[str]:
    body = "\n".join(line for line in _lines(text) if not line.lstrip().startswith(">"))
    found = sorted({w for w in FORBIDDEN_WORDS if w in body})
    return [f"評価・推奨の語が含まれる: {', '.join(found)}"] if found else []


def validate_text(text: str, template_text: str | None) -> list[str]:
    issues = check_fill(text) + check_tables(text) + check_words(text)
    if template_text is not None:
        issues = check_structure(text, template_text) + issues
    return issues


def validate_file(path: Path, template: Path | None) -> list[str]:
    if not path.exists():
        return ["ファイルが無い"]
    template_text = template.read_text(encoding="utf-8") if template else None
    return validate_text(path.read_text(encoding="utf-8"), template_text)
