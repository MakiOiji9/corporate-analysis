"""valuation orchestrator (企業分析フレームワーク.md STEP 3 バリュエーション): everything except the background text.

Usage:
  valuation.py list
  valuation.py check   --company X
  valuation.py prepare --company X [--redo] [--skip-collect]
  valuation.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies under companies/ with the state of their valuation result (for choosing one).
check:   is the latest result still valid (7 days, the sections and the numbers it used unchanged)? Is the growth
         analysis finished and valid (required upstream)? Which inputs are missing, and is the price older than
         7 days? -> "next".
prepare: analysis/valuation/{date}_brief.md (what the writer reads) and the {date}_valuation.md skeleton
         (every table and judgement computed, FILL markers for the background only).
build:   check the filled md, write the conclusion (STEP 3 割安/妥当/割高/判定保留) and {date}_valuation.json.
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
import freshness as T  # noqa: E402
import gr_paths as GP  # noqa: E402
import growth as GR  # noqa: E402
import mdparse as M  # noqa: E402
import sw_paths as WP  # noqa: E402
import va_brief as B  # noqa: E402
import va_doc as D  # noqa: E402
import va_inputs as I  # noqa: E402
import va_metrics as X  # noqa: E402
import va_paths as P  # noqa: E402
import va_rules as R  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "valuation" / "valuation.md"
OUTLOOK_HEADER = re.compile(r"^\*\*地合い\*\*:\s*(.+)$", re.M)
SERIES_KEY = "numbers"  # input_digests entry for every number (read beyond the SPECS sections)
FILL_KEY = re.compile(r"<!--\s*FILL:([\w-]+)")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "valuation" / "valuation.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


def _growth_company(company: P.Company) -> GP.Company:
    return GP.Company(company.root, company.path)


def _summary(result: tuple[str, dict] | None) -> dict | None:
    return {"date": result[0], "verdict": result[1].get("verdict")} if result else None


# ---------- state ----------

def _upstream_changes(company: P.Company, result: dict) -> list[str]:
    """Upstream analyses (growth, the other STEP 2 analyses, SWOT) whose conclusion differs from the one this result
    recorded at build. Only the conclusion counts: a re-run that reaches the same verdict re-opens nothing."""
    recorded = result.get("upstream") or {}
    labels = {k: lb for k, _, lb in X.UPSTREAM}
    out = []
    for key, value in X.others(company).items():
        before, after = (recorded.get(key) or {}).get("verdict"), (value or {}).get("verdict")
        if before != after:
            out.append(f"{labels.get(key, key)}分析の結論が {before or '未実施'} → {after or '未実施'} に変わった")
    return out

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
        state["newer_raw"] = T.triggers(company, date, "annual_results") + _upstream_changes(company, result)
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="バリュエーション分析の結果が無い")
    elif state["newer_raw"]:
        state.update(result="triggered", reason="; ".join(state["newer_raw"]))
    elif today > state["latest"]["valid_until"]:
        state.update(result="expired", reason=f"有効期限 {state['latest']['valid_until']} を過ぎた（株価が動いている）")
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


def _next_step(company: P.Company, result: str, growth_result: str, requests: list[dict]) -> str:
    if result == "fresh":
        return "report_existing"
    if not _has_raw(company):
        return "collect"
    if growth_result != "fresh":
        return "growth"  # STEP 2-2 first; the growth skill runs collection itself
    if requests:
        return "collect"
    return "prepare"  # the growth verdict does not stop the valuation


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        raw_dates = [d for kind in I.TRIGGER_KINDS for d, _ in I.raw_files(company, kind)]
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "last_collected": max(raw_dates) if raw_dates else None, "valuation": state["result"],
                     "valuation_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "growth": _summary(GP.latest_result(_growth_company(company)))})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    growth = GR.evaluate(_growth_company(company), today)
    found = I.gather_valuation(company)
    cands = X.candidates(company, found, today)
    requests = X.collect_requests(company, found, cands)
    outlook = A.latest_outlook(root, today)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "growth": {"result": growth["result"], "reason": growth["reason"], "latest": growth["latest"]},
                 "price_date": cands["base"]["price"]["date"], "price_age": cands["price_age"],
                 "needs_full_collect": not _has_raw(company), "missing_inputs": requests,
                 "unavailable": _unavailable(found), "outlook": outlook,
                 "next": _next_step(company, state["result"], growth["result"], requests)})


def _growth_header(company: P.Company) -> str:
    result = GP.latest_result(_growth_company(company))
    if not result:
        return "—（完成済みの成長性分析なし）"
    date, r = result
    md = company.rel(_growth_company(company).file(date, GP.MD_SUFFIX))
    rating = (r.get("step3") or {}).get("rating", "—")
    return f"{md}（成長性 {r.get('verdict', '—')}、会社計画の信頼性 {rating}）"


def _upstream_header(cands: dict) -> str:
    parts = [f"{label} {(cands['upstream'].get(key) or {}).get('verdict') or '未実施'}" for key, _, label in X.UPSTREAM]
    return "、".join(parts) + "（5章の手順3 最終確認に使う）"


def _values(company: P.Company, date: str, found: dict, outlook: dict, cands: dict) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None})
    price = cands["base"]["price"]
    age = cands["price_age"]
    return {"company": company.display_name(), "date": date,
            "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)), "inputs": ", ".join(inputs) or "—",
            "valid_until": P.valid_until(date),
            "price_date": f"{price['date'] or '不明'}（分析日の{age if age is not None else '—'}日前。"
                          f"{X.yen(price['price'], price['currency'])}）",
            "growth": _growth_header(company), "upstream": _upstream_header(cands),
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週。参照のみ。判定には使わない）"
                        if outlook["path"] else "—（完成済みの outlook.md なし）")}


def _skeleton(root: Path, company: P.Company, date: str, found: dict, outlook: dict, cands: dict,
              today: str) -> str:
    alt = X.candidates(company, found, today, "あり") if D.pbr_pending(cands) else None
    return D.render_skeleton(_template(root), _values(company, date, found, outlook, cands), cands, alt)


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
    found = I.gather_valuation(company)
    cands = X.candidates(company, found, today)
    requests = X.collect_requests(company, found, cands)
    draft = P.latest_draft(company)
    untouched = bool(draft) and A.is_untouched(company.file(draft[0], P.BRIEF_SUFFIX), draft[1])
    kept = state["result"] == "draft" and not args.redo and not untouched  # an older draft behind a built result is abandoned
    growth = GR.evaluate(_growth_company(company), today)
    blocking = _next_step(company, "none", growth["result"], requests)
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
    swot = WP.latest_result(WP.Company(company.root, company.path))
    brief = B.render_brief(company, date, P.valid_until(date), found, cands, previous,
                           GP.latest_result(_growth_company(company)), swot, outlook, warnings)
    if not kept:
        skeleton = _skeleton(root, company, date, found, outlook, cands, today)
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, brief)
    md_text = md_path.read_text(encoding="utf-8")
    return emit({
        "ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "regenerated": untouched and not args.redo,
        "skipped_collect": requests if blocking == "collect" else [], "warnings": warnings,
        "fill": len(A.FILL.findall(md_text)), "fill_keys": FILL_KEY.findall(md_text),
        "candidate": {"verdict": cands["verdict"], "why": cands["why"],
                      **{name: cands[key]["rating"] for key, name in X.INDICATORS}},
        "measures_matter": D.pbr_pending(cands), "price_date": cands["base"]["price"]["date"],
        "price_age": cands["price_age"], "borderline": cands["borderline"],
        "previous": previous[0] if previous else None, "growth": growth["result"],
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


def _clean(d: dict, keys: tuple[str, ...]) -> dict:
    return {k: _round(d.get(k)) for k in keys}


def _rule_json(rule: dict | None) -> dict | None:
    if not rule:
        return None
    return {"rating": rule["rating"], "basis": rule["basis"], "single_axis": rule["single_axis"],
            "axis1": _clean(rule["axis1"], ("zone", "position", "low", "high", "basis")),
            "axis2": _clean(rule["axis2"], ("zone", "raw_zone", "median", "diff", "count", "explained", "basis"))}


def _items_json(cands: dict) -> dict:
    per, pbr, peg, ev = cands["per"], cands["pbr"], cands["peg"], cands["ev"]
    return {
        "per": {"rating": per["rating"], "sentence": per["sentence"], "used": per["used"],
                "per_actual": _round(per["per_actual"]), "per_forecast": _round(per["per_forecast"]),
                "discount": per["discount"], "na": per["na"], "rule": _rule_json(per["rule"]),
                "eps": _clean(per["step1"], ("year", "eps", "eps_used", "adjusted", "share", "gain", "loss"))},
        "pbr": {"rating": pbr["rating"], "sentence": pbr["sentence"], "pbr": _round(pbr["pbr"]),
                "before_trap": pbr["before_trap"], "rule": _rule_json(pbr["rule"]),
                "fair": _clean(pbr["fair"], ("fair", "roe", "roe_basis", "average_per", "average_basis", "diff",
                                             "rating")),
                "trap": pbr["trap"], "measures": pbr["trap"]["measures"]},
        "peg": {"rating": peg["rating"], "sentence": peg["sentence"], "na": peg["na"], "margin": peg["margin"],
                "candidates": [{"name": c["name"], "value": _round(c["value"])} for c in peg["candidates"]],
                "cases": {k: _round(v) for k, v in peg["cases"].items()},
                "peg": {k: _round(v) for k, v in peg["peg"].items()}},
        "ev": {"rating": ev["rating"], "sentence": ev["sentence"], "value": _round(ev["value"]),
               "rule": _rule_json(ev["rule"]),
               **_clean(ev, ("year", "debt", "cash", "operating_income", "depreciation", "ebitda", "ev", "net_cash")),
               "market_cap": _round((ev["market_cap"] or {}).get("value")),
               "history": [_clean(h, ("year", "high", "low", "basis")) for h in ev["history"]],
               "divergence": ev["divergence"],
               "sensitivity": ({k: _round(v) for k, v in ev["sensitivity"].items()}
                               if ev.get("sensitivity") else None)},
    }


def result_json(company: P.Company, date: str, text: str, parsed: dict, cands: dict) -> dict:
    found = I.gather_valuation(company)
    previous = P.latest_result(company, before=date)
    base, s3 = cands["base"], cands["step3"]
    return {
        "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "verdict": cands["verdict"], "verdict_reason": cands["why"],
        "conservative": ([f"点数になった指標が {next(iter(s3['scores']))} だけ（材料不足のため1指標で判定）"]
                         if s3.get("single") else []),
        "price": {"value": base["price"]["price"], "date": base["price"]["date"], "currency": base["price"]["currency"]},
        **_items_json(cands),
        "step3": {"ratings": s3["ratings"], "scores": s3["scores"], "average": _round(s3["average"]),
                  "raw_verdict": s3["raw_verdict"], "final_check": s3["final_check"]},
        "sheet": D.sheet_cell(cands), "flip_prices": cands["flip_prices"], "borderline": cands["borderline"],
        "handoff": {"report_points": parsed["report_points"], "final_checks": parsed["final_checks"],
                    "special_bg": parsed["special_bg"], "measures": parsed["measures"],
                    "divergence_bg": parsed["divergence_bg"], "cheap_reason": parsed["cheap_reason"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "peers": [_clean(p, ("name", "per_actual", "per_forecast", "pbr", "ev_ebitda_calc", "cagr", "roe"))
                  for p in base["peers"]["peers"]],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "seen": I.raw_seen(company),
        "input_digests": {**I.input_digests(found), SERIES_KEY: X.series_digest(cands)},
        "growth": {"date": cands["growth_date"]}, "upstream": cands["upstream"],
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
        return emit({"ok": False, "error": "valuation.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    parsed = D.parse(text)
    # the numbers are recomputed (with the writer's measures answer) so edited cells cannot change the conclusion;
    # the analysis day is the reference for the price's age
    found = I.gather_valuation(company)
    cands = X.candidates(company, found, date, parsed["measures_choice"])
    brief = company.file(date, P.BRIEF_SUFFIX)
    reference = brief.read_text(encoding="utf-8") if brief.exists() else ""
    issues = D.validate(text, _template(root), cands, reference)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    atomic_write_text(md_path, D.apply_conclusion(text, cands))
    result = result_json(company, date, text, parsed, cands)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
        "verdict": cands["verdict"], "verdict_reason": cands["why"],
        **{name: f"{cands[key]['rating']}: {cands[key]['sentence']}" for key, name in X.INDICATORS},
        "sheet": result["sheet"], "flip_prices": cands["flip_prices"], "price": result["price"],
        "valid_until": result["valid_until"], "previous": result["previous"], **D.flags(parsed, cands),
        "gaps": [g for g in parsed["gaps"] if not M.is_blank(g) and g != "なし"],
        "pending": [name for key, name in X.INDICATORS if cands[key]["rating"] == R.PENDING],
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
                           help="収集を1回試しても材料が足りない（株価が古い）まま進む（brief の警告・取れていない材料に出る）")
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
