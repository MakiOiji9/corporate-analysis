import datetime as dt
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT), str(REPORT.parent / "analysis"), str(REPORT.parent / "collect" / "market"),
                str(REPORT.parent / "collect")]

import cr_moves as MV  # noqa: E402
import news_table as NT  # noqa: E402

NEWS = """# プレスリリース

## 1. 適時開示・プレスリリース
| 日付 | 見出し | 要旨 | URL |
|---|---|---|---|
| 2026-10-09 | 第2四半期決算短信 | 通期見通しを下方修正 | https://example.com/a |
| 2026-09-01 | 新製品の発売 | 見出しのみ | https://example.com/b |
"""


def _days(n: int, end: str = "2026-11-10") -> list[str]:
    """n weekdays ending on `end`."""
    out, day = [], dt.date.fromisoformat(end)
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= dt.timedelta(days=1)
    return out[::-1]


def _series(index_moves: list[float], beta: float, own: dict[str, float] | None = None):
    """A stock that moves beta × the index each day, plus its own moves on given days."""
    dates = _days(len(index_moves) + 1)
    idx, stock = [1000.0], [100.0]
    for d, m in zip(dates[1:], index_moves):
        idx.append(idx[-1] * (1 + m))
        stock.append(stock[-1] * (1 + beta * m + (own or {}).get(d, 0.0)))
    rows = [{"date": d, "close": c, "high": c * 1.005, "low": c * 0.995, "volume": 100.0} for d, c in zip(dates, stock)]
    return dates, rows, [(d, v) for d, v in zip(dates, idx)]


def test_news_table_reads_every_file_and_classifies(tmp_path):
    (tmp_path / "2026-10-11_press-releases.md").write_text(NEWS, encoding="utf-8")
    (tmp_path / "2026-11-01_press-releases.md").write_text(NEWS.replace("2026-09-01", "2026-10-30"), encoding="utf-8")
    items = NT.load(tmp_path)
    assert [i["date"] for i in items] == ["2026-10-30", "2026-10-09", "2026-09-01"]  # the repeated row once
    assert items[1]["kind"] == "業績修正" and items[0]["kind"] == "その他"
    assert NT.classify("第1四半期決算短信", "") == "決算"
    assert NT.classify("第1四半期決算短信", "売上高 +13.1%。通期予想の修正なし") == "決算"


def test_beta_and_the_market_part_of_the_move():
    moves = [0.01 if i % 3 else -0.012 for i in range(300)]
    dates, rows, index = _series(moves, beta=1.5)
    beta = MV.beta(rows, index)
    assert beta == pytest.approx(1.5, abs=0.05)
    out = MV.evaluate(rows, index, None, [], {"state": "もみ合い（方向感なし）"}, "日経平均", None)
    three = next(r for r in out["returns"] if r["label"] == "3か月")
    split = out["split"]
    assert split["span"] == "3か月"
    assert split["market"] == pytest.approx(beta * three["index"], abs=0.2)
    assert split["own"] == pytest.approx(three["stock"] - split["market"], abs=0.01)


def test_big_days_are_matched_with_disclosures(tmp_path):
    moves = [0.001] * 120
    dates, rows, index = _series(moves, beta=1.0, own={"2026-10-12": -0.08})  # 10-12 is a Monday
    rows = [dict(r, volume=400.0) if r["date"] == "2026-10-12" else r for r in rows]
    (tmp_path / "2026-10-11_press-releases.md").write_text(NEWS, encoding="utf-8")
    out = MV.evaluate(rows, index, None, NT.load(tmp_path), {"state": "下降トレンド"}, "日経平均", None)
    day = out["big_days"][0]
    assert day["date"] == "2026-10-12" and day["change"] < -7
    assert [n["title"] for n in day["news"]] == ["第2四半期決算短信"]  # 10-09 is within two business days
    assert day["volume_ratio"] == pytest.approx(4.0, abs=0.1)


def test_index_ending_earlier_aligns_the_comparison():
    moves = [0.001] * 300
    dates, rows, index = _series(moves, beta=1.0)
    out = MV.evaluate(rows, index[:-8], None, [], {}, "日経平均", None)
    assert out["end"] == index[-9][0]
    assert any("まで" in n for n in out["notes"])


def test_without_index_data():
    dates, rows, _ = _series([0.001] * 30, beta=1.0)
    out = MV.evaluate(rows, [], None, [], {}, "日経平均", None)
    assert out["ok"] and out["beta"] is None and out["split"] is None
    assert all(r["index"] is None for r in out["returns"])
