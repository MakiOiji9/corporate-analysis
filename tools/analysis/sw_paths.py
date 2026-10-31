"""Analysis files and validity of the SWOT result.

A result lives in companies/{ticker}_{name}/analysis/swot/ as
  {date}_brief.md (script), {date}_swot.md (skeleton by script, FILL by the LLM,
  1 / 1.1 / 3 tables by prepare, 6. 結論 by build) and {date}_swot.json (build).
"""
from __future__ import annotations

from pathlib import Path

import an_common as A

VALID_DAYS = 365  # STEP 1: redone with a new 有報 period / industry data (freshness.py "annual")
ANALYSIS_SUBDIR = ("analysis", "swot")
MD_SUFFIX, JSON_SUFFIX, BRIEF_SUFFIX = "_swot.md", "_swot.json", "_brief.md"


class Company(A.Company):
    @property
    def analysis_dir(self) -> Path:
        return self.path.joinpath(*ANALYSIS_SUBDIR)

    def file(self, date: str, suffix: str) -> Path:
        return self.analysis_dir / f"{date}{suffix}"


def resolve_company(root: Path, arg: str) -> tuple[Company | None, list[str]]:
    return A.resolve_company(root, arg, Company)


def latest_result(company: Company, before: str | None = None) -> tuple[str, dict] | None:
    return A.latest_result(company.analysis_dir, MD_SUFFIX, JSON_SUFFIX, before)


def latest_draft(company: Company) -> tuple[str, Path] | None:
    return A.latest_draft(company.analysis_dir, MD_SUFFIX)


def valid_until(date: str) -> str:
    return A.valid_until(date, VALID_DAYS)
