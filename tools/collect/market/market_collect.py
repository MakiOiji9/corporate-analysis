"""collect-market-info orchestrator: everything except summarising and web search.

Usage:
  market_collect.py prepare  --market japan|us|both --topic TOPIC [--mode full|update] [--date YYYY-MM-DD]
  market_collect.py finalize --session market/sessions/YYYY-MM-DD_topic
  market_collect.py validate --session market/sessions/YYYY-MM-DD_topic
  market_collect.py abort    --session market/sessions/YYYY-MM-DD_topic
  market_collect.py check-watch --market japan|us            # catalog maintenance (dry run)
  market_collect.py search boj --db CO --word 業況判断         # find BOJ series codes
  market_collect.py search dashboard --word 消費者物価指数      # find e-Stat dashboard codes

prepare: fetch time series (API) -> data/*.csv -> indicators raw; detect new policy
documents -> originals + excerpts + skeletons; write tasks.json; mark the session
running (tools/guard/write_guard.py then blocks edits outside the allowed files).
finalize: validate every output against its template, build policy-digest and
status.md, compare git changes with the allowed paths, clear the running mark.
stdout is a short JSON summary so the calling agent spends few tokens.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]  # scripts run with python -I

import docs as D  # noqa: E402
import render as R  # noqa: E402
import series as S  # noqa: E402
import store  # noqa: E402
from common import REPO_ROOT, atomic_write_text, http_get, load_env, utf8_stdout  # noqa: E402
from validate import validate_file  # noqa: E402

MARKETS = ("japan", "us")
SESSIONS = REPO_ROOT / "market" / "sessions"
DATA_DIR = REPO_ROOT / "market" / "data"
CATALOG_DIR = HERE / "catalog"
RUNNING, TASKS, BASELINE = ".running", "tasks.json", ".baseline.json"
LOOKBACK_YEARS = {"full": 10, "update": 3}
JPX_WEEKS = {"full": 12, "update": 4}
CALENDAR_DAYS_AHEAD = 90
TOPIC = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")


def load_catalog(market: str) -> dict:
    return json.loads((CATALOG_DIR / f"{market}.json").read_text(encoding="utf-8"))


def series_csv(market: str) -> Path:
    return DATA_DIR / f"{market}_series.csv"


def resolve_session(arg: str) -> Path:
    path = Path(arg)
    path = path if path.is_absolute() else REPO_ROOT / path
    if not (path.parent.resolve() == SESSIONS.resolve() and path.is_dir()):
        raise SystemExit(f"session not found under market/sessions/: {arg}")
    return path


def git_changes() -> set[str]:
    out = subprocess.run(["git", "-c", "core.quotepath=false", "status", "--porcelain", "-uall", "-z"],
                         cwd=REPO_ROOT, capture_output=True, check=False).stdout.decode("utf-8", "replace")
    paths, entries = set(), iter(out.split("\0"))
    for entry in entries:
        if len(entry) > 3:
            paths.add(entry[3:])
            if entry[0] in "RC":  # rename/copy: the next field is the original path
                next(entries, None)
    return paths


# ---------------------------------------------------------------- prepare

def collect_series(market: str, catalog: dict, mode: str) -> tuple[dict, dict, list]:
    entries = catalog.get("series", [])
    start = S.lookback_start(LOOKBACK_YEARS[mode])
    failures: dict[str, str] = {}
    jpx = [e for e in entries if e["provider"] == "jpx_flows"]
    for entry in (e for e in entries if e["provider"] != "jpx_flows"):
        try:
            store.upsert_series(series_csv(market), S.fetch(entry, start, http_get))
        except Exception as exc:  # noqa: BLE001 - record the reason and continue
            failures[entry["id"]] = f"{type(exc).__name__}: {str(exc)[:100]}"
    if jpx:
        try:
            store.upsert_series(series_csv(market), S.fetch_jpx_flows(jpx, JPX_WEEKS[mode], http_get))
        except Exception as exc:  # noqa: BLE001
            failures.update({e["id"]: f"{type(exc).__name__}: {str(exc)[:100]}" for e in jpx})
    points = store.load_points(series_csv(market))
    summaries = {e["id"]: store.summarize(points.get(e["id"], []), e.get("transform", "level"),
                                          e.get("frequency", "monthly")) for e in entries}
    for e in entries:
        if summaries[e["id"]] is None and e["id"] not in failures:
            failures[e["id"]] = "データなし（系列コード・期間を catalog で確認）"
    rows = [[market, e["name"], s.latest_date if (s := summaries[e["id"]]) else "—",
             "失敗: " + failures[e["id"]] if e["id"] in failures else "OK"] for e in entries]
    return summaries, failures, rows


def calendar_task(session: Path, market: str, catalog: dict, collected: str) -> dict:
    cal = catalog.get("calendar", {})
    out = session / "raw" / f"calendar-{market}.md"
    if not out.exists():
        until = (dt.date.fromisoformat(collected) + dt.timedelta(days=CALENDAR_DAYS_AHEAD)).isoformat()
        out.write_text(R.render_template(
            "raw/calendar.md", market_label=R.MARKET_LABEL[market], collected=collected,
            window_from=collected, window_to=until, max_searches=cal.get("max_searches", 8),
            event_hint=cal.get("event_hint", ""), recent_hint=cal.get("recent_hint", ""),
            sentiment_items="、".join(cal.get("sentiment_items", []))), encoding="utf-8")
    return {"type": "search-calendar", "market": market, "title": f"政治・イベント日程（{R.MARKET_LABEL[market]}）",
            "output": R.rel(out), "inputs": [], "max_searches": cal.get("max_searches", 8),
            "template": ".ai/templates/collect-market-info/raw/calendar.md", "allowed_files": [R.rel(out)]}


def merge_new_docs(session: Path, new_docs: list[dict]) -> list[dict]:
    """Keep documents added by an earlier prepare of the same session (re-runs only add more)."""
    previous = session / TASKS
    earlier = json.loads(previous.read_text(encoding="utf-8")).get("new_docs", []) if previous.exists() else []
    merged = {(d["market"], d["doc_key"]): d for d in earlier + new_docs}
    return list(merged.values())


def cmd_prepare(args: argparse.Namespace) -> int:
    if not TOPIC.match(args.topic):
        raise SystemExit("topic must be lowercase letters, digits and hyphens (e.g. weekly, 2026q4)")
    load_env()
    collected = args.date or dt.date.today().isoformat()
    markets = MARKETS if args.market == "both" else (args.market,)
    session = SESSIONS / f"{collected}_{args.topic}"
    (session / "raw").mkdir(parents=True, exist_ok=True)
    if not (session / BASELINE).exists():
        atomic_write_text(session / BASELINE, json.dumps(sorted(git_changes()), ensure_ascii=False))
    atomic_write_text(session / RUNNING, json.dumps({"session": R.rel(session),
                                                     "started": dt.datetime.now().isoformat(timespec="seconds")}))
    series_rows, watch_rows, new_docs, tasks = [], [], [], []
    failed_series = 0
    for market in markets:
        catalog = load_catalog(market)
        summaries, failures, rows = collect_series(market, catalog, args.mode)
        failed_series += len(failures)
        series_rows += rows
        atomic_write_text(session / "raw" / f"indicators-{market}.md", R.render_indicators(
            market, catalog.get("series", []), summaries, failures, collected, series_csv(market)))
        result = D.process_watches(market, catalog, collected)
        watch_rows += result.watch_rows
        new_docs += result.new_docs
        tasks += D.pending_doc_tasks(market) + [calendar_task(session, market, catalog, collected)]
    for i, task in enumerate(tasks, 1):
        task["id"] = f"T{i:02d}"
    new_docs = merge_new_docs(session, new_docs)
    state = {"session": R.rel(session), "collected": collected, "markets": list(markets),
             "mode": args.mode, "tasks": tasks, "new_docs": new_docs}
    atomic_write_text(session / TASKS, json.dumps(state, ensure_ascii=False, indent=1))
    write_status(session, state, "prepare 完了（タスク実行待ち）", series_rows, watch_rows, [], [])
    print(json.dumps({"session": R.rel(session), "tasks_file": R.rel(session / TASKS),
                      "tasks": len(tasks), "new_docs": len(new_docs), "series_failed": failed_series,
                      "watch_failed": sum(1 for r in watch_rows if r[2].startswith("失敗"))},
                     ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- finalize / validate

def check_outputs(session: Path, state: dict) -> tuple[dict[str, list[str]], list[str]]:
    """Issues per file, and ids of tasks whose output is not complete yet."""
    issues: dict[str, list[str]] = {}
    pending = []
    for task in state["tasks"]:
        found = validate_file(REPO_ROOT / task["output"], REPO_ROOT / task["template"])
        if found:
            issues[task["output"]] = found
            pending.append(task["id"])
    for market in state["markets"]:
        path = session / "raw" / f"indicators-{market}.md"
        found = validate_file(path, R.template_path("raw/series-table.md"))
        if found:
            issues[R.rel(path)] = found
    return issues, pending


def out_of_scope(session: Path) -> list[str]:
    baseline = set(json.loads((session / BASELINE).read_text(encoding="utf-8")))
    allowed = (R.rel(session) + "/", "market/policy/", "market/data/")
    return sorted(p for p in git_changes() - baseline if not p.startswith(allowed))


def write_status(session: Path, state: dict, stage: str, series_rows: list, watch_rows: list,
                 validation: list[str], scope: list[str], pending: list[str] | None = None) -> None:
    pending = pending if pending is not None else [t["id"] for t in state["tasks"]]
    task_rows = [[t["id"], t["type"], t["output"], "未完了" if t["id"] in pending else "完了"]
                 for t in state["tasks"]]
    summary = [["市場", "・".join(R.MARKET_LABEL[m] for m in state["markets"])], ["モード", state["mode"]],
               ["新規文書", str(len(state["new_docs"]))], ["タスク", f"{len(state['tasks'])} 件（未完了 {len(pending)} 件）"]]
    previous = session / "status.md"
    if previous.exists() and not series_rows:  # finalize keeps prepare's series / watch tables
        text = previous.read_text(encoding="utf-8")
        series_rows = _table_after(text, "## 2. 時系列")
        watch_rows = _table_after(text, "## 3. 文書監視")
    atomic_write_text(previous, R.render_status(R.rel(session), dt.datetime.now().isoformat(timespec="minutes"),
                                                stage, summary, series_rows, watch_rows, task_rows,
                                                validation, scope))


def _table_after(text: str, heading: str) -> list[list[str]]:
    """Data rows of the first table under heading (stops at the next '## ')."""
    if heading not in text:
        return []
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in rows]


def cmd_finalize(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    state = json.loads((session / TASKS).read_text(encoding="utf-8"))
    issues, pending = check_outputs(session, state)
    done = {t["output"] for t in state["tasks"] if t["id"] not in pending}
    for market in state["markets"]:
        D.mark_done(market, done)
    # The index is saved after every watch entry, so it survives re-runs of prepare.
    added = [(m, r) for m in state["markets"] for r in D.W.load_index(D.index_path(m))
             if r["collected"] == state["collected"]]
    new_rows, listed = [], {}
    for m, r in added:
        if r["status"] == "listed":  # list-kind entries (e.g. 30 presidential actions) -> one row per list file
            listed.setdefault((m, r["layer"], r["raw_path"]), []).append(r)
            continue
        new_rows.append([R.MARKET_LABEL[m], r["layer"], r["published"] or "—", r["title"], r["raw_path"],
                         "完了" if r["status"] == "done" else "未完了"])
    for (m, layer, raw_path), items in listed.items():
        latest = max(i["published"] for i in items) or "—"
        new_rows.append([R.MARKET_LABEL[m], layer, latest, f"{items[0]['title']} ほか {len(items) - 1} 件（一覧）",
                         raw_path, "完了"])
    latest = [[R.MARKET_LABEL[m], r["layer"], r["watch_key"], r["published"] or "—", r["title"], r["raw_path"]]
              for m in state["markets"] for r in D.latest_by_watch(m)]
    atomic_write_text(session / "raw" / "policy-digest.md",
                      R.render_digest(R.rel(session), state["collected"], new_rows, latest))
    scope = out_of_scope(session)
    flat = [f"{f}: {i}" for f, items in issues.items() for i in items]
    ok = not issues and not scope
    stage = "完了" if ok else "finalize で問題あり（未完了タスクを再実行して再度 finalize）"
    write_status(session, state, stage, [], [], flat, scope, pending)
    if ok:
        (session / RUNNING).unlink(missing_ok=True)
    print(json.dumps({"ok": ok, "pending_tasks": pending, "issues": issues, "out_of_scope": scope,
                      "status": R.rel(session / "status.md")}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_validate(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    state = json.loads((session / TASKS).read_text(encoding="utf-8"))
    issues, pending = check_outputs(session, state)
    print(json.dumps({"pending_tasks": pending, "issues": issues}, ensure_ascii=False))
    return 0 if not issues else 1


def cmd_abort(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    (session / RUNNING).unlink(missing_ok=True)
    print(json.dumps({"aborted": R.rel(session)}, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- catalog maintenance

def cmd_check_watch(args: argparse.Namespace) -> int:
    import watch as W

    catalog = load_catalog(args.market)
    variables, errors = W.resolve_vars(catalog.get("vars", {}), http_get)
    for error in errors:
        print(f"[vars] 失敗: {error}")
    for entry in catalog.get("watch", []):
        try:
            cands = W.list_candidates(entry, http_get, variables)
            print(f"[{entry['key']}] {len(cands)} 件")
            for c in cands[:3]:
                print(f"  {c.published or '----------'} {c.title[:50]} {c.url}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{entry['key']}] 失敗: {type(exc).__name__}: {str(exc)[:120]}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    if args.source == "boj":
        meta = http_get("https://www.stat-search.boj.or.jp/api/v1/getMetadata",
                        params={"format": "json", "lang": "jp", "db": args.db}).json()
        for x in meta.get("RESULTSET", []):
            name = x.get("NAME_OF_TIME_SERIES_J", "")
            if all(w in name for w in args.word) and x.get("SERIES_CODE"):
                print(x["SERIES_CODE"], name[:70], x.get("FREQUENCY"), x.get("END_OF_THE_TIME_SERIES"))
    else:
        info = http_get("https://dashboard.e-stat.go.jp/api/1.0/Json/getIndicatorInfo",
                        params={"Lang": "JP", "SearchIndicatorWord": " ".join(args.word)}).json()
        objs = info["GET_META_INDICATOR_INF"].get("METADATA_INF", {}).get("CLASS_INF", {}).get("CLASS_OBJ") or []
        seen = set()
        for o in objs if isinstance(objs, list) else [objs]:
            classes = o.get("CLASS") or []
            for c in classes if isinstance(classes, list) else [classes]:
                cycles = c.get("cycle") or []
                names = [x.get("@name") for x in (cycles if isinstance(cycles, list) else [cycles]) if isinstance(x, dict)]
                key = (o["@code"], tuple(names))
                if c.get("@toDate", "").startswith("9999") and key not in seen:
                    seen.add(key)
                    print(o["@code"], o["@name"][:60], "/".join(names), c.get("@statName", ""))
    return 0


def main() -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--market", choices=("japan", "us", "both"), required=True)
    p.add_argument("--topic", required=True)
    p.add_argument("--mode", choices=("full", "update"), default="update")
    p.add_argument("--date")
    for name in ("finalize", "validate", "abort"):
        sub.add_parser(name).add_argument("--session", required=True)
    sub.add_parser("check-watch").add_argument("--market", choices=MARKETS, required=True)
    s = sub.add_parser("search")
    s.add_argument("source", choices=("boj", "dashboard"))
    s.add_argument("--db", default="CO")
    s.add_argument("--word", nargs="+", required=True)
    args = ap.parse_args()
    handlers = {"prepare": cmd_prepare, "finalize": cmd_finalize, "validate": cmd_validate,
                "abort": cmd_abort, "check-watch": cmd_check_watch, "search": cmd_search}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
