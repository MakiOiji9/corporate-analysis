import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import facts as F  # noqa: E402
import sanity  # noqa: E402

WEEK = "2026-10-26"


def _extra(indicator: str, value: str, date: str, note: str = "") -> dict:
    return {"market": "us", "indicator": indicator, "value": value, "note": note, "date": date}


def _ind(sid: str, value: float) -> dict:
    return {"id": sid, "value": value, "date": "2026-09-01"}


def test_core_pce_above_core_cpi_is_flagged():
    rows = {"us": [_ind("US_CORE_PCE_YOY", 3.0), _ind("US_CORE_CPI_YOY", 2.6)]}
    assert len(sanity.pce_vs_cpi(rows)) == 1
    rows = {"us": [_ind("US_CORE_PCE_YOY", 2.7), _ind("US_CORE_CPI_YOY", 2.6)]}
    assert sanity.pce_vs_cpi(rows) == []


def test_extreme_searched_values_and_old_dates():
    extras = [_extra("S&P500 予想PER", "45.0倍", "2026-10-16"),
              _extra("S&P500 予想EPS（今期）", "—", "2026-10-16", "CY2026 の EPS 成長率予想は前年比 +32.8%"),
              _extra("日経平均 予想PER", "17.32倍", "2026-08-07"),
              _extra("AAII センチメント調査", "Bullish 36.9%", "2026-10-21 週")]
    items = [c["item"] for c in sanity.extra_checks(extras, WEEK)]
    assert any("範囲外" in i for i in items)
    assert any("成長率が極端" in i for i in items)
    assert any("日経平均 予想PER の時点が古い" in i for i in items)
    assert not any("AAII" in i for i in items)


def test_split_note_keeps_values_with_inner_parentheses_whole():
    aaii = "Bullish 36.9%（平均 37.5%）/ Neutral 17.3% / Bearish 45.8%（平均 31.5%）"
    assert F.split_note(aaii) == (aaii, "")
    assert F.split_note("19.1倍（前週 19.0倍）") == ("19.1倍", "前週 19.0倍")
    assert F.split_note("—（PDF が読めず）") == ("—", "PDF が読めず")


def test_period_label_reads_quarters_and_months():
    assert F.period_label("2026-07-01", "quarterly") == "2026Q3"
    assert F.period_label("2026-10-01", "quarterly") == "2026Q4"
    assert F.period_label("2026-09-01", "monthly") == "2026-09"
    assert F.period_label("2026-10-23", "daily") == "2026-10-23"
    assert F.period_label(None, "monthly") is None and F.period_label("—", "monthly") == "—"
