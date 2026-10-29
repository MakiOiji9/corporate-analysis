"""market-report orchestrator: everything except writing the judgement text.

Usage:
  market_report.py check   [--week YYYY-MM-DD]                    # is this week's material collected?
  market_report.py prepare [--week YYYY-MM-DD] [--redo] [--allow-stale]
  market_report.py build   [--week YYYY-MM-DD]

--week takes any date of the report week (default: today); files are named after its Monday.
check:   freshness of market/LATEST.md against the report week, running collections, report state.
prepare: market/report/{week}_facts.json (numbers, chart series, dates, documents),
         {week}_brief.md (what the writer reads) and the {week}_outlook.md skeleton (FILL markers).
         A draft outlook (FILL left) is kept unless --redo; a finished one needs --redo.
build:   check outlook.md (template structure, FILL, judgement words, forbidden phrases) and
         render {week}_market-report.html (one self-contained file).
stdout is one JSON line so the calling agent spends few tokens. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "collect" / "market"), str(HERE.parent / "collect")]  # python -I

import backtest as BT  # noqa: E402
import brief as B  # noqa: E402
import consistency as K  # noqa: E402
import facts as F  # noqa: E402
import outlook as O  # noqa: E402
import slides as S  # noqa: E402
from common import atomic_write_text, utf8_stdout  # noqa: E402
from state import FILL, REPO_ROOT, STATE_DONE, STATE_DRAFT, Paths, check, parse_week  # noqa: E402


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def cmd_check(args: argparse.Namespace, paths: Paths) -> int:
    return emit(check(paths, parse_week(args.week)))


def prepare_blocker(status: dict, args: argparse.Namespace) -> str | None:
    if status["running"]:
        return status["reason"] + "。収集の完了（finalize）を待つ"
    if not status["latest_session"]:
        return status["reason"] + "。先に collect-market-info を実行する"
    if not status["fresh"] and not args.allow_stale:
        return (status["reason"] + "。先に collect-market-info を実行する"
                "（ユーザーが古い材料で良いと指示した場合だけ --allow-stale）")
    if status["outlook"] == STATE_DONE and not args.redo:
        return "この週の outlook.md は完成済み。作り直すのはユーザーが指示したときだけ（--redo）"
    return None


def cmd_prepare(args: argparse.Namespace, paths: Paths) -> int:
    week = parse_week(args.week)
    status = check(paths, week)
    blocker = prepare_blocker(status, args)
    if blocker:
        return emit({"ok": False, "week": week, "error": blocker})
    today = dt.date.today().isoformat()
    facts = F.build_facts(paths, week, status["latest_session"], today)
    facts["moved"] = K.check(facts, paths.report_dir)
    paths.report_dir.mkdir(parents=True, exist_ok=True)
    facts_path, brief_path = paths.report_file(week, "facts.json"), paths.report_file(week, "brief.md")
    outlook_path = paths.report_file(week, "outlook.md")
    atomic_write_text(facts_path, json.dumps(facts, ensure_ascii=False, indent=1) + "\n")
    atomic_write_text(brief_path, B.render_brief(paths, facts))
    kept = status["outlook"] == STATE_DRAFT and not args.redo
    if not kept:
        template = (paths.template_dir / "outlook.md").read_text(encoding="utf-8")
        atomic_write_text(outlook_path, B.render_outlook(paths, facts, template, today))
    warnings = [K.label(c) for c in facts["moved"] + facts["checks"]]
    if kept and B.handoff_rows(facts) not in outlook_path.read_text(encoding="utf-8"):
        warnings.append("作成途中の outlook.md は前の facts.json から作られた骨組みで、8章の候補・10章が今回の数値と違う。"
                        "このまま書くと build が通らない（作り直しはユーザーの指示で prepare --redo）")
    prev = facts["previous"] or {}
    if prev and not prev.get("viewpoints"):
        warnings.append(f"前回（{prev['week']} 週）の judgment.json が無いため、観点の評価にヒステリシスを使っていない")
    return emit({
        "ok": True, "week": week, "session": status["latest_session"], "stale": not status["fresh"],
        "facts": paths.rel(facts_path), "brief": paths.rel(brief_path), "outlook": paths.rel(outlook_path),
        "outlook_kept": kept, "fill": len(FILL.findall(outlook_path.read_text(encoding="utf-8"))),
        "kpis_missing": [k["label"] for k in facts["kpis"] if k["value"] is None],
        "series_failed": len(facts["series_failed"]), "events": len(facts["events"]), "docs": len(facts["docs"]),
        "previous": {k: v for k, v in (facts["previous"] or {}).items() if k in ("week", "path", "japan", "us")}
        or None,
        "candidates": {m: s["candidate"] for m, s in facts["scores"].items()},
        "warnings": warnings,
    })


def cmd_build(args: argparse.Namespace, paths: Paths) -> int:
    week = parse_week(args.week)
    facts_path, outlook_path = paths.report_file(week, "facts.json"), paths.report_file(week, "outlook.md")
    missing = [paths.rel(p) for p in (facts_path, outlook_path) if not p.exists()]
    if missing:
        return emit({"ok": False, "week": week, "error": f"ファイルが無い: {', '.join(missing)}（先に prepare）"})
    text = outlook_path.read_text(encoding="utf-8")
    issues = O.validate(text, (paths.template_dir / "outlook.md").read_text(encoding="utf-8"))
    if issues:
        return emit({"ok": False, "week": week, "outlook": paths.rel(outlook_path), "issues": issues})
    facts = json.loads(facts_path.read_text(encoding="utf-8"))
    parsed = O.parse(text)
    issues = O.check_against_facts(parsed, facts)
    if issues:
        if f"収集セッション {facts['session']}" not in text:
            issues.append(f"outlook.md の骨組みは facts.json（{facts['session']}）より前の収集から作られた。"
                          "8章の候補・10章が合わないのはこのため（作り直しはユーザーの指示で prepare --redo）")
        return emit({"ok": False, "week": week, "outlook": paths.rel(outlook_path), "issues": issues})
    warnings = []
    if f"収集セッション {facts['session']}" not in text:
        warnings.append(f"outlook.md の骨組みは facts.json（{facts['session']}）より前の収集から作られた。"
                        "6章の日程・7章の欠損が古い可能性がある（作り直しはユーザーの指示で prepare --redo）")
    warnings += O.length_warnings(parsed) + O.source_warnings(parsed) + O.plain_warnings(parsed)
    payload = O.judgment_payload(parsed, facts)
    judgment_path = paths.report_file(week, "judgment.json")
    atomic_write_text(judgment_path, json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    history = judgment_history(paths, week) + [payload]
    # words a reader meets in the deck: the written text (template instructions dropped) and the KPI labels
    template_lines = set((paths.template_dir / "outlook.md").read_text(encoding="utf-8").splitlines())
    written = "\n".join(line for line in text.splitlines() if line not in template_lines and not line.startswith(">"))
    shown = written + " " + " ".join(k["label"] for k in facts["kpis"])
    html = S.render(facts, parsed, (paths.template_dir / "report.html").read_text(encoding="utf-8"), history,
                    shown)
    html_path = paths.report_file(week, "market-report.html")
    atomic_write_text(html_path, html)
    return emit({
        "ok": True, "week": week, "html": paths.rel(html_path), "outlook": paths.rel(outlook_path),
        "judgment": paths.rel(judgment_path),
        "judgments": {m: v["judgment"] for m, v in parsed["judgments"].items()},
        "candidates": payload["candidates"],
        "overrides": [f"{F.MARKET_LABEL[m]} {v['name']}: {v['candidate']} → {v['adopted']}"
                      for m, vs in payload["viewpoints"].items() for v in vs.values()
                      if v["adopted"] != v["candidate"]],
        "previous": {k: v for k, v in (facts.get("previous") or {}).items() if k in ("week", "japan", "us")} or None,
        "kb": round(len(html.encode("utf-8")) / 1024), "warnings": warnings,
    })


def cmd_backtest(args: argparse.Namespace, paths: Paths) -> int:
    today = dt.date.today().isoformat()
    weeks = BT.replay(paths, args.years, today)
    summary = BT.summarize(weeks)
    out_dir = paths.report_dir / "backtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path, json_path = out_dir / f"{today}_backtest.md", out_dir / f"{today}_backtest.json"
    atomic_write_text(md_path, BT.render(summary, args.years, today, weeks))
    atomic_write_text(json_path, json.dumps({"generated": today, "years": args.years, "summary": summary,
                                             "weeks": weeks}, ensure_ascii=False, indent=1) + "\n")
    return emit({
        "ok": True, "md": paths.rel(md_path), "json": paths.rel(json_path), "weeks": len(weeks),
        "candidates": {m: {j: s["by_judgement"][j]["r13"]["n"] for j in BT.JUDGEMENT_ORDER}
                       for m, s in summary.items()},
        "inverted": BT.inverted(summary),
    })


HISTORY_WEEKS = 8


def judgment_history(paths: Paths, week: str) -> list[dict]:
    """Earlier weeks' judgment.json (oldest first), for the scorecard heatmap."""
    found = sorted(p for p in paths.report_dir.glob("*_judgment.json") if p.name[:10] < week)
    return [json.loads(p.read_text(encoding="utf-8")) for p in found[-(HISTORY_WEEKS - 1):]]


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "prepare", "build"):
        p = sub.add_parser(name)
        p.add_argument("--week", help="YYYY-MM-DD（その週の任意の日。省略時は今日）")
        if name == "prepare":
            p.add_argument("--redo", action="store_true", help="完成済み・作成中の outlook.md を骨組みに戻す")
            p.add_argument("--allow-stale", action="store_true", help="今週の収集が無くても作る（ユーザーの指示時のみ）")
    p = sub.add_parser("backtest")
    p.add_argument("--years", type=int, default=10, help="さかのぼる年数（既定 10）")
    args = parser.parse_args(argv)
    try:
        parse_week(getattr(args, "week", None))
    except ValueError:
        return emit({"ok": False, "error": f"--week は YYYY-MM-DD で指定する: {getattr(args, 'week', None)}"})
    handler = {"check": cmd_check, "prepare": cmd_prepare, "build": cmd_build, "backtest": cmd_backtest}[args.cmd]
    return handler(args, Paths(root))


if __name__ == "__main__":
    sys.exit(main())
