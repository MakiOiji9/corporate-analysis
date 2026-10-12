"""Paths, report week and freshness of the collected material for market-report.

The report week is identified by its Monday (YYYY-MM-DD). The material is "fresh" when the
latest completed collect-market-info session (market/LATEST.md) is dated on or after that Monday.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FILL = re.compile(r"<!--\s*FILL:\w")  # same as tools/collect/market/validate.FILL
LATEST_HEADING = re.compile(r"^#\s+地合い情報の最新版\s+—\s+(\d{4}-\d{2}-\d{2})_(\S+)\s*$", re.M)
WEEK_FILE = re.compile(r"^(\d{4}-\d{2}-\d{2})_outlook\.md$")

STATE_NONE, STATE_DRAFT, STATE_DONE = "none", "draft", "done"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def market(self) -> Path:
        return self.root / "market"

    @property
    def latest(self) -> Path:
        return self.market / "LATEST.md"

    @property
    def sessions(self) -> Path:
        return self.market / "sessions"

    @property
    def data(self) -> Path:
        return self.market / "data"

    @property
    def report_dir(self) -> Path:
        return self.market / "report"

    @property
    def catalog_dir(self) -> Path:
        return self.root / "tools" / "collect" / "market" / "catalog"

    @property
    def template_dir(self) -> Path:
        return self.root / ".ai" / "templates" / "market-report"

    def report_file(self, week: str, kind: str) -> Path:
        """kind: facts.json / brief.md / outlook.md / market-report.html"""
        return self.report_dir / f"{week}_{kind}"

    def rel(self, path: Path) -> str:
        try:
            return path.resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return path.as_posix()


def week_monday(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def parse_week(arg: str | None, today: dt.date | None = None) -> str:
    """--week accepts any date of the week; the Monday is returned."""
    day = dt.date.fromisoformat(arg) if arg else (today or dt.date.today())
    return week_monday(day).isoformat()


def latest_session(paths: Paths) -> tuple[str, str] | None:
    """(session name, session date) of the latest completed session, from market/LATEST.md."""
    if not paths.latest.exists():
        return None
    m = LATEST_HEADING.search(paths.latest.read_text(encoding="utf-8"))
    if not m:
        return None
    return f"{m.group(1)}_{m.group(2)}", m.group(1)


def running_sessions(paths: Paths) -> list[str]:
    if not paths.sessions.exists():
        return []
    return sorted(p.parent.name for p in paths.sessions.glob("*/.running"))


def outlook_state(path: Path) -> str:
    if not path.exists():
        return STATE_NONE
    return STATE_DRAFT if FILL.search(path.read_text(encoding="utf-8")) else STATE_DONE


def previous_outlook(paths: Paths, week: str) -> Path | None:
    """The newest completed outlook of an earlier week."""
    if not paths.report_dir.exists():
        return None
    done = []
    for p in paths.report_dir.glob("*_outlook.md"):
        m = WEEK_FILE.match(p.name)
        if m and m.group(1) < week and outlook_state(p) == STATE_DONE:
            done.append((m.group(1), p))
    return max(done)[1] if done else None


def check(paths: Paths, week: str) -> dict:
    latest = latest_session(paths)
    running = running_sessions(paths)
    session, session_date = latest if latest else ("", "")
    fresh = bool(latest) and session_date >= week
    if running:
        reason = f"collect-market-info の実行中: {', '.join(running)}"
    elif not latest:
        reason = "market/LATEST.md が無い（収集の完了セッションが無い）"
    elif not fresh:
        reason = f"最新の収集 {session} が {week} 週より前"
    else:
        reason = f"最新の収集 {session} は {week} 週のもの"
    return {
        "week": week,
        "latest_session": session or None,
        "fresh": fresh,
        "running": running,
        "outlook": outlook_state(paths.report_file(week, "outlook.md")),
        "html_exists": paths.report_file(week, "market-report.html").exists(),
        "reason": reason,
    }
