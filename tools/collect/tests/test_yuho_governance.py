import sys
from pathlib import Path

import pytest

COLLECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(COLLECT)]

import xbrl_financials as XF  # noqa: E402
import yuho_governance as YG  # noqa: E402

OFFICER = "FilingDateInstant_jpcrp030000-asr_E00001-000{}Member"


def _yuho(fy_end: str, filed: str, issued: dict[int, int], shareholders: list[tuple[str, float]],
          officers: list[tuple[str, str, str, int]], history: str = "") -> list[XF.Row]:
    rows = [XF.Row("jpdei_cor:CurrentFiscalYearEndDateDEI", "", "FilingDateInstant", "－", fy_end),
            XF.Row("jpdei_cor:DocumentTypeDEI", "", "FilingDateInstant", "－", "第三号様式"),
            XF.Row("jpcrp_cor:FilingDateCoverPage", "", "FilingDateInstant", "－", filed),
            XF.Row("jpcrp_cor:ChangesInNumberOfIssuedSharesStatedCapitalEtcTextBlock", "", "FilingDateInstant", "－",
                   history)]
    rel = {0: "CurrentYear", 1: "Prior1Year", 2: "Prior2Year", 3: "Prior3Year", 4: "Prior4Year"}
    rows += [XF.Row("jpcrp_cor:TotalNumberOfIssuedSharesSummaryOfBusinessResults", "",
                    f"{rel[back]}Instant_NonConsolidatedMember", "shares", str(n)) for back, n in issued.items()]
    for i, (name, ratio) in enumerate(shareholders, start=1):
        ctx = f"CurrentYearInstant_No{i}MajorShareholdersMember"
        rows += [XF.Row("jpcrp_cor:NameMajorShareholders", "", ctx, "－", name),
                 XF.Row("jpcrp_cor:ShareholdingRatio", "", ctx, "pure", str(ratio))]
    for key, (name, title, birth, shares) in enumerate(officers):
        ctx = OFFICER.format(f"P{key}")
        rows += [XF.Row("jpcrp_cor:NameInformationAboutDirectorsAndCorporateAuditors", "", ctx, "－", name),
                 XF.Row("jpcrp_cor:OfficialTitleOrPositionInformationAboutDirectorsAndCorporateAuditors", "", ctx, "－",
                        title),
                 XF.Row("jpcrp_cor:DateOfBirthInformationAboutDirectorsAndCorporateAuditors", "", ctx, "－", birth),
                 XF.Row("jpcrp_cor:CareerSummaryInformationAboutDirectorsAndCorporateAuditorsTextBlock", "", ctx, "－",
                        "1990年4月当社設立 代表取締役社長"),
                 XF.Row("jpcrp_cor:NumberOfSharesHeldOrdinarySharesInformationAboutDirectorsAndCorporateAuditors", "",
                        ctx, "shares", str(shares))]
    return rows


SHAREHOLDERS = [("漆原　茂", 0.4540), ("株式会社漆原興産", 0.05), ("ULSグループ従業員持株会", 0.0424),
                ("株式会社日本カストディ銀行（信託口）", 0.0213), ("漆原　花子", 0.01)]
OFFICERS = [("漆原　茂", "代表取締役会長", "1965-04-01", 5000000), ("高橋　敬一", "代表取締役社長", "1970-10-15", 100)]


def test_owner_family_and_asset_company_count():
    g = YG.build([("S100AAAA", _yuho("2026-03-31", "2026-06-20", {0: 100}, SHAREHOLDERS, OFFICERS))])
    owner = g["owner"]
    assert owner["is_owner"] and owner["ratio"] == pytest.approx(51.4)
    assert [m["name"] for m in owner["members"]] == ["漆原　茂", "株式会社漆原興産", "漆原　花子"]
    assert g["shareholders"][0] == {"rank": 1, "name": "漆原　茂", "ratio": 45.4}


def test_president_and_age():
    g = YG.build([("S100AAAA", _yuho("2026-03-31", "2026-06-20", {0: 100}, SHAREHOLDERS, OFFICERS))])
    assert g["president"]["name"] == "高橋　敬一" and g["president"]["age"] == 55
    assert g["officers"][0]["career"].startswith("1990年4月")
    assert (g["as_of"], g["filed"], g["doc_id"]) == ("2026-03-31", "2026-06-20", "S100AAAA")


def test_issuances_split_offering_and_options():
    old = _yuho("2021-03-31", "2021-06-20", {4: 1000, 3: 1000, 2: 1000, 1: 2000, 0: 2000}, [], [], "株式分割（1:2）")
    new = _yuho("2025-03-31", "2025-06-20", {4: 2000, 3: 2000, 2: 2300, 1: 2302, 0: 2302}, [], [],
                "有償一般募集 発行価格 1,000円 新株予約権の行使")
    g = YG.build([("S100OLD1", old), ("S100NEW1", new)])
    kinds = {i["period_end"]: i["kind"] for i in g["issuances"]}
    assert kinds["2020-03-31"] == "株式分割"
    assert kinds["2023-03-31"] == "公募増資"
    assert "2024-03-31" not in kinds  # +0.1% is below the threshold
    assert g["offering_within_5y"] is True and g["offering_last"] == "2023-03-31"


def test_no_annual_report():
    assert YG.build([]) is None
