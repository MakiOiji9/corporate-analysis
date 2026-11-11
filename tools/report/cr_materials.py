"""How fresh the company report's material is, and who collects it when it is not.

The report scripts never fetch material themselves (the share prices that prepare refreshes are the one
exception): each material below has an as-of date, a maximum age and the collect-company-info agent that brings
it. check routes a stale or missing one to collect-company-info (mode=update with those agents and items), or to
market-report for the market data, before the report is prepared; the report shows every material's as-of date.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path

import mdparse as M

ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
FILE_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})_")
NEWS_SPAN_DAYS = 80  # the disclosure table must reach about three months back from its collection day
MARKET_MAX_DAYS = 7
COLLECT_SKILL, MARKET_SKILL, PREPARE = "collect-company-info", "market-report", "prepare"


@dataclass(frozen=True)
class Material:
    key: str
    label: str
    max_days: int
    by: str        # who refreshes it: a collect-company-info agent, market-report, or prepare (the share prices)
    item: str      # what to ask the agent for (collect-company-info's 項目)


MATERIALS = (
    Material("prices", "日々の株価", 7, PREPARE, "株価"),
    Material("news", "直近3か月の開示・ニュース", 7, "collect-ir",
             "直近3か月の適時開示・決算・業績修正・主要ニュースの日付と見出し"),
    Material("consensus", "アナリスト予想・株価指標", 30, "collect-peers-valuation",
             "アナリスト予想（今期・来期の予想EPS）と株価指標"),
    Material("market", "地合いレポート（指数・業種の値動き）", MARKET_MAX_DAYS, MARKET_SKILL, ""),
    # the annual report's fiscal year end: the next report is out within about 13 months
    Material("governance", "大株主・役員・増資の履歴（有価証券報告書）", 400, "collect-filings",
             "大株主・役員・発行済株式数の推移（有価証券報告書の XBRL から yuho_governance.py）"),
    Material("management", "経営者の目標と実績・発言", 120, "collect-ir",
             "経営者の目標と実績・社長メッセージ（過去3〜4年の決算説明会資料）"),
)
JAPAN_TICKER = re.compile(r"^\d{3}[0-9A-Z]_")


def _newest(directory: Path, pattern: str) -> Path | None:
    files = sorted(p for p in directory.glob(pattern) if FILE_DATE.match(p.name))
    return files[-1] if files else None


def _file_date(path: Path | None) -> str | None:
    return FILE_DATE.match(path.name).group(1) if path else None


def _prices_date(company_path: Path) -> str | None:
    path = company_path / "data" / "prices.csv"
    if not path.exists():
        return None
    with path.open(encoding="utf-8", newline="") as f:
        dates = [r.get("date") for r in csv.DictReader(f) if r.get("date")]
    return max(dates) if dates else None


def news_span(path: Path) -> tuple[str | None, str | None]:
    """(oldest, newest) date of the table rows of a press-releases file."""
    dates = [m.group(1) for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("| ")
             for m in [ISO_DATE.search(line.split("|")[1])] if m]
    return (min(dates), max(dates)) if dates else (None, None)


def _age(date: str | None, today: str) -> int | None:
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(date)).days if date else None


def _state(m: Material, date: str | None, today: str, note: str = "") -> dict:
    age = _age(date, today)
    stale = age is None or age > m.max_days or bool(note)
    why = ("無い" if date is None else note or (f"{age}日前（上限 {m.max_days}日）" if stale else ""))
    return {"key": m.key, "label": m.label, "date": date, "age_days": age, "max_days": m.max_days, "by": m.by,
            "item": m.item, "stale": stale, "why": why}


def evaluate(company_path: Path, outlook: dict, today: str) -> list[dict]:
    """One row per material: {key, label, date, age_days, max_days, by, item, stale, why}."""
    out = []
    for m in MATERIALS:
        note = ""
        if m.key == "prices":
            date = _prices_date(company_path)
        elif m.key == "news":
            # an update writes only what is new since the last collection: the span is over every file's rows
            files = sorted((company_path / "raw" / "news").glob("*_press-releases.md"))
            date = _file_date(_newest(company_path / "raw" / "news", "*_press-releases.md"))
            oldest = min((d for p in files if (d := news_span(p)[0])), default=None)
            if date and (not oldest or _age(oldest, date) < NEWS_SPAN_DAYS):
                note = f"表の範囲が3か月に届かない（最も古い行 {oldest or '無し'}）"
        elif m.key == "consensus":
            date = _file_date(_newest(company_path / "raw" / "ir", "*_valuation-data.md"))
        elif m.key == "governance":
            if not JAPAN_TICKER.match(company_path.name):  # no EDINET annual report for a US company
                out.append({**_state(m, None, today), "stale": False, "why": "米国株は対象外", "date": None})
                continue
            date = _governance_date(company_path)
        elif m.key == "management":
            date = _management_date(_newest(company_path / "raw" / "ir", "*_management.md"))
        else:
            date = outlook.get("week")
        out.append(_state(m, date, today, note))
    return out


def _governance_date(company_path: Path) -> str | None:
    """The fiscal year end of the annual report data/governance.json was made from."""
    path = company_path / "data" / "governance.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("as_of") if path.exists() else None
    except ValueError:
        return None


def _management_date(path: Path | None) -> str | None:
    """The latest results briefing the file names in its chapter 1, else the collection day."""
    if not path:
        return None
    first = M.section(path.read_text(encoding="utf-8"), "1.")
    found = ISO_DATE.search(first or "")
    return found.group(1) if found else _file_date(path)


def next_for(materials: list[dict]) -> str | None:
    """market-report for stale market data, then collect-company-info for stale company material; None when every
    material the report cannot refresh itself is fresh (prepare refreshes the share prices)."""
    stale = [m for m in materials if m["stale"] and m["by"] != PREPARE]
    if any(m["by"] == MARKET_SKILL for m in stale):
        return MARKET_SKILL
    return COLLECT_SKILL if stale else None


def collect_request(materials: list[dict]) -> dict | None:
    """collect-company-info's arguments for the stale company material: {mode, agents, items}."""
    stale = [m for m in materials if m["stale"] and m["by"] not in (PREPARE, MARKET_SKILL)]
    if not stale:
        return None
    return {"mode": "update", "agents": sorted({m["by"] for m in stale}), "items": [m["item"] for m in stale]}


def as_of_line(materials: list[dict]) -> str:
    """'日々の株価 2026-11-10・…' for the report (each material with its as-of date; 古い材料 marked)."""
    return "、".join(f"{m['label']} {m['date'] or '無し'}" + ("（古い材料）" if m["stale"] else "") for m in materials)
