"""PreToolUse hook: block file writes that the collection skills' rules forbid.

Claude Code passes the tool call as JSON on stdin. Exit 2 blocks the call and the
stderr message is shown to the agent; exit 0 lets it through. Standard library only,
so it runs with any Python 3.10+ (`python -I tools/guard/write_guard.py`).

Rules (paths relative to the repository; writes outside it are not checked):
  1. Script-only files (data CSVs, sources/, index.csv, tasks.json, status.md, generated
     raw tables) are never written by hand.
  2. market/**/raw/*.md: the scripts create them. Only an existing file that still has
     <!-- FILL:... --> markers may be changed, and only with Edit (not overwritten). While a
     session runs, its allowed_files stay editable after the last FILL is gone, so a summariser
     can correct its own output; afterwards the file is immutable (market_collect.py reopen).
  3. companies/*/raw/**: files collected on an earlier day are immutable.
  4. While a market session is running (market/sessions/*/.running), only the files listed
     in that session's tasks.json "allowed_files" may be written.
  5. market/report/: facts.json, brief.md and the HTML are script-only. {week}_outlook.md is
     created by market_report.py prepare and only edited (not overwritten); once an earlier
     week's outlook is finished (no FILL left) it is immutable.
  6. companies/*/analysis/{five-forces,three-c,moat,swot,profitability,cash-flow,growth,safety}/: {date}_brief.md and
     {date}_{kind}.json are script-only. {date}_{kind}.md is created by the analysis script's prepare (five_forces.py /
     three_c.py / moat.py / swot.py / profitability.py / cash_flow.py / growth.py / safety.py) and only edited (not
     overwritten);
     once an earlier day's analysis is built (its json exists) it is immutable.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
FILL = re.compile(r"<!--\s*FILL:\w")  # same as validate.FILL; the header note "<!-- FILL:... -->" must not match
RAW_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
SCRIPT_ONLY = [
    re.compile(p) for p in (
        r"^market/data/",
        r"^market/LATEST\.md$",
        r"^market/.*/sources/",
        r"^market/policy/[^/]+/index\.csv$",
        r"^market/sessions/[^/]+/(tasks\.json|status\.md|\.running|\.baseline\.json)$",
        r"^market/sessions/[^/]+/raw/(indicators-[^/]+|policy-digest)\.md$",
        r"^companies/[^/]+/sources/",
        r"^companies/[^/]+/data/",
        r"^market/report/[^/]+_(facts\.json|brief\.md|market-report\.html)$",
        r"^companies/[^/]+/analysis/(five-forces|three-c|moat|swot|profitability|cash-flow|growth|safety)/[^/]+_(brief\.md"
        r"|five-forces\.json|three-c\.json|moat\.json|swot\.json|profitability\.json|cash-flow\.json|growth\.json"
        r"|safety\.json)$",
    )
]
ANALYSIS_SCRIPT = {"five-forces": "five_forces.py", "three-c": "three_c.py", "moat": "moat.py", "swot": "swot.py",
                   "profitability": "profitability.py", "cash-flow": "cash_flow.py",
                   "growth": "growth.py", "safety": "safety.py"}
ANALYSIS_MD = re.compile(
    r"^companies/[^/]+/analysis/(five-forces|three-c|moat|swot|profitability|cash-flow|growth|safety)/"
    r"(\d{4}-\d{2}-\d{2})"
    r"_(?P<kind>[\w-]+)\.md$")
MARKET_RAW = re.compile(r"^market/(policy/[^/]+|sessions/[^/]+)/raw/[^/]+\.md$")
COMPANY_RAW = re.compile(r"^companies/[^/]+/raw/")
REPORT_OUTLOOK = re.compile(r"^market/report/(\d{4}-\d{2}-\d{2})_outlook\.md$")
ABORT_HINT = "スキルを中断するには: python -I tools/collect/market/market_collect.py abort --session <session>"


def relative(path_str: str, cwd: str, root: Path) -> str | None:
    path = Path(path_str)
    if not path.is_absolute():
        path = Path(cwd or root) / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def running_allowed(root: Path) -> tuple[list[str], set[str]]:
    """Running sessions and the union of their allowed_files."""
    sessions, allowed = [], set()
    for marker in sorted((root / "market" / "sessions").glob("*/.running")):
        sessions.append(marker.parent.name)
        tasks = marker.parent / "tasks.json"
        if tasks.exists():
            try:
                for task in json.loads(tasks.read_text(encoding="utf-8")).get("tasks", []):
                    allowed.update(task.get("allowed_files", []))
            except (OSError, ValueError):
                pass
    return sessions, allowed


def outlook_reason(tool: str, rel: str, target: Path, week: str, today: str) -> str | None:
    if not target.exists():
        return f"{rel} は market_report.py prepare が骨組みを作る。新しいファイルを作らない。"
    if tool == "Write":
        return f"{rel} は上書きしない。Edit で <!-- FILL:... --> の部分（build の指摘箇所）だけを直す。"
    day = dt.date.fromisoformat(today)
    this_monday = (day - dt.timedelta(days=day.weekday())).isoformat()
    if week < this_monday and not FILL.search(target.read_text(encoding="utf-8", errors="replace")):
        return (f"{rel} は過去の週の完成済み地合い判断なので変更禁止。作り直すときはユーザーの指示で "
                f"market_report.py prepare --week {week} --redo を実行する。")
    return None


def analysis_reason(tool: str, rel: str, target: Path, kind: str, date: str, today: str) -> str | None:
    script = ANALYSIS_SCRIPT[kind]
    if not target.exists():
        return f"{rel} は {script} prepare が骨組みを作る。新しいファイルを作らない。"
    if tool == "Write":
        return f"{rel} は上書きしない。Edit で <!-- FILL:... --> の部分（build の指摘箇所）だけを直す。"
    if date < today and target.with_name(f"{date}_{kind}.json").exists():
        return (f"{rel} は過去の日付の完成済み分析（{kind}）なので変更禁止。作り直すときはユーザーの指示で "
                f"{script} prepare --redo を実行する。")
    return None


def decide(tool: str, rel: str | None, root: Path, today: str) -> str | None:
    """Reason to block, or None to allow."""
    if tool not in WRITE_TOOLS or rel is None:
        return None
    target = root / rel
    if any(p.search(rel) for p in SCRIPT_ONLY):
        return f"{rel} はスクリプトだけが書くファイル。手で編集しない（tools/collect の該当スクリプトを再実行する）。"
    sessions, allowed = running_allowed(root)
    if MARKET_RAW.match(rel):
        if not target.exists():
            return f"{rel}: market の raw はスクリプトが骨組みを作る。新しいファイルを作らない。"
        if tool == "Write":
            return f"{rel} は上書きしない。Edit で <!-- FILL:... --> の行（実行中なら自分の担当ファイルの誤り）だけを直す。"
        if rel not in allowed and not FILL.search(target.read_text(encoding="utf-8", errors="replace")):
            return (f"{rel} は完成済みの raw なので変更禁止。作り直すときはユーザーの指示で "
                    f"market_collect.py reopen --raw {rel} を実行する。")
    outlook = REPORT_OUTLOOK.match(rel)
    if outlook:
        reason = outlook_reason(tool, rel, target, outlook.group(1), today)
        if reason:
            return reason
    analysis = ANALYSIS_MD.match(rel)
    if analysis and analysis.group("kind") == analysis.group(1):
        reason = analysis_reason(tool, rel, target, analysis.group(1), analysis.group(2), today)
        if reason:
            return reason
    if COMPANY_RAW.match(rel) and target.exists():
        m = RAW_DATE.match(target.name)
        if m and m.group(1) < today:
            return f"{rel} は過去の収集日の raw なので変更禁止。再収集は新しい日付のファイルとして追加する。"
    if sessions and rel not in allowed:
        return (f"collect-market-info の実行中（{', '.join(sessions)}）。書けるのは tasks.json の allowed_files "
                f"に載ったファイルだけで、{rel} は対象外。{ABORT_HINT}")
    return None


def check_cli(path: str) -> int:
    """Manual check for agents without hooks (GitHub Copilot): write_guard.py --check <path>."""
    sys.stdout.reconfigure(encoding="utf-8")
    reason = decide("Edit", relative(path, str(Path.cwd()), REPO_ROOT), REPO_ROOT, dt.date.today().isoformat())
    print(f"BLOCKED: {reason}" if reason else f"OK {path}")
    return 2 if reason else 0


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        return check_cli(sys.argv[2])
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0  # not a tool call we understand; never break the session
    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return 0
    reason = decide(tool, relative(path, payload.get("cwd", ""), REPO_ROOT), REPO_ROOT,
                    dt.date.today().isoformat())
    if reason:
        sys.stderr.reconfigure(encoding="utf-8")
        print(f"[write_guard] BLOCKED: {reason}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
