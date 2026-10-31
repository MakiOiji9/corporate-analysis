import datetime as dt
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT)]

import cr_prices as CP  # noqa: E402

HEADER = "date,open,high,low,close,adj_close,volume,retrieved\n"


def _write(company: Path, closes: list[float], start: str = "2016-01-04", step_days: int = 1) -> None:
    (company / "data").mkdir(parents=True, exist_ok=True)
    day = dt.date.fromisoformat(start)
    lines = []
    for c in closes:
        lines.append(f"{day.isoformat()},{c},{c + 1},{c - 1},{c},{c},100,2026-10-31")
        day += dt.timedelta(days=step_days)
    (company / "data" / "prices.csv").write_text(HEADER + "\n".join(lines) + "\n", encoding="utf-8")


def test_position_bounds():
    assert CP.position(5, 0, 10) == 50
    assert CP.position(10, 0, 10) == 100
    assert CP.position(-1, 0, 10) == 0
    assert CP.position(3, 3, 3) == 50


def test_summarize_ranges_and_averages(tmp_path):
    company = tmp_path / "c"
    _write(company, [100.0] * 301 + [150.0] * 65)  # 366 rows = a full 365-day window
    s = CP.summarize(company)
    assert s["source"] == "prices" and s["current"] == 150.0 and s["days"] == 366
    w52 = s["ranges"][0]
    assert w52["label"] == "52週" and w52["high"] == 151.0 and w52["low"] == 99.0
    assert w52["position"] == pytest.approx((150 - 99) / (151 - 99) * 100, abs=0.1)
    assert w52["partial"] is False
    assert s["ranges"][1]["partial"] is True   # 3年 > stored history
    ma13 = s["averages"][0]
    assert ma13["value"] == 150.0 and ma13["gap"] == 0.0
    ma26 = s["averages"][1]
    assert ma26["value"] == pytest.approx((100 * 65 + 150 * 65) / 130)
    assert s["averages"][2]["value"] == pytest.approx((100 * 195 + 150 * 65) / 260)


def test_short_inputs(tmp_path):
    company = tmp_path / "c"
    _write(company, [100.0] * 200)
    pos, gap = CP.short_inputs(CP.summarize(company))
    assert pos == 50.0 and gap == 0.0
    assert CP.short_inputs({"source": "none"}) == (None, None)


def test_short_history_has_no_long_averages(tmp_path):
    company = tmp_path / "c"
    _write(company, [10.0, 12.0, 11.0])  # e.g. a fresh IPO
    s = CP.summarize(company)
    assert all(a["value"] is None for a in s["averages"])
    assert all(w["partial"] for w in s["ranges"])


def test_monthly_and_yearly(tmp_path):
    company = tmp_path / "c"
    _write(company, [float(i) for i in range(1, 801)], start="2024-01-01")
    s = CP.summarize(company)
    closes = s["monthly"]["close"]
    assert closes[0][0] == "2024-01-31" and closes[0][1] == 31.0
    assert s["monthly"]["ma"][0][0] >= "2024-05-01"  # the 26-week average needs 130 days
    years = s["yearly"]
    assert [y["year"] for y in years] == ["2026", "2025", "2024"]
    assert years[0]["partial"] and not years[1]["partial"] and not years[2]["partial"]
    assert years[1]["change"] == pytest.approx((731 / 366 - 1) * 100, abs=0.1)
    assert years[2]["change"] is None


def test_fallback_reads_the_raw_range_table(tmp_path):
    company = tmp_path / "c"
    (company / "raw" / "ir").mkdir(parents=True)
    (company / "raw" / "ir" / "2026-10-11_valuation-data.md").write_text(
        "# x\n\n## 4. PER\n\n### 株価レンジ（有報）\n\n| 年度 | 最高株価 | 最低株価 |\n|---|---|---|\n"
        "| 2026年3月期 | 854円 | 472円 |\n", encoding="utf-8")
    s = CP.summarize(company)
    assert s["source"] == "fallback"
    assert s["fallback"]["rows"] == [{"年度": "2026年3月期", "最高株価": "854円", "最低株価": "472円"}]


def test_no_prices_at_all(tmp_path):
    assert CP.summarize(tmp_path / "none") == {"source": "none", "fallback": None}
