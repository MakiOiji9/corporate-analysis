"""Time-series CSV store (market/data/{market}_series.csv) and latest/previous/year-ago summaries.

CSV columns: series_id, date (YYYY-MM-DD), value, retrieved (YYYY-MM-DD).
Writes go through common.file_lock + write_csv_atomic, so parallel runs never lose rows.
"""
from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from common import file_lock, read_csv_rows, today, write_csv_atomic
from series import Obs

FIELDS = ["series_id", "date", "value", "retrieved"]
DAILY_PREVIOUS_DAYS = 30   # daily series compare with ~1 month earlier
YEAR_TOLERANCE_DAYS = 10   # a "year-ago" point may be up to this many days earlier


@dataclass(frozen=True)
class Summary:
    latest_date: str
    latest: float | None
    prev_date: str
    prev: float | None
    year_date: str
    year: float | None


def upsert_series(csv_path: Path, observations: list[Obs]) -> int:
    """Insert or replace (series_id, date) rows. Returns the number of rows written."""
    if not observations:
        return 0
    stamp = today()
    with file_lock(csv_path):
        rows = {(r["series_id"], r["date"]): r for r in read_csv_rows(csv_path)}
        for o in observations:
            rows[(o.series_id, o.date)] = {"series_id": o.series_id, "date": o.date,
                                           "value": _fmt_raw(o.value), "retrieved": stamp}
        write_csv_atomic(csv_path, FIELDS, [rows[k] for k in sorted(rows)])
    return len(observations)


def _fmt_raw(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else repr(round(value, 6))


def load_points(csv_path: Path) -> dict[str, list[tuple[str, float]]]:
    out: dict[str, list[tuple[str, float]]] = {}
    for r in read_csv_rows(csv_path):
        out.setdefault(r["series_id"], []).append((r["date"], float(r["value"])))
    return {k: sorted(v) for k, v in out.items()}


def _shift(date: str, days: int = 0, years: int = 0) -> str:
    d = dt.date.fromisoformat(date)
    if years:
        try:
            d = d.replace(year=d.year + years)
        except ValueError:  # Feb 29
            d = d.replace(year=d.year + years, day=28)
    return (d + dt.timedelta(days=days)).isoformat()


def _at_or_before(points: list[tuple[str, float]], date: str) -> int | None:
    i = bisect.bisect_right([p[0] for p in points], date) - 1
    return i if i >= 0 else None


def _year_ago_index(points: list[tuple[str, float]], i: int) -> int | None:
    target = _shift(points[i][0], years=-1)
    j = _at_or_before(points, target)
    if j is None or points[j][0] < _shift(target, days=-YEAR_TOLERANCE_DAYS):
        return None
    return j


def transformed(points: list[tuple[str, float]], i: int | None, transform: str) -> float | None:
    """Value shown in the table: level / diff (vs previous point) / yoy_pct (vs a year earlier)."""
    if i is None or i < 0:
        return None
    value = points[i][1]
    if transform == "level":
        return value
    if transform == "diff":
        return value - points[i - 1][1] if i > 0 else None
    if transform == "yoy_pct":
        j = _year_ago_index(points, i)
        if j is None or points[j][1] == 0:
            return None
        return (value / points[j][1] - 1) * 100
    raise ValueError(f"unknown transform {transform}")


def summarize(points: list[tuple[str, float]], transform: str = "level",
              frequency: str = "monthly") -> Summary | None:
    if not points:
        return None
    last = len(points) - 1
    if frequency == "daily":
        prev = _at_or_before(points, _shift(points[last][0], days=-DAILY_PREVIOUS_DAYS))
    else:
        prev = last - 1 if last > 0 else None
    year = _year_ago_index(points, last)

    def date_of(i: int | None) -> str:
        return points[i][0] if i is not None else "—"

    return Summary(date_of(last), transformed(points, last, transform),
                   date_of(prev), transformed(points, prev, transform),
                   date_of(year), transformed(points, year, transform))
