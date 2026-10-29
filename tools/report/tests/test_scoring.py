import itertools
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import scoring as SC  # noqa: E402

H, N, T = SC.HEAD, SC.NEUTRAL, SC.TAIL


def _kpi(value: float, from_high: float, month: float, streak: int = 0) -> dict:
    return {"value": value, "from_high": from_high, "streak": streak, "changes": {"1m": {"delta": month}}}


def _data(**series) -> SC.Inputs:
    return SC.Inputs(kpis={}, derived={}, series=series)


@pytest.mark.parametrize("ratings, expected", [
    ({"1": T, "2": T, "3": N, "4": N}, "慎重"),   # ① 逆風 and one more: the gap in the old table
    ({"1": T, "2": N, "3": N, "4": N}, "慎重"),
    ({"1": T, "2": T, "3": T, "4": N}, "弱気"),
    ({"1": N, "2": T, "3": T, "4": T}, "慎重"),   # ① not 逆風 is never 弱気
    ({"1": H, "2": H, "3": N, "4": N}, "強気"),
    ({"1": H, "2": T, "3": N, "4": N}, "中立"),   # equal counts
    ({"1": N, "2": N, "3": N, "4": N}, "中立"),
])
def test_combine_examples(ratings, expected):
    assert SC.combine(ratings) == expected


def test_combine_covers_every_combination():
    for combo in itertools.product(SC.RATINGS, repeat=4):
        assert SC.combine(dict(zip("1234", combo))) in ("強気", "中立", "慎重", "弱気")


@pytest.mark.parametrize("total, previous, expected", [
    (-2, None, (T, False)), (-1, None, (N, False)), (2, None, (H, False)),
    (-1, T, (T, True)), (0, T, (N, False)), (1, H, (H, True)), (-1, H, (N, False)), (1, T, (N, False)),
])
def test_rate_thresholds_and_hysteresis(total, previous, expected):
    assert SC.rate(total, previous) == expected


def test_equity_signals_score_drawdown_month_and_streak():
    data = SC.Inputs(kpis={"JP_NIKKEI225": _kpi(62190, -14.1, -6.3, -3)},
                     derived={"JP_NIKKEI225_MA200": {"value": 1.1, "stale": False}},
                     series={"JP_FLOW_FOREIGN": [("2026-10-09", 14298.0), ("2026-10-16", -3747.0)]})
    scores = {s.name: s.score for s in SC.equity_signals("japan", data)}
    assert scores == {"1年高値比": -1, "1か月の騰落率": -1, "週末値の連続": -1, "200日移動平均からの乖離": 0,
                      "海外投資家の売買差引": 0}


def test_threshold_is_inclusive():
    data = SC.Inputs(kpis={"US_SP500": _kpi(1, -10.0, 5.0)}, derived={}, series={})
    scores = {s.name: s.score for s in SC.equity_signals("us", data)}
    assert scores["1年高値比"] == -1 and scores["1か月の騰落率"] == 1


def test_missing_inputs_score_zero_and_are_listed():
    result = SC.score_market("us", SC.Inputs({}, {}, {}), None)
    assert all(v["total"] == 0 and v["rating"] == N for v in result["viewpoints"])
    assert "1年高値比" in result["viewpoints"][0]["missing"]
    assert result["candidate"] == "中立"


def test_stale_derived_value_is_not_scored():
    data = SC.Inputs({}, {"JP_YIELD_GAP": {"value": 0.1, "stale": True}}, {})
    sig = next(s for s in SC.valuation_signals("japan", data) if s.name.startswith("益利回り"))
    assert not sig.available and sig.score == 0


def test_cot_signal_compares_four_weeks_back():
    pts = [("w0", -100000.0), ("w1", 0.0), ("w2", 0.0), ("w3", 0.0), ("w4", -120000.0)]
    assert SC.cot_signal(_data(US_COT_ES_NET=pts)).score == -1
    pts[-1] = ("w4", -105000.0)
    assert SC.cot_signal(_data(US_COT_ES_NET=pts)).score == 0


def test_policy_hike_within_three_months_is_a_headwind():
    data = _data(US_FFR_UPPER=[("2026-07-01", 3.75), ("2026-09-17", 4.0), ("2026-10-26", 4.0)])
    sig = SC.rate_signals("us", data)[0]
    assert sig.score == -1 and "3.75 → 4.00" in sig.value


def test_inflation_band_and_unemployment_rise():
    data = _data(US_CORE_PCE_YOY=[("2026-08-01", 3.0)], US_UNRATE=[("a", 4.0), ("b", 4.1), ("c", 4.2), ("d", 4.3)])
    sigs = {s.name: s.score for s in SC.macro_signals("us", data)}
    assert sigs["基調インフレ（コアPCE）"] == -1 and sigs["失業率の3か月の変化"] == -1


def test_oil_year_on_year_signal():
    pts = [("2025-10-20", 58.0), ("2026-10-20", 107.9)]
    sig = SC.oil_signal(_data(US_WTI=pts))
    assert sig.score == -1 and "+86.0%" in sig.value
    assert SC.oil_signal(_data(US_WTI=[("2025-10-20", 100.0), ("2026-10-20", 65.0)])).score == 1
    assert not SC.oil_signal(_data(US_WTI=[("2026-01-01", 60.0), ("2026-10-20", 107.9)])).available  # no year-ago point


def test_old_monthly_points_count_half():
    data = SC.Inputs({}, {}, {"JP_CI_COINCIDENT": [("a", 1.0), ("b", 1.0), ("c", 1.0), ("2026-08-01", 2.0)],
                              "JP_CI_LEADING": [("a", 1.0), ("b", 1.0), ("c", 1.0), ("2026-10-01", 2.0)]},
                     asof="2026-10-26")
    macro = SC.score_market("japan", data, None)["viewpoints"][2]
    points = {s["name"]: s["points"] for s in macro["signals"]}
    assert points["景気動向指数 一致の3か月の変化"] == 0.5 and points["景気動向指数 先行の3か月の変化"] == 1
    assert macro["total"] == 1.5 and macro["rating"] == N
    assert SC.total_text(1.5) == "+1.5" and SC.total_text(-2.0) == "−2" and SC.total_text(0) == "+0"
    # counted from the month end: a September figure is full weight through mid-November
    assert SC.weighted([SC.Signal("x", "", "", 1, date="2026-09-01")], "2026-11-14")[0].weight == 1
    assert SC.weighted([SC.Signal("x", "", "", 1, date="2026-09-01")], "2026-11-16")[0].weight == 0.5
    assert SC.month_end("2026-02-01") == "2026-02-28"


def _divergence_data(hy_month: float) -> SC.Inputs:
    kpis = {"US_SP500": _kpi(1, -2.0, 6.0), "US_HY_OAS": {"changes": {"1m": {"delta": hy_month}}},
            "JP_NIKKEI225": _kpi(1, -2.0, 6.0)}
    return SC.Inputs(kpis, {}, {})


def test_equity_tailwind_is_cut_when_credit_widens_us_only():
    us = SC.score_market("us", _divergence_data(0.65), None)["viewpoints"][0]
    assert us["rating"] == N and us["adjusted"]
    calm = SC.score_market("us", _divergence_data(0.05), None)["viewpoints"][0]
    assert calm["rating"] == H and not calm["adjusted"]
    jp = SC.score_market("japan", _divergence_data(0.65), None)["viewpoints"][0]
    assert jp["rating"] == H and not jp["adjusted"]
    held = SC.Inputs({"US_SP500": _kpi(1, -2.0, 0.0), "US_HY_OAS": {"changes": {"1m": {"delta": 0.65}}}}, {}, {})
    us_held = SC.score_market("us", held, {"1": H})["viewpoints"][0]  # total +1 would be held as 追い風
    assert us_held["rating"] == N and not us_held["held"]


def test_previous_ratings_feed_hysteresis():
    data = SC.Inputs(kpis={"US_SP500": _kpi(1, -9.0, -5.0)}, derived={}, series={})  # total −1
    fresh = SC.score_market("us", data, None)["viewpoints"][0]
    held = SC.score_market("us", data, {"1": T})["viewpoints"][0]
    assert fresh["rating"] == N and held["rating"] == T and held["held"]
