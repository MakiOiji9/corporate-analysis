"""swot orchestrator: everything except writing the judgement text.

Usage:
  swot.py list
  swot.py check   --company X
  swot.py prepare --company X [--redo] [--skip-collect] [--skip-market-report]
  swot.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their SWOT and moat results (for choosing one).
check:   is the latest SWOT result still valid (180 days, no changed yuho / mid-term-plan / business-overview /
         industry section, no newer five-forces / 3C / moat result)? Is the moat result usable (STEP 1-3 comes
         first; it runs 3C and five-forces itself)? Is the market outlook fresh? Which inputs are missing? -> "next".
prepare: analysis/swot/{date}_brief.md (what the writer reads) and the {date}_swot.md skeleton
         (FILL markers, the upstream conclusions, the items that must be written and the impact yardstick).
build:   check the filled md, write the conclusion (SWOT Yes / 条件付き / No / 判定保留) and {date}_swot.json.
stdout is one JSON line so the calling agent spends few tokens. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
sys.path[:0] = [str(HERE), str(TOOLS / "report"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import an_common as A  # noqa: E402
import ff_paths as FP  # noqa: E402
import mdparse as M  # noqa: E402
import moat as MT  # noqa: E402
import mt_paths as MP  # noqa: E402
import sw_brief as B  # noqa: E402
import sw_doc as D  # noqa: E402
import sw_inputs as I  # noqa: E402
import sw_metrics as X  # noqa: E402
import freshness as T  # noqa: E402
import sw_paths as P  # noqa: E402
import tc_paths as TP  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "swot" / "swot.md"
LIST_KINDS = ("yuho", "mid-term-plan", "business-overview", "industry-overview", "competitors")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "swot" / "swot.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


# ---------- upstream ----------

UPSTREAM = {"five_forces": (FP.Company, FP.latest_result, FP.MD_SUFFIX, FP.JSON_SUFFIX),
            "three_c": (TP.Company, TP.latest_result, TP.MD_SUFFIX, TP.JSON_SUFFIX),
            "moat": (MP.Company, MP.latest_result, MP.MD_SUFFIX, MP.JSON_SUFFIX)}


def upstream(company: P.Company) -> dict[str, tuple[str, dict] | None]:
    """Newest finished five-forces, 3C and moat results."""
    return {kind: latest(cls(company.root, company.path)) for kind, (cls, latest, _, _) in UPSTREAM.items()}


def _upstream_file(company: P.Company, kind: str, date: str, md: bool = False) -> str:
    cls, _, md_suffix, json_suffix = UPSTREAM[kind]
    return company.rel(cls(company.root, company.path).file(date, md_suffix if md else json_suffix))


def _upstream_summary(ups: dict) -> dict:
    return {k: ({"date": v[0], "verdict": v[1].get("verdict") or v[1].get("attractiveness")} if v else None)
            for k, v in ups.items()}


def moat_state(company: P.Company, today: str) -> dict:
    state = MT.evaluate(MP.Company(company.root, company.path), today)
    return {"result": state["result"], "reason": state["reason"], "latest": state["latest"]}


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
        state["newer_raw"] = T.triggers(company, date, "annual",
                                        [("ファイブフォース", FP), ("3C", TP), ("モート", MP)])
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="SWOT分析の結果が無い")
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


def _next_step(company: P.Company, result: str, moat_result: str, outlook_stale: bool,
               requests: list[dict]) -> str:
    if result == "fresh":
        return "report_existing"
    if not _has_raw(company):
        return "collect"
    if moat_result != "fresh":
        return "moat"  # STEP 1-3 first; the moat skill runs three-c, five-forces and collection itself
    if outlook_stale:
        return "market_report"  # opportunities and threats read the market outlook
    if requests:
        return "collect"
    return "prepare"  # the upstream verdicts (なし / 判定保留) do not stop the SWOT


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in LIST_KINDS for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "swot": state["result"],
                     "swot_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "moat": moat_state(company, today)["result"]})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    moat = moat_state(company, today)
    found = I.gather_swot(company)
    requests = I.collect_requests(found)
    outlook = A.latest_outlook(root, today)
    next_step = _next_step(company, state["result"], moat["result"], outlook["stale"], requests)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state, "moat": moat,
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": next_step})


def _gate(blocking: str, has_raw: bool, skip_collect: bool) -> str | None:
    if blocking == "market_report":
        return ("地合い（outlook.md）が無いか古い。先に market-report を最後まで実行する"
                "（1回実行しても古いままなら --skip-market-report）")
    return A.prepare_gate(blocking, has_raw, skip_collect)


def _header(company: P.Company, kind: str, found: tuple[str, dict] | None, label: str, key: str) -> str:
    if not found:
        return f"—（完成済みの{label}なし）"
    date, r = found
    return f"{_upstream_file(company, kind, date, md=True)}（{r.get(key, '—')}）"


def _verdict_cells(ups: dict) -> dict:
    ff, tc, mt = ups["five_forces"], ups["three_c"], ups["moat"]
    strong = [f.get("name") for f in (ff[1].get("factors", []) if ff else []) if f.get("rating") == "強"]
    return {
        "ff_verdict": D.cell(f"{ff[1].get('attractiveness', '—')}（「強」の要因: {'、'.join(strong) or 'なし'}）"
                             if ff else None),
        "tc_verdict": D.cell(f"{tc[1].get('verdict', '—')}: {tc[1].get('win_reason') or '—'}" if tc else None),
        "moat_verdict": D.cell(f"{mt[1].get('verdict', '—')}（残ったモート: "
                               f"{'、'.join(mt[1].get('effective_moats', [])) or 'なし'}）" if mt else None),
    }


def _values(company: P.Company, date: str, found: dict, ups: dict, outlook: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs) or "—", "valid_until": P.valid_until(date),
            "five_forces": _header(company, "five_forces", ups["five_forces"], "ファイブフォース分析", "attractiveness"),
            "three_c": _header(company, "three_c", ups["three_c"], "3C分析", "verdict"),
            "moat": _header(company, "moat", ups["moat"], "モート分析", "verdict"),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週）" if outlook["path"]
                        else "—（完成済みの outlook.md なし）"),
            **_verdict_cells(ups)}


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
    found = I.gather_swot(company)
    requests = I.collect_requests(found)
    outlook = A.latest_outlook(root, today)
    draft = P.latest_draft(company)
    untouched = bool(draft) and A.is_untouched(company.file(draft[0], P.BRIEF_SUFFIX), draft[1])
    kept = state["result"] == "draft" and not args.redo and not untouched  # an older draft behind a built result is abandoned
    blocking = _next_step(company, "none", moat_state(company, today)["result"],
                          outlook["stale"] and not args.skip_market_report, requests)
    gate = None if kept else _gate(blocking, _has_raw(company), args.skip_collect)  # a started draft goes on
    if gate:
        return emit({"ok": False, "error": gate, "next": blocking, "missing_inputs": requests})
    if untouched and draft[0] != today:
        for suffix in (P.MD_SUFFIX, P.BRIEF_SUFFIX):  # nobody wrote into it: today's skeleton replaces it
            company.file(draft[0], suffix).unlink(missing_ok=True)
    date = draft[0] if kept and draft else today
    previous = P.latest_result(company, before=date)
    ups = upstream(company)
    items = D.required_items(ups["five_forces"], ups["moat"])
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    scale = X.scale(company)
    brief = B.render_brief(company, date, P.valid_until(date), found, ups, previous, outlook, scale)
    if not kept:
        skeleton = D.render_skeleton(_template(root), _values(company, date, found, ups, outlook), items,
                                     scale, previous)
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, brief)
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "regenerated": untouched and not args.redo,
        "skipped_collect": requests if blocking == "collect" else [],
        "skipped_market_report": bool(outlook["stale"] and args.skip_market_report),
        "fill": len(A.FILL.findall(md_path.read_text(encoding="utf-8"))),
        "required": [f"{i['quadrant']}: {i['tag']} {i['name']}" for i in items],
        "previous": previous[0] if previous else None, "upstream": _upstream_summary(ups),
        "missing_inputs": requests, "unavailable": _unavailable(found), "outlook": outlook["path"],
    })


def _target(company: P.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, P.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = A.dated_files(company.analysis_dir, P.MD_SUFFIX)
    return files[-1] if files else None


def _outlook_path(text: str) -> str | None:
    """The outlook path in the md header ('—（…なし）' -> None)."""
    line = next((row for row in text.splitlines() if row.startswith("**地合い**:")), "")
    path = line.split(":", 1)[1].split("（")[0].strip() if line else ""
    return None if M.is_blank(path) else path


def result_json(company: P.Company, date: str, text: str, parsed: dict, judged: dict, items: list[dict],
                ups: dict) -> dict:
    found = I.gather_swot(company)
    previous = P.latest_result(company, before=date)
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date),
        "quadrants": {q: D.items_of(parsed, q) for q, _, _ in D.QUADRANTS},
        "required": items, "scale": X.scale(company),
        "top_strength": judged["top_strength"], "top_threat": judged["top_threat"],
        "answer": parsed["answer"], "answer_reason": parsed["answer_reason"], "measure": parsed["measure"],
        "sentence": parsed["sentence"], "verdict": judged["verdict"], "verdict_reason": judged["why"],
        "conservative": judged["conservative"],
        "handoff": {"step2_checks": parsed["step2_checks"], "summary": parsed["summary"],
                    "triggers": parsed["triggers"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "input_digests": I.input_digests(found), "upstream": _upstream_summary(ups),
        "outlook": _outlook_path(text),
        "previous": {"date": previous[0], "verdict": previous[1].get("verdict")} if previous else None,
        "md": company.rel(company.file(date, P.MD_SUFFIX)),
    }


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "swot.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    ups = upstream(company)
    # the required items are recomputed so a row deleted from 1.1 can't bypass the rule
    items = D.required_items(ups["five_forces"], ups["moat"])
    issues = D.validate(text, _template(root), items)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    issues = D.check_reference(parsed, P.latest_result(company, before=date))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    judged = D.judge(parsed)
    atomic_write_text(md_path, D.apply_conclusion(text, judged, parsed["sentence"]))
    result = result_json(company, date, text, parsed, judged, items, ups)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": judged["verdict"], "verdict_reason": judged["why"], "sentence": parsed["sentence"],
        "top_strength": judged["top_strength"], "top_threat": judged["top_threat"],
        "counts": {q: len(D.items_of(parsed, q)) for q, _, _ in D.QUADRANTS},
        "valid_until": result["valid_until"], "previous": result["previous"], "upstream": result["upstream"],
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
            p.add_argument("--skip-market-report", action="store_true",
                           help="market-report を1回実行しても地合いが古いまま進む（brief で「古い」と示す）")
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
