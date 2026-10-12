"""Pick the five-forces inputs out of a company's raw/ files (collect-company-info output).

Each input is one section of one raw kind, found by a heading keyword (the headings come from
.ai/templates/collect-company-info/raw/). Raw files are dated (YYYY-MM-DD_{kind}.md) and an update
run may add a diff-only file, so the newest file whose section has content wins.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import mdparse as M
from ff_paths import DATED, Company

EXCERPT_LIMIT = 3000  # characters per section in the brief
COMMENT = re.compile(r"<!--.*?-->", re.S)
MEANINGLESS = re.compile(r"[\s|—\-:：（）()・]")


@dataclass(frozen=True)
class Spec:
    key: str
    label: str
    kind: str  # raw file suffix: YYYY-MM-DD_..._{kind}.md
    keyword: str  # heading keyword (level 2)
    agent: str  # collect-company-info 担当 that collects it
    required: bool
    unavailable_words: tuple[str, ...] = ()  # words in status.md 未取得項目 meaning "tried, not obtainable"


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
    status: str  # ok / blank / missing / unavailable
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
    """True when the section has no data rows and no text besides dashes and punctuation."""
    text = COMMENT.sub("", body)
    for table in M.tables(text):
        if any(not M.is_blank(c) for row in table[1:] for c in row):
            return False
    prose = [line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("|")]
    return not any(MEANINGLESS.sub("", line.lstrip("-*> #")) for line in prose)


def unavailable_items(company: Company) -> list[str]:
    """項目 column of status.md 未取得項目 (things collect tried and could not get)."""
    status = company.path / "status.md"
    if not status.exists():
        return []
    found = M.section_by_title(status.read_text(encoding="utf-8"), "未取得")
    return [r.get("項目", "") for r in M.table_dicts(found[1])] if found else []


def find(company: Company, spec: Spec, unavailable: list[str]) -> Found:
    blank: Found | None = None
    for _, path in raw_files(company, spec.kind):
        hit = M.section_by_title(path.read_text(encoding="utf-8"), spec.keyword)
        if not hit:
            continue
        heading, body = hit
        if not is_blank_section(body):
            return Found(spec, "ok", path, heading, body)
        blank = blank or Found(spec, "blank", path, heading, body)
    if any(w in item for w in spec.unavailable_words for item in unavailable):
        if blank:
            return Found(spec, "unavailable", blank.path, blank.heading, blank.body)
        return Found(spec, "unavailable")
    return blank or Found(spec, "missing")


def gather(company: Company, specs: tuple[Spec, ...] = SPECS) -> dict[str, Found]:
    unavailable = unavailable_items(company)
    return {spec.key: find(company, spec, unavailable) for spec in specs}


def collect_requests(found: dict[str, Found]) -> list[dict]:
    """Required inputs that are missing or blank, grouped by the collect-company-info 担当."""
    by_agent: dict[str, list[str]] = {}
    for f in found.values():
        if f.spec.required and f.status in ("missing", "blank"):
            by_agent.setdefault(f.spec.agent, []).append(f.spec.label)
    return [{"agent": agent, "items": items} for agent, items in by_agent.items()]


def excerpt(f: Found, company: Company) -> str:
    """Section body for the brief, with its source line; capped at EXCERPT_LIMIT characters."""
    if f.path is None:
        note = "status.md の未取得項目に記載あり" if f.status == "unavailable" else "raw に無い"
        return f"（{f.spec.label}: {note}）"
    body = COMMENT.sub("", f.body).strip()
    body = re.sub(r"^#{1,6}\s+(.+)$", r"**\1**", body, flags=re.M)  # keep the brief's own heading levels
    if len(body) > EXCERPT_LIMIT:
        body = body[:EXCERPT_LIMIT].rstrip() + "\n\n（以下略。上限で切り詰めた）"
    note = {"blank": "（節はあるが中身が空）", "unavailable": "（status.md の未取得項目に記載あり）"}.get(f.status, "")
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


def newer_trigger_files(company: Company, since: str) -> list[str]:
    """Raw files of the trigger kinds collected after the analysis date."""
    return [company.rel(p) for kind in TRIGGER_KINDS for d, p in raw_files(company, kind) if d > since]
