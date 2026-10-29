import datetime as dt
import shutil
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import backtest as BT  # noqa: E402
from state import Paths  # noqa: E402


def _daily(start: str, values: list[float]) -> list[tuple[str, float]]:
    day = dt.date.fromisoformat(start)
    return [((day + dt.timedelta(days=i)).isoformat(), v) for i, v in enumerate(values)]


def test_fridays_start_on_the_first_friday():
    assert BT.fridays("2026-10-26", "2026-11-10") == ["2026-10-30", "2026-11-06"]


def test_published_cuts_by_release_lag_so_nothing_from_the_future_is_used():
    catalogs = {"M": {"frequency": "monthly", "market": "us"}, "J": {"frequency": "monthly", "market": "japan"},
                "Q": {"frequency": "quarterly", "market": "japan"}, "D": {"frequency": "daily"}}
    raw = {"M": [("2026-08-01", 1.0), ("2026-09-01", 2.0)], "J": [("2026-08-01", 1.0), ("2026-09-01", 2.0)],
           "Q": [("2026-04-01", 1.0), ("2026-07-01", 2.0)], "D": [("2026-10-15", 5.0), ("2026-10-16", 6.0)]}
    pub = BT.Published(catalogs, raw, raw)
    cut, _ = pub.at("2026-10-16")
    assert cut["M"] == [("2026-08-01", 1.0), ("2026-09-01", 2.0)]  # US: 09-01 + 45 days = 10-16, published
    assert cut["J"] == [("2026-08-01", 1.0)]                       # Japan: September is out ~70 days later
    assert cut["Q"] == [("2026-04-01", 1.0)]                       # Q3 (07-01) is not out before mid-November
    cut, _ = pub.at("2026-10-15")
    assert cut["M"] == [("2026-08-01", 1.0)] and cut["D"] == [("2026-10-15", 5.0)]
    assert BT.lag_days({"frequency": "monthly", "release_lag_days": 30}) == 30


def test_volatility_drawdown_and_the_end_of_the_data():
    calm = _daily("2026-01-02", [100.0 + (i % 2) * 0.1 for i in range(120)])
    crash = _daily("2026-01-02", [100.0 - i * 0.5 for i in range(120)])
    v_calm, dd_calm, _ = BT.vol_and_drawdown(calm, [d for d, _ in calm], "2026-01-02")
    v_crash, dd_crash, ret = BT.vol_and_drawdown(crash, [d for d, _ in crash], "2026-01-02")
    assert v_calm > 0 and dd_calm is False and dd_crash is True and ret == pytest.approx(-45.5)
    dates = [d for d, _ in calm]
    assert BT.vol_and_drawdown(calm, dates, dates[-10]) == (None, None, None)


def test_level_change_uses_the_level_weeks_later():
    pts = [("2026-01-01", 4.0), ("2026-04-01", 4.5), ("2026-08-01", 5.0)]
    dates = [d for d, _ in pts]
    assert BT.level_change(pts, dates, "2026-01-02", 26) == pytest.approx(0.5)  # 07-03 reads the 04-01 level
    assert BT.level_change(pts, dates, "2026-06-01", 26) is None              # past the data


def _week(i: int, stress: str, vol: float) -> dict:
    return {"asof": f"w{i:03d}", "japan": {"labels": {"stress": stress, "attention": "警戒" if stress == "高い" else "平常",
                                                      "money": "中立", "economy": "横ばい"},
                                           "after": {"vol": vol, "dd": 100.0 if stress == "高い" else 0.0, "ret": 1.0,
                                                     "policy": 0.0, "ten": 0.0, "unemp": 0.0}},
            "us": {"labels": {}, "after": {}}}


def test_summary_orders_labels_and_judges_both_halves():
    weeks = []
    for i in range(160):  # every 4th is sampled: 40 weeks, 20 per half
        stress = ("高い", "普通", "低い")[i // 4 % 3]
        weeks.append(_week(i, stress, {"高い": 30.0, "普通": 18.0, "低い": 11.0}[stress]))
    s = BT.summarize(weeks)["japan"]
    vol = next(c for c in s["checks"] if c["key"] == "stress" and c["outcome"] == "vol")
    assert vol["verdict"] == BT.MEANS_OK and vol["by_half"]["前半"]["高い"]["mean"] == 30.0
    assert vol["by_half"]["前半"]["高い"]["episodes"] >= 2
    money = next(c for c in s["checks"] if c["key"] == "money" and c["outcome"] == "policy")
    assert money["verdict"] == BT.MEANS_UNKNOWN  # only 中立 was seen
    md = BT.render(BT.summarize(weeks), 10, "2026-10-29", weeks)
    assert "意味どおり" in md and "参考（目標ではない）" in md


def test_reversed_and_weak_verdicts():
    assert BT.verdict([False, False]) == BT.MEANS_REVERSED
    assert BT.verdict([True, False]) == BT.MEANS_WEAK
    assert BT.verdict([True, None]) == BT.MEANS_UNKNOWN


def test_replay_runs_on_a_small_repo(tmp_path: Path):
    shutil.copytree(REPO / "tools" / "collect" / "market" / "catalog", tmp_path / "tools/collect/market/catalog")
    (tmp_path / "market" / "data").mkdir(parents=True)
    start = dt.date(2025, 1, 1)
    rows = [f"US_SP500,{(start + dt.timedelta(days=i)).isoformat()},{5000 + i},x" for i in range(400)]
    (tmp_path / "market" / "data" / "us_series.csv").write_text("series_id,date,value,retrieved\n" + "\n".join(rows)
                                                                + "\n", encoding="utf-8")
    weeks = BT.replay(Paths(tmp_path), 1, "2026-02-01")
    assert weeks and all(w["us"]["labels"]["attention"] in ("平常", "注意", "警戒") for w in weeks)
    assert weeks[0]["us"]["after"]["vol"] is not None
