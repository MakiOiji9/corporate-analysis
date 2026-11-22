import datetime as dt
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_patterns as P  # noqa: E402
import cr_tech_views as V  # noqa: E402


def _rows(closes: list[float]) -> list[dict]:
    day = dt.date(2023, 1, 2)
    return [{"date": (day + dt.timedelta(days=i)).isoformat(), "close": c, "high": c * 1.01, "low": c * 0.99,
             "volume": 100.0 + (i % 5)} for i, c in enumerate(closes)]


UP = [100 + i * 0.5 for i in range(400)]
DOWN = [400 - i * 0.5 for i in range(400)]


def test_view_has_every_aspect_and_overall():
    v = V.view(_rows(UP), P.DAILY)
    assert v["ok"] and v["timeframe"] == P.DAILY and v["current"] == UP[-1]
    assert set(V.KEYS) <= set(v["aspects"])
    for a in v["aspects"].values():
        assert a["confidence"] in ("高", "中", "低") and a["direction"] in (P.UP, P.DOWN, P.FLAT, None)
    assert v["overall"]["scenarios"]["base"] and set(v["chart"]) >= {"close", "mas", "zigzag"}


def test_uptrend_and_downtrend_directions():
    assert V.view(_rows(UP), P.DAILY)["aspects"]["trend"]["direction"] == P.UP
    assert V.view(_rows(DOWN), P.DAILY)["aspects"]["trend"]["direction"] == P.DOWN


def test_weekly_view_works_from_daily_rows():
    v = V.view(_rows(UP), P.WEEKLY)
    assert v["ok"] and v["label"]


def test_short_history_is_not_judged():
    v = V.view(_rows([10.0, 11.0, 12.0]), P.DAILY)
    assert not v["ok"] or v["aspects"]["trend"]["direction"] is None


def test_evidence_carries_style_and_vote():
    for a in V.view(_rows(UP), P.DAILY)["aspects"].values():
        for e in a["evidence"]:
            assert e["style"] in ("順張り", "逆張り", None, "") or isinstance(e["style"], str)
            assert e["vote"] in (-1, 0, 1)
