"""company_report.py run: the STEP 2・3 analyses (profitability, growth, safety, cash-flow, valuation) in one go.

Each call goes as far as the scripts can without the writer, then stops:
  - an analysis whose writer's JSON ({date}_fills.json) is there is filled (the JSON is then removed) and built
  - an analysis that is not fresh and whose upstream is ready is prepared (cash-flow waits for profitability,
    growth and safety; valuation for all four, since its final check reads them), and its fields are returned in `write` (brief, fill_spec, rules)
  - valuation whose only gap is the price gets new closes from refresh_valuation.py (no agent)
  - an analysis that needs collecting is returned in `collect` (the writer runs that skill)
STEP 1 (five-forces → three-c → moat → swot) is not run here: while one of them is not usable, `next` is its skill.
The analysis scripts are called in-process through their own main(), so every gate and check of theirs applies.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import an_common as A  # noqa: E402
import an_fill as AF  # noqa: E402
import cr_status as S  # noqa: E402
import refresh_valuation as RV  # noqa: E402
from common import atomic_write_text  # noqa: E402

BATCH = ("profitability", "growth", "safety", "cash-flow", "valuation")
DEPENDS = {"cash-flow": ("profitability", "growth", "safety"),  # its consistency rows read their results
           "valuation": ("profitability", "growth", "safety", "cash-flow")}  # growth, and the final check reads all four
MAX_ROUNDS = 12  # every round builds or refreshes something, or stops


def call(step: S.Step, root: Path, *argv: str) -> dict:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        step.script.main(list(argv), root)
    return json.loads(out.getvalue().strip().splitlines()[-1])


def rules(md: Path) -> list[str]:
    """The writing rules at the top of the md (its '> ' lines): what the skill document would add."""
    return [line[2:].strip() for line in md.read_text(encoding="utf-8").splitlines() if line.startswith("> ")]


def _pour_and_build(step: S.Step, root: Path, company: S.Company, md: Path, date: str,
                    build_keys: tuple[str, ...]) -> dict | None:
    """Pour {date}_fills.json when it is there; build once no writer's field is left. None: the writer is not done."""
    fills = AF.default_fills_path(md)
    if fills.exists():
        poured = AF.run_fill(md, fills, atomic_write_text)
        if not poured["ok"]:
            return {"error": poured.get("issues") or poured.get("error"), "fills_json": company.rel(fills)}
        fills.unlink()  # poured: a later redo of the same day must not pour it again
    if [k for k in AF.fill_keys(md.read_text(encoding="utf-8")) if k not in build_keys]:
        return None
    built = call(step, root, "build", "--company", company.dirname, "--date", date)
    if built.get("ok"):
        return {"built": built}
    return {"error": built.get("issues") or built.get("error"), "md": company.rel(md)}


def _collect(step: S.Step, root: Path, company: S.Company, today: str, checked: dict, refreshed: set[str]) -> dict:
    if checked.get("price_refresh") and step.skill not in refreshed:
        refreshed.add(step.skill)
        result = RV.run(root, company.dirname, today)
        if result["ok"]:
            return {"kind": "refreshed", "skill": step.skill, "result": result}
        return {"kind": "collect", "skill": step.skill, "missing_inputs": checked.get("missing_inputs"),
                "refresh_error": result.get("error"), "fallback": result.get("fallback")}
    return {"kind": "collect", "skill": step.skill, "missing_inputs": checked.get("missing_inputs"),
            "needs_full_collect": checked.get("needs_full_collect", False)}


def advance(step: S.Step, root: Path, company: S.Company, today: str, refreshed: set[str]) -> dict:
    """One analysis one step further: {kind: built / write / collect / refreshed / blocked / error, ...}."""
    checked = call(step, root, "check", "--company", company.dirname, "--date", today)
    if checked.get("next") == "collect":
        return _collect(step, root, company, today, checked, refreshed)
    if checked.get("next") != "prepare":
        return {"kind": "blocked", "skill": step.skill, "next": checked.get("next"), "reason": checked.get("reason")}
    unbuilt = _unbuilt_md(step, company)
    if unbuilt:  # written (in the md or in the JSON) but not built: prepare would start the skeleton over
        done = _pour_and_build(step, root, company, unbuilt[1], unbuilt[0], ())
        if done is not None:
            return _done(step, done)
    prep = call(step, root, "prepare", "--company", company.dirname, "--date", today)
    if not prep.get("ok"):
        return {"kind": "error", "skill": step.skill, "error": prep.get("error"), "next": prep.get("next")}
    md = root / prep["md"]
    build_keys = tuple(prep.get("filled_at_build", []))
    done = _pour_and_build(step, root, company, md, prep["date"], build_keys)
    if done is None:
        left = AF.prepare_fields(company, md, build_keys)
        return {"kind": "write", "skill": step.skill, "md": prep["md"], "brief": prep["brief"], **left,
                "rules": rules(md), "warnings": prep.get("warnings", [])}
    return _done(step, done)


def _done(step: S.Step, done: dict) -> dict:
    if "error" in done:
        return {"kind": "error", "skill": step.skill, **done}
    built = done["built"]
    return {"kind": "built", "skill": step.skill, "verdict": built.get("verdict"), "json": built.get("json")}


def _unbuilt_md(step: S.Step, company: S.Company) -> tuple[str, Path] | None:
    """(date, path) of the newest analysis md that has no json yet."""
    pc = step.paths.Company(company.root, company.path)
    files = A.dated_files(pc.analysis_dir, step.paths.MD_SUFFIX)
    if not files:
        return None
    date, path = files[-1]
    return None if pc.file(date, step.paths.JSON_SUFFIX).exists() else (date, path)


def _pending_step1(status: dict, use_existing: bool) -> str | None:
    for s in status["steps"]:
        if s["skill"] in BATCH:
            return None
        if not S.usable(s, use_existing):
            return s["skill"]
    return None


def run(root: Path, company: S.Company, today: str, use_existing: bool = False) -> dict:
    by_skill = {s.skill: s for s in S.STEPS}
    out: dict[str, list] = {"built": [], "write": [], "collect": [], "errors": [], "refreshed": [], "blocked": []}
    refreshed: set[str] = set()
    for _ in range(MAX_ROUNDS):
        status = S.check(root, company, today, use_existing=use_existing)
        step1 = _pending_step1(status, use_existing)
        if step1:
            return _result(status, out, step1)
        states = {s["skill"]: s for s in status["steps"]}
        handled = {p["skill"] for key in ("write", "collect", "errors", "blocked") for p in out[key]}
        ready = [k for k in BATCH if not S.usable(states[k], use_existing) and k not in handled
                 and all(S.usable(states[d], use_existing) for d in DEPENDS.get(k, ()))]
        progressed = False
        for skill in ready:
            result = advance(by_skill[skill], root, company, today, refreshed)
            kind = result.pop("kind")
            if kind in ("built", "refreshed"):
                out[kind].append(result)
                progressed = True
                break  # the states changed: look again from the top
            out[{"write": "write", "collect": "collect", "blocked": "blocked"}.get(kind, "errors")].append(result)
        if not progressed:
            return _result(S.check(root, company, today, use_existing=use_existing), out, None)
    out["errors"].append({"error": f"{MAX_ROUNDS} 回進めても終わらない"})
    return _result(S.check(root, company, today, use_existing=use_existing), out, None)


def _result(status: dict, out: dict, step1: str | None) -> dict:
    if step1:
        nxt = step1
    elif out["errors"]:
        nxt = "fix"
    elif out["write"]:
        nxt = "write"
    elif out["collect"]:
        nxt = "collect"
    else:
        nxt = status["next"]
    return {"ok": not out["errors"], "next": nxt, "built": out["built"], "write": out["write"],
            "collect": out["collect"], "errors": out["errors"], "blocked": out["blocked"], "price_refreshed": out["refreshed"],
            "steps": [{k: s[k] for k in ("skill", "result", "date", "verdict")} for s in status["steps"]]}
