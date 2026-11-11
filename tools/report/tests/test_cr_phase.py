import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_phase as PH  # noqa: E402

BASE = {"from_high": -5.0, "from_low": 10.0, "pos52": 50.0, "trend": "レンジ", "tech_state": "もみ合い（方向感なし）",
        "rsi": 50.0, "ma26_gap": 0.0, "step1": "B", "step2": "B", "flags": [], "step3": "妥当", "per_position": 50,
        "price_rate": 8.0, "eps_rate": 8.0}


def _ev(**kw):
    return PH.evaluate({**BASE, **kw})


def test_neither_phase():
    out = _ev()
    assert out["phase"] == PH.NONE and out["verdict"] == "下落局面でも上昇局面でもない"


@pytest.mark.parametrize("kw, verdict", [
    ({"from_high": -30.0, "step3": "割安"}, PH.DIP_GOOD),
    ({"from_high": -30.0, "per_position": 20}, PH.DIP_GOOD),
    ({"from_high": -30.0, "step1": "C", "step3": "割安"}, PH.DIP_TRAP),
    ({"from_high": -30.0}, PH.DIP_NOT_CHEAP),
    ({"from_high": -10.0, "trend": "下降トレンド", "step2": "C"}, PH.DIP_WEAK),
])
def test_down_phase(kw, verdict):
    out = _ev(**kw)
    assert out["phase"] == PH.DOWN and out["verdict"] == verdict


@pytest.mark.parametrize("kw, verdict", [
    ({"pos52": 90.0}, PH.UP_EARNED),
    ({"from_low": 40.0, "tech_state": "上昇トレンド"}, PH.UP_EARNED),
    ({"pos52": 90.0, "rsi": 75.0}, PH.UP_HOPE),
    ({"pos52": 90.0, "step3": "割高"}, PH.UP_HOPE),
    ({"pos52": 90.0, "price_rate": 25.0, "eps_rate": 5.0}, PH.UP_HOPE),
    ({"pos52": 90.0, "step1": "C"}, PH.UP_WEAK),
])
def test_up_phase(kw, verdict):
    out = _ev(**kw)
    assert out["phase"] == PH.UP and out["verdict"] == verdict


def test_a_fall_wins_over_a_long_uptrend():
    out = _ev(from_high=-32.0, trend="上昇トレンド", step3="割安")
    assert out["phase"] == PH.DOWN


def test_checks_are_listed_with_their_result():
    out = _ev(from_high=-30.0, step3="割安")
    items = {c["item"]: c["ok"] for c in out["checks"]}
    assert items["事業・財務の質（STEP 1・2 が A/B、赤信号なし）"] is True
    assert items["割安（STEP 3 割安、または PER が過去レンジの下側）"] is True


def test_missing_material_is_unknown_not_good():
    out = _ev(from_high=-30.0, step1=None, step3="割安")
    assert out["verdict"] != PH.DIP_GOOD
