"""moat orchestrator: everything except writing the judgement text.

Usage:
  moat.py list
  moat.py check   --company X
  moat.py prepare --company X [--redo]
  moat.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their moat and 3C results (for choosing one).
check:   is the latest moat result still valid (180 days, no newer yuho / financials-historical /
         business-overview / industry / competitors raw, no newer 3C result)? Is the 3C result usable (STEP 1-2
         comes first; its verdict does not stop the analysis)? Which required inputs are missing? -> "next".
prepare: analysis/moat/{date}_brief.md (what the writer reads) and the {date}_moat.md skeleton
         (FILL markers, the computed margin comparison, the cost table and the script candidate).
build:   check the filled md, write the conclusion (モート 広い/狭い/なし/判定保留) and {date}_moat.json.
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

import an_common as A  # noqa: E402
import ff_paths as FP  # noqa: E402
import mdparse as M  # noqa: E402
import mt_brief as B  # noqa: E402
import mt_doc as D  # noqa: E402
import mt_inputs as I  # noqa: E402
import mt_metrics as X  # noqa: E402
import mt_paths as P  # noqa: E402
import tc_paths as TP  # noqa: E402
import three_c as TC  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "moat" / "moat.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)
MARGIN_KEY = "margin_series"  # input_digests entry for the 3.1 comparison (read beyond the SPECS sections)


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "moat" / "moat.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


def _tc_company(company: P.Company) -> TP.Company:
    return TP.Company(company.root, company.path)


def _ff_company(company: P.Company) -> FP.Company:
    return FP.Company(company.root, company.path)


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
                           "verdict": result.get("verdict"), "valid_until": result.get("valid_until") or P.valid_until(date)}
        digests = result.get("input_digests")
        if digests is None:  # results built before digests
            state["newer_raw"] = I.newer_trigger_files(company, date, result.get("inputs") or (),
                                                       result.get("seen") or ())
        else:
            found = I.gather_moat(company)
            state["newer_raw"] = I.changed_input_files(company, found, digests)
            if digests.get(MARGIN_KEY, "") != X.margin_digest(X.candidates(company, found)):
                state["newer_raw"].append("（営業利益率の時系列: data/*.csv・財務時系列・有報・競合）")
        tc = TP.latest_result(_tc_company(company))
        if tc and tc[0] > date:
            state["newer_raw"].append(company.rel(_tc_company(company).file(tc[0], TP.JSON_SUFFIX)))
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="モート分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="分析後に新しい raw・3C分析がある: " + ", ".join(state["newer_raw"]))
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


def _unavailable(found: dict) -> list[str]:
    return [f.spec.label for f in found.values() if f.status == "unavailable"]


def _three_c_summary(company: P.Company, three_c: tuple[str, dict] | None) -> dict | None:
    if not three_c:
        return None
    date, r = three_c
    return {"date": date, "verdict": r.get("verdict"), "md": company.rel(_tc_company(company).file(date, TP.MD_SUFFIX))}


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in I.TRIGGER_KINDS for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "moat": state["result"],
                     "moat_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "three_c": TC.evaluate(_tc_company(company), today)["result"]})
    return emit({"ok": True, "companies": rows})


def _requests(company: P.Company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, plus older peer margins when they could still lift the candidate to 強い."""
    return X.with_history_request(I.collect_requests(found), cands["margin"], I.unavailable_items(company))


def _next_step(company: P.Company, result: str, tc_result: str, requests: list[dict]) -> str:
    if result == "fresh":
        return "report_existing"
    if not _has_raw(company):
        return "collect"
    if tc_result != "fresh":
        return "three_c"  # STEP 1-2 first; the three-c skill runs five-forces and collection itself
    if requests:
        return "collect"
    return "prepare"  # the 3C verdict (なし / 判定保留) does not stop the moat analysis


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    tc_state = TC.evaluate(_tc_company(company), today)
    found = I.gather_moat(company)
    requests = _requests(company, found, X.candidates(company, found))
    outlook = A.latest_outlook(root, today)
    next_step = _next_step(company, state["result"], tc_state["result"], requests)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "three_c": {"result": tc_state["result"], "reason": tc_state["reason"],
                             "latest": tc_state["latest"]},
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": next_step})


def _three_c_header(company: P.Company, three_c: tuple[str, dict] | None) -> str:
    if not three_c:
        return "—（完成済みの3C分析なし）"
    date, r = three_c
    md = company.rel(_tc_company(company).file(date, TP.MD_SUFFIX))
    return f"{md}（勝てる理由 {r.get('verdict', '—')}）"


def _five_forces_header(company: P.Company, five_forces: tuple[str, dict] | None) -> str:
    if not five_forces:
        return "—（完成済みのファイブフォース分析なし）"
    date, r = five_forces
    md = company.rel(_ff_company(company).file(date, FP.MD_SUFFIX))
    return f"{md}（業界の魅力度 {r.get('attractiveness', '—')}）"


def _cell(text: str | None) -> str:
    """A value for a table cell: '|' and line breaks would break the table."""
    return "—" if M.is_blank(text) else text.replace("|", "／").replace("\n", " ")


def _values(company: P.Company, date: str, found: dict, three_c: tuple[str, dict] | None,
            five_forces: tuple[str, dict] | None, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    tc = three_c[1] if three_c else {}
    verdict = f"{tc['verdict']}: {tc.get('win_reason') or '—'}" if tc.get("verdict") else None
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "three_c": _three_c_header(company, three_c), "five_forces": _five_forces_header(company, five_forces),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週）" if outlook["path"]
                        else "—（完成済みの outlook.md なし）"),
            "three_c_verdict": _cell(verdict), "three_c_strengths": _cell((tc.get("handoff") or {}).get("strengths"))}


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
    found = I.gather_moat(company)
    cands = X.candidates(company, found)
    requests = _requests(company, found, cands)
    draft = P.latest_draft(company)
    untouched = bool(draft) and A.is_untouched(company.file(draft[0], P.BRIEF_SUFFIX), draft[1])
    kept = state["result"] == "draft" and not args.redo and not untouched  # an older draft behind a built result is abandoned
    blocking = _next_step(company, "none", TC.evaluate(_tc_company(company), today)["result"], requests)
    gate = None if kept else A.prepare_gate(blocking, _has_raw(company), args.skip_collect)  # a started draft goes on
    if gate:
        return emit({"ok": False, "error": gate, "next": blocking, "missing_inputs": requests})
    if untouched and draft[0] != today:
        for suffix in (P.MD_SUFFIX, P.BRIEF_SUFFIX):  # nobody wrote into it: today's skeleton replaces it
            company.file(draft[0], suffix).unlink(missing_ok=True)
    date = draft[0] if kept and draft else today
    previous = P.latest_result(company, before=date)
    three_c = TP.latest_result(_tc_company(company))
    five_forces = FP.latest_result(_ff_company(company))
    outlook = A.latest_outlook(root, today)
    warnings = X.warnings(cands)
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    brief = B.render_brief(company, date, P.valid_until(date), found, cands, previous, three_c, five_forces,
                           outlook, warnings)
    if not kept:
        values = _values(company, date, found, three_c, five_forces, outlook)
        skeleton = D.render_skeleton(_template(root), values, cands, previous)
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, brief)
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "regenerated": untouched and not args.redo,
        "skipped_collect": requests if blocking == "collect" else [], "warnings": warnings,
        "fill": len(A.FILL.findall(md_path.read_text(encoding="utf-8"))),
        "candidates": {"margin": cands["margin"]["rating"], "years_above": cands["margin"]["years_above"],
                       "compared_years": cands["margin"]["compared_years"]},
        "previous": previous[0] if previous else None, "three_c": _three_c_summary(company, three_c),
        "missing_inputs": I.collect_requests(found), "unavailable": _unavailable(found), "outlook": outlook["path"],
    })


def _target(company: P.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, P.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = A.dated_files(company.analysis_dir, P.MD_SUFFIX)
    return files[-1] if files else None


def _header_path(text: str, pattern: re.Pattern) -> str | None:
    """'market/report/X_outlook.md（3 日前の週）' -> the path; None for '—（…なし）'."""
    m = pattern.search(text)
    path = m.group(1).split("（")[0].strip() if m else ""
    return None if M.is_blank(path) else path


def result_json(company: P.Company, date: str, text: str, parsed: dict, cands: dict, judged: dict) -> dict:
    found = I.gather_moat(company)
    previous = P.latest_result(company, before=date)
    three_c = TP.latest_result(_tc_company(company))
    effective = set(judged["effective"])
    moats = [dict(m, effective=m["type"] in effective) for m in parsed["moats"]]
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "strength": parsed["strength"], "moats": moats,
        "margin": {"candidate": cands["margin"]["rating"], "years_above": cands["margin"]["years_above"],
                   "compared_years": cands["margin"]["compared_years"], "basis": cands["margin"]["basis"],
                   "rows": cands["rows"], "sources": cands["sources"]},
        "costs": cands["costs"], "share": parsed["share"], "risks": parsed["risks"],
        "durability": parsed["durability"], "backing": judged["backing"], "backing_reason": judged["backing_why"],
        "effective_moats": judged["effective"], "corrected": judged["corrected"], "near_risks": judged["near_risks"],
        "verdict": judged["verdict"], "verdict_reason": judged["why"], "triggers": parsed["triggers"],
        "handoff": {"strengths": parsed["strengths"], "threats": parsed["threats"],
                    "step2_checks": parsed["step2_checks"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "seen": I.raw_seen(company),
        "input_digests": {**I.input_digests(found), MARGIN_KEY: X.margin_digest(cands)},
        "three_c": ({"date": three_c[0], "verdict": three_c[1].get("verdict")} if three_c else None),
        "outlook": _header_path(text, OUTLOOK_HEADER),
        "previous": {"date": previous[0], "verdict": previous[1].get("verdict")} if previous else None,
        "md": company.rel(company.file(date, P.MD_SUFFIX)),
    }


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "moat.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    issues = D.validate(text, _template(root))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    issues = D.check_reference(parsed, P.latest_result(company, before=date))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    # the margin candidate is recomputed so edited cells in the md can't bypass the rules
    cands = X.candidates(company, I.gather_moat(company))
    judged = D.judge(parsed, cands["margin"])
    atomic_write_text(md_path, D.apply_conclusion(text, judged, cands["margin"], parsed["share"]["trend"]))
    result = result_json(company, date, text, parsed, cands, judged)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": judged["verdict"], "verdict_reason": judged["why"], "effective_moats": judged["effective"],
        "claimed_moats": judged["claimed"], "corrected": judged["corrected"], "backing": judged["backing"],
        "backing_reason": judged["backing_why"], "share": parsed["share"]["trend"],
        "near_risks": judged["near_risks"], "durability": parsed["durability"],
        "valid_until": result["valid_until"], "previous": result["previous"], "three_c": result["three_c"],
        **D.flags(parsed), "gaps": [g for g in parsed["gaps"] if not M.is_blank(g) and g != "なし"],
    })


def main(argv: list[str] | None = None, root: Path = A.REPO_ROOT) -> int:
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
            p.add_argument("--skip-collect", action="store_true",
                           help="収集を1回試しても材料が足りないまま進む（欠損は brief の「取れていない材料」に出る）")
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
