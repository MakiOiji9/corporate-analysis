"""How far the first collection (collect-company-info mode=full) of a company has come, so a stopped run resumes.

Usage:
  collect_progress.py --company <dir>

An agent is done when every raw file it writes exists (any date) and is not empty; the files follow the
「実行モード」table of .ai/skills/collect-company-info.md. The aggregation is done when status.md has no template
cell left and summaries/business.md has its「主力事業の定義」. next: the first pending agent, then "aggregate",
then "done".
A company directory that does not exist yet is all pending.
stdout is one JSON line.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import REPO_ROOT, utf8_stdout  # noqa: E402

# agent -> the raw files it writes (glob under raw/, one dated file of each is enough)
AGENT_FILES = {
    "collect-ir": ("ir/*_business-overview.md", "ir/*_mid-term-plan.md", "ir/*_ir-materials-index.md",
                   "ir/*_management.md", "news/*_press-releases.md"),
    "collect-filings": ("filings/*.md", "ir/*_financials-historical.md"),
    "collect-market": ("market/*_industry-overview.md",),
    "collect-peers-valuation": ("market/*_competitors.md", "ir/*_valuation-data.md"),
}
AGGREGATE = "aggregate"
DONE = "done"
PLACEHOLDER = "YYYY-MM-DD"  # the status.md template's cells; Phase 0 fills only the「最終更新」line
MAIN_BUSINESS = re.compile(r"^##[^\n]*主力事業[^\n]*\n(.*?)(?=^#|\Z)", re.M | re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def _has(raw: Path, pattern: str) -> bool:
    return any(p.is_file() and p.stat().st_size > 0 for p in raw.glob(pattern))


def aggregated(company: Path) -> bool:
    """The parent's last steps are done: status.md has no template cell left (Phase 8) and summaries/business.md
    has the「主力事業の定義」the analyses read (Phase 7)."""
    status, summary = company / "status.md", company / "summaries" / "business.md"
    if not status.exists() or PLACEHOLDER in status.read_text(encoding="utf-8") or not summary.exists():
        return False
    m = MAIN_BUSINESS.search(summary.read_text(encoding="utf-8"))
    return bool(m and COMMENT.sub("", m.group(1)).strip())


def progress(company: Path) -> dict:
    raw = company / "raw"
    agents = {}
    for agent, patterns in AGENT_FILES.items():
        missing = [p for p in patterns if not _has(raw, p)]
        agents[agent] = {"state": "pending" if missing else "done", "missing": missing}
    pending = [a for a, s in agents.items() if s["state"] == "pending"]
    is_aggregated = aggregated(company)
    nxt = pending[0] if pending else (DONE if is_aggregated else AGGREGATE)
    return {"ok": True, "company": company.name, "exists": company.is_dir(), "agents": agents,
            "pending": pending, "aggregated": is_aggregated, "next": nxt}


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", required=True, help="企業ディレクトリ名（companies/ の下）")
    args = ap.parse_args(argv)
    print(json.dumps(progress(root / "companies" / Path(args.company).name), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
