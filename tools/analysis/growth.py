"""growth orchestrator (企業分析フレームワーク.md STEP 2-2 成長性): everything except the background text.

Usage:
  growth.py list
  growth.py check   --company X
  growth.py prepare --company X [--redo] [--skip-collect]
  growth.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their growth result (for choosing one).
check:   is the latest result still valid (180 days, the sections and the yearly numbers it used unchanged, no
         newer 3C / SWOT result)? Which required inputs are missing (the own series needs 5 years of sales and
         EPS; the plan, the M&A section and the company's explanation of the decline years)? -> "next".
         STEP 1 is not required: 3C / SWOT results are only referred to when they exist.
prepare: analysis/growth/{date}_brief.md (what the writer reads) and the {date}_growth.md skeleton
         (every table and judgement computed, FILL markers for the background and the decline-year classes).
build:   check the filled md, write the conclusion (成長性 良好/普通/懸念/判定保留) and {date}_growth.json.
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
import gr_brief as B  # noqa: E402
import gr_doc as D  # noqa: E402
import gr_facts as F  # noqa: E402
import gr_inputs as I  # noqa: E402
import gr_metrics as X  # noqa: E402
import gr_paths as P  # noqa: E402
import mdparse as M  # noqa: E402
import sw_paths as SP  # noqa: E402
import tc_paths as TP  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "growth" / "growth.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)
SERIES_KEY = "yearly_series"  # input_digests entry for every number (read beyond the SPECS sections)
FILL_KEY = re.compile(r"<!--\s*FILL:([\w-]+)")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "growth" / "growth.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


def _three_c(company: P.Company) -> tuple[str, dict] | None:
    return TP.latest_result(TP.Company(company.root, company.path))


def _swot(company: P.Company) -> tuple[str, dict] | None:
    return SP.latest_result(SP.Company(company.root, company.path))


def _upstream_files(company: P.Company) -> list[tuple[str, str]]:
    """(date, json path) of the finished 3C and SWOT results."""
    out = []
    for result, cls, suffix in ((_three_c(company), TP.Company, TP.JSON_SUFFIX),
                                (_swot(company), SP.Company, SP.JSON_SUFFIX)):
        if result:
            out.append((result[0], company.rel(cls(company.root, company.path).file(result[0], suffix))))
    return out


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
        digests = result.get("input_digests") or {}
        found = I.gather_growth(company)
        state["newer_raw"] = I.changed_input_files(company, found, digests)
        if digests.get(SERIES_KEY, "") != X.series_digest(X.candidates(company, found)):
            state["newer_raw"].append("（年次の数値: data/*.csv・有報・財務時系列）")
        state["newer_raw"] += [path for d, path in _upstream_files(company) if d > date]
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="成長性分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="分析後に材料・数値・上流の分析が変わった: " + ", ".join(state["newer_raw"]))
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


def _summary(result: tuple[str, dict] | None) -> dict | None:
    return {"date": result[0], "verdict": result[1].get("verdict")} if result else None


def _three_c_summary(result: tuple[str, dict] | None) -> dict | None:
    if not result:
        return None
    return {**_summary(result), "market_growth": (result[1].get("growth") or {}).get("rating")}


def _next_step(company: P.Company, result: str, requests: list[dict]) -> str:
    if result == "fresh":
        return "report_existing"
    if not _has_raw(company) or requests:
        return "collect"
    return "prepare"


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in I.TRIGGER_KINDS for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "growth": state["result"],
                     "growth_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "three_c": _three_c_summary(_three_c(company)), "swot": _summary(_swot(company))})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    found = I.gather_growth(company)
    requests = X.collect_requests(company, found, X.candidates(company, found))
    outlook = A.latest_outlook(root, today)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "three_c": _three_c_summary(_three_c(company)), "swot": _summary(_swot(company)),
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": _next_step(company, state["result"], requests)})


def _upstream_header(company: P.Company, result: tuple[str, dict] | None, cls, suffix: str, label: str,
                     what: str) -> str:
    if not result:
        return f"—（完成済みの{label}なし）"
    date, r = result
    md = company.rel(cls(company.root, company.path).file(date, suffix))
    return f"{md}（{what}）" if what else md


def _values(company: P.Company, date: str, found: dict, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    three_c, swot = _three_c(company), _swot(company)
    tc_what = (f"市場の成長性 {(three_c[1].get('growth') or {}).get('rating', '—')}、"
               f"勝てる理由 {three_c[1].get('verdict', '—')}") if three_c else ""
    sw_what = f"SWOT {swot[1].get('verdict', '—')}" if swot else ""
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "three_c": _upstream_header(company, three_c, TP.Company, TP.MD_SUFFIX, "3C分析", tc_what),
            "swot": _upstream_header(company, swot, SP.Company, SP.MD_SUFFIX, "SWOT分析", sw_what),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週）" if outlook["path"]
                        else "—（完成済みの outlook.md なし）")}


def _consistency(company: P.Company, cands: dict) -> list[dict]:
    three_c = _three_c(company)
    return X.consistency(cands["step1"], three_c[1] if three_c else None)


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
    found = I.gather_growth(company)
    cands = X.candidates(company, found)
    requests = X.collect_requests(company, found, cands)
    draft = P.latest_draft(company)
    untouched = bool(draft) and A.is_untouched(company.file(draft[0], P.BRIEF_SUFFIX), draft[1])
    kept = state["result"] == "draft" and not args.redo and not untouched  # an older draft behind a built result is abandoned
    blocking = _next_step(company, "none", requests)
    gate = None if kept else A.prepare_gate(blocking, _has_raw(company), args.skip_collect)  # a started draft goes on
    if gate:
        return emit({"ok": False, "error": gate, "next": blocking, "missing_inputs": requests})
    if untouched and draft[0] != today:
        for suffix in (P.MD_SUFFIX, P.BRIEF_SUFFIX):  # nobody wrote into it: today's skeleton replaces it
            company.file(draft[0], suffix).unlink(missing_ok=True)
    date = draft[0] if kept and draft else today
    previous = P.latest_result(company, before=date)
    outlook = A.latest_outlook(root, today)
    warnings = X.warnings(cands)
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    brief = B.render_brief(company, date, P.valid_until(date), found, cands, previous, _three_c(company),
                           _swot(company), outlook, warnings)
    if not kept:
        skeleton = D.render_skeleton(_template(root), _values(company, date, found, outlook), cands,
                                     _consistency(company, cands))
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, brief)
    text = md_path.read_text(encoding="utf-8")
    s1 = cands["step1"]
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "regenerated": untouched and not args.redo,
        "skipped_collect": requests if blocking == "collect" else [], "warnings": warnings,
        "fill": len(A.FILL.findall(text)), "fill_keys": FILL_KEY.findall(text),
        "candidate": {"verdict": cands["verdict"], "why": cands["why"], "step1": s1["rating"],
                      "step3": cands["step3"]["rating"], "quality": cands["step4"]["quality"],
                      "downgraded": cands["downgraded"]},
        "progress": F.progress_text(cands["progress"]),
        "cagr": {"sales": _round(s1["sales"]["value"]), "operating_income": _round(s1["operating_income"]["value"]),
                 "eps": _round(s1["eps"]["value"]), "net_income": _round(s1["net_income"]["value"])},
        "decline_years": [d["year"] for d in cands["declines"]], "borderline": cands["borderline"],
        "previous": previous[0] if previous else None, "three_c": _three_c_summary(_three_c(company)),
        "swot": _summary(_swot(company)), "unavailable": _unavailable(found), "outlook": outlook["path"],
    })


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


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


def _cagr_json(c: dict) -> dict:
    return {"value": _round(c["value"]), "first": c["first"], "last": c["last"], "reason": c.get("reason", "")}


def _step_json(cands: dict) -> dict:
    s1, s3, s4 = cands["step1"], cands["step3"], cands["step4"]
    return {
        "step1": {"rating": s1["rating"], "basis": s1["basis"], "sentence": s1["sentence"], "years": s1["years"],
                  "first": s1["first"], "last": s1["last"], "eps_basis": s1["eps_key"],
                  "sales_cagr": _round(s1["sales"]["value"]), "eps_cagr": _round(s1["eps"]["value"]),
                  "cagr": {k: _cagr_json(s1[k]) for k in ("sales", "operating_income", "eps", "net_income")}},
        "step3": {"rating": s3["rating"], "basis": s3["basis"], "sentence": s3["sentence"],
                  "average": _round(s3.get("average")),
                  "rows": [{k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()} for r in s3["rows"]]},
        "step4": {"quality": s4["quality"], "sentence": s4["sentence"], "problems": s4["problems"],
                  "unknown": s4["unknown"], "adjusted": s4["adjusted"],
                  "checks": [{k: c[k] for k in ("name", "status", "detail")} for c in s4["checks"]]},
    }


def result_json(company: P.Company, date: str, text: str, parsed: dict, cands: dict,
                consistency: list[dict], verdict: str, why: str) -> dict:
    found = I.gather_growth(company)
    previous = P.latest_result(company, before=date)
    by_year = {d["year"]: d for d in parsed["declines"]}
    rows = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()
             if k in ("year", "sales", "operating_income", "net_income", "eps", "source", "primary")}
            for r in cands["rows"]]
    declines = [{"year": d["year"], "recovery": d["recovery"],
                 "metrics": [{"name": m["name"], "change": _round(m["change"]), "recovery": m["recovery"],
                              "recovered": m["recovered"]} for m in d["metrics"]],
                 **{k: by_year.get(d["year"], {}).get(k, "") for k in ("reason", "class", "swot")}}
                for d in cands["declines"]]
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "verdict": verdict, "verdict_reason": why,
        **_step_json(cands), "step2": {"sentence": D.step2_sentence(cands, D.classes(parsed)),
                                       "structural": parsed["structural"]},
        "rows": rows, "splits": [{k: n[k] for k in ("before", "after", "factor", "matched", "record", "text")}
                                 for n in cands["split_notes"]],
        "progress": cands["progress"], "receivables": cands["receivables"],
        "declines": declines, "ma": cands["ma"],
        "borderline": cands["borderline"], "consistency": consistency,
        "consistency_comment": parsed["consistency_comment"], "mtp": parsed["mtp"], "drivers": parsed["drivers"],
        "handoff": {"report_points": parsed["report_points"], "step3_hint": parsed["step3_hint"],
                    "step2_checks": parsed["step2_checks"], "triggers": parsed["triggers"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "seen": I.raw_seen(company),
        "input_digests": {**I.input_digests(found), SERIES_KEY: X.series_digest(cands)},
        "three_c": _three_c_summary(_three_c(company)), "swot": _summary(_swot(company)),
        "outlook": _header_path(text, OUTLOOK_HEADER),
        "previous": {"date": previous[0], "verdict": previous[1].get("verdict")} if previous else None,
        "md": company.rel(company.file(date, P.MD_SUFFIX)),
    }


def _allowed_text(root: Path, company: P.Company, date: str, found: dict, cands: dict) -> str:
    """The numbers the writer may quote: the brief and the skeleton as prepare would write it now."""
    brief = company.file(date, P.BRIEF_SUFFIX)
    outlook = A.latest_outlook(root, date)
    skeleton = D.render_skeleton(_template(root), _values(company, date, found, outlook), cands,
                                 _consistency(company, cands))
    return (brief.read_text(encoding="utf-8") if brief.exists() else "") + "\n" + skeleton


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "growth.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    # the numbers are recomputed so edited cells in the md can't change the conclusion
    found = I.gather_growth(company)
    cands = X.candidates(company, found)
    issues = D.validate(text, _template(root), cands["declines"], _allowed_text(root, company, date, found, cands))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    year_classes = D.classes(parsed)
    verdict, why, downgraded = D.final(cands, year_classes)
    consistency = _consistency(company, cands)
    atomic_write_text(md_path, D.apply_conclusion(text, cands, year_classes))
    result = result_json(company, date, text, parsed, cands, consistency, verdict, why)
    result["downgraded"] = downgraded
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": verdict, "verdict_reason": why, "downgraded": downgraded,
        "progress": F.progress_text(cands["progress"]),
        "step1": cands["step1"]["sentence"], "step2": result["step2"]["sentence"],
        "step3": cands["step3"]["sentence"], "step4": cands["step4"]["sentence"],
        "consistency": [f"{c['check']}: {c['result']}" for c in consistency],
        "borderline": cands["borderline"], "valid_until": result["valid_until"], "previous": result["previous"],
        "three_c": result["three_c"], "swot": result["swot"], **D.flags(parsed),
        "gaps": [g for g in parsed["gaps"] if not M.is_blank(g) and g != "なし"],
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
