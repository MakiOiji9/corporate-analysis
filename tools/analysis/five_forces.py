"""five-forces orchestrator: everything except writing the judgement text.

Usage:
  five_forces.py list
  five_forces.py check   --company X
  five_forces.py prepare --company X [--redo]
  five_forces.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their five-forces result (for choosing one).
check:   is the latest result still valid (365 days, no newer yuho / industry / competitors raw)?
         Which required inputs are missing (and which collect-company-info 担当 gets them)?
         How old is the market outlook (header reference only; never blocks)? -> "next" says what to do.
prepare: analysis/five-forces/{date}_brief.md (what the writer reads) and the {date}_five-forces.md
         skeleton (FILL markers). A draft (FILL left) is kept unless --redo; a valid result needs --redo.
build:   check the filled md, write the points / attractiveness into it and {date}_five-forces.json.
stdout is one JSON line so the calling agent spends few tokens. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path[:0] = [str(HERE), str(TOOLS / "report"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import ff_brief as B  # noqa: E402
import ff_doc as D  # noqa: E402
import ff_inputs as I  # noqa: E402
import ff_metrics as X  # noqa: E402
import ff_paths as P  # noqa: E402
import mdparse as M  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = P.REPO_ROOT / ".ai" / "templates" / "five-forces" / "five-forces.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "five-forces" / "five-forces.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


# ---------- state ----------

def evaluate(company: P.Company, today: str) -> dict:
    """result: fresh / expired / triggered / draft / none, with the latest result and draft."""
    latest = P.latest_result(company)
    draft = P.latest_draft(company)
    state: dict = {"latest": None, "draft": company.rel(draft[1]) if draft else None, "newer_raw": []}
    if latest:
        date, result = latest
        state["latest"] = {"date": date, "md": company.rel(company.file(date, P.MD_SUFFIX)),
                           "json": company.rel(company.file(date, P.JSON_SUFFIX)),
                           "attractiveness": result.get("attractiveness"), "total": result.get("total"),
                           "valid_until": result.get("valid_until") or P.valid_until(date)}
        state["newer_raw"] = I.newer_trigger_files(company, date, result.get("inputs") or ())
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="ファイブフォース分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="分析後に新しい raw が収集された: " + ", ".join(state["newer_raw"]))
    elif today > state["latest"]["valid_until"]:
        state.update(result="expired", reason=f"有効期限 {state['latest']['valid_until']} を過ぎた")
    else:
        state.update(result="fresh", reason=f"有効期限 {state['latest']['valid_until']} まで有効（再分析しない）")
    return state


def _has_raw(company: P.Company) -> bool:
    raw = company.path / "raw"
    return raw.exists() and any(raw.rglob("*.md"))


def _resolve(root: Path, arg: str | None) -> tuple[P.Company | None, dict | None]:
    if not arg:
        return None, {"ok": False, "error": "--company を指定する（候補は list で確認）"}
    company, candidates = P.resolve_company(root, arg)
    if company:
        return company, None
    if candidates:
        return None, {"ok": False, "error": f"「{arg}」に複数の企業が当たる", "candidates": candidates}
    return None, {"ok": False, "company_missing": True, "error": f"companies/ に「{arg}」の企業が無い。"
                  "collect-company-info（mode=full）で収集する（ホームページ URL が要る）"}


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in P.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in I.TRIGGER_KINDS + ("business-overview",) for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "five_forces": state["result"],
                     "five_forces_date": (state["latest"] or {}).get("date"),
                     "attractiveness": (state["latest"] or {}).get("attractiveness")})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    found = I.gather(company)
    requests = I.collect_requests(found)
    outlook = P.latest_outlook(root, today)
    if state["result"] == "fresh":
        next_step = "report_existing"
    elif not _has_raw(company) or requests:
        next_step = "collect"
    else:
        next_step = "prepare"  # an old outlook is only noted (header reference), never a reason to collect
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": [f.spec.label for f in found.values() if f.status == "unavailable"],
                 "outlook": outlook, "outlook_stale": outlook["stale"], "next": next_step})


def _values(company: P.Company, date: str, found: dict, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週）" if outlook["path"]
                        else "—（完成済みの outlook.md なし）")}


def cmd_prepare(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    if state["result"] == "fresh" and not args.redo:
        return emit({"ok": False, "error": state["reason"] + "。作り直すのはユーザーが指示したときだけ（--redo）",
                     "latest": state["latest"]})
    if args.redo and company.file(today, P.JSON_SUFFIX).exists():
        return emit({"ok": False, "error": f"{today} の分析は build 済み。同じ日に作り直さず、"
                     f"{company.rel(company.file(today, P.MD_SUFFIX))} を Edit で直して build し直す"})
    draft = P.latest_draft(company)
    kept = state["result"] == "draft" and not args.redo  # an older draft behind a built result is abandoned
    date = draft[0] if kept and draft else today
    found = I.gather(company)
    candidates = X.candidates(company, found)
    previous = P.latest_result(company, before=date)
    outlook = P.latest_outlook(root, today)
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    atomic_write_text(brief_path, B.render_brief(company, date, P.valid_until(date), found, candidates,
                                                 previous, outlook))
    if not kept:
        values = _values(company, date, found, outlook)
        atomic_write_text(md_path, D.render_skeleton(_template(root), values, candidates, previous))
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "fill": len(P.FILL.findall(md_path.read_text(encoding="utf-8"))),
        "candidates": {key: candidates[key]["rating"] for key, _, _ in D.FACTORS},
        "previous": previous[0] if previous else None, "missing_inputs": I.collect_requests(found),
        "unavailable": [f.spec.label for f in found.values() if f.status == "unavailable"],
        "outlook": outlook["path"],
    })


def _target(company: P.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, P.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = P.dated_files(company.analysis_dir, P.MD_SUFFIX)
    return files[-1] if files else None


def _outlook_path(header: str) -> str | None:
    """'market/report/X_outlook.md（3 日前の週）' -> the path; None for '—（…なし）'."""
    path = header.split("（")[0].strip()
    return None if M.is_blank(path) else path


def result_json(company: P.Company, date: str, text: str, parsed: dict, scored: dict) -> dict:
    found = I.gather(company)
    outlook = OUTLOOK_HEADER.search(text)
    previous = P.latest_result(company, before=date)
    keep = ("key", "name", "rating", "points", "seen", "source", "confidence", "triggers", "reason",
            "tie_break", "candidate", "previous")
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "industry": parsed["industry"],
        "industry_source": parsed["industry_source"],
        "factors": [{k: f[k] for k in keep} for f in scored["factors"]],
        "total": scored["total"], "attractiveness": scored["attractiveness"],
        "attractiveness_by_points": scored["attractiveness_by_points"],
        "unknown_count": scored["unknown_count"], "downgraded": scored["downgraded"],
        "swot_threats": scored["swot_threats"], "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "outlook": _outlook_path(outlook.group(1)) if outlook else None,
        "previous": {"date": previous[0], "attractiveness": previous[1].get("attractiveness")} if previous else None,
        "md": company.rel(company.file(date, P.MD_SUFFIX)),
    }


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "five-forces.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    issues = D.validate(text, _template(root))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    # the candidate / previous cells in the md are editable text: recompute them so the rules can't be bypassed
    candidates = X.candidates(company, I.gather(company))
    previous = P.latest_result(company, before=date)
    parsed = D.with_reference(D.parse(text), candidates, previous)
    issues = D.check_factors(parsed)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    scored = D.score(parsed)
    atomic_write_text(md_path, D.apply_scores(text, scored))
    result = result_json(company, date, text, parsed, scored)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "industry": parsed["industry"], "ratings": {f["name"]: f["rating"] for f in scored["factors"]},
        "total": scored["total"], "attractiveness": scored["attractiveness"],
        "unknown_count": scored["unknown_count"], "downgraded": scored["downgraded"],
        "swot_threats": scored["swot_threats"], "valid_until": result["valid_until"],
        "previous": result["previous"],
        "tie_breaks": [f["name"] for f in scored["factors"] if f["tie_break"]],
        "low_confidence": [f["name"] for f in scored["factors"] if f["confidence"] == D.LOW_CONFIDENCE],
        "gaps": [g for g in parsed["gaps"] if not M.is_blank(g) and g != "なし"],
    })


def main(argv: list[str] | None = None, root: Path = P.REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("check", "prepare", "build"):
        p = sub.add_parser(name)
        p.add_argument("--company", help="銘柄コード・企業ディレクトリ名・社名の一部")
        p.add_argument("--date", help="YYYY-MM-DD（check/prepare: 今日の代わり、build: 対象の分析日。省略時は今日／最新）")
        if name == "prepare":
            p.add_argument("--redo", action="store_true", help="有効な結果・作成途中の結果があっても作り直す")
    args = parser.parse_args(argv)
    if getattr(args, "date", None):
        try:
            dt.date.fromisoformat(args.date)
        except ValueError:
            return emit({"ok": False, "error": f"--date は YYYY-MM-DD で指定する: {args.date}"})
    handler = {"list": cmd_list, "check": cmd_check, "prepare": cmd_prepare, "build": cmd_build}[args.cmd]
    return handler(args, root)


if __name__ == "__main__":
    sys.exit(main())
