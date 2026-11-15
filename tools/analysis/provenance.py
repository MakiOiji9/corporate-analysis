"""Evidence chain of an analysis claim: the 情報源 cell -> raw file and section -> front matter -> manifest.csv ->
the saved original and its pages (BL-01).

A 情報源 cell names raw files the way the briefs show them:
    2026-11-01_2026-02_yuho.md「6. 研究開発・特許・許認可（p.42-43）」、2026-11-01_competitors.md「7.」、md 3.1
Each raw file with the sections after it becomes one Ref; 'md 3.1' (the analysis' own computed chapter) is not a
document and is skipped. resolve() returns one Evidence per cited document with a status:
    検証済み            the raw section names a document saved in sources/ (manifest.csv, file present) and its pages
    未検証              with the reason: Front Matter なし / Front Matter の形式の誤り / 節の出典なし / 原本なし /
                        ページなし / 検索要約
    参照先なし          the raw file does not exist (a typo in the cell); build lists it as a warning
Unverified claims are recorded, not refused: this is the trial on one analysis (moat) before it is widened.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

import front_matter as FM
from common import read_manifest

VERIFIED = "検証済み"
UNVERIFIED = "未検証"
MISSING = "参照先なし"
NO_FRONT_MATTER = "Front Matter なし"
BAD_FRONT_MATTER = "Front Matter の形式の誤り"
NO_SECTION = "節の出典なし"
NO_ORIGINAL = "原本なし"
NO_PAGES = "ページなし"
SEARCH_ONLY = "検索要約"
RAW_REF = re.compile(r"(\d{4}-\d{2}-\d{2}_[^\s「」、，,／/]+?\.md)((?:\s*「[^」]*」)*)")
SECTION_REF = re.compile(r"「([^」]*)」")
SECTION_NUMBER = re.compile(r"^\s*([0-9０-９]+)[.．]")  # full-width digits are read as the same section
ORIGINAL_SUFFIXES = (".pdf", ".html", ".htm", ".xlsx", ".txt")  # what a reader opens, before the XBRL zip


@dataclass(frozen=True)
class Ref:
    raw: str  # file name as written in the cell
    sections: tuple[str, ...]  # section numbers ('6'); a heading without a number is kept as written


@dataclass(frozen=True)
class Evidence:
    raw: str
    section: str | None
    status: str
    reason: str | None = None
    doc_id: str | None = None
    title: str | None = None
    url: str | None = None
    published: str | None = None
    period: str | None = None
    confidence: str | None = None
    pages: str | None = None
    local_path: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def split_refs(cell: str | None) -> list[Ref]:
    refs = []
    for m in RAW_REF.finditer(cell or ""):
        sections = []
        for title in SECTION_REF.findall(m.group(2)):
            number = SECTION_NUMBER.match(title)
            sections.append(str(int(number.group(1))) if number else title.strip())  # int() reads '７' as 7
        refs.append(Ref(m.group(1), tuple(sections)))
    return refs


class Resolver:
    """Resolves cells of one company; raw files and the manifest are read once."""

    def __init__(self, company_dir: Path):
        self.company_dir = company_dir
        self.raw_dir = company_dir / "raw"
        self.manifest = read_manifest(company_dir)
        self._meta: dict[str, tuple[dict | None, str | None]] = {}

    def _raw_path(self, name: str) -> Path | None:
        """The raw file with exactly this name (the cell's text is not used as a glob pattern)."""
        if not self.raw_dir.is_dir():
            return None
        return next((p for p in sorted(self.raw_dir.rglob("*.md")) if p.name == name), None)

    def _front_matter(self, path: Path) -> tuple[dict | None, str | None]:
        """(front matter, error); (None, None) when the file has none."""
        if path.name not in self._meta:
            try:
                self._meta[path.name] = FM.parse(path.read_text(encoding="utf-8"))[0], None
            except FM.FrontMatterError as e:
                self._meta[path.name] = None, str(e)
        return self._meta[path.name]

    def _original(self, doc_id: str) -> dict | None:
        rows = [r for r in self.manifest if r.get("doc_id") == doc_id]
        rows.sort(key=lambda r: not (r.get("local_path") or "").lower().endswith(ORIGINAL_SUFFIXES))
        return rows[0] if rows else None

    def _evidence(self, raw: str, section: str | None, source: dict, pages: str | None) -> Evidence:
        row = self._original(source["id"])
        present = bool(row and row.get("local_path") and (self.company_dir / row["local_path"]).is_file())
        if source["confidence"] == SEARCH_ONLY:
            status, reason = UNVERIFIED, SEARCH_ONLY
        elif not present:
            status, reason = UNVERIFIED, NO_ORIGINAL
        elif not pages:
            status, reason = UNVERIFIED, NO_PAGES
        else:
            status, reason = VERIFIED, None
        row = row or {}
        return Evidence(raw, section, status, reason, doc_id=source["id"], title=source["title"] or row.get("note"),
                        url=row.get("url") or source["url"],
                        published=row.get("published_date") or source["published"],
                        period=row.get("period") or source["period"], confidence=source["confidence"],
                        pages=pages, local_path=row.get("local_path") if present else None)

    def _section(self, raw: str, section: str | None, meta: dict) -> list[Evidence]:
        sources = {s["id"]: s for s in meta["sources"]}
        if section is None:
            if len(sources) != 1:
                return [Evidence(raw, None, UNVERIFIED, NO_SECTION)]
            return [self._evidence(raw, None, meta["sources"][0], None)]
        cited = meta["sections"].get(section)
        if not cited:
            return [Evidence(raw, section, UNVERIFIED, NO_SECTION)]
        return [self._evidence(raw, section, sources[c["source"]], c["pages"]) for c in cited]

    def resolve_ref(self, ref: Ref) -> list[Evidence]:
        sections: list[str | None] = list(ref.sections) or [None]
        path = self._raw_path(ref.raw)
        if path is None:
            return [Evidence(ref.raw, s, MISSING) for s in sections]
        meta, error = self._front_matter(path)
        if meta is None:
            reason = BAD_FRONT_MATTER if error else NO_FRONT_MATTER
            return [Evidence(ref.raw, s, UNVERIFIED, reason) for s in sections]
        return [e for s in sections for e in self._section(ref.raw, s, meta)]

    def resolve(self, cell: str | None) -> list[Evidence]:
        return [e for ref in split_refs(cell) for e in self.resolve_ref(ref)]


def summary(evidence: list[Evidence]) -> dict:
    """Counts for the md and the json: {'verified': n, 'unverified': n, 'missing': n, 'reasons': {reason: n}}."""
    reasons: dict[str, int] = {}
    for e in evidence:
        if e.status == UNVERIFIED:
            reasons[e.reason or ""] = reasons.get(e.reason or "", 0) + 1
    return {"verified": sum(e.status == VERIFIED for e in evidence),
            "unverified": sum(e.status == UNVERIFIED for e in evidence),
            "missing": sum(e.status == MISSING for e in evidence), "reasons": reasons}


def label(e: Evidence) -> str:
    """'検証済み' / '未検証（ページなし）' / '参照先なし'."""
    return f"{e.status}（{e.reason}）" if e.reason else e.status
