"""Shared by the company analyses (five-forces, three-c): company directories, dated result files,
validity and the market outlook reference.

Each analysis lives in companies/{ticker}_{name}/analysis/{kind}/ as {date}_brief.md (script),
{date}_{kind}.md (skeleton by script, FILL by the LLM, judgement cells by build) and {date}_{kind}.json
(build). {date} is the analysis day. The analysis-specific modules (ff_paths, tc_paths) subclass
Company with their analysis_dir and wrap the result helpers with their suffixes.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

REPO_ROOT = Path(__file__).resolve().parents[2]
FILL = re.compile(r"<!--\s*FILL:\w")  # same as tools/collect/market/validate.FILL
DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_(.+)$")
TITLE = re.compile(r"^#\s+(.+?)\s*$", re.M)
OUTLOOK_MAX_AGE_DAYS = 35


@dataclass(frozen=True)
class Company:
    root: Path  # repository root
    path: Path  # companies/{ticker}_{name}

    @property
    def dirname(self) -> str:
        return self.path.name

    @property
    def ticker(self) -> str:
        return self.dirname.split("_", 1)[0]

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()

    def display_name(self) -> str:
        overview = self.path / "overview.md"
        if overview.exists():
            m = TITLE.search(overview.read_text(encoding="utf-8"))
            if m:
                return m.group(1)
        return self.dirname


C = TypeVar("C", bound=Company)


def company_dirs(root: Path) -> list[Path]:
    base = root / "companies"
    if not base.exists():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and "_" in p.name and not p.name.startswith("."))


def resolve_company(root: Path, arg: str, cls: type[C]) -> tuple[C | None, list[str]]:
    """(company, candidates). Accepts '3798', '3798_uls-group', 'companies/3798_uls-group' or part of
    the name. Returns (None, candidates) when nothing or more than one directory matches."""
    key = arg.strip().replace("\\", "/").rstrip("/").split("/")[-1].lower()
    dirs = company_dirs(root)
    for rule in (lambda d: d.name.lower() == key,
                 lambda d: d.name.lower().split("_", 1)[0] == key,
                 lambda d: key in d.name.lower()):
        hits = [d for d in dirs if rule(d)]
        if len(hits) == 1:
            return cls(root, hits[0]), []
        if hits:
            return None, [d.name for d in hits]
    return None, []


def dated_files(directory: Path, suffix: str) -> list[tuple[str, Path]]:
    """(date, path) of {date}{suffix} files, oldest first."""
    if not directory.exists():
        return []
    out = []
    for p in directory.glob(f"*{suffix}"):
        m = DATED.match(p.name)
        if m and p.name == f"{m.group(1)}{suffix}":
            out.append((m.group(1), p))
    return sorted(out)


def is_draft(path: Path) -> bool:
    return bool(FILL.search(path.read_text(encoding="utf-8")))


def load_result(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_result(directory: Path, md_suffix: str, json_suffix: str,
                  before: str | None = None) -> tuple[str, dict] | None:
    """(date, result) of the newest finished analysis (json written by build), optionally before a date."""
    for date, path in reversed(dated_files(directory, json_suffix)):
        if before and date >= before:
            continue
        md = directory / f"{date}{md_suffix}"
        result = load_result(path)
        if result and md.exists() and not is_draft(md):
            return date, result
    return None


def latest_draft(directory: Path, md_suffix: str) -> tuple[str, Path] | None:
    """Newest analysis md that still has FILL markers."""
    for date, path in reversed(dated_files(directory, md_suffix)):
        if is_draft(path):
            return date, path
    return None


def digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


SKELETON_MARK = re.compile(r"<!-- skeleton-sha1: ([0-9a-f]{40}) -->")


def mark_skeleton(brief_text: str, skeleton_text: str) -> str:
    """The brief with the digest of the skeleton written alongside it: the next prepare regenerates an untouched one."""
    return brief_text.rstrip() + f"\n\n<!-- skeleton-sha1: {digest(skeleton_text)} -->\n"


def is_untouched(brief: Path, md: Path) -> bool:
    """True when the md is still exactly the skeleton the last prepare wrote (nobody has written into it)."""
    if not brief.exists() or not md.exists():
        return False
    m = SKELETON_MARK.search(brief.read_text(encoding="utf-8"))
    return bool(m) and m.group(1) == digest(md.read_text(encoding="utf-8"))


UPSTREAM_SKILLS = {"three_c": "three-c", "five_forces": "five-forces"}


def prepare_gate(next_step: str, has_raw: bool, skip_collect: bool) -> str | None:
    """Why prepare must not run yet (check's next is not prepare), or None. A collection that was tried once and
    did not bring everything is passed over with --skip-collect; a missing upstream analysis never is."""
    if next_step == "prepare" or (next_step == "collect" and has_raw and skip_collect):
        return None
    if next_step == "collect":
        return ("材料が足りない（missing_inputs）。collect-company-info で収集してから prepare する"
                "（収集を1回試しても取れなかったときだけ --skip-collect）")
    return f"先に {UPSTREAM_SKILLS.get(next_step, next_step)} を最後まで実行する（check の next が {next_step}）"


def valid_until(date: str, days: int) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=days)).isoformat()


def latest_outlook(root: Path, today: str) -> dict:
    """Newest finished market/report/{week}_outlook.md and how old it is."""
    report = root / "market" / "report"
    done = [(d, p) for d, p in dated_files(report, "_outlook.md") if not is_draft(p)]
    if not done:
        return {"path": None, "week": None, "age_days": None, "stale": True}
    week, path = done[-1]
    age = (dt.date.fromisoformat(today) - dt.date.fromisoformat(week)).days
    return {"path": path.relative_to(root).as_posix(), "week": week, "age_days": age,
            "stale": age > OUTLOOK_MAX_AGE_DAYS}
