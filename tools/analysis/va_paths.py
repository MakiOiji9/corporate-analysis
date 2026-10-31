"""Analysis files and validity of the valuation (バリュエーション) result.

A result lives in companies/{ticker}_{name}/analysis/valuation/ as
  {date}_brief.md (script), {date}_valuation.md (skeleton and every number by script, FILL by the LLM,
  6. 結論 by build) and {date}_valuation.json (build).
The price moves every day, so a result is valid for 7 days only.
"""
from __future__ import annotations

from pathlib import Path

import an_common as A

VALID_DAYS = 7
ANALYSIS_SUBDIR = ("analysis", "valuation")
MD_SUFFIX, JSON_SUFFIX, BRIEF_SUFFIX = "_valuation.md", "_valuation.json", "_brief.md"


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
