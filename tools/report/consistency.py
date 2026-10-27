"""Week-over-week check of the searched calendar: the same event listed with a different date.

The calendar rows come from web search, so a deadline can silently move between weeks
(e.g. a stop-gap budget ending 12-11 last week and 12-04 this week). Officially fetched rows
("確定") repeat every month and are not compared. Exact name matches are paired first, the
rest by character-bigram overlap against the shorter name, so recurring releases with
near-identical names (GDP 1次速報 / 2次速報) stay with their own row.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from facts import MARKET_LABEL, event_span

SIMILAR = 0.5                 # bigram overlap (|A ∩ B| / min(|A|, |B|)) that counts as the same event
COMPARED_KINDS = ("検索",)
NOISE = re.compile(r"[\s（）()・、。「」]")


def normalized(name: str) -> str:
    return NOISE.sub("", name)


def bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


def overlap(a: str, b: str) -> float:
    x, y = bigrams(normalized(a)), bigrams(normalized(b))
    return len(x & y) / min(len(x), len(y))


def previous_facts(report_dir: Path, week: str) -> dict | None:
    done = sorted(p for p in report_dir.glob("*_facts.json") if p.name[:10] < week)
    return json.loads(done[-1].read_text(encoding="utf-8")) if done else None


def _start(event: dict) -> str | None:
    span = event_span(event["date"])
    return span[0] if span else None


def _exact(event: dict) -> bool:
    span = event_span(event["date"])
    return bool(span and span[2])


def _moved(before: dict, after: dict) -> bool:
    """Both dated to the day and different. '2026-12 予定' becoming '2026-12-11' is a confirmation."""
    return _exact(before) and _exact(after) and _start(before) != _start(after)


def moved_events(current: list[dict], previous: list[dict], week: str) -> list[dict]:
    """[{market, event, previous_event, before, after}] for searched events whose date changed."""
    now = [e for e in current if e.get("kind") in COMPARED_KINDS]
    before = [e for e in previous if e.get("kind") in COMPARED_KINDS and (_start(e) or "") >= week]
    unmatched = list(now)
    pairs: list[tuple[dict, dict]] = []
    leftover = []
    for p in before:
        exact = next((e for e in unmatched if e["market"] == p["market"]
                      and normalized(e["event"]) == normalized(p["event"])), None)
        if exact:
            unmatched.remove(exact)
            pairs.append((p, exact))
        else:
            leftover.append(p)
    for p in leftover:
        best = max((e for e in unmatched if e["market"] == p["market"]),
                   key=lambda e: overlap(e["event"], p["event"]), default=None)
        if best and overlap(best["event"], p["event"]) >= SIMILAR:
            unmatched.remove(best)
            pairs.append((p, best))
    return [{"market": e["market"], "event": e["event"], "previous_event": p["event"],
             "before": p["date"], "after": e["date"]}
            for p, e in pairs if _moved(p, e)]


def check(facts: dict, report_dir: Path) -> list[dict]:
    """[{market, item, detail}] shown in brief 13. and outlook 7."""
    prev = previous_facts(report_dir, facts["week"])
    if not prev:
        return []
    out = []
    for m in moved_events(facts["events"], prev.get("events", []), facts["week"]):
        name = m["event"] if m["event"] == m["previous_event"] else f"{m['event']}（前週: {m['previous_event']}）"
        out.append({"market": m["market"], "item": f"日付が前週と違う: {name}",
                    "detail": f"前週 {m['before']} → 今週 {m['after']}（{prev['week']} 週の facts.json と比較）"})
    return out


def label(row: dict) -> str:
    return f"{MARKET_LABEL.get(row['market'], row['market'])}: {row['item']}（{row['detail']}）"
