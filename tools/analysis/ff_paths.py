"""Company directories, analysis files and validity of the five-forces result.

A result lives in companies/{ticker}_{name}/analysis/five-forces/ as
  {date}_brief.md (script), {date}_five-forces.md (skeleton by script, FILL by the LLM,
  scores by build) and {date}_five-forces.json (build). {date} is the analysis day.
The generic parts are in an_common (shared with three-c).
"""
from __future__ import annotations

from pathlib import Path

import an_common as A
from an_common import DATED, FILL, REPO_ROOT, TITLE, company_dirs, dated_files, is_draft, load_result  # noqa: F401

VALID_DAYS = 365
OUTLOOK_MAX_AGE_DAYS = A.OUTLOOK_MAX_AGE_DAYS
ANALYSIS_SUBDIR = ("analysis", "five-forces")
MD_SUFFIX, JSON_SUFFIX, BRIEF_SUFFIX = "_five-forces.md", "_five-forces.json", "_brief.md"


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


def latest_outlook(root: Path, today: str) -> dict:
    return A.latest_outlook(root, today)
