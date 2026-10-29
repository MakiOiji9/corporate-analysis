import datetime as dt
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import sectors as SE  # noqa: E402


def _line(start: float, end: float, days: int = 100) -> list[tuple[str, float]]:
    first = dt.date(2026, 7, 20)
    return [((first + dt.timedelta(days=i)).isoformat(), start + (end - start) * i / (days - 1)) for i in range(days)]


def _entry(sid: str, name: str, market: str = "us") -> dict:
    return {"id": sid, "name": name, "market": market, "display": "sectors", "params": {"symbol": sid[-3:]},
            "source": "x"}


def test_changes_gap_against_index_and_ranking():
    catalogs = {e["id"]: e for e in (_entry("US_SEC_AAA", "A"), _entry("US_SEC_BBB", "B"), _entry("US_SEC_CCC", "C"),
                                    _entry("US_SEC_DDD", "D"), _entry("US_SEC_EEE", "E"), _entry("US_SEC_FFF", "F"),
                                    _entry("US_SEC_GGG", "G"))}
    series = {"US_SP500": _line(100, 110)}
    for i, sid in enumerate(sorted(catalogs)):
        series[sid] = _line(100, 100 + i * 5)  # A flat ... G +30% over the span
    out = SE.build_sectors(catalogs, series)["us"]
    rows = {r["id"]: r for r in out["rows"]}
    index_m1 = out["index_m1"]
    assert rows["US_SEC_GGG"]["rel1"] == pytest.approx(rows["US_SEC_GGG"]["m1"] - index_m1)
    assert out["top"] == ["US_SEC_GGG", "US_SEC_FFF", "US_SEC_EEE"]
    assert out["bottom"] == ["US_SEC_AAA", "US_SEC_BBB", "US_SEC_CCC"]
    assert not set(out["top"]) & set(out["bottom"])


def test_a_stalled_etf_is_not_compared_with_a_later_index_span():
    catalogs = {"US_SEC_AAA": _entry("US_SEC_AAA", "A")}
    index = _line(100, 110)
    stalled = _line(100, 120)[:-20]  # stops 20 days before the index
    out = SE.build_sectors(catalogs, {"US_SP500": index, "US_SEC_AAA": stalled})["us"]
    assert out["rows"][0]["m1"] is None and out["rows"][0]["rel1"] is None


def test_short_lists_and_missing_series():
    catalogs = {e["id"]: e for e in (_entry("US_SEC_AAA", "A"), _entry("US_SEC_BBB", "B"))}
    out = SE.build_sectors(catalogs, {"US_SP500": _line(100, 110), "US_SEC_AAA": _line(100, 120)})["us"]
    assert out["top"] == ["US_SEC_AAA"] and out["bottom"] == []
    assert next(r for r in out["rows"] if r["id"] == "US_SEC_BBB")["m1"] is None
    assert SE.build_sectors({}, {}) == {}
