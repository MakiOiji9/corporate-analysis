import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from render_tables import financials_table, forecast_records  # noqa: E402
from xbrl_financials import extract, load_rows, upsert  # noqa: E402

HEADER = "要素ID\t項目名\tコンテキストID\t相対年度\t連結・個別\t期間・時点\tユニットID\t単位\t値"
LINES = [
    "jpdei_cor:CurrentFiscalYearEndDateDEI\t期末日\tFilingDateInstant\t提出日時点\tその他\t時点\t\t\t2026-03-31",
    "jpcrp_cor:NetSalesSummaryOfBusinessResults\t売上高\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t16600000000",
    "jpcrp_cor:NetSalesSummaryOfBusinessResults\t売上高\tPrior4YearDuration\t4期前\t連結\t期間\tJPY\t円\t7367000000",
    "jpcrp_cor:EquityToAssetRatioSummaryOfBusinessResults\t自己資本比率\tCurrentYearInstant\t当期末\t連結\t時点\tpure\t\t0.747",
    "jpcrp_cor:DividendPaidPerShareSummaryOfBusinessResults\t配当\tCurrentYearDuration_NonConsolidatedMember\t当期\t個別\t期間\tJPYPerShares\t円\t7.30",
    "jppfs_cor:CostOfSales\t売上原価\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t9990000000",
    "jppfs_cor:CostOfSales\t売上原価\tPrior1YearDuration\t前期\t連結\t期間\tJPY\t円\t7885000000",
    "jppfs_cor:CostOfSales\t売上原価\tCurrentYearDuration_NonConsolidatedMember\t当期\t個別\t期間\tJPY\t円\t1",
]


def _write_csv(dir_: Path) -> Path:
    target = dir_ / "XBRL_TO_CSV" / "jpcrp030000-asr-001_E00000-000_2026-03-31_01_2026-06-17.csv"
    target.parent.mkdir(parents=True)
    target.write_text("\n".join([HEADER, *LINES]) + "\n", encoding="utf-16")
    return dir_


def test_extract_summary_and_statements(tmp_path):
    rows = extract(load_rows(_write_csv(tmp_path)), "S100TEST")
    got = {(r["period_end"], r["item"]): (r["value"], r["unit"]) for r in rows}
    assert got[("2026-03-31", "summary.net_sales")] == ("16600", "百万円")
    assert got[("2022-03-31", "summary.net_sales")] == ("7367", "百万円")
    assert got[("2026-03-31", "summary.equity_ratio")] == ("74.7", "%")
    assert got[("2026-03-31", "summary.dps")] == ("7.30", "円")
    assert got[("2026-03-31", "cost_of_sales")] == ("9990", "百万円")  # consolidated, not 個別
    assert got[("2025-03-31", "cost_of_sales")] == ("7885", "百万円")


IFRS_LINES = [
    "jpdei_cor:CurrentFiscalYearEndDateDEI\t期末日\tFilingDateInstant\t提出日時点\tその他\t時点\t\t\t2026-02-28",
    "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults\t売上収益\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t542122000000",
    "jpcrp030000-asr_E01741-000:OperatingProfitLossIFRSSummaryOfBusinessResults\t営業利益\tPrior1YearDuration\t前期\t連結\t期間\tJPY\t円\t50160000000",
    "jpcrp_cor:EquityToAssetRatioIFRSSummaryOfBusinessResults\t1株当たり親会社所有者帰属持分\tCurrentYearInstant\t当期末\t連結\t時点\tJPYPerShares\t円\t1864.31",
    "jpcrp_cor:RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults\t親会社所有者帰属持分比率\tCurrentYearInstant\t当期末\t連結\t時点\tpure\t\t0.595",
    "jpcrp_cor:NetSalesSummaryOfBusinessResults\t売上高\tCurrentYearDuration_NonConsolidatedMember\t当期\t個別\t期間\tJPY\t円\t181072000000",
    "jpigp_cor:RevenueIFRS\t売上収益\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t542122000000",
    "jpigp_cor:OperatingProfitLossIFRS\t営業利益\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t47307000000",
    "jpigp_cor:TradeReceivablesCAIFRS\t営業債権\tCurrentYearInstant\t当期末\t連結\t時点\tJPY\t円\t163942000000",
    "jpigp_cor:EquityIFRS\t資本\tCurrentYearInstant\t当期末\t連結\t時点\tJPY\t円\t493615000000",
    "jpigp_cor:BondsAndBorrowingsNCLIFRS\t社債及び借入金\tCurrentYearInstant\t当期末\t連結\t時点\tJPY\t円\t64457000000",
    "jpigp_cor:NetCashProvidedByUsedInOperatingActivitiesIFRS\t営業CF\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t52170000000",
    "jpigp_cor:DividendsPaidFinCFIFRS\t配当金の支払額\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t-17670000000",
]


def test_extract_ifrs_summary_and_statements(tmp_path):
    target = tmp_path / "XBRL_TO_CSV" / "jpcrp030000-asr-001_E01741-000_2026-02-28_01_2026-05-25.csv"
    target.parent.mkdir(parents=True)
    target.write_text("\n".join([HEADER, *IFRS_LINES]) + "\n", encoding="utf-16")
    rows = extract(load_rows(tmp_path), "S100IFRS")
    got = {(r["period_end"], r["item"]): (r["value"], r["unit"]) for r in rows}
    assert got[("2026-02-28", "summary.net_sales")] == ("542122", "百万円")  # consolidated IFRS, not 個別
    assert got[("2025-02-28", "summary.operating_income")] == ("50160", "百万円")  # company extension element
    assert got[("2026-02-28", "summary.bps")] == ("1864.31", "円")  # the taxonomy's misnamed BPS element
    assert got[("2026-02-28", "summary.equity_ratio")] == ("59.5", "%")
    assert got[("2026-02-28", "net_sales")] == ("542122", "百万円")
    assert got[("2026-02-28", "operating_income")] == ("47307", "百万円")
    assert got[("2026-02-28", "receivables")] == ("163942", "百万円")
    assert got[("2026-02-28", "net_assets")] == ("493615", "百万円")
    assert got[("2026-02-28", "long_term_loans")] == ("64457", "百万円")
    assert got[("2026-02-28", "cfo")] == ("52170", "百万円")
    assert got[("2026-02-28", "dividends_paid")] == ("-17670", "百万円")


def test_february_year_ends_keep_the_last_day_of_february(tmp_path):
    lines = [
        "jpdei_cor:CurrentFiscalYearEndDateDEI\t期末日\tFilingDateInstant\t提出日時点\tその他\t時点\t\t\t2024-02-29",
        "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults\t売上収益\tPrior1YearDuration\t前期\t連結\t期間\tJPY\t円\t1000000",
        "jpcrp_cor:RevenueIFRSSummaryOfBusinessResults\t売上収益\tPrior4YearDuration\t4期前\t連結\t期間\tJPY\t円\t1000000",
    ]
    target = tmp_path / "XBRL_TO_CSV" / "jpcrp030000-asr-001_E01741-000_2024-02-29_01_2024-05-27.csv"
    target.parent.mkdir(parents=True)
    target.write_text("\n".join([HEADER, *lines]) + "\n", encoding="utf-16")
    ends = {r["period_end"] for r in extract(load_rows(tmp_path), "S100FEB")}
    assert ends == {"2023-02-28", "2020-02-29"}


def test_per_and_employees_are_not_percentages(tmp_path):
    lines = [
        "jpdei_cor:CurrentFiscalYearEndDateDEI\t期末日\tFilingDateInstant\t提出日時点\tその他\t時点\t\t\t2026-02-28",
        "jpcrp_cor:PriceEarningsRatioIFRSSummaryOfBusinessResults\tPER\tCurrentYearDuration\t当期\t連結\t期間\tpure\t\t40.59",
        "jpcrp_cor:NumberOfEmployees\t従業員数\tCurrentYearInstant\t当期末\t連結\t時点\tpure\t\t12483",
    ]
    target = tmp_path / "XBRL_TO_CSV" / "jpcrp030000-asr-001_E01741-000_2026-02-28_01_2026-05-25.csv"
    target.parent.mkdir(parents=True)
    target.write_text("\n".join([HEADER, *lines]) + "\n", encoding="utf-16")
    got = {r["item"]: (r["value"], r["unit"]) for r in extract(load_rows(tmp_path), "S100PURE")}
    assert got["summary.per"] == ("40.59", "倍")
    assert got["summary.employees"] == ("12483", "人")


def test_upsert_is_idempotent_and_renders(tmp_path):
    rows = extract(load_rows(_write_csv(tmp_path)), "S100TEST")
    out = tmp_path / "financials.csv"
    upsert(out, rows)
    upsert(out, rows)
    with out.open(encoding="utf-8") as f:
        stored = list(csv.DictReader(f))
    assert len(stored) == len(rows)
    table = financials_table(stored, 10)
    assert "| 売上高 | 7,367 | — | 16,600 |" in table


def test_forecast_records_classifies_initial_and_actual():
    def fact(doc, fy, ctx, el, val):
        return {"doc_id": doc, "document": "", "filing_date": f"{doc}-date", "fiscal_year_end": fy,
                "context": ctx, "element": el, "value": val, "unit": "百万円"}
    rows = [
        fact("FY25", "2025-03-31", "NextYearDuration_ConsolidatedMember_ForecastMember", "NetSales", "15900"),
        fact("FY26", "2026-03-31", "CurrentYearDuration_ConsolidatedMember_ResultMember", "NetSales", "16600"),
        fact("Q1", "2027-03-31", "CurrentAccumulatedQ1Duration_ConsolidatedMember_ResultMember", "NetSales", "4304"),
        fact("Q1", "2027-03-31", "CurrentYearDuration_ConsolidatedMember_ForecastMember", "NetSales", "20200"),
    ]
    recs = {(r["target"], r["kind"]): r for r in forecast_records(rows)}
    assert recs[("2026-03-31", "期初予想")]["NetSales"] == "15900"
    assert recs[("2026-03-31", "実績")]["NetSales"] == "16600"
    assert recs[("2027-03-31", "期中予想")]["NetSales"] == "20200"
