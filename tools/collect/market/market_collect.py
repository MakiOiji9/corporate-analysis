"""collect-market-info orchestrator: everything except summarising and web search.

Usage:
  market_collect.py prepare  --market japan|us|both --topic TOPIC [--mode auto|full|update] [--date YYYY-MM-DD]
  market_collect.py finalize --session market/sessions/YYYY-MM-DD_topic
  market_collect.py validate --session market/sessions/YYYY-MM-DD_topic
  market_collect.py abort    --session market/sessions/YYYY-MM-DD_topic
  market_collect.py reopen   --raw market/policy/{market}/raw/FILE.md   # redo one summary (user request only)
  market_collect.py check-watch --market japan|us            # catalog maintenance (dry run)
  market_collect.py search boj --db CO --word 業況判断         # find BOJ series codes
  market_collect.py search dashboard --word 消費者物価指数      # find e-Stat dashboard codes

prepare: reconcile index.csv; fetch time series (API) -> data/*.csv -> indicators raw;
detect new policy documents -> originals + excerpts + skeletons; fixed calendar dates
from official sites; write tasks.json (summaries bundled by excerpt size); mark the
session running (tools/guard/write_guard.py then blocks edits outside the allowed files).
finalize: validate every output against its template, apply the summarisers' date
checks, build policy-digest, status.md (with the items to review) and market/LATEST.md,
compare git changes with the allowed paths, clear the running mark.
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

import calendar_fixed as CF  # noqa: E402
import docs as D  # noqa: E402
import render as R  # noqa: E402
import series as S  # noqa: E402
import store  # noqa: E402
from common import REPO_ROOT, atomic_write_text, http_get, load_env, utf8_stdout  # noqa: E402
from validate import validate_file  # noqa: E402

MARKETS = ("japan", "us")
MARKET_DIR = REPO_ROOT / "market"
SESSIONS = MARKET_DIR / "sessions"
DATA_DIR = MARKET_DIR / "data"
LATEST = MARKET_DIR / "LATEST.md"
CATALOG_DIR = HERE / "catalog"
RUNNING, TASKS, BASELINE = ".running", "tasks.json", ".baseline.json"
LOOKBACK_YEARS = {"full": 10, "update": 3}
JPX_WEEKS = {"full": 12, "update": 4}
CALENDAR_DAYS_AHEAD = 90
BATCH_MAX_DOCS = 3          # summaries per summarize-doc agent
BATCH_MAX_CHARS = 45_000    # excerpt characters per agent
REVIEW_CELL_CHARS = 200
STAGE_DONE = "完了"
STAGE_ABORTED = "中断（未完了の要旨化は次回 prepare で引き継ぐ）"
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


def resolve_mode(market: str, requested: str) -> str:
    """auto: full (10 years) the first time a market is collected, update (3 years) afterwards."""
    if requested != "auto":
        return requested
    return "update" if series_csv(market).exists() else "full"


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


# ---------------------------------------------------------------- tasks

def task_outputs(task: dict) -> list[tuple[str, str]]:
    """(output, template) of every file a task fills: summarize-doc tasks bundle several docs."""
    return [(d["output"], d["template"]) for d in task.get("docs", [task])]


def batch_doc_tasks(doc_tasks: list[dict]) -> list[dict]:
    """Bundle summaries into tasks of at most BATCH_MAX_DOCS docs / BATCH_MAX_CHARS excerpt chars."""
    batches: list[list[dict]] = []
    size = 0
    for doc in doc_tasks:
        chars = sum(len((REPO_ROOT / p).read_text(encoding="utf-8")) for p in doc["inputs"][:1]
                    if (REPO_ROOT / p).exists())
        if not batches or len(batches[-1]) >= BATCH_MAX_DOCS or size + chars > BATCH_MAX_CHARS:
            batches.append([])
            size = 0
        batches[-1].append({k: doc[k] for k in ("market", "title", "doc_key", "output", "inputs", "template")})
        size += chars
    return [{"type": "summarize-doc", "docs": docs, "allowed_files": [d["output"] for d in docs]}
            for docs in batches]


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


def calendar_task(session: Path, market: str, catalog: dict, collected: str) -> tuple[dict, list[list[str]]]:
    """The calendar skeleton (fixed dates already filled by the script) and its watch-table rows."""
    cal = catalog.get("calendar", {})
    out = session / "raw" / f"calendar-{market}.md"
    status_rows = []
    if not out.exists():
        until = (dt.date.fromisoformat(collected) + dt.timedelta(days=CALENDAR_DAYS_AHEAD)).isoformat()
        fixed, errors = CF.fetch_fixed(cal.get("fixed_sources", []), collected, until, http_get)
        status_rows = [[market, "calendar", f"確定日程 {len(fixed)} 件"]]
        status_rows += [[market, "calendar", f"失敗: {e}"] for e in errors]
        out.write_text(R.render_template(
            "raw/calendar.md", market_label=R.MARKET_LABEL[market], collected=collected,
            window_from=collected, window_to=until, max_searches=cal.get("max_searches", 8),
            event_hint=cal.get("event_hint", ""), recent_hint=cal.get("recent_hint", ""),
            sentiment_items="、".join(cal.get("sentiment_items", [])),
            fixed_rows=R.table(fixed or [["—", "—", "取得できた確定日程なし", "—", "—"]], 5)), encoding="utf-8")
    task = {"type": "search-calendar", "market": market, "title": f"政治・イベント日程（{R.MARKET_LABEL[market]}）",
            "output": R.rel(out), "inputs": [], "max_searches": cal.get("max_searches", 8),
            "template": ".ai/templates/collect-market-info/raw/calendar.md", "allowed_files": [R.rel(out)]}
    return task, status_rows


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
    modes = {m: resolve_mode(m, args.mode) for m in markets}
    session = SESSIONS / f"{collected}_{args.topic}"
    (session / "raw").mkdir(parents=True, exist_ok=True)
    if not (session / BASELINE).exists():
        atomic_write_text(session / BASELINE, json.dumps(sorted(git_changes()), ensure_ascii=False))
    atomic_write_text(session / RUNNING, json.dumps({"session": R.rel(session),
                                                     "started": dt.datetime.now().isoformat(timespec="seconds")}))
    series_rows, watch_rows, new_docs, doc_tasks, calendar_tasks = [], [], [], [], []
    failed_series = 0
    for market in markets:
        catalog = load_catalog(market)
        watch_rows += [[market, key, "index 整合: 要旨済みを done に更新"] for key in D.reconcile_index(market)]
        summaries, failures, rows = collect_series(market, catalog, modes[market])
        failed_series += len(failures)
        series_rows += rows
        atomic_write_text(session / "raw" / f"indicators-{market}.md", R.render_indicators(
            market, catalog.get("series", []), summaries, failures, collected, series_csv(market)))
        result = D.process_watches(market, catalog, collected)
        watch_rows += result.watch_rows
        new_docs += result.new_docs
        doc_tasks += D.pending_doc_tasks(market)
        task, rows = calendar_task(session, market, catalog, collected)
        calendar_tasks.append(task)
        watch_rows += rows
    tasks = batch_doc_tasks(doc_tasks) + calendar_tasks
    for i, task in enumerate(tasks, 1):
        task["id"] = f"T{i:02d}"
    new_docs = merge_new_docs(session, new_docs)
    mode = next(iter(set(modes.values()))) if len(set(modes.values())) == 1 else \
        ", ".join(f"{m}={v}" for m, v in modes.items())
    state = {"session": R.rel(session), "collected": collected, "markets": list(markets),
             "mode": mode, "tasks": tasks, "new_docs": new_docs}
    atomic_write_text(session / TASKS, json.dumps(state, ensure_ascii=False, indent=1))
    write_status(session, state, "prepare 完了（タスク実行待ち）", series_rows, watch_rows, [], [])
    print(json.dumps({"session": R.rel(session), "tasks_file": R.rel(session / TASKS), "mode": mode,
                      "tasks": len(tasks), "docs_to_summarize": len(doc_tasks), "new_docs": len(new_docs),
                      "series_failed": failed_series,
                      "watch_failed": sum(1 for r in watch_rows if r[2].startswith("失敗"))},
                     ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- finalize / validate

def check_outputs(session: Path, state: dict) -> tuple[dict[str, list[str]], list[str], set[str]]:
    """Issues per file, ids of tasks with an incomplete output, and the outputs that are complete."""
    issues: dict[str, list[str]] = {}
    pending, done = [], set()
    for task in state["tasks"]:
        for output, template in task_outputs(task):
            found = validate_file(REPO_ROOT / output, REPO_ROOT / template)
            if found:
                issues[output] = found
            else:
                done.add(output)
        if any(output in issues for output, _ in task_outputs(task)):
            pending.append(task["id"])
    for market in state["markets"]:
        path = session / "raw" / f"indicators-{market}.md"
        found = validate_file(path, R.template_path("raw/series-table.md"))
        if found:
            issues[R.rel(path)] = found
    return issues, pending, done


def out_of_scope(session: Path) -> list[str]:
    baseline = set(json.loads((session / BASELINE).read_text(encoding="utf-8")))
    allowed = (R.rel(session) + "/", "market/policy/", "market/data/", R.rel(LATEST))
    return sorted(p for p in git_changes() - baseline if not p.startswith(allowed))


def write_status(session: Path, state: dict, stage: str, series_rows: list, watch_rows: list,
                 validation: list[str], scope: list[str], pending: list[str] | None = None,
                 review_rows: list[list[str]] | None = None) -> None:
    pending = pending if pending is not None else [t["id"] for t in state["tasks"]]
    task_rows = [[t["id"], t["type"], "、".join(o for o, _ in task_outputs(t)), "未完了" if t["id"] in pending else "完了"]
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
                                                validation, scope, review_rows))


def _table_after(text: str, heading: str) -> list[list[str]]:
    """Data rows of the first table under heading (stops at the next '## ')."""
    if heading not in text:
        return []
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in rows]


def _stage(status: Path) -> str:
    m = re.search(r"^\*\*段階\*\*: (.+)$", status.read_text(encoding="utf-8"), re.M) if status.exists() else None
    return m.group(1).strip() if m else ""


def script_findings(watch_rows: list[list[str]], date_notes: list[str]) -> list[list[str]]:
    """Problems the scripts detected: date corrections / mismatches and failed watch or calendar sources."""
    rows = [[f"{r[0]} {r[1]}", r[2]] for r in watch_rows if "公表日" in r[2] or r[2].startswith("失敗")]
    return rows + [note.split(": ", 1) for note in date_notes]


def review_rows(state: dict, done: set[str], findings: list[list[str]]) -> list[list[str]]:
    """What the user should check before analysis: the script findings and every '未確認・保留事項'."""
    rows = list(findings)
    for task in state["tasks"]:
        for output, _ in task_outputs(task):
            if output in done:
                text = (REPO_ROOT / output).read_text(encoding="utf-8")
                rows += [[output, item[:REVIEW_CELL_CHARS]] for item in D.pending_items(text)]
    return rows


def write_latest() -> None:
    """market/LATEST.md: per market, the newest finished session and the newest document per watch."""
    files, latest_session = [], ""
    # newest first: collection date, then (several sessions on one day) when status.md was last written
    sessions = sorted((p for p in SESSIONS.iterdir() if p.is_dir()), reverse=True,
                      key=lambda p: (p.name[:10], (p / "status.md").stat().st_mtime if (p / "status.md").exists() else 0))
    for market in MARKETS:
        for session in sessions:
            tasks = session / TASKS
            if not tasks.exists() or market not in json.loads(tasks.read_text(encoding="utf-8")).get("markets", []):
                continue
            if _stage(session / "status.md") != STAGE_DONE:
                continue
            label = R.MARKET_LABEL[market]
            latest_session = latest_session or session.name
            files += [[f"指標（{label}）", R.rel(session / "raw" / f"indicators-{market}.md")],
                      [f"日程・市場指標（{label}）", R.rel(session / "raw" / f"calendar-{market}.md")],
                      [f"文書ダイジェスト（{label} を含む）", R.rel(session / "raw" / "policy-digest.md")],
                      [f"収集ステータス（{label}）", R.rel(session / "status.md")],
                      [f"時系列 CSV（{label}）", R.rel(series_csv(market))]]
            break
    latest = [[R.MARKET_LABEL[m], r["layer"], r["watch_key"], r["published"] or "—", r["title"], r["raw_path"]]
              for m in MARKETS for r in D.latest_by_watch(m)]
    atomic_write_text(LATEST, R.render_latest(latest_session or "—", dt.datetime.now().isoformat(timespec="minutes"),
                                              files, latest))


def _digest(session: Path, state: dict) -> None:
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


def _series_counts(status_text: str) -> tuple[int, list[str]]:
    rows = _table_after(status_text, "## 2. 時系列")
    failed = [f"{r[0]} {r[1]}: {r[3]}" for r in rows if len(r) == 4 and r[3] != "OK"]
    return len(rows) - len(failed), failed


def cmd_finalize(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    state = json.loads((session / TASKS).read_text(encoding="utf-8"))
    issues, pending, done = check_outputs(session, state)
    date_notes = []
    for market in state["markets"]:
        D.mark_done(market, done)
        date_notes += D.apply_published_checks(market, done)
    _digest(session, state)
    status_text = (session / "status.md").read_text(encoding="utf-8")
    findings = script_findings(_table_after(status_text, "## 3. 文書監視"), date_notes)
    review = review_rows(state, done, findings)
    scope = out_of_scope(session)
    flat = [f"{f}: {i}" for f, items in issues.items() for i in items]
    ok = not issues and not scope
    stage = STAGE_DONE if ok else "finalize で問題あり（未完了タスクを再実行して再度 finalize）"
    write_status(session, state, stage, [], [], flat, scope, pending, review)
    if ok:
        (session / RUNNING).unlink(missing_ok=True)
        write_latest()
    series_ok, series_failed = _series_counts(status_text)
    warnings = [f"{r[0]}: {r[1]}" for r in findings]
    print(json.dumps({
        "ok": ok, "pending_tasks": pending, "issues": issues, "out_of_scope": scope,
        "series_ok": series_ok, "series_failed": series_failed,
        "new_docs": [d["title"] for d in state["new_docs"]],
        "tasks_done": len(state["tasks"]) - len(pending), "tasks_total": len(state["tasks"]),
        "warnings": warnings, "review_items": len(review),
        "status": R.rel(session / "status.md"), "latest": R.rel(LATEST) if ok else None}, ensure_ascii=False))
    return 0 if ok else 1


def cmd_validate(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    state = json.loads((session / TASKS).read_text(encoding="utf-8"))
    issues, pending, _ = check_outputs(session, state)
    print(json.dumps({"pending_tasks": pending, "issues": issues}, ensure_ascii=False))
    return 0 if not issues else 1


def cmd_abort(args: argparse.Namespace) -> int:
    session = resolve_session(args.session)
    (session / RUNNING).unlink(missing_ok=True)
    if (session / TASKS).exists() and _stage(session / "status.md") != STAGE_DONE:
        state = json.loads((session / TASKS).read_text(encoding="utf-8"))
        _, pending, _ = check_outputs(session, state)
        write_status(session, state, STAGE_ABORTED, [], [], [], [], pending)
    print(json.dumps({"aborted": R.rel(session)}, ensure_ascii=False))
    return 0


def cmd_reopen(args: argparse.Namespace) -> int:
    running = sorted(p.parent.name for p in SESSIONS.glob(f"*/{RUNNING}"))
    if running:
        raise SystemExit(f"実行中のセッションがある（{', '.join(running)}）。finalize か abort の後で reopen する")
    raw = R.rel(Path(args.raw) if Path(args.raw).is_absolute() else REPO_ROOT / args.raw)
    m = re.match(r"^market/policy/([^/]+)/raw/[^/]+\.md$", raw)
    if not m or m.group(1) not in MARKETS:
        raise SystemExit(f"market/policy/{{japan,us}}/raw/ の要旨ファイルを指定する: {args.raw}")
    print(json.dumps(D.reopen_doc(m.group(1), raw, load_catalog(m.group(1))), ensure_ascii=False))
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
                print(f"  {c.published or '----------'} ({c.date_source}) {c.title[:50]} {c.url}")
        except Exception as exc:  # noqa: BLE001
            print(f"[{entry['key']}] 失敗: {type(exc).__name__}: {str(exc)[:120]}")
    load_env()
    today = dt.date.today().isoformat()
    until = (dt.date.today() + dt.timedelta(days=CALENDAR_DAYS_AHEAD)).isoformat()
    fixed, errors = CF.fetch_fixed(catalog.get("calendar", {}).get("fixed_sources", []), today, until, http_get)
    print(f"[calendar] 確定日程 {len(fixed)} 件")
    for row in fixed[:5]:
        print(f"  {row[0]} {row[1]} {row[2]}")
    for error in errors:
        print(f"[calendar] 失敗: {error}")
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
    p.add_argument("--mode", choices=("auto", "full", "update"), default="auto")
    p.add_argument("--date")
    for name in ("finalize", "validate", "abort"):
        sub.add_parser(name).add_argument("--session", required=True)
    sub.add_parser("reopen").add_argument("--raw", required=True)
    sub.add_parser("check-watch").add_argument("--market", choices=MARKETS, required=True)
    s = sub.add_parser("search")
    s.add_argument("source", choices=("boj", "dashboard"))
    s.add_argument("--db", default="CO")
    s.add_argument("--word", nargs="+", required=True)
    args = ap.parse_args()
    handlers = {"prepare": cmd_prepare, "finalize": cmd_finalize, "validate": cmd_validate, "abort": cmd_abort,
                "reopen": cmd_reopen, "check-watch": cmd_check_watch, "search": cmd_search}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
