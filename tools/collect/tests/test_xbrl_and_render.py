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
