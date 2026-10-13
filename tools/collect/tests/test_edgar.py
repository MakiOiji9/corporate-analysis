import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from edgar import annual_rows, filing_rows  # noqa: E402
from render_tables import financials_table  # noqa: E402


def _fact(val, end, start=None, form="10-K", filed="2026-02-01", accn="0000000001-26-000001"):
    fact = {"val": val, "end": end, "form": form, "filed": filed, "accn": accn}
    return {**fact, "start": start} if start else fact


FACTS = {"facts": {"us-gaap": {
    "Revenues": {"units": {"USD": [
        _fact(500_000_000, "2025-12-31", "2025-01-01", form="424B4", filed="2026-05-14"),
        _fact(290_000_000, "2024-12-31", "2024-01-01", form="S-1", filed="2024-09-30"),
        _fact(291_000_000, "2024-12-31", "2024-01-01", form="424B4", filed="2026-05-14"),  # later filing wins
        _fact(180_000_000, "2026-06-30", "2026-04-01", form="10-Q", filed="2026-08-12"),   # quarter: ignored
    ]}},
    "NetIncomeLoss": {"units": {"USD": [_fact(-100_000_000, "2025-12-31", "2025-01-01")]}},
    "EarningsPerShareBasic": {"units": {"USD/shares": [_fact(-1.5, "2025-12-31", "2025-01-01")]}},
    "Assets": {"units": {"USD": [_fact(2_000_000_000, "2025-12-31"), _fact(9_000_000_000, "2026-06-30")]}},
    "StockholdersEquity": {"units": {"USD": [_fact(-500_000_000, "2025-12-31")]}},
}}}


def test_annual_rows_keeps_fiscal_years_and_latest_filing():
    rows = {(r["period_end"], r["item"]): r for r in annual_rows(FACTS)}
    assert rows[("2025-12-31", "summary.net_sales")]["value"] == "500"
    assert rows[("2025-12-31", "summary.net_sales")]["unit"] == "百万ドル"
    assert rows[("2024-12-31", "summary.net_sales")]["value"] == "291"
    assert rows[("2025-12-31", "net_sales")]["value"] == "500"  # alias read by ff_metrics / tc_metrics
    assert rows[("2025-12-31", "summary.eps")]["value"] == "-1.5"
    assert rows[("2025-12-31", "summary.eps")]["unit"] == "ドル"
    assert ("2026-06-30", "summary.net_sales") not in rows
    assert ("2026-06-30", "summary.total_assets") not in rows  # not a fiscal year end


def test_equity_ratio_is_computed_from_equity_and_assets():
    rows = {(r["period_end"], r["item"]): r for r in annual_rows(FACTS)}
    ratio = rows[("2025-12-31", "summary.equity_ratio")]
    assert ratio["value"] == "-25.0" and ratio["element"].startswith("computed:")


def test_years_limit_drops_older_fiscal_years():
    ends = {r["period_end"] for r in annual_rows(FACTS, years=1)}
    assert ends == {"2025-12-31"}


def test_render_uses_dollar_unit_for_edgar_rows():
    table = financials_table(annual_rows(FACTS), 10)
    assert "項目（百万ドル）" in table and "EPS（ドル）" in table


def test_filing_rows_filters_forms_and_builds_urls():
    subs = {"cik": "2021728", "filings": {"recent": {
        "form": ["8-K", "4", "10-Q"], "filingDate": ["2026-08-12", "2026-08-10", "2026-08-12"],
        "reportDate": ["2026-08-12", "", "2026-06-30"],
        "accessionNumber": ["0001628280-26-056186", "0001-26-1", "0001628280-26-056357"],
        "primaryDocument": ["cbrs-8k.htm", "x.xml", "cbrs-20260630.htm"]}}}
    rows = filing_rows(subs, {"10-Q", "8-K"}, limit=10)
    assert [r["form"] for r in rows] == ["8-K", "10-Q"]
    assert rows[1]["url"] == ("https://www.sec.gov/Archives/edgar/data/2021728/000162828026056357/"
                              "cbrs-20260630.htm")
