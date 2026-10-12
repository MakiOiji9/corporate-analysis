"""three-c orchestrator: everything except writing the judgement text.

Usage:
  three_c.py list
  three_c.py check   --company X
  three_c.py prepare --company X [--redo]
  three_c.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their 3C and five-forces results (for choosing one).
check:   is the latest 3C result still valid (180 days, no newer yuho / business-overview / industry /
         competitors raw, no newer five-forces result)? Is the five-forces result usable (STEP 1-1 comes
         first)? Which required inputs are missing? How old is the outlook (header only)? -> "next".
prepare: analysis/three-c/{date}_brief.md (what the writer reads) and the {date}_three-c.md skeleton
         (FILL markers, the computed comparison table and the script candidates).
build:   check the filled md, write the conclusion (勝てる理由 明確/あいまい/なし/判定保留) and {date}_three-c.json.
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
import five_forces as FF  # noqa: E402
import mdparse as M  # noqa: E402
import tc_brief as B  # noqa: E402
import tc_doc as D  # noqa: E402
import tc_inputs as I  # noqa: E402
import tc_metrics as X  # noqa: E402
import tc_paths as P  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "three-c" / "three-c.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "three-c" / "three-c.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


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
        state["newer_raw"] = I.newer_trigger_files(company, date)
        ff = FP.latest_result(_ff_company(company))
        if ff and ff[0] > date:
            state["newer_raw"].append(company.rel(_ff_company(company).file(ff[0], FP.JSON_SUFFIX)))
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="3C分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="分析後に新しい raw・ファイブフォースがある: " + ", ".join(state["newer_raw"]))
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


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in I.TRIGGER_KINDS for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "three_c": state["result"],
                     "three_c_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "five_forces": FF.evaluate(_ff_company(company), today)["result"]})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    ff_state = FF.evaluate(_ff_company(company), today)
    found = I.gather_3c(company)
    requests = I.collect_requests(found)
    outlook = A.latest_outlook(root, today)
    if state["result"] == "fresh":
        next_step = "report_existing"
    elif not _has_raw(company):
        next_step = "collect"
    elif ff_state["result"] != "fresh":
        next_step = "five_forces"  # STEP 1-1 first; the five-forces skill collects what it needs itself
    elif requests:
        next_step = "collect"
    else:
        next_step = "prepare"  # an old outlook is only noted (header reference), never a reason to collect
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "five_forces": {"result": ff_state["result"], "reason": ff_state["reason"],
                                 "latest": ff_state["latest"]},
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": next_step})


def _five_forces_header(company: P.Company, five_forces: tuple[str, dict] | None) -> str:
    if not five_forces:
        return "—（完成済みのファイブフォース分析なし）"
    date, r = five_forces
    md = company.rel(_ff_company(company).file(date, FP.MD_SUFFIX))
    return f"{md}（業界の魅力度 {r.get('attractiveness', '—')}。業界: {r.get('industry', '—')}）"


def _values(company: P.Company, date: str, found: dict, five_forces: tuple[str, dict] | None, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "five_forces": _five_forces_header(company, five_forces),
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
    found = I.gather_3c(company)
    cands = X.candidates(company, found)
    previous = P.latest_result(company, before=date)
    five_forces = FP.latest_result(_ff_company(company))
    outlook = A.latest_outlook(root, today)
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    atomic_write_text(brief_path, B.render_brief(company, date, P.valid_until(date), found, cands, previous,
                                                 five_forces, outlook))
    if not kept:
        values = _values(company, date, found, five_forces, outlook)
        atomic_write_text(md_path, D.render_skeleton(_template(root), values, cands, previous))
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "fill": len(A.FILL.findall(md_path.read_text(encoding="utf-8"))),
        "candidates": {"growth": cands["growth"]["rating"], "competitor": cands["competitor"]["rating"],
                       "competitor_fixed": cands["competitor"]["fixed"]},
        "peers": X.peer_names(cands["rows"]), "previous": previous[0] if previous else None,
        "five_forces": five_forces[0] if five_forces else None,
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
    found = I.gather_3c(company)
    previous = P.latest_result(company, before=date)
    five_forces = FP.latest_result(_ff_company(company))
    peers = X.peer_names(cands["rows"])
    kbf_rows = [{"kbf": r["kbf"], "self": r["self"],
                 "peers": {peers[i]: m for i, m in enumerate(r["peers"]) if i < len(peers)}, "basis": r["basis"]}
                for r in parsed["kbf_rows"]]
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date),
        "customer": parsed["customer"], "kbf": parsed["customer"]["kbf"],
        "growth": dict(parsed["growth"], candidate=cands["growth"]["rating"]),
        "competitor": dict(parsed["competitor"], candidate=cands["competitor"]["rating"],
                           candidate_fixed=cands["competitor"]["fixed"]),
        "comparison": cands["rows"], "kbf_table": kbf_rows, "company_conclusion": parsed["company_conclusion"],
        "top_kbf": judged["top_kbf"], "top_kbf_win": judged["top_kbf_win"],
        "win_reason": parsed["win_reason"], "verdict": judged["verdict"], "verdict_reason": judged["why"],
        "triggers": parsed["triggers"],
        "handoff": {"strengths": parsed["strengths"], "weaknesses": parsed["weaknesses"],
                    "moat_checks": parsed["moat_checks"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "five_forces": ({"date": five_forces[0], "attractiveness": five_forces[1].get("attractiveness"),
                         "industry": five_forces[1].get("industry")} if five_forces else None),
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
        return emit({"ok": False, "error": "three-c.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    # candidates / peers are recomputed so edited cells in the md can't bypass the rules
    cands = X.candidates(company, I.gather_3c(company))
    peer_count = len(X.peer_names(cands["rows"]))
    issues = D.validate(text, _template(root), peer_count)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    issues = D.check_reference(parsed, cands, P.latest_result(company, before=date))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    judged = D.judge(parsed, peer_count)
    atomic_write_text(md_path, D.apply_conclusion(text, judged, parsed["competitor"]["rating"], cands["competitor"]))
    result = result_json(company, date, text, parsed, cands, judged)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": judged["verdict"], "verdict_reason": judged["why"], "win_reason": parsed["win_reason"],
        "kbf": parsed["customer"]["kbf"], "top_kbf_win": judged["top_kbf_win"],
        "growth": parsed["growth"]["rating"], "competitor": parsed["competitor"]["rating"],
        "valid_until": result["valid_until"], "previous": result["previous"], "five_forces": result["five_forces"],
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
