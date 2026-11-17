"""YAML front matter of a raw md: which documents it was written from, and which pages each section rests on.

    ---
    provenance: 1
    collected: 2026-11-01
    sources:
      - id: S100Y69H              # manifest.csv の doc_id; otherwise w1, w2 … (web only) or d1 … (data/ tables)
        title: 有価証券報告書 第110期
        url: https://...
        published: 2026-05-25
        period: 2026-02
        confidence: 一次          # 一次 / 二次 / 検索要約
    sections:                     # '## N.' section number -> the documents and pages it rests on
      "6": [{source: S100Y69H, pages: "42-43"}]
      "8": [{source: w1, pages: null}]
    ---

The body after the block is left as it was, so every reader that looks for '## ' sections and '|' tables keeps
working. Lines of the block must not start with '|' (mdparse.tables would read them as a table row), so block
scalars are refused.
"""
from __future__ import annotations

import datetime as dt
import re

import yaml

VERSION = 1
FENCE = "---"
CONFIDENCE = ("一次", "二次", "検索要約")
SOURCE_KEYS = ("id", "title", "url", "published", "period", "confidence")
LOCAL_ID = re.compile(r"^[wd]\d+$")  # w1: a web page with no saved original; d1: a table a script built from data/


MARKER = re.compile(r"^provenance\s*:", re.M)  # a leading '---' block without it is body (a rule, a table)


class FrontMatterError(ValueError):
    pass


class _StringLoader(yaml.SafeLoader):
    """Scalars stay the strings that were written: 0012345, 6.10 and 1:30 are IDs, sections and pages, not
    numbers (YAML 1.1 would read them as octal, float and sexagesimal). null and true/false are kept."""


_StringLoader.yaml_implicit_resolvers = {
    first: [(tag, regexp) for tag, regexp in resolvers if tag.rsplit(":", 1)[-1] not in ("int", "float", "timestamp")]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()}


def split(text: str) -> tuple[str | None, str]:
    """(the YAML between the fences or None, the body). A file with no opening fence, or whose leading block has
    no 'provenance:' line, is all body."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != FENCE:
        return None, text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == FENCE:
            block = "".join(lines[1:i])
            return (block, "".join(lines[i + 1:])) if MARKER.search(block) else (None, text)
    if MARKER.search(text):
        raise FrontMatterError("front matter の閉じの --- が無い")
    return None, text


def _text(value: object) -> str | None:
    """YAML reads 2026-05-25 as a date; keep every value as the string that was written."""
    if value is None:
        return None
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return str(value)


def _source(item: object, n: int) -> dict:
    if not isinstance(item, dict) or not item.get("id"):
        raise FrontMatterError(f"sources[{n}]: id のある対応表（id・title・url・published・period・confidence）にする")
    unknown = set(item) - set(SOURCE_KEYS)
    if unknown:
        raise FrontMatterError(f"sources[{n}]: 知らないキー {sorted(unknown)}")
    source = {key: _text(item.get(key)) for key in SOURCE_KEYS}
    if source["confidence"] not in CONFIDENCE:
        raise FrontMatterError(f"sources[{n}] {source['id']}: confidence は {'/'.join(CONFIDENCE)} の1語")
    return source


def _citations(number: str, items: object, ids: set[str]) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise FrontMatterError(f"sections.{number}: [{{source: ID, pages: \"..\"}}] の一覧にする")
    cited = []
    for item in items:
        if not isinstance(item, dict) or set(item) - {"source", "pages"}:
            raise FrontMatterError(f"sections.{number}: 各項目は source と pages だけ")
        source = _text(item.get("source"))
        if source not in ids:
            raise FrontMatterError(f"sections.{number}: source「{source}」が sources に無い")
        cited.append({"source": source, "pages": _text(item.get("pages"))})
    return cited


def validate(meta: object) -> dict:
    """The checked, normalised front matter (every value a string or None)."""
    if not isinstance(meta, dict):
        raise FrontMatterError("front matter が対応表になっていない")
    if str(meta.get("provenance")) != str(VERSION):
        raise FrontMatterError(f"provenance: {VERSION} が無い（形式の版）")
    raw_sources = meta.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise FrontMatterError("sources が空")
    sources = [_source(item, n) for n, item in enumerate(raw_sources)]
    ids = [s["id"] for s in sources]
    if len(set(ids)) != len(ids):
        raise FrontMatterError("sources の id が重複している")
    sections = meta.get("sections") or {}
    if not isinstance(sections, dict):
        raise FrontMatterError("sections は節番号をキーにした対応表にする")
    return {"provenance": VERSION, "collected": _text(meta.get("collected")), "sources": sources,
            "sections": {str(k): _citations(str(k), v, set(ids)) for k, v in sections.items()}}


def parse(text: str) -> tuple[dict | None, str]:
    """(validated front matter or None when the file has none, the body)."""
    block, body = split(text)
    if block is None:
        return None, body
    if any(line.lstrip().startswith("|") for line in block.splitlines()):
        raise FrontMatterError("front matter に | で始まる行がある（ブロックスカラーは使わない）")
    try:
        meta = yaml.load(block, Loader=_StringLoader)  # noqa: S506 (a SafeLoader with fewer resolvers)
    except yaml.YAMLError as e:
        raise FrontMatterError(f"YAML として読めない: {e}") from e
    return validate(meta), body


def body_of(text: str) -> str:
    """The text without its front matter (a malformed block is left in place: the readers see what is there)."""
    try:
        return split(text)[1]
    except FrontMatterError:
        return text


def render(meta: dict) -> str:
    """The front matter block for a validated dict, ending with a newline."""
    checked = validate(meta)
    doc: dict = {"provenance": VERSION}
    if checked["collected"]:
        doc["collected"] = checked["collected"]
    doc["sources"] = [{k: v for k, v in s.items() if v is not None} for s in checked["sources"]]
    if checked["sections"]:
        doc["sections"] = checked["sections"]
    dumped = yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, default_flow_style=None, width=1000)
    return f"{FENCE}\n{dumped}{FENCE}\n"


def with_front_matter(text: str, meta: dict) -> str:
    """text with its front matter replaced by (or prefixed with) meta; the body is kept byte for byte."""
    return render(meta) + split(text)[1]


def source_line(meta: dict) -> str:
    """One short line for the brief: '資料 ID: S100Y69H 有価証券報告書 第110期 2026-05-25 一次／…'."""
    parts = [" ".join(p for p in (s["id"], s["title"], s["published"] or s["period"], s["confidence"]) if p)
             for s in meta["sources"]]
    return "資料 ID: " + "／".join(parts)
