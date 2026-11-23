"""investment orchestrator (投資の質: 何に投資したか・変化点・投資効率・中計/潮流との整合・競合比較): all but the writer's text.

Usage:
  investment.py list
  investment.py check   --company X
  investment.py prepare --company X [--redo] [--skip-collect]
  investment.py fill    --company X [--from JSON] [--build]
  investment.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
check:   is the latest result still valid (365 days, no newer annual report / mid-term plan / industry data, no
         changed five-forces / 3C conclusion)? Which inputs are missing (the yearly capex series, and for a Japanese
         company data/investments.json from the annual reports' XBRL)? -> "next".
prepare: analysis/investment/{date}_brief.md and the {date}_investment.md skeleton (every number, change point and
         (a)〜(h) computed; FILL for what was invested, the themes, the backgrounds and the plan / trend classes).
build:   check the filled md, aggregate ② and ③ from the writer's classes, write the conclusion (投資の質
         良好/普通/懸念/判定保留) and {date}_investment.json.
The numbers of the growth investment (ratio, incremental ROIC) are gr_invest's, computed here from the same inputs as
the growth analysis, so this analysis does not wait for a growth result. stdout is one JSON line. Exit 1 when not ok.
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

import an_brief as AB  # noqa: E402
import an_common as A  # noqa: E402
import an_fill as AF  # noqa: E402
import an_quality as Q  # noqa: E402
import ff_paths as FP  # noqa: E402
import freshness as T  # noqa: E402
import gr_inputs as GI  # noqa: E402
import gr_metrics as GX  # noqa: E402
import gr_paths as GP  # noqa: E402
import iv_brief as B  # noqa: E402
import iv_doc as D  # noqa: E402
import iv_inputs as I  # noqa: E402
import iv_metrics as X  # noqa: E402
import iv_paths as P  # noqa: E402
import mt_returns as R  # noqa: E402
import tc_paths as TP  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = A.REPO_ROOT / ".ai" / "templates" / "investment" / "investment.md"
INVEST_ITEM = "有報 XBRL: 何に投資したか（yuho_investments.py の data/investments.json）"
SERIES_ITEM = "財務時系列: 設備投資・減価償却費（5年以上）"
UPSTREAM = (("ファイブフォース", FP), ("3C", TP))


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path) -> str:
    path = root / ".ai" / "templates" / "investment" / "investment.md"
    return (path if path.exists() else TEMPLATE).read_text(encoding="utf-8")


def _growth_result(company: P.Company) -> tuple[str, dict] | None:
    return GP.latest_result(GP.Company(company.root, company.path))


def compute(company: P.Company, cls: dict | None = None) -> tuple[dict, dict, dict | None]:
    """(investment candidates, the inputs found, investments.json). cls: the writer's classes (build)."""
    growth_found = GI.gather_growth(company)
    growth = GX.candidates(company, growth_found)
    invest = X.load_investments(company)
    cls = cls or {}
    cands = X.candidates(company, growth, invest, cls.get("year_themes"), cls.get("mtp_class"),
                         cls.get("outcomes", ()), cls.get("trend_classes", ()))
    # ④ compares with the peers' growth-investment table (moved here from the growth analysis with 手順5)
    cands["peer_request"] = GX.peer_request(growth_found, company, growth, I.unavailable_items(company))
    return cands, I.gather_investment(company), invest


# ---------- state ----------

def evaluate(company: P.Company, today: str) -> dict:
    latest = P.latest_result(company)
    draft = P.latest_draft(company)
    state: dict = {"latest": None, "draft": company.rel(draft[1]) if draft else None, "newer_raw": []}
    if latest:
        date, result = latest
        state["latest"] = {"date": date, "md": company.rel(company.file(date, P.MD_SUFFIX)),
                           "json": company.rel(company.file(date, P.JSON_SUFFIX)),
                           "verdict": result.get("verdict"), "valid_until": P.valid_until(date)}
        state["newer_raw"] = T.triggers(company, date, "annual", list(UPSTREAM))
        old_rules = Q.outdated(result, D.VERSION)
        if old_rules:
            state["newer_raw"] = state["newer_raw"] + [old_rules]
    if draft and (not latest or draft[0] >= latest[0]):
        state.update(result="draft", reason=f"作成途中の {company.rel(draft[1])} がある（続きから書く）")
    elif not latest:
        state.update(result="none", reason="投資の質の分析の結果が無い")
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


def _has_xbrl(company: P.Company) -> bool:
    manifest = company.path / "sources" / "manifest.csv"
    return manifest.exists() and "edinet-csv" in manifest.read_text(encoding="utf-8")


def collect_requests(company: P.Company, cands: dict, invest: dict | None) -> list[dict]:
    unavailable = I.unavailable_items(company)
    items = []
    if not cands["rows"] and not cands["excluded"]:
        items.append(SERIES_ITEM)
    if R.market(company) == "japan" and not invest and not any("investments" in u for u in unavailable):
        items.append(INVEST_ITEM)
    hints = ["有報の XBRL→CSV（sources/ の edinet-csv）があれば yuho_investments.py --company {dir} を1回実行するだけでよい"] \
        if INVEST_ITEM in items and _has_xbrl(company) else []
    out = [{"agent": "collect-filings", "items": items, "hints": hints}] if items else []
    if cands.get("peer_request"):
        out.append({"agent": "collect-peers-valuation", "items": [cands["peer_request"]],
                    "hints": ["雛形 competitors.md「成長投資の材料」（競合ごとに設備投資・減価償却費・研究開発費を最大5期）"]})
    return out


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


def _next_step(company: P.Company, result: str, requests: list[dict]) -> str:
    if result == "fresh":
        return "report_existing"
    if not _has_raw(company) or requests:
        return "collect"
    return "prepare"


def _summary(result: tuple[str, dict] | None) -> dict | None:
    return {"date": result[0], "verdict": result[1].get("verdict")} if result else None


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = dt.date.today().isoformat()
    rows = []
    for path in A.company_dirs(root):
        company = P.Company(root, path)
        state = evaluate(company, today)
        rows.append({"dir": company.dirname, "peer_only": A.peer_only(path),
                     "ticker": company.ticker, "name": company.display_name(), "investment": state["result"],
                     "investment_date": (state["latest"] or {}).get("date"),
                     "verdict": (state["latest"] or {}).get("verdict"),
                     "has_investments_json": (path / "data" / "investments.json").exists()})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    cands, found, invest = compute(company)
    requests = collect_requests(company, cands, invest)
    outlook = A.latest_outlook(root, today)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), **state,
                 "growth": _summary(_growth_result(company)), "needs_full_collect": not _has_raw(company),
                 "missing_inputs": requests, "outlook": outlook, "outlook_stale": outlook["stale"],
                 "next": _next_step(company, state["result"], requests)})


def _values(company: P.Company, date: str, found: dict, outlook: dict, invest: dict | None) -> dict:
    inputs = sorted({f.path.name for f in found.values() if f.path is not None}
                    | ({"data/investments.json", "data/financials.csv"} if invest else {"data/financials.csv"}))
    growth = _growth_result(company)
    return {"company": company.display_name(), "date": date, "brief": company.rel(company.file(date, P.BRIEF_SUFFIX)),
            "inputs": ", ".join(inputs), "valid_until": P.valid_until(date),
            "growth": (f"{company.rel(GP.Company(company.root, company.path).file(growth[0], GP.MD_SUFFIX))}（成長性 "
                       f"{growth[1].get('verdict', '—')}）") if growth else "—（完成済みの成長性分析なし。数値は同じ計算をこの分析で行う）",
            "outlook": (f"{outlook['path']}（{outlook['age_days']} 日前の週）" if outlook["path"]
                        else "—（完成済みの outlook.md なし）")}


def _warnings(cands: dict, invest: dict | None) -> list[str]:
    out = []
    if invest and invest.get("missing"):
        out.append("有報の文章ブロックが見つからない期がある: " + "、".join(
            f"{k} {len(v)}期" for k, v in invest["missing"].items()))
    if cands["top_segment"] and re.search(r"[A-Za-z]", cands["top_segment"]["segment"]):
        out.append("セグメント名は XBRL の英語の要素名（例 Robotics）。1章の主な内容・本文では有報の日本語のセグメント名で書く")
    return out


def cmd_prepare(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = args.date or dt.date.today().isoformat()
    state = evaluate(company, today)
    if state["result"] == "fresh" and not args.redo:
        return emit({"ok": False, "error": state["reason"] + "。作り直すのはユーザーが指示したときだけ（--redo）",
                     "latest": state["latest"]})
    redo_built = args.redo and company.file(today, P.JSON_SUFFIX).exists()
    cands, found, invest = compute(company)
    requests = collect_requests(company, cands, invest)
    draft = P.latest_draft(company)
    untouched = bool(draft) and A.is_untouched(company.file(draft[0], P.BRIEF_SUFFIX), draft[1])
    kept = state["result"] == "draft" and not args.redo and not untouched
    blocking = _next_step(company, "none", requests)
    gate = None if kept else A.prepare_gate(blocking, _has_raw(company), args.skip_collect)
    if gate:
        return emit({"ok": False, "error": gate, "next": blocking, "missing_inputs": requests})
    if untouched and draft[0] != today:
        for suffix in (P.MD_SUFFIX, P.BRIEF_SUFFIX):
            company.file(draft[0], suffix).unlink(missing_ok=True)
    date = draft[0] if kept and draft else today
    previous = P.latest_result(company, before=date)
    outlook = A.latest_outlook(root, today)
    warnings = _warnings(cands, invest)
    superseded = A.supersede_today(company.file(today, P.JSON_SUFFIX).parent, today) if redo_built else None
    brief_path, md_path = company.file(date, P.BRIEF_SUFFIX), company.file(date, P.MD_SUFFIX)
    brief_path.parent.mkdir(parents=True, exist_ok=True)
    brief = B.render_brief(company, root, date, P.valid_until(date), found, cands, invest, previous,
                           _growth_result(company), outlook)
    if warnings:
        brief = brief.replace("\n## 0. 前提", "\n## 警告（執筆の前に確かめ、完了報告に書く）\n\n"
                              + "\n".join(f"- {w}" for w in warnings) + "\n\n## 0. 前提", 1)
    auto = D.auto_fills(cands, previous, found, warnings)
    if kept:
        atomic_write_text(md_path, AF.prefill(md_path.read_text(encoding="utf-8"), auto))
    else:
        skeleton = AF.prefill(D.render_skeleton(_template(root), _values(company, date, found, outlook, invest), cands),
                              auto)
        atomic_write_text(md_path, skeleton)
        brief = A.mark_skeleton(brief, skeleton)
    atomic_write_text(brief_path, AB.dedupe(brief, company, brief_path.parent, date))
    return emit({"ok": True, "company": company.dirname, "date": date, "brief": company.rel(brief_path),
                 "superseded": company.rel(superseded) if superseded else None, "md": company.rel(md_path),
                 "kept": kept, "regenerated": untouched and not args.redo,
                 "skipped_collect": requests if blocking == "collect" else [], "warnings": warnings,
                 **AF.prepare_fields(company, md_path),
                 "candidate": {"verdict": cands["verdict"], "why": cands["why"],
                               **{k: v["rating"] for k, v in cands["axes"].items()}},
                 "years": [r["year"] for r in cands["rows"]], "points": len(cands["points"]),
                 "plan_years": [p["year"] for p in cands["plan_years"]], "has_investments_json": bool(invest),
                 "previous": previous[0] if previous else None, "outlook": outlook["path"]})


def _target(company: P.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, P.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = A.dated_files(company.analysis_dir, P.MD_SUFFIX)
    return files[-1] if files else None


def _allowed_text(root: Path, company: P.Company, date: str, found: dict, cands: dict, invest: dict | None) -> str:
    brief = company.file(date, P.BRIEF_SUFFIX)
    outlook = A.latest_outlook(root, date)
    skeleton = D.render_skeleton(_template(root), _values(company, date, found, outlook, invest), cands)
    auto = D.auto_fills(cands, P.latest_result(company, before=date), found, _warnings(cands, invest))
    return "\n".join([AB.read_brief(brief, company.root), skeleton, AF.auto_reference(auto)])


def _round(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()
                    if k in ("year", "sales", "capex", "depreciation", "capex_to_dep", "rnd", "acquisition", "impairment",
                             "goodwill", "ppe", "cip", "capex_share", "rnd_share", "mix")})
    return out


def result_json(company: P.Company, date: str, parsed: dict, cands: dict, found: dict) -> dict:
    previous = P.latest_result(company, before=date)
    return {
        "version": D.VERSION, "company": company.dirname, "name": company.display_name(), "date": date,
        "valid_until": P.valid_until(date), "verdict": cands["verdict"], "verdict_reason": cands["why"],
        "axes": {k: {"rating": v["rating"], "sentence": v["sentence"]} for k, v in cands["axes"].items()},
        "checks": {k: {"name": v["name"], "status": v["status"], "detail": v["detail"]} for k, v in cands["checks"].items()},
        "rows": _round(cands["rows"]), "points": cands["points"], "top_segment": cands["top_segment"],
        "years": [{"year": y["year"], "content": y["content"], "themes": y["themes"]} for y in parsed["years"]],
        "themes": parsed["themes"], "mtp": {"text": parsed["mtp_text"], "class": parsed["mtp_class"]},
        "plans": parsed["plans"], "point_backgrounds": parsed["points"],
        "handoff": {"report_points": parsed["report_points"], "triggers": parsed["triggers"]},
        "growth_investment": {"verdict": cands["step5"].get("verdict"), "sentence": cands["step5"].get("sentence"),
                              "ratio": cands["ratio"]},
        "changes": parsed["changes"], "gaps": parsed["gaps"],
        "inputs": sorted({company.rel(f.path) for f in found.values() if f.path is not None}),
        "seen": I.raw_seen(company), "input_digests": I.input_digests(found),
        "growth": _summary(_growth_result(company)),
        "previous": {"date": previous[0], "verdict": previous[1].get("verdict")} if previous else None,
        "md": company.rel(company.file(date, P.MD_SUFFIX)),
    }


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "investment.md が無い（先に prepare）"})
    date, md_path = target
    text = md_path.read_text(encoding="utf-8")
    base, found, invest = compute(company)  # without the writer's classes: the rows and change points of the skeleton
    issues = D.validate(text, _template(root), base, _allowed_text(root, company, date, found, base, invest))
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues})
    parsed = D.parse(text)
    cands, _, _ = compute(company, D.classes(parsed))
    atomic_write_text(md_path, D.apply_conclusion(text, cands))
    result = result_json(company, date, parsed, cands, found)
    json_path = company.file(date, P.JSON_SUFFIX)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    pruned = A.prune(company.analysis_dir, P.MD_SUFFIX)
    return emit({"ok": True, "md": company.rel(md_path), "json": company.rel(json_path), "date": date,
                 "pruned": [company.rel(p) for p in pruned], "verdict": cands["verdict"],
                 "verdict_reason": cands["why"],
                 "axes": {k: f"{v['rating']}: {v['sentence']}" for k, v in cands["axes"].items()},
                 "points": [f"{p['year']} {p['kind']}" for p in cands["points"]],
                 "themes": [f"{t['id']} {t['name']}（{t['trend']}）" for t in parsed["themes"]],
                 "valid_until": result["valid_until"], "previous": result["previous"],
                 "gaps": [g for g in parsed["gaps"] if g and g != "なし"]})


def cmd_fill(args: argparse.Namespace, root: Path) -> int:
    return AF.cmd_fill(args, root, resolve=_resolve, target=_target, build=cmd_build, name="investment.md",
                      emit=emit, write=atomic_write_text)


def main(argv: list[str] | None = None, root: Path = A.REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    for name in ("check", "prepare", "fill", "build"):
        p = sub.add_parser(name)
        p.add_argument("--company", help="銘柄コード・企業ディレクトリ名・社名の一部")
        p.add_argument("--date", help="YYYY-MM-DD（check/prepare: 今日の代わり、build: 対象の分析日）")
        if name == "prepare":
            p.add_argument("--redo", action="store_true", help="有効な結果・作成途中の結果があっても作り直す")
            p.add_argument("--skip-collect", action="store_true", help="収集を1回試しても材料が足りないまま進む")
        if name == "fill":
            AF.add_fill_args(p)
    args = parser.parse_args(argv)
    if getattr(args, "date", None):
        try:
            dt.date.fromisoformat(args.date)
        except ValueError:
            return emit({"ok": False, "error": f"--date は YYYY-MM-DD で指定する: {args.date}"})
    handler = {"list": cmd_list, "check": cmd_check, "prepare": cmd_prepare, "fill": cmd_fill, "build": cmd_build}[args.cmd]
    return handler(args, root)


if __name__ == "__main__":
    sys.exit(main())
