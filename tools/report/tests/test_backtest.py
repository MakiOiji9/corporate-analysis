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


def test_forward_returns_and_drawdown():
    day = dt.date(2026, 1, 2)
    points = [((day + dt.timedelta(days=i)).isoformat(), 100 - i if i < 30 else 70 + (i - 30)) for i in range(200)]
    dates = [d for d, _ in points]
    out = BT.forward(points, dates, "2026-01-02")
    assert out["r4"] == pytest.approx(-28.0) and out["mdd"] == pytest.approx(-30.0)  # low of 70 on day 30
    late = BT.forward(points, dates, dates[-10])
    assert late["r4"] is None and late["mdd"] is None


def test_summary_groups_and_flags_inverted_signals():
    weeks = []
    for i in range(40):
        good = i % 2 == 0
        weeks.append({"asof": f"w{i}", "japan": {"candidate": "中立", "ratings": {"1": "追い風" if good else "逆風"},
                                                  "signals": {"S": -1 if good else 1},
                                                  "forward": {"r4": 1.0, "r13": 5.0 if good else -5.0, "r26": 0.0,
                                                              "mdd": -2.0}},
                      "us": {"candidate": "慎重", "ratings": {}, "signals": {}, "forward": {}}})
    s = BT.summarize(weeks)
    assert s["japan"]["by_judgement"]["中立"]["r13"]["n"] == 40
    assert s["japan"]["by_viewpoint"]["1"]["追い風"]["mean"] == 5.0
    assert BT.inverted(s) == ["日本: S（−1 のあと +5.0% / +1 のあと −5.0%）"]
    md = BT.render(s, 10, "2026-10-29", weeks)
    assert "| 中立 | 40 |" in md and "向きが逆の信号" in md


def test_replay_runs_on_a_small_repo(tmp_path: Path):
    shutil.copytree(REPO / "tools" / "collect" / "market" / "catalog", tmp_path / "tools/collect/market/catalog")
    (tmp_path / "market" / "data").mkdir(parents=True)
    start = dt.date(2025, 1, 1)
    rows = [f"US_SP500,{(start + dt.timedelta(days=i)).isoformat()},{5000 + i},x" for i in range(400)]
    (tmp_path / "market" / "data" / "us_series.csv").write_text("series_id,date,value,retrieved\n" + "\n".join(rows)
                                                                + "\n", encoding="utf-8")
    weeks = BT.replay(Paths(tmp_path), 1, "2026-02-01")
    assert weeks and all(w["us"]["candidate"] in BT.JUDGEMENT_ORDER for w in weeks)
    assert weeks[0]["us"]["forward"]["r4"] is not None
