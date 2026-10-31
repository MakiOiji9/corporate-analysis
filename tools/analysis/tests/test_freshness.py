import json
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import an_common as A  # noqa: E402
import freshness as T  # noqa: E402
import tc_paths as TP  # noqa: E402

HEADER = "doc_id,document,filing_date,fiscal_year_end,context,element,value,unit\n"
FULL_YEAR = "a,決算短信〔日本基準〕（連結）,2026年5月13日,2026-03-31,CurrentYearDuration,NetSales,1,百万円\n"
Q1 = "q1,第１四半期決算短信〔日本基準〕（連結）,2026年８月12日,2027-03-31,CurrentAccumulatedQ1Duration,NetSales,1,百万円\n"
Q2 = "q2,第２四半期（中間期）決算短信〔日本基準〕（連結）,2026年11月10日,2027-03-31,X,NetSales,1,百万円\n"


def _company(tmp_path: Path, tdnet: str = "") -> A.Company:
    path = tmp_path / "companies" / "7203_toyota"
    for sub in ("data", "raw/filings", "raw/market"):
        (path / sub).mkdir(parents=True)
    if tdnet:
        (path / "data" / "tdnet_facts.csv").write_text(HEADER + tdnet, encoding="utf-8")
    return A.Company(tmp_path, path)


def _raw(company: A.Company, sub: str, name: str) -> None:
    (company.path / "raw" / sub / name).write_text("# raw\n", encoding="utf-8")


def test_tdnet_periods_read_quarter_and_filing_date(tmp_path):
    company = _company(tmp_path, FULL_YEAR + Q1 + Q2)
    assert T.tdnet_periods(company.path) == [("2026-03-31", 4, "2026-05-13"), ("2027-03-31", 1, "2026-08-12"),
                                             ("2027-03-31", 2, "2026-11-10")]


@pytest.mark.parametrize("unit, until, expected", [
    ("quarter", "2026-09-01", ("2027-03-31", 1)),
    ("half", "2026-09-01", ("2026-03-31", 4)),       # a first quarter is not a half-year result
    ("half", "2026-11-11", ("2027-03-31", 2)),
    ("annual_results", "2026-11-11", ("2026-03-31", 4)),
    ("quarter", "2026-05-01", None),
])
def test_settled_period_by_unit(tmp_path, unit, until, expected):
    company = _company(tmp_path, FULL_YEAR + Q1 + Q2)
    assert T.settled_period(company.path, unit, until) == expected


def test_quarterly_result_triggers_growth_but_not_profitability(tmp_path):
    company = _company(tmp_path, FULL_YEAR + Q1)
    assert T.material_triggers(company, "2026-06-01", "quarter") == [
        "新しい決算（2027-03 期 第1四半期。分析時は 2026-03 期 通期）が出た"]
    assert T.material_triggers(company, "2026-06-01", "half") == []


def test_filings_are_used_without_tdnet(tmp_path):
    company = _company(tmp_path)
    _raw(company, "filings", "2026-06-20_2026-03_yuho.md")
    assert T.material_triggers(company, "2026-07-01", "half") == []
    _raw(company, "filings", "2027-06-20_2027-03_yuho.md")
    assert T.material_triggers(company, "2026-07-01", "half")


def test_annual_unit_ignores_peers_and_same_period_reports(tmp_path):
    company = _company(tmp_path)
    _raw(company, "filings", "2026-06-20_2026-03_yuho.md")
    _raw(company, "market", "2026-06-20_industry-overview.md")
    _raw(company, "market", "2026-08-01_competitors.md")
    _raw(company, "filings", "2026-08-02_2026-03_yuho.md")  # the same period collected again
    assert T.material_triggers(company, "2026-07-01", "annual") == []
    _raw(company, "market", "2026-08-03_industry-overview.md")
    assert "業界データ" in T.material_triggers(company, "2026-07-01", "annual")[0]
    _raw(company, "filings", "2027-06-20_2027-03_yuho.md")
    assert "新しい期の有報（2027-03 期" in T.material_triggers(company, "2026-07-01", "annual")[0]


def _three_c(company: A.Company, date: str, verdict: str) -> None:
    directory = company.path / "analysis" / "three-c"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_three-c.md").write_text("# 3C\n", encoding="utf-8")
    (directory / f"{date}_three-c.json").write_text(json.dumps({"verdict": verdict}, ensure_ascii=False),
                                                    encoding="utf-8")


def test_upstream_triggers_only_on_a_changed_conclusion(tmp_path):
    company = _company(tmp_path)
    upstream = [("3C", TP)]
    _three_c(company, "2026-07-01", "判定保留")
    assert T.upstream_triggers(company, "2026-07-02", upstream) == []
    _three_c(company, "2026-07-10", "判定保留")  # redone with the same conclusion
    assert T.upstream_triggers(company, "2026-07-02", upstream) == []
    _three_c(company, "2026-07-11", "あいまい")
    assert T.upstream_triggers(company, "2026-07-02", upstream) == [
        "3Cの結論が 判定保留 → あいまい に変わった（2026-07-11）"]


def test_upstream_created_after_the_analysis_triggers(tmp_path):
    company = _company(tmp_path)
    _three_c(company, "2026-07-10", "明確")
    assert T.upstream_triggers(company, "2026-07-02", [("3C", TP)]) == [
        "3Cの結論が 未実施 → 明確 に変わった（2026-07-10）"]


def test_unknown_unit_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        T.triggers(_company(tmp_path), "2026-07-01", "monthly")
