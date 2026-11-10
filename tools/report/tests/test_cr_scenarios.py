import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT), str(REPORT.parent / "analysis"), str(REPORT.parent / "collect" / "market"),
                str(REPORT.parent / "collect")]

import cr_scenarios as SC  # noqa: E402

LINES = [{"label": "52週安値", "price": 800.0}, {"label": "直近の安値（2026-08-01）", "price": 900.0},
         {"label": "26週線", "price": 950.0}, {"label": "直近の高値（2026-09-01）", "price": 1100.0},
         {"label": "52週高値", "price": 1300.0}]
TECH = {"ok": True, "current": 1000.0, "date": "2026-11-10", "state": "もみ合い（方向感なし）",
        "levels": {"lines": LINES, "atr": 20.0, "stop": {"label": "26週線の 1 ATR 下", "price": 930.0}}}
FLIPS = {"per_cheap": 850.0, "per_rich": 1500.0, "pbr_cheap": 960.0, "pbr_fair": 1200.0, "pbr_rich": 1440.0}
CONTEXT = {"outlook": "警戒", "week": "2026-11-09", "review": "2027-01 の第3四半期決算", "trend": "レンジ"}


def test_three_entries_with_a_merged_level():
    s = SC.build(TECH, FLIPS, CONTEXT)
    assert [e["price"] for e in s["buys"]] == [1000.0, 950.0, 850.0]
    assert s["buys"][0]["label"] == "今の株価"
    # the 26-week line and the PBR cheap price (960, within 3%) are one entry with both reasons
    assert "26週線" in s["buys"][1]["basis"] and "適正PBR" in s["buys"][1]["basis"]
    assert "PER" in s["buys"][2]["basis"]


def test_each_entry_has_its_stop_targets_and_reward_ratio():
    now = SC.build(TECH, FLIPS, CONTEXT)["buys"][0]
    assert now["stop"]["price"] == 930.0            # the next line below (950) less one ATR
    assert now["target1"]["price"] == 1100.0        # the first line above
    assert now["target2"]["price"] == 1200.0        # then the fair-PBR price
    assert (now["down"], now["up1"], now["up2"]) == (-7.0, 10.0, 20.0)
    assert now["rr"] == pytest.approx(1.43, abs=0.01)
    low = SC.build(TECH, FLIPS, CONTEXT)["buys"][2]
    assert low["stop"]["price"] == 780.0            # 52-week low 800 less one ATR


def test_risks_name_the_market_the_results_and_the_entry():
    buys = SC.build(TECH, FLIPS, CONTEXT)["buys"]
    assert any("地合いが警戒" in r for r in buys[0]["risks"])
    assert any("第3四半期決算" in r for r in buys[0]["risks"])
    assert any("割り込む" in r for r in buys[1]["risks"])
    assert any("下方修正" in r for r in buys[2]["risks"])


def test_holder_levels():
    h = SC.build(TECH, FLIPS, CONTEXT)["holder"]
    assert [x["price"] for x in h["take"]] == [1100.0, 1300.0, 1440.0]  # the nearest three (PBR 2割高 before PER)
    assert h["exit"][0]["price"] == 930.0 and h["exit"][1]["price"] == 800.0


def test_value_price_above_the_market_is_a_note_not_an_entry():
    s = SC.build(TECH, {"per_cheap": 1050.0}, CONTEXT)
    assert all(e["price"] < 1050 for e in s["buys"])
    assert "割安圏" in s["buys"][0]["basis"]  # the current price is already in it


def test_without_technicals():
    assert SC.build({"ok": False}, FLIPS, CONTEXT) == {"ok": False, "buys": [], "holder": {"take": [], "exit": []}}


def test_no_advice_or_forecast_words():
    import outlook as O
    text = str(SC.build(TECH, FLIPS, CONTEXT))
    assert not any(w in text for w in O.FORBIDDEN)


def test_targets_are_at_least_one_atr_away_and_distinct():
    lines = LINES + [{"label": "直近の高値（2026-10-01）", "price": 1010.0}, {"label": "x", "price": 1105.0}]
    s = SC.build({**TECH, "levels": {**TECH["levels"], "lines": lines}}, {}, CONTEXT)
    now = s["buys"][0]
    assert now["target1"]["price"] == 1100.0          # 1010 is within one ATR (20) of 1000
    assert now["target2"]["price"] == 1300.0          # 1105 is the same level as 1100


def test_past_lows_above_the_price_are_named_as_ceilings():
    lines = [{"label": "直近の安値（2026-07-01）", "price": 1100.0}, {"label": "52週安値", "price": 800.0}]
    s = SC.build({**TECH, "levels": {**TECH["levels"], "lines": lines}}, {}, CONTEXT)
    assert s["buys"][0]["target1"]["label"] == "以前の安値（2026-07-01）（今は上値の抵抗になりやすい）"
