import datetime as dt
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_tech_cache as C  # noqa: E402


def _rows(n: int, start: dt.date = dt.date(2023, 1, 2)) -> list[dict]:
    return [{"date": (start + dt.timedelta(days=i)).isoformat(), "close": 100 + i * 0.5, "high": 101 + i * 0.5,
             "low": 99 + i * 0.5, "volume": 100.0} for i in range(n)]


def test_needs_refresh_by_close_date_and_version():
    saved = {"version": C.VERSION, "price_asof": "2024-01-05"}
    assert not C.needs_refresh(saved, "2024-01-05")
    assert C.needs_refresh(saved, "2024-01-06") and C.needs_refresh({**saved, "version": "0"}, "2024-01-05")
    assert C.needs_refresh(None, "2024-01-05")


def test_ensure_saves_then_reuses_until_the_close_moves(tmp_path):
    rows = _rows(400)
    a = C.ensure(tmp_path, rows)
    assert not a["reused"] and a["price_asof"] == rows[-1]["date"] and a["generated_at"].endswith("+09:00")
    assert (tmp_path / "analysis/technical/technical.json").exists() and (tmp_path / "analysis/technical/technical.md").exists()
    b = C.ensure(tmp_path, rows)
    assert b["reused"] and b["generated_at"] == a["generated_at"]
    assert not C.ensure(tmp_path, _rows(401))["reused"]


def test_ensure_without_rows_and_broken_file(tmp_path):
    assert not C.ensure(tmp_path, [])["ok"]
    (tmp_path / "analysis/technical").mkdir(parents=True)
    (tmp_path / "analysis/technical/technical.json").write_text("{", encoding="utf-8")
    assert C.ensure(tmp_path, _rows(400))["ok"]
