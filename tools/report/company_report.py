"""company-report orchestrator: STEP 1〜3 の分析結果をまとめた企業分析レポート（単一 HTML）。

Usage:
  company_report.py list
  company_report.py check   --company X [--redo]
  company_report.py prepare --company X [--redo] [--skip-prices] [--skip-market-report]
  company_report.py build   --company X [--date YYYY-MM-DD]

--company takes '3798', '3798_uls-group' or part of the directory name.
list:    companies with how many of the nine analyses are not fresh and the state of their latest report.
check:   the nine analyses in dependency order (each script's own evaluate()), the market outlook and today's
         report -> "next": the skill to run (five-forces ... valuation, market-report), prepare, write (FILL left),
         build (filled, not built) or report_existing.
prepare: fetch the share prices (tools/collect/stock_prices.py), compute every judgement into
         reports/{date}_company-report_facts.json, write {date}_company-report_brief.md (what the writer reads)
         and the {date}_company-report.md skeleton (conclusion table by script, FILL markers for the words).
build:   check the filled md against the template and facts.json, then write {date}_company-report.html and
         {date}_company-report.json.
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
sys.path[:0] = [str(HERE), str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import an_common as A  # noqa: E402
import cr_doc as D  # noqa: E402
import cr_facts as F  # noqa: E402
import cr_render as R  # noqa: E402
import cr_status as S  # noqa: E402
import stock_prices as SP  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE_DIR = A.REPO_ROOT / ".ai" / "templates" / "company-report"
FILL_KEY = re.compile(r"<!--\s*FILL:([\w-]+)")
HORIZON_ROW = re.compile(r"^\| (短期|中期|長期)（.*$", re.M)


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _template(root: Path, name: str) -> str:
    path = root / ".ai" / "templates" / "company-report" / name
    return (path if path.exists() else TEMPLATE_DIR / name).read_text(encoding="utf-8")


def _resolve(root: Path, arg: str | None) -> tuple[S.Company | None, dict | None]:
    if not arg:
        return None, {"ok": False, "error": "--company を指定する（候補は list で確認）"}
    company, candidates = S.resolve_company(root, arg)
    if company:
        return company, None
    if candidates:
        return None, {"ok": False, "error": f"「{arg}」に複数の企業が当たる", "candidates": candidates}
    return None, {"ok": False, "company_missing": True, "error": f"companies/ に「{arg}」の企業が無い。"
                  "collect-company-info（mode=full）で収集する（ホームページ URL が要る）"}


def _today(args: argparse.Namespace) -> str:
    return getattr(args, "date", None) or dt.date.today().isoformat()


def _compact(steps: list[dict]) -> list[dict]:
    return [{k: s[k] for k in ("step", "skill", "result", "date", "verdict", "reason")} for s in steps]


def _grade(s: dict) -> str:
    return s["grade"] + ("（暫定）" if s["pending"] else "")


# ---------- commands ----------

def cmd_list(args: argparse.Namespace, root: Path) -> int:
    today = _today(args)
    rows = []
    for path in A.company_dirs(root):
        company = S.Company(root, path)
        steps = [S.step_state(step, company, today) for step in S.STEPS]
        report = S.report_state(company)
        rows.append({"dir": company.dirname, "ticker": company.ticker, "name": company.display_name(),
                     "not_fresh": [s["skill"] for s in steps if s["result"] != "fresh"],
                     "report_date": report["date"], "report_state": report["state"]})
    return emit({"ok": True, "companies": rows})


def cmd_check(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = _today(args)
    status = S.check(root, company, today, args.redo, args.use_existing)
    return emit({"ok": True, "company": company.dirname, "name": company.display_name(), "date": today,
                 "steps": _compact(status["steps"]), "outlook": status["outlook"], "report": status["report"],
                 "next": status["next"]})


def _prepare_gate(status: dict, args: argparse.Namespace) -> str | None:
    pending = [s for s in status["steps"] if not S.usable(s, args.use_existing)]
    if pending:
        first = pending[0]
        hint = "" if args.use_existing or first["result"] != "triggered" else \
            "（作り直さずに既存の結果を使うなら --use-existing）"
        return (f"先に {first['skill']} を最後まで実行する（{first['result']}: {first['reason']}）{hint}。"
                f"新しくないもの: {', '.join(s['skill'] for s in pending)}")
    if status["outlook"].get("stale") and not args.skip_market_report:
        return ("地合い判断（outlook.md）が無いか35日より古い。先に market-report を実行する"
                "（実行しても作れなかったときだけ --skip-market-report）")
    if status["next"] == "report_existing":
        return "今日のレポートは build 済み。作り直すのはユーザーが指示したときだけ（--redo）"
    return None


def _refresh_table(md: str, facts: dict) -> str:
    """A started draft keeps its words; the script-owned conclusion rows follow today's facts."""
    rows = iter(D.horizon_rows(facts).splitlines())
    return HORIZON_ROW.sub(lambda _: next(rows, ""), md)


def cmd_prepare(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    today = _today(args)
    status = S.check(root, company, today, args.redo, args.use_existing)
    gate = _prepare_gate(status, args)
    if gate:
        return emit({"ok": False, "error": gate, "next": status["next"], "steps": _compact(status["steps"])})
    prices = ({"ok": False, "skipped": True} if args.skip_prices
              else SP.run(root, company.dirname, SP.DEFAULT_YEARS, today))
    facts = F.build(root, company, today, status)
    md_path, brief_path = company.file(today, S.MD_SUFFIX), company.file(today, S.BRIEF_SUFFIX)
    kept = md_path.exists() and A.is_draft(md_path) and not args.redo
    atomic_write_text(company.file(today, S.FACTS_SUFFIX), json.dumps(facts, ensure_ascii=False, indent=1) + "\n")
    atomic_write_text(brief_path, D.render_brief(facts, company.rel(md_path)))
    if kept:
        atomic_write_text(md_path, _refresh_table(md_path.read_text(encoding="utf-8"), facts))
    else:
        atomic_write_text(md_path, D.render_skeleton(_template(root, "report.md"), facts, company.rel(brief_path)))
    md_text = md_path.read_text(encoding="utf-8")
    return emit({
        "ok": True, "company": company.dirname, "date": today, "brief": company.rel(brief_path),
        "md": company.rel(md_path), "kept": kept, "fill_keys": FILL_KEY.findall(md_text),
        "prices": {k: prices[k] for k in ("ok", "skipped", "rows", "first", "last", "error") if k in prices},
        "price_source": facts["prices"]["source"], "step1": _grade(facts["step1"]), "step2": _grade(facts["step2"]),
        "step3": facts["step3"]["verdict"],
        "horizons": {k: D.verdict_label(h) for k, h in facts["horizons"].items()},
        "outlook": facts["outlook"].get("path"), "outlook_stale": facts["outlook"].get("stale"),
        "used_existing": [f"{s['skill']}（{s['date']}）" for s in facts["stale"]],
    })


def _target(company: S.Company, date: str | None) -> tuple[str, Path] | None:
    if date:
        path = company.file(date, S.MD_SUFFIX)
        return (date, path) if path.exists() else None
    files = A.dated_files(company.reports_dir, S.MD_SUFFIX)
    return files[-1] if files else None


def result_json(company: S.Company, facts: dict, date: str, warnings: list[str]) -> dict:
    p = facts["prices"]
    w52 = next((w for w in p.get("ranges") or [] if w["label"] == "52週"), None)
    return {
        "company": company.dirname, "name": facts["name"], "date": date, "market": facts["market"],
        "horizons": {k: {"verdict": h["verdict"], "provisional": h["provisional"], "why": h["why"]}
                     for k, h in facts["horizons"].items()},
        "step1": {k: facts["step1"][k] for k in ("grade", "pending", "why")},
        "step2": {k: facts["step2"][k] for k in ("grade", "pending", "why", "mismatch")},
        "step3": facts["step3"], "price": facts["price"],
        "price_range": {"source": p["source"], "current": p.get("current"), "first": p.get("first"),
                        "last": p.get("last"), "position_52w": w52["position"] if w52 else None},
        "analyses": {k: {"date": a["date"], "verdict": a["verdict"]} for k, a in facts["analyses"].items()},
        "outlook": facts["outlook"].get("path"), "review": facts["review"], "warnings": warnings,
        "used_existing": [{k: s[k] for k in ("skill", "date", "reason")} for s in facts.get("stale") or []],
        "md": company.rel(company.file(date, S.MD_SUFFIX)), "html": company.rel(company.file(date, S.HTML_SUFFIX)),
    }


def cmd_build(args: argparse.Namespace, root: Path) -> int:
    company, error = _resolve(root, args.company)
    if error:
        return emit(error)
    target = _target(company, args.date)
    if not target:
        return emit({"ok": False, "error": "company-report.md が無い（先に prepare）"})
    date, md_path = target
    facts = A.load_result(company.file(date, S.FACTS_SUFFIX))
    if not facts:
        return emit({"ok": False, "error": f"{date} の facts.json が無い（prepare をやり直す）"})
    text = md_path.read_text(encoding="utf-8")
    issues, warnings = D.validate(text, _template(root, "report.md"), facts)
    if issues:
        return emit({"ok": False, "md": company.rel(md_path), "issues": issues, "warnings": warnings})
    html_path, json_path = company.file(date, S.HTML_SUFFIX), company.file(date, S.JSON_SUFFIX)
    atomic_write_text(html_path, R.render(_template(root, "report.html"), facts, D.parse(text), text))
    result = result_json(company, facts, date, warnings)
    atomic_write_text(json_path, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    return emit({"ok": True, "html": result["html"], "json": company.rel(json_path), "date": date,
                 "horizons": {k: D.verdict_label(h) for k, h in facts["horizons"].items()},
                 "step1": _grade(facts["step1"]), "step2": _grade(facts["step2"]), "step3": facts["step3"]["verdict"],
                 "warnings": warnings})


def main(argv: list[str] | None = None, root: Path = A.REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    lister = sub.add_parser("list")
    lister.add_argument("--date", help="YYYY-MM-DD（今日の代わり）")
    for name in ("check", "prepare", "build"):
        p = sub.add_parser(name)
        p.add_argument("--company", help="銘柄コード・企業ディレクトリ名・社名の一部")
        p.add_argument("--date", help="YYYY-MM-DD（check/prepare: 今日の代わり、build: 対象のレポートの日付）")
        if name in ("check", "prepare"):
            p.add_argument("--redo", action="store_true", help="今日の build 済み・作成途中のレポートがあっても作り直す")
            p.add_argument("--use-existing", action="store_true",
                           help="分析後に材料が変わった（triggered）分析を作り直さず既存の結果で進む（レポートに明記）。"
                                "期限切れ・未実施・作成途中の分析は実行する")
        if name == "prepare":
            p.add_argument("--skip-prices", action="store_true", help="株価を取りに行かない（data/prices.csv をそのまま使う）")
            p.add_argument("--skip-market-report", action="store_true",
                           help="地合い判断が古いまま進む（market-report を実行しても作れなかったときだけ）")
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
