"""safety orchestrator (企業分析フレームワーク.md STEP 2-3 安全性): everything except the background text.

Usage:
  safety.py list
  safety.py check   --company X
  safety.py prepare --company X [--redo] [--skip-collect]
  safety.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their safety result (for choosing one).
check:   is the latest result still valid (180 days, the sections and the yearly numbers it used unchanged)?
         Which required inputs are missing (the own balance sheet needs the three indicators and 3 years of
         trend; the peers need competitors.md「安全性の指標」)? -> "next". Nothing upstream is required: the
         profitability result and the market outlook are only quoted in the brief.
prepare: analysis/safety/{date}_brief.md (what the writer reads) and the {date}_safety.md skeleton
         (every table and judgement computed, FILL markers for the background only).
build:   check the filled md, write the conclusion (安全性 良好/普通/懸念/判定保留) and {date}_safety.json.
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
import mdparse as M  # noqa: E402
import pf_paths as PP  # noqa: E402
import sf_brief as B  # noqa: E402
import sf_doc as D  # noqa: E402
import sf_inputs as I  # noqa: E402
import sf_metrics as X  # noqa: E402
import freshness as T  # noqa: E402
import sf_paths as P  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "safety" / "safety.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)
SERIES_KEY = "yearly_series"  # input_digests entry for every number (read beyond the SPECS sections)
FILL_KEY = re.compile(r"<!--\s*FILL:([\w-]+)")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "safety" / "safety.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


def _profitability(company: P.Company) -> tuple[str, dict] | None:
    return PP.latest_result(PP.Company(company.root, company.path))


def _summary(result: tuple[str, dict] | None) -> dict | None:
    return {"date": result[0], "verdict": result[1].get("verdict")} if result else None


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
                           "verdict": result.get("verdict"), "valid_until": P.valid_until(date)}
        state["newer_raw"] = T.triggers(company, date, "quarter")
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="安全性分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="; ".join(state["newer_raw"]))
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
                     "last_collected": max(raw_dates) if raw_dates else None, "safety": state["result"],
                     "safety_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "profitability": _summary(_profitability(company))})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    found = I.gather_safety(company)
    requests = X.collect_requests(company, found, X.candidates(company, found))
    outlook = A.latest_outlook(root, today)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "profitability": _summary(_profitability(company)),
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": _next_step(company, state["result"], requests)})


def _profitability_header(company: P.Company) -> str:
    result = _profitability(company)
    if not result:
        return "—（完成済みの収益性分析なし。安全性の判定には使わない）"
    date, r = result
    md = company.rel(PP.Company(company.root, company.path).file(date, PP.MD_SUFFIX))
    return f"{md}（収益性 {r.get('verdict', '—')}）"


def _values(company: P.Company, date: str, found: dict, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "profitability": _profitability_header(company),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週。金利・金融政策の行を brief に抜粋。判定には使わない）"
                        if outlook["path"] else "—（完成済みの outlook.md なし）")}


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
    found = I.gather_safety(company)
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
    brief = B.render_brief(company, date, P.valid_until(date), found, cands, previous, _profitability(company),
                           outlook, warnings)
    if not kept:
        skeleton = D.render_skeleton(_template(root), _values(company, date, found, outlook), cands)
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, brief)
    s1 = cands["step1"]
    md_text = md_path.read_text(encoding="utf-8")
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "regenerated": untouched and not args.redo,
        "skipped_collect": requests if blocking == "collect" else [], "warnings": warnings,
        "fill": len(A.FILL.findall(md_text)), "fill_keys": FILL_KEY.findall(md_text),
        "candidate": {"verdict": cands["verdict"], "why": cands["why"],
                      "step1": {i["name"]: i["rating"] for i in s1["items"]},
                      "step2": cands["step2"]["rating"], "step3": cands["step3"]["rating"]},
        "net_cash": s1["net_cash"], "borderline": cands["borderline"],
        "debt_years": [y["year"] for y in cands["step3"]["years"]],
        "previous": previous[0] if previous else None, "profitability": _summary(_profitability(company)),
        "unavailable": _unavailable(found), "outlook": outlook["path"],
    })


def _target(company: P.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, P.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = A.dated_files(company.analysis_dir, P.MD_SUFFIX)
    return files[-1] if files else None


def _header_path(text: str, pattern: re.Pattern) -> str | None:
    """'market/report/X_outlook.md（3 日前の週…）' -> the path; None for '—（…なし）'."""
    m = pattern.search(text)
    path = m.group(1).split("（")[0].strip() if m else ""
    return None if M.is_blank(path) else path


def _round(value):
    return round(value, 4) if isinstance(value, float) else value


def _step_json(cands: dict) -> dict:
    s1, s2, s3 = cands["step1"], cands["step2"], cands["step3"]
    return {
        "step1": {"year": s1["year"], "sentence": s1["sentence"], "counts": s1["counts"], "excluded": s1["excluded"],
                  "net_cash": s1["net_cash"], "debt_free": s1["debt_free"],
                  "items": [{k: _round(v) for k, v in i.items()} for i in s1["items"]],
                  "peers": [{k: _round(v) for k, v in p.items()} for p in s1["peers"]],
                  "peer_avg": {k: _round(v) for k, v in s1["peer_avg"].items()}},
        "step2": {k: s2.get(k) for k in ("rating", "basis", "sentence", "years", "drop", "de_rising")},
        "step3": {"rating": s3["rating"], "basis": s3["basis"], "sentence": s3["sentence"],
                  "years": [{k: _round(v) for k, v in y.items()} for y in s3["years"]]},
    }


def result_json(company: P.Company, date: str, text: str, parsed: dict, cands: dict) -> dict:
    found = I.gather_safety(company)
    previous = P.latest_result(company, before=date)
    backgrounds = {y["year"]: y["background"] for y in parsed["purpose_by_year"]}
    steps = _step_json(cands)
    steps["step3"]["years"] = [dict(y, background=backgrounds.get(y["year"], "")) for y in steps["step3"]["years"]]
    keys = ("year", "total_assets", "equity", "equity_ratio", "debt", "de", "current_ratio", "cash", "net_cash",
            "cfo", "cfi", "cff", "primary", "debt_source")
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "verdict": cands["verdict"], "verdict_reason": cands["why"],
        "conservative": cands["conservative"],
        **steps,
        "rows": [{k: _round(r[k]) for k in keys} for r in cands["rows"]],
        "borderline": cands["borderline"], "level_background": parsed["level_background"],
        "handoff": {"report_points": parsed["report_points"], "policy": parsed["policy"],
                    "step2_checks": parsed["step2_checks"], "triggers": parsed["triggers"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "seen": I.raw_seen(company),
        "input_digests": {**I.input_digests(found), SERIES_KEY: X.series_digest(cands)},
        "profitability": _summary(_profitability(company)),
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
        return emit({"ok": False, "error": "safety.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    # the numbers are recomputed so edited cells in the md can't change the conclusion
    cands = X.candidates(company, I.gather_safety(company))
    brief = company.file(date, P.BRIEF_SUFFIX)
    reference = brief.read_text(encoding="utf-8") if brief.exists() else ""
    issues = D.validate(text, _template(root), cands["step3"]["years"], reference)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    atomic_write_text(md_path, D.apply_conclusion(text, cands))
    result = result_json(company, date, text, parsed, cands)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": cands["verdict"], "verdict_reason": cands["why"], "step1": cands["step1"]["sentence"],
        "step2": cands["step2"]["sentence"], "step3": cands["step3"]["sentence"],
        "valid_until": result["valid_until"], "previous": result["previous"],
        "profitability": result["profitability"], **D.flags(parsed, cands),
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
