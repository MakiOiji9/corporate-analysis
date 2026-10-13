"""Pick the five-forces inputs out of a company's raw/ files (collect-company-info output).

Each input is one section of one raw kind, found by a heading keyword (the headings come from
.ai/templates/collect-company-info/raw/). Raw files are dated (YYYY-MM-DD_{kind}.md) and an update
run may add a diff-only file, so the newest file whose section has content wins. A diff file's
out-of-scope section that only says it is carried over (前回ファイルから変更なし・今回の範囲外) counts as blank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import an_common as A
import mdparse as M
from ff_paths import DATED, Company

EXCERPT_LIMIT = 3000  # characters per section in the brief
HEADER_NOTE_LIMIT = 600  # characters of a raw file's 情報源・注意 header shown in the brief
COMMENT = re.compile(r"<!--.*?-->", re.S)
MEANINGLESS = re.compile(r"[\s|—\-:：（）()・]")
THIN_WORDS = ("見つからなかった", "見つからない", "見つけられなかった", "確認できず", "確認できなかった", "未取得")
CARRIED_OVER_WORDS = ("前回ファイルから変更なし", "今回の範囲外")  # a diff file's note for a section it did not collect


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    kind: str  # raw file suffix: YYYY-MM-DD_..._{kind}.md
    keyword: str  # heading keyword (level 2)
    agent: str  # collect-company-info 担当 that collects it
    required: bool
    unavailable_words: tuple[str, ...] = ()  # words in status.md 未取得項目 meaning "tried, not obtainable"
    thin_check: bool = False  # a section saying "not found" or with an empty company row is not enough


SPECS = (
    Spec("segment", "有報: 事業の内容・セグメント情報", "yuho", "事業の内容", "collect-filings", True),
    Spec("customers", "有報: 主要な販売先", "yuho", "主要な販売先", "collect-filings", True),
    Spec("procurement", "有報: 主要な原材料・調達先", "yuho", "原材料", "collect-filings", True),
    Spec("ip", "有報: 研究開発・特許・許認可", "yuho", "許認可", "collect-filings", False),
    Spec("risks", "有報: 事業等のリスク", "yuho", "事業等のリスク", "collect-filings", False),
    Spec("customer_base", "事業概要: 顧客層", "business-overview", "顧客層", "collect-ir", False),
    Spec("market_size", "業界: 市場規模と成長率", "industry-overview", "市場規模", "collect-market", True),
    Spec("share", "業界: 上位企業とシェア", "industry-overview", "シェア", "collect-market", True, ("シェア",)),
    Spec("entry", "業界: 参入条件・新規参入", "industry-overview", "参入", "collect-market", True),
    Spec("substitutes", "業界: 代替手段", "industry-overview", "代替", "collect-market", True),
    Spec("kbf", "業界: 購買決定要因", "industry-overview", "購買決定要因", "collect-market", False,
         ("購買決定要因",)),
    Spec("supply", "業界: 調達構造・価格高騰", "industry-overview", "調達", "collect-market", True),
    Spec("industry_margin", "業界: 業界全体の利益率", "industry-overview", "利益率", "collect-market", False,
         ("利益率",)),
    Spec("structural", "業界: 構造を変えうる要因", "industry-overview", "構造を変え", "collect-market", False),
    Spec("peers", "競合: 売上高・営業利益の推移", "competitors", "売上高・営業利益", "collect-peers-valuation",
         True),
    Spec("peer_share", "競合: 市場シェア", "competitors", "市場シェア", "collect-peers-valuation", False,
         ("シェア",)),
)
SPEC = {s.key: s for s in SPECS}
TRIGGER_KINDS = ("yuho", "industry-overview", "competitors")  # a newer file re-opens a valid result


@dataclass(frozen=True)
class Found:
    spec: Spec
    status: str  # ok / thin / blank / missing / unavailable
    path: Path | None = None
    heading: str = ""
    body: str = ""


def raw_files(company: Company, kind: str) -> list[tuple[str, Path]]:
    """(date, path) of raw/**/YYYY-MM-DD_*{kind}.md, newest first."""
    raw = company.path / "raw"
    if not raw.exists():
        return []
    out = []
    for p in raw.rglob(f"*_{kind}.md"):
        m = DATED.match(p.name)
        if m:
            out.append((m.group(1), p))
    return sorted(out, reverse=True)


def is_blank_section(body: str) -> bool:
    """True when the section has no data rows and no text besides dashes, punctuation and carried-over notes."""
    text = COMMENT.sub("", body)
    for table in M.tables(text):
        if any(not M.is_blank(c) for row in table[1:] for c in row):
            return False
    prose = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("|")
             and not any(w in line for w in CARRIED_OVER_WORDS)]
    return not any(MEANINGLESS.sub("", line.lstrip("-*> #")) for line in prose)


def _empty_cell(cell: str) -> bool:
    """'' / '—' / '—（公表値なし）': a dash with at most a note in brackets."""
    return M.is_blank(cell) or cell.strip().startswith("—")


def is_thin_section(body: str) -> bool:
    """Tables: thin when a row has nothing but its first cell (a company with no data); caveats in cells are fine.
    Prose only: thin when it says the data was not found."""
    text = COMMENT.sub("", body)
    rows = [row for table in M.tables(text) for row in table[1:]]
    if rows:
        return any(len(row) > 1 and all(_empty_cell(c) for c in row[1:]) for row in rows)
    return any(w in text for w in THIN_WORDS)


def unavailable_items(company: Company) -> list[str]:
    """項目 column of status.md 未取得項目 (things collect tried and could not get)."""
    status = company.path / "status.md"
    if not status.exists():
        return []
    found = M.section_by_title(status.read_text(encoding="utf-8"), "未取得")
    return [r.get("項目", "") for r in M.table_dicts(found[1])] if found else []


def find(company: Company, spec: Spec, unavailable: list[str]) -> Found:
    """Newest section with content wins; a thin one (thin_check specs) only when nothing better exists."""
    weak: Found | None = None  # the newest thin section, else the newest blank one
    for _, path in raw_files(company, spec.kind):
        hit = M.section_by_title(path.read_text(encoding="utf-8"), spec.keyword)
        if not hit:
            continue
        heading, body = hit
        if is_blank_section(body):
            weak = weak or Found(spec, "blank", path, heading, body)
        elif spec.thin_check and is_thin_section(body):
            if weak is None or weak.status == "blank":
                weak = Found(spec, "thin", path, heading, body)
        else:
            return Found(spec, "ok", path, heading, body)
    if any(w in item for w in spec.unavailable_words for item in unavailable):
        if weak:
            return Found(spec, "unavailable", weak.path, weak.heading, weak.body)
        return Found(spec, "unavailable")
    return weak or Found(spec, "missing")


def gather(company: Company, specs: tuple[Spec, ...] = SPECS) -> dict[str, Found]:
    unavailable = unavailable_items(company)
    return {spec.key: find(company, spec, unavailable) for spec in specs}


def collect_requests(found: dict[str, Found]) -> list[dict]:
    """Required inputs that are missing, blank or thin, grouped by the collect-company-info 担当."""
    by_agent: dict[str, list[str]] = {}
    for f in found.values():
        if f.spec.required and f.status in ("missing", "blank", "thin"):
            by_agent.setdefault(f.spec.agent, []).append(f.spec.label)
    return [{"agent": agent, "items": items} for agent, items in by_agent.items()]


def header_notes(path: Path) -> str:
    """情報源・注意 lines above a raw file's first section (title and 収集日 dropped), capped."""
    lines = []
    for line in COMMENT.sub("", path.read_text(encoding="utf-8")).splitlines():
        if line.startswith("## ") or line.strip() == "---":
            break
        if line.startswith("# ") or line.startswith("**収集日**") or not line.strip() or line.strip() == ">":
            continue
        lines.append(line.strip())
    text = " ".join(lines)
    return text if len(text) <= HEADER_NOTE_LIMIT else text[:HEADER_NOTE_LIMIT].rstrip() + "…（以下略）"


def excerpt(f: Found, company: Company) -> str:
    """Section body for the brief, with its source line; capped at EXCERPT_LIMIT characters."""
    if f.path is None:
        note = "status.md の未取得項目に記載あり" if f.status == "unavailable" else "raw に無い"
        return f"（{f.spec.label}: {note}）"
    body = COMMENT.sub("", f.body).strip()
    body = re.sub(r"^#{1,6}\s+(.+)$", r"**\1**", body, flags=re.M)  # keep the brief's own heading levels
    if len(body) > EXCERPT_LIMIT:
        body = body[:EXCERPT_LIMIT].rstrip() + "\n\n（以下略。上限で切り詰めた）"
    note = {"blank": "（節はあるが中身が空）", "thin": "（中身が薄い: 見つからなかった旨の記載、または空の行がある）",
            "unavailable": "（status.md の未取得項目に記載あり）"}.get(f.status, "")
    return f"出典: {company.rel(f.path)} 「{f.heading}」{note}\n\n{body}"


def main_business(company: Company) -> str:
    """主力事業 in overview.md 基本情報 (written by collect-company-info)."""
    overview = company.path / "overview.md"
    if not overview.exists():
        return ""
    found = M.section_by_title(overview.read_text(encoding="utf-8"), "基本情報")
    rows = M.table_dicts(found[1]) if found else []
    return next((r.get("内容", "") for r in rows if r.get("項目") == "主力事業"), "")


def summary_main_business(company: Company) -> str:
    path = company.path / "summaries" / "business.md"
    if not path.exists():
        return ""
    found = M.section_by_title(path.read_text(encoding="utf-8"), "主力事業")
    return found[1].strip() if found else ""


def _section_digest(f: Found) -> str:
    """Only usable content counts: a blank, thin or unobtainable section reads as nothing, so wording changes in
    such a section (or a heading added with an empty body) re-open nothing."""
    return A.digest(COMMENT.sub("", f.body).strip()) if f.status == "ok" else ""


def input_digests(found: dict[str, Found]) -> dict[str, str]:
    """Digest of each input section the analysis read (recorded at build)."""
    return {key: _section_digest(f) for key, f in found.items()}


def changed_input_files(company: Company, found: dict[str, Found], recorded: dict[str, str]) -> list[str]:
    """Raw files whose section now differs from what the analysis read: a newer file that only adds sections
    the analysis does not use, or repeats the same values, re-opens nothing."""
    paths = {company.rel(f.path) if f.path is not None else f"（{f.spec.label}）"
             for key, f in found.items() if _section_digest(f) != recorded.get(key, "")}
    return sorted(paths)


def raw_seen(company: Company, kinds: tuple[str, ...] = TRIGGER_KINDS) -> list[str]:
    """Raw files of the trigger kinds that exist now (recorded at build, so a same-day file is not taken as newer)."""
    return sorted(company.rel(p) for kind in kinds for _, p in raw_files(company, kind))


def newer_trigger_files(company: Company, since: str, used: tuple[str, ...] | list[str] = (),
                        kinds: tuple[str, ...] = TRIGGER_KINDS,
                        seen: tuple[str, ...] | list[str] = ()) -> list[str]:
    """Raw files of the trigger kinds collected after the analysis date, or on that date but neither among the
    inputs the analysis used nor present at its build (collected later the same day). Without a list of used
    inputs only the date counts."""
    return [company.rel(p) for kind in kinds for d, p in raw_files(company, kind)
            if d > since or (d == since and used and company.rel(p) not in used and company.rel(p) not in seen)]
