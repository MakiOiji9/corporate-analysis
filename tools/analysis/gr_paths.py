"""Analysis files and validity of the growth (成長性) result.

A result lives in companies/{ticker}_{name}/analysis/growth/ as
  {date}_brief.md (script), {date}_growth.md (skeleton and every number by script, FILL by the LLM,
  5. 結論 by build) and {date}_growth.json (build).
"""
from __future__ import annotations

from pathlib import Path

import an_common as A

VALID_DAYS = 120  # a quarter plus the filing lag; redone with each new 決算短信 (freshness.py "quarter")
ANALYSIS_SUBDIR = ("analysis", "growth")
MD_SUFFIX, JSON_SUFFIX, BRIEF_SUFFIX = "_growth.md", "_growth.json", "_brief.md"


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
