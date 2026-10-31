"""Where the company report stands: the nine analyses in dependency order, the market outlook and the report.

The order five-forces → three-c → moat → swot → profitability → growth → safety → cash-flow → valuation is the
only one in which a finished analysis never makes a downstream one 'triggered' again, so the command always runs
the first analysis that is not fresh and checks again. Freshness is each analysis script's own evaluate();
nothing is re-judged here.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

TOOLS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import an_common as A  # noqa: E402
import cash_flow  # noqa: E402
import cf_paths  # noqa: E402
import ff_paths  # noqa: E402
import five_forces  # noqa: E402
import gr_paths  # noqa: E402
import growth  # noqa: E402
import moat  # noqa: E402
import mt_paths  # noqa: E402
import pf_paths  # noqa: E402
import profitability  # noqa: E402
import safety  # noqa: E402
import sf_paths  # noqa: E402
import sw_paths  # noqa: E402
import swot  # noqa: E402
import tc_paths  # noqa: E402
import three_c  # noqa: E402
import va_paths  # noqa: E402
import valuation  # noqa: E402

MD_SUFFIX, JSON_SUFFIX = "_company-report.md", "_company-report.json"
BRIEF_SUFFIX, FACTS_SUFFIX, HTML_SUFFIX = "_company-report_brief.md", "_company-report_facts.json", "_company-report.html"


@dataclass(frozen=True)
class Step:
    key: str        # result key in facts.json
    skill: str      # skill to run when not fresh
    label: str
    number: str     # 企業分析フレームワーク.md
    script: ModuleType
    paths: ModuleType
    verdict_key: str = "verdict"


STEPS = (
    Step("five_forces", "five-forces", "ファイブフォース", "1-1", five_forces, ff_paths, "attractiveness"),
    Step("three_c", "three-c", "3C", "1-2", three_c, tc_paths),
    Step("moat", "moat", "モート", "1-3", moat, mt_paths),
    Step("swot", "swot", "SWOT", "1-4", swot, sw_paths),
    Step("profitability", "profitability", "収益性", "2-1", profitability, pf_paths),
    Step("growth", "growth", "成長性", "2-2", growth, gr_paths),
    Step("safety", "safety", "安全性", "2-3", safety, sf_paths),
    Step("cash_flow", "cash-flow", "キャッシュフロー", "2-4", cash_flow, cf_paths),
    Step("valuation", "valuation", "バリュエーション", "3", valuation, va_paths),
)


class Company(A.Company):
    @property
    def reports_dir(self) -> Path:
        return self.path / "reports"

    def file(self, date: str, suffix: str) -> Path:
        return self.reports_dir / f"{date}{suffix}"


def resolve_company(root: Path, arg: str) -> tuple[Company | None, list[str]]:
    return A.resolve_company(root, arg, Company)


def latest(step: Step, company: Company) -> tuple[str, dict] | None:
    return step.paths.latest_result(step.paths.Company(company.root, company.path))


def step_state(step: Step, company: Company, today: str) -> dict:
    state = step.script.evaluate(step.paths.Company(company.root, company.path), today)
    found = latest(step, company)
    return {"key": step.key, "skill": step.skill, "label": step.label, "step": step.number,
            "result": state["result"], "reason": state.get("reason", ""),
            "date": found[0] if found else None,
            "verdict": found[1].get(step.verdict_key) if found else None}


def report_state(company: Company) -> dict:
    """The newest report md and whether it is built (json) or still a draft (FILL left)."""
    files = A.dated_files(company.reports_dir, MD_SUFFIX)
    if not files:
        return {"date": None, "state": "none", "md": None}
    date, path = files[-1]
    if A.is_draft(path):
        state = "draft"
    elif company.file(date, JSON_SUFFIX).exists() and company.file(date, HTML_SUFFIX).exists():
        state = "built"
    else:
        state = "filled"  # every FILL written, build not run (or it failed)
    return {"date": date, "state": state, "md": company.rel(path)}


def next_step(steps: list[dict], outlook: dict, report: dict, today: str, redo: bool) -> str:
    """The first analysis that is not fresh, then the outlook, then the report itself."""
    pending = next((s for s in steps if s["result"] != "fresh"), None)
    if pending:
        return pending["skill"]
    if outlook.get("stale"):
        return "market-report"
    if report["date"] == today:
        if report["state"] == "built" and not redo:
            return "report_existing"
        if report["state"] in ("draft", "filled"):
            return "write" if report["state"] == "draft" else "build"
    return "prepare"


def check(root: Path, company: Company, today: str, redo: bool = False) -> dict:
    steps = [step_state(step, company, today) for step in STEPS]
    outlook = A.latest_outlook(root, today)
    report = report_state(company)
    return {"steps": steps, "outlook": outlook, "report": report,
            "next": next_step(steps, outlook, report, today, redo)}
