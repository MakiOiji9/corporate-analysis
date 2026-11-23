import sys
from pathlib import Path

COLLECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(COLLECT)]

import xbrl_financials as XF  # noqa: E402
import yuho_investments as YI  # noqa: E402

SEG = "jpcrp030000-asr_E01741-000{}ReportableSegmentMember"


def _yuho(fy_end: str, capex_text: str, segs: dict[tuple[str, str], int], extra: list[XF.Row] = ()) -> list[XF.Row]:
    rows = [XF.Row("jpdei_cor:CurrentFiscalYearEndDateDEI", "", "FilingDateInstant", "－", fy_end),
            XF.Row("jpdei_cor:DocumentTypeDEI", "", "FilingDateInstant", "－", "第三号様式"),
            XF.Row("jpcrp_cor:FilingDateCoverPage", "", "FilingDateInstant", "－", fy_end[:4] + "-06-20"),
            XF.Row("jpcrp_cor:OverviewOfCapitalExpendituresEtcTextBlock", "設備投資等の概要 [テキストブロック]",
                   "FilingDateInstant", "－", capex_text),
            XF.Row("jpcrp_cor:ResearchAndDevelopmentActivitiesTextBlock", "研究開発活動 [テキストブロック]",
                   "FilingDateInstant", "－", "<p>ロボットの開発</p>")]
    for (ctx, element), value in segs.items():
        rows.append(XF.Row(element, "", ctx, "JPY", str(value)))
    return rows + list(extra)


def test_plain_text_tables_and_entities():
    raw = "<table><tr><td>MC</td><td>17,573&nbsp;百万円</td></tr><tr><td>ロボット</td><td>19,799</td></tr></table>"
    assert YI.plain_text(raw) == "MC | 17,573 百万円\nロボット | 19,799"


def test_texts_by_label_and_consolidated_first():
    rows = _yuho("2026-02-28", "<p>当期の設備投資は<br/>57,037百万円</p>", {}, [
        XF.Row("jppfs_cor:NotesBusinessCombinationsNonConsolidatedTextBlock", "企業結合等関係（個別） [テキストブロック]",
               "CurrentYearDuration", "－", "個別"),
        XF.Row("jpigp_cor:NotesBusinessCombinationsIFRSTextBlock", "企業結合 [テキストブロック]",
               "CurrentYearDuration", "－", "<p>東京ロボティクスを取得</p>"),
        # a company extension with the standard label is found by the label
        XF.Row("jpcrp030000-asr_E01741-000:PlannedFacilitiesTextBlock", "設備の新設、除却等の計画 [テキストブロック]",
               "FilingDateInstant", "－", "<p>新工場 2027年完成予定</p>")])
    got = YI.texts(rows)
    assert got["capex_overview"]["text"] == "当期の設備投資は\n57,037百万円"
    assert got["business_combinations"]["text"] == "東京ロボティクスを取得"
    assert got["planned_facilities"]["text"] == "新工場 2027年完成予定"
    assert "major_facilities" not in got and "shareholdings" not in got


def test_segments_priority_and_names():
    segs = {(f"CurrentYearDuration_{SEG.format('MotionControl')}",
             "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"): 17_573_000_000,
            (f"CurrentYearDuration_{SEG.format('MotionControl')}", "jpigp_cor:RevenueIFRS"): 300_000_000_000,
            (f"CurrentYearDuration_{SEG.format('MotionControl')}",
             "jpcrp_cor:RevenuesFromExternalCustomers"): 290_000_000_000,
            (f"Prior1YearDuration_{SEG.format('Robotics')}",
             "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"): 15_000_000_000,
            ("CurrentYearDuration_jpcrp030000-asr_E01741-000SystemEngineeringReportableSegmentsMember",
             "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"): 1_241_000_000,
            ("CurrentYearDuration_ReportableSegmentsMember",
             "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"): 49_200_000_000,
            ("CurrentYearDuration_ReconcilingItemsMember",
             "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"): 7_836_000_000,
            # two axes, the parent only, and a non-segment member are skipped
            (f"CurrentYearDuration_{SEG.format('Robotics')}_JapanMember", "jpigp_cor:RevenueIFRS"): 1,
            ("CurrentYearDuration_NonConsolidatedMember", "jppfs_cor:NetSales"): 1}
    got = {(s["period_end"], s["segment"], s["metric"]): s["value"]
           for s in YI.segments(_yuho("2026-02-28", "", segs), "2026-02-28")}
    assert got == {("2026-02-28", "MotionControl", "capex"): "17573",
                   ("2026-02-28", "MotionControl", "revenue"): "290000",  # external customers before the total
                   ("2025-02-28", "Robotics", "capex"): "15000",
                   ("2026-02-28", "SystemEngineering", "capex"): "1241",  # older 'ReportableSegments' member name
                   ("2026-02-28", "ReportableSegments", "capex"): "49200",
                   ("2026-02-28", "ReconcilingItems", "capex"): "7836"}


def test_build_merges_years_and_reports_missing():
    capex = "jpcrp_cor:IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets"
    old = _yuho("2025-02-28", "<p>旧</p>", {(f"CurrentYearDuration_{SEG.format('Robotics')}", capex): 14_000_000_000})
    new = _yuho("2026-02-28", "<p>新</p>", {(f"Prior1YearDuration_{SEG.format('Robotics')}", capex): 15_000_000_000})
    result = YI.build([("S100NEW1", new), ("S100OLD1", old)])
    assert [y["period_end"] for y in result["years"]] == ["2025-02-28", "2026-02-28"]
    assert result["as_of"] == "2026-02-28"
    restated = next(s for s in result["segments"] if s["period_end"] == "2025-02-28")
    assert restated["value"] == "15000" and restated["doc_id"] == "S100NEW1"  # the later report's restatement wins
    assert result["missing"]["major_facilities"] == ["2025-02-28", "2026-02-28"]
    assert result["elements"]["capex_overview"] == ["jpcrp_cor:OverviewOfCapitalExpendituresEtcTextBlock"]


def test_long_text_truncated():
    rows = _yuho("2026-02-28", "<p>" + "あ" * (YI.MAX_TEXT + 10) + "</p>", {})
    block = YI.texts(rows)["capex_overview"]
    assert block["truncated"] and len(block["text"]) == YI.MAX_TEXT


def test_no_annual_report():
    assert YI.build([]) is None
