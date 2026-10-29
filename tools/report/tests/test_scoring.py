import itertools
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import scoring as SC  # noqa: E402

MONEY, ECONOMY, STRESS = (SC.AXIS_LABELS[k] for k in ("money", "economy", "stress"))


def _kpi(value: float, from_high: float, month: float, streak: int = 0) -> dict:
    return {"value": value, "from_high": from_high, "streak": streak,
            "changes": {"1m": {"delta": month}, "1y": {"delta": 10.0}}}


def _data(**series) -> SC.Inputs:
    return SC.Inputs(kpis={}, derived={}, series=series)


def _axis(result: dict, key: str) -> dict:
    return next(a for a in result["axes"] if a["key"] == key)


# ---------------------------------------------------------------- attention

@pytest.mark.parametrize("money, economy, stress, expected", [
    ("中立", "横ばい", "高い", "警戒"),
    ("引き締め", "減速", "普通", "警戒"),
    ("引き締め", "横ばい", "普通", "注意"),
    ("緩和", "減速", "低い", "注意"),
    ("中立", "拡大", "普通", "平常"),
    ("緩和", "拡大", "低い", "平常"),
])
def test_attention_examples(money, economy, stress, expected):
    assert SC.attention({"money": money, "economy": economy, "stress": stress}) == expected


def test_attention_covers_every_combination():
    for combo in itertools.product(MONEY, ECONOMY, STRESS):
        assert SC.attention(dict(zip(("money", "economy", "stress"), combo))) in SC.ATTENTION_WORDS


@pytest.mark.parametrize("total, previous, expected", [
    (2, None, ("引き締め", False)), (1, None, ("中立", False)), (-2, None, ("緩和", False)),
    (1, "引き締め", ("引き締め", True)), (0, "引き締め", ("中立", False)), (-1, "緩和", ("緩和", True)),
    (-1, "引き締め", ("中立", False)),
])
def test_rate_thresholds_and_hysteresis(total, previous, expected):
    assert SC.rate(total, previous, MONEY) == expected


# ---------------------------------------------------------------- signal directions (+1 = attention side)

def test_money_hike_inflation_and_oil_point_to_tightening():
    data = _data(US_FFR_UPPER=[("2026-07-01", 3.75), ("2026-10-26", 4.0)],
                 US_CORE_PCE_YOY=[("2026-08-01", 3.0)], US_WTI=[("2025-10-20", 58.0), ("2026-10-20", 107.9)],
                 US_REAL10Y=[("2026-10-23", 2.66)])
    sigs = {s.name: s.score for s in SC.money_signals("us", data)}
    assert sigs["政策金利の3か月の変化"] == 1 and sigs["基調インフレ（コアPCE）"] == 1
    assert sigs["原油（WTI）の前年比"] == 1 and sigs["実質10年金利（TIPS）"] == 1
    assert "実質10年金利（TIPS）" not in {s.name for s in SC.money_signals("japan", data)}


def test_money_easing_side():
    data = _data(JP_CALL=[("2026-07-01", 0.5), ("2026-10-26", 0.25)], JP_CPI_CORECORE_YOY=[("2026-09-01", 1.0)])
    sigs = {s.name: s.score for s in SC.money_signals("japan", data)}
    assert sigs["政策金利の3か月の変化"] == -1 and sigs["基調インフレ（CPI 生鮮食品・エネルギーを除く）"] == -1


def test_economy_rising_unemployment_and_falling_indicators_point_to_slowing():
    data = _data(JP_UNEMP=[("a", 2.4), ("b", 2.5), ("c", 2.6), ("d", 2.7)],
                 JP_CI_COINCIDENT=[("a", 120.0), ("b", 119.0), ("c", 118.5), ("d", 118.0)],
                 JP_IIP=[("a", 100.0), ("b", 101.0), ("c", 102.0), ("d", 103.0)])
    sigs = {s.name: s.score for s in SC.economy_signals("japan", data)}
    assert sigs["失業率の3か月の変化"] == 1 and sigs["景気動向指数 一致の3か月の変化"] == 1
    assert sigs["鉱工業生産の3か月の変化"] == -1


def test_stress_spreads_volatility_and_drawdown():
    data = SC.Inputs(kpis={"US_HY_OAS": {"changes": {"1m": {"delta": 0.65}}}, "US_VIX": {"value": 30.0},
                           "US_SP500": _kpi(1, -12.0, -6.0)},
                     derived={"US_SP500_RV20": {"value": 31.0, "stale": False}}, series={})
    sigs = {s.name: s.score for s in SC.stress_signals("us", data)}
    assert all(sigs[n] == 1 for n in ("HY スプレッド（米国。日米共通の信用指標）", "VIX",
                                      "指数の値動きの大きさ（20日の実現変動率）", "1年高値からの下落"))
    calm = SC.Inputs(kpis={"US_VIX": {"value": 12.0}, "JP_NIKKEI225": _kpi(1, -1.0, 2.0)},
                     derived={"JP_NIKKEI225_RV20": {"value": 13.0, "stale": False}}, series={})
    result = SC.score_market("japan", calm, None)
    assert _axis(result, "stress")["rating"] == "低い" and result["candidate"] == "平常"


def test_price_momentum_is_reference_only():
    data = SC.Inputs(kpis={"US_SP500": _kpi(1, -1.0, -8.0, -4)}, derived={}, series={})
    result = SC.score_market("us", data, None)
    names = {s["name"] for a in result["axes"] for s in a["signals"]}
    assert "1か月の騰落率" not in names and "週末値の連続" not in names
    ref = {r["name"]: r["value"] for r in result["reference"]}
    assert ref["1か月の騰落率"] == "−8.0%" and ref["週末値の連続"] == "4週連続低下"


def test_missing_inputs_score_zero_and_are_listed():
    result = SC.score_market("us", SC.Inputs({}, {}, {}), None)
    assert all(a["total"] == 0 for a in result["axes"])
    assert [a["rating"] for a in result["axes"]] == ["中立", "横ばい", "普通"] and result["candidate"] == "平常"
    assert "VIX" in _axis(result, "stress")["missing"]


def test_stale_derived_value_is_not_scored():
    data = SC.Inputs({}, {"US_REAL_POLICY": {"value": 3.0, "stale": True}}, {})
    sig = SC.real_policy_signal("us", data)
    assert not sig.available and sig.score == 0


def test_oil_needs_a_year_ago_point():
    assert SC.oil_signal(_data(US_WTI=[("2025-10-20", 100.0), ("2026-10-20", 65.0)])).score == -1
    assert not SC.oil_signal(_data(US_WTI=[("2026-01-01", 60.0), ("2026-10-20", 107.9)])).available
    assert not SC.oil_signal(_data(US_WTI=[("2025-10-20", -37.0), ("2026-10-20", 60.0)])).available


def test_old_monthly_points_count_half():
    data = SC.Inputs({}, {}, {"JP_CI_COINCIDENT": [("a", 1.0), ("b", 1.0), ("c", 1.0), ("2026-08-01", 0.0)],
                              "JP_CI_LEADING": [("a", 1.0), ("b", 1.0), ("c", 1.0), ("2026-10-01", 0.0)]},
                     asof="2026-10-26")
    economy = _axis(SC.score_market("japan", data, None), "economy")
    points = {s["name"]: s["points"] for s in economy["signals"]}
    assert points["景気動向指数 一致の3か月の変化"] == 0.5 and points["景気動向指数 先行の3か月の変化"] == 1
    assert economy["total"] == 1.5 and economy["rating"] == "横ばい"
    assert SC.total_text(1.5) == "+1.5" and SC.total_text(-2.0) == "−2" and SC.total_text(0) == "+0"
    assert SC.weighted([SC.Signal("x", "", "", 1, date="2026-09-01")], "2026-11-14")[0].weight == 1
    assert SC.weighted([SC.Signal("x", "", "", 1, date="2026-09-01")], "2026-11-16")[0].weight == 0.5
    assert SC.month_end("2026-02-01") == "2026-02-28"


def test_previous_labels_feed_hysteresis():
    data = SC.Inputs(kpis={"US_VIX": {"value": 30.0}}, derived={}, series={})  # stress total +1
    fresh = _axis(SC.score_market("us", data, None), "stress")
    held = _axis(SC.score_market("us", data, {"stress": "高い"}), "stress")
    assert fresh["rating"] == "普通" and held["rating"] == "高い" and held["held"]
