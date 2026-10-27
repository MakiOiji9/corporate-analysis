import datetime as dt
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import derived as D  # noqa: E402

WEEK = "2026-10-26"


def _daily(start: str, values: list[float]) -> list[tuple[str, float]]:
    day = dt.date.fromisoformat(start)
    return [((day + dt.timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]


def _extra(market: str, indicator: str, value: str, date: str, note: str = "") -> dict:
    return {"market": market, "indicator": indicator, "value": value, "note": note, "date": date,
            "source": "x", "certainty": "一次"}


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {d["id"]: d for d in items}


def test_parse_number_handles_units_minus_and_blank():
    assert D.parse_number("19.0倍") == 19.0
    assert D.parse_number("−3,747") == -3747
    assert D.parse_number("—") is None and D.parse_number(None) is None


def test_real_policy_rate_uses_each_latest_point():
    series = {"US_FFR_UPPER": [("2026-10-26", 4.0)], "US_CORE_PCE_YOY": [("2026-07-01", 3.1), ("2026-08-01", 3.0)]}
    item = _by_id(D.build_derived(series, [], WEEK))["US_REAL_POLICY"]
    assert item["value"] == pytest.approx(1.0) and item["date"] == "2026-10-26"
    assert [i["date"] for i in item["inputs"]] == ["2026-10-26", "2026-08-01"]


def test_missing_input_leaves_value_none():
    item = _by_id(D.build_derived({"JP_CALL": [("2026-10-23", 1.25)]}, [], WEEK))["JP_REAL_POLICY"]
    assert item["value"] is None


def test_yield_gap_from_searched_per_and_stale_flag():
    series = {"US_10Y": [("2026-10-23", 5.0)], "JP_JGB10Y": [("2026-10-26", 2.8)]}
    extras = [_extra("us", "S&P500 予想PER（12か月先）", "20.0倍", "2026-10-16", "5年平均 19.8、10年平均 19.1"),
              _extra("japan", "日経平均 予想PER", "17.32倍", "2026-08-07")]
    items = _by_id(D.build_derived(series, extras, WEEK))
    assert items["US_YIELD_GAP"]["value"] == pytest.approx(0.0) and not items["US_YIELD_GAP"]["stale"]
    assert items["JP_YIELD_GAP"]["stale"]  # 08-07 is more than 35 days before the week
    assert items["US_PER_VS_10Y_AVG"]["value"] == pytest.approx(0.9)


def test_searched_cells_with_trailing_period_or_bad_date_do_not_crash():
    extras = [_extra("us", "S&P500 予想PER（12か月先）", "19.0倍", "2026-13-45", "5年平均 19.8、10年平均 19.1.")]
    item = _by_id(D.build_derived({}, extras, WEEK))["US_PER_VS_10Y_AVG"]
    assert item["value"] == pytest.approx(-0.1) and item["date"] is None and item["stale"]


def test_difference_is_stale_when_an_input_is():
    series = {"JP_CALL": [("2026-10-23", 1.25)], "JP_CPI_CORE_YOY": [("2026-03-01", 2.0)]}
    item = _by_id(D.build_derived(series, [], WEEK, frozenset({"JP_CPI_CORE_YOY"})))["JP_REAL_POLICY"]
    assert item["stale"] and item["value"] == pytest.approx(-0.75)


def test_moving_average_gap_needs_enough_points():
    assert D.ma_gap([("2026-01-01", 1.0)] * 10, 50) is None
    closes = _daily("2026-01-01", [100.0] * 199 + [110.0])
    date, gap = D.ma_gap(closes, 200)
    assert date == closes[-1][0] and gap == pytest.approx((110 / 100.05 - 1) * 100)


def test_percentile_reports_the_years_covered():
    pts = _daily("2025-10-24", [float(i) for i in range(366)])
    date, share, covered = D.percentile(pts)
    assert share == pytest.approx(100.0) and 0.99 < covered < 1.01
