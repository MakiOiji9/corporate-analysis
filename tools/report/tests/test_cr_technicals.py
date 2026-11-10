import datetime as dt
import math
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_technicals as T  # noqa: E402


def _rows(closes: list[float], volumes: list[float] | None = None, spread: float = 1.0) -> list[dict]:
    day = dt.date(2024, 1, 1)
    return [{"date": (day + dt.timedelta(days=i)).isoformat(), "close": c, "high": c + spread, "low": c - spread,
             "volume": volumes[i] if volumes else 100.0} for i, c in enumerate(closes)]


UP = [100 + i * 0.5 for i in range(400)]
DOWN = [400 - i * 0.5 for i in range(400)]


def test_sma_and_ema():
    assert T.sma([1, 2, 3, 4], 2) == [None, 1.5, 2.5, 3.5]
    e = T.ema([1, 2, 3, 4, 5], 3)
    assert e[:2] == [None, None] and e[2] == 2.0 and e[3] == pytest.approx(3.0) and e[4] == pytest.approx(4.0)


def test_rsi_extremes_and_balance():
    assert T.rsi([float(i) for i in range(30)])[-1] == 100.0
    assert T.rsi([float(30 - i) for i in range(30)])[-1] == pytest.approx(0.0)
    assert T.rsi([100.0 + (i % 2) for i in range(40)])[-1] == pytest.approx(50.0, abs=5)  # +1, −1, +1 ...
    assert T.rsi([1.0] * 10)[-1] is None


def test_bollinger_flat_series_has_zero_width():
    upper, lower = T.bollinger([10.0] * 25)
    assert upper[-1] == lower[-1] == 10.0 and upper[18] is None


def test_atr_constant_range():
    assert T.atr(_rows([100.0] * 30, spread=2.0)) == pytest.approx(4.0)
    assert T.atr(_rows([100.0] * 5)) is None


def test_uptrend_scores_plus_and_is_overbought():
    t = T.evaluate(_rows(UP))
    assert t["trend"]["score"] == 1.0 and t["trend"]["slope"] > 0
    assert t["momentum"]["rsi"] == 100.0 and t["momentum"]["rsi_word"] == "買われすぎ"
    assert t["state"] == "上昇トレンド・買われすぎ"
    assert t["position"]["position"] > T.TOP_ZONE
    assert all(x["price"] < t["current"] for x in t["levels"]["supports"])
    assert all(x["price"] > t["current"] for x in t["levels"]["resistances"])


def test_downtrend_scores_minus_and_is_oversold():
    t = T.evaluate(_rows(DOWN))
    assert t["trend"]["score"] == -1.0
    assert t["state"] == "下降トレンド・売られすぎ"
    assert t["position"]["position"] < T.LOW_ZONE


def test_golden_cross_is_found():
    # the 13-week line crosses the 26-week line on row 246, inside the last CROSS_LOOKBACK rows of 280
    t = T.evaluate(_rows([200 - i * 0.5 for i in range(200)] + [100 + i * 1.5 for i in range(80)]))
    assert t["trend"]["cross"]["kind"] == "golden"
    assert any("ゴールデンクロス" in s for s in t["signals"])


def test_levels_and_stop_follow_the_chart():
    rows = _rows([100 + 10 * math.sin(i / 8) for i in range(400)])
    t = T.evaluate(rows)
    lv = t["levels"]
    supports, resistances = [x["price"] for x in lv["supports"]], [x["price"] for x in lv["resistances"]]
    assert 0 < len(supports) <= T.LEVELS_SHOWN and supports == sorted(supports, reverse=True)
    assert resistances == sorted(resistances)
    assert lv["stop"]["price"] < t["current"]
    assert lv["stop"]["price"] >= round(min(r["low"] for r in rows[-365:]), 2)  # prices are kept to 2 decimals


def test_stop_is_labelled_52_week_low_when_clamped():
    # ATR 40 (high − low), nearest support the 52-week line just under 100: 1 ATR below it is under the 52-week
    # low of 60 (the one dip), so the stop is the 52-week low itself
    rows = _rows([100.0] * 300 + [80.0] + [100.0] * 60, spread=20.0)
    stop = T.evaluate(rows)["levels"]["stop"]
    assert stop["label"] == "52週安値" and stop["price"] == 60.0


def test_price_under_every_average_still_has_the_52_week_low_as_support():
    # a fall to 82, just above the year's low of 79 (one dip): the averages and recent lows are all above the price
    closes = [100.0] * 200 + [80.0] + [100.0] * 160 + [100.0 - i for i in range(1, 19)]
    t = T.evaluate(_rows(closes))
    assert [x["label"] for x in t["levels"]["supports"]] == [T.LOW_52]
    stop = t["levels"]["stop"]
    assert stop["label"] == f"{T.LOW_52}の 1 ATR 下" and stop["price"] < 79.0


def test_short_history_scores_position_only():
    t = T.evaluate(_rows([10.0, 12.0, 11.0]))
    assert t["ok"] and t["trend"]["score"] is None and t["momentum"]["score"] is None
    assert t["score"] == t["position"]["score"] and t["state"] == T.NO_DATA


def test_no_rows():
    t = T.evaluate([])
    assert not t["ok"] and t["score"] is None
    assert T.value_text(t).startswith("不明")
    assert len(T.table_rows(t).splitlines()) == len(T.TABLE_LABELS)


def test_volume_ratio():
    v = T.volume_part(_rows([100.0] * 60, volumes=[100.0] * 40 + [300.0] * 20))
    assert v["ratio"] == pytest.approx(300 / ((100 * 40 + 300 * 20) / 60), abs=0.01) and v["word"] == "増加"
    assert T.volume_part(_rows([100.0] * 10))["ratio"] is None


def test_state_table():
    up, down, flat = {"score": 1.0}, {"score": -1.0}, {"score": 0.0}
    assert T.state(up, {"rsi": 50}, 105, 100) == "上昇トレンド"
    assert T.state(up, {"rsi": 50}, 95, 100) == "上昇トレンド中の押し目"
    assert T.state(down, {"rsi": 50}, 105, 100) == "下降トレンド中の戻り"
    assert T.state(flat, {"rsi": 75}, 100, 100) == "もみ合い・買われすぎ"
    assert T.state(flat, {"rsi": 50}, 100, 100) == "もみ合い（方向感なし）"
    assert T.state({"score": None}, {"rsi": 50}, 100, 100) == T.NO_DATA


def test_alignment_with_the_long_verdict():
    t = {"ok": True, "state": "上昇トレンド中の押し目"}
    assert "見送り" in T.alignment(t, "見送り")
    assert T.alignment(t, "投資検討") is None
    assert "下向き" in T.alignment({"ok": True, "state": "下降トレンド"}, "投資検討")


def test_validate_accepts_conditions_and_rejects_forecasts():
    t = T.evaluate(_rows(UP))
    table = T.table_rows(t)
    ok = f"今の状態は{t['state']}。1,800円まで下がったら26週線を割り込む。"
    assert T.validate(ok, table, t) == []
    issues = T.validate("RSI が高い。2,000円まで上がる。", table, t)
    assert any("状態" in i for i in issues) and any("予想" in i for i in issues)
    edited = table.replace("押し目の目安（下の支持線） | ", "押し目の目安（下の支持線） | 1,000円、", 1)
    assert any("表" in i for i in T.validate(ok, edited, t))
