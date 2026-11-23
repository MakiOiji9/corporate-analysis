import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
TOOLS = ANALYSIS.parent
sys.path[:0] = [str(ANALYSIS), str(TOOLS / "report"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import iv_metrics as IV  # noqa: E402


def _row(year: str, **kw) -> dict:
    base = {"year": year, "sales": 1000.0, "capex": 50.0, "depreciation": 40.0, "capex_to_dep": 1.25, "rnd": 30.0,
            "acquisition": 0.0, "capex_share": 5.0, "rnd_share": 3.0, "acquisition_share": 0.0, "impairment": None,
            "goodwill": None, "ppe": None, "cip": None, "net_assets": 2000.0, "cfo": 120.0, "securities": None,
            "mix": {}}
    base.update(kw)
    return base


YEARS = [f"{y}-03" for y in range(2019, 2027)]


def test_change_points_each_kind():
    rows = [_row(y) for y in YEARS]
    rows[4] = _row(YEARS[4], capex_share=8.0, capex=80.0)                      # 1.6x of 5.0
    rows[5] = _row(YEARS[5], capex_share=2.0, capex=20.0, capex_to_dep=0.5)     # 0.4x and 攻め → 守り
    rows[6] = _row(YEARS[6], rnd_share=4.5, acquisition=60.0, acquisition_share=6.0)
    rows[6]["mix"], rows[5]["mix"] = {"A": 70.0, "B": 30.0}, {"A": 50.0, "B": 50.0}
    points = IV.change_points(rows, ma_note_years=["2020-03"])
    kinds = {(p["year"], p["kind"]) for p in points}
    assert ("2023-03", "投資の急増") in kinds and ("2024-03", "投資の急減") in kinds
    assert ("2024-03", "局面の切り替わり") in kinds and ("2025-03", "局面の切り替わり") in kinds  # 守り → 攻め again
    assert ("2025-03", "配分の変化") in kinds and ("2025-03", "M&A") in kinds and ("2020-03", "M&A") in kinds
    assert ("2025-03", "研究開発の変化") in kinds
    assert not any(p["year"] == "2019-03" for p in points)  # nothing to compare with


def test_theme_points_new_theme_after_first_year():
    got = IV.theme_points({"2024-03": ["EV"], "2025-03": ["EV", "AI"], "2026-03": ["AI"]})
    assert got == [{"year": "2025-03", "kind": "新しい投資テーマ", "text": "AI"}]


def test_impairment_and_goodwill():
    rows = [_row(y, goodwill=800.0) for y in YEARS]
    rows[-1] = _row(YEARS[-1], impairment=120.0, goodwill=650.0)  # 6% of equity, covers the fall of 150
    a = IV.impairment(rows)
    assert a["status"] == IV.WATCH and a["share"] == 6.0 and a["goodwill_hits"] == 1
    assert IV.goodwill(rows, impaired=True)["status"] == IV.WATCH  # 32.5% of equity
    rows[-2] = _row(YEARS[-2], impairment=100.0, goodwill=700.0)
    rows[-1] = _row(YEARS[-1], impairment=100.0, goodwill=500.0, net_assets=900.0)
    assert IV.impairment(rows)["status"] == IV.BAD  # 22% of equity
    assert IV.goodwill(rows, impaired=True)["status"] == IV.BAD  # 55.6% with an impairment


def test_small_impairment_with_fx_fall_is_not_goodwill_hit():
    rows = [_row(y, goodwill=7300.0, net_assets=490000.0) for y in YEARS]
    rows[-1] = _row(YEARS[-1], impairment=10.0, goodwill=7144.0, net_assets=490000.0)
    assert IV.impairment(rows)["goodwill_hits"] == 0


def test_turnover_falling():
    rows = [_row(y, ppe=100.0 + 20 * i) for i, y in enumerate(YEARS)]  # falls every year
    growth = [{"year": y, "sales": 1000.0, "operating_income": 100.0 - 5 * i} for i, y in enumerate(YEARS)]
    assert IV.turnover(rows, growth)["status"] == IV.BAD
    flat = [{"year": y, "sales": 1000.0, "operating_income": 100.0} for y in YEARS]
    assert IV.turnover(rows, flat)["status"] == IV.WATCH


def test_construction_run():
    rows = [_row(y, ppe=1000.0, cip=50.0) for y in YEARS]
    for i in (5, 6, 7):
        rows[i] = _row(YEARS[i], ppe=1000.0, cip=50.0 * 2 ** (i - 3))
    assert IV.construction(rows)["status"] == IV.BAD
    rows = [_row(y, ppe=1000.0, cip=50.0) for y in YEARS[:-1]] + [_row(YEARS[-1], ppe=1000.0, cip=150.0)]
    assert IV.construction(rows)["status"] == IV.WATCH


def test_under_investment_and_asset_light():
    rows = [_row(y, capex_to_dep=0.7) for y in YEARS]
    assert IV.under_investment(rows, asset_light=False)["status"] == IV.WATCH
    assert IV.under_investment(rows, asset_light=True)["status"] == IV.OK


def test_funding_gap():
    rows = [_row(y, capex=100.0, acquisition=0.0, cfo=40.0) for y in YEARS]  # 60% not covered
    assert IV.funding(rows, "普通")["status"] == IV.BAD
    assert IV.funding(rows, "良好")["status"] == IV.WATCH


def test_continuity():
    themes = {"2023-03": ["A", "B"], "2024-03": ["C", "D"], "2025-03": ["E"], "2026-03": ["E"]}
    got = IV.continuity(themes)
    assert got["status"] == IV.WATCH and got["low_years"] == ["2024-03", "2025-03"]
    assert IV.continuity(None)["status"] == "不明"


def test_securities_proxy():
    rows = [_row(y, securities=100.0 + 100 * i, net_assets=2000.0) for i, y in enumerate(YEARS)]
    assert IV.securities(rows)["status"] == IV.BAD  # 40% and growing


@pytest.mark.parametrize("mtp,outcomes,want", [
    ("整合", ["予定どおり"], "整合"), ("整合", ["延期"], "一部"), ("乖離", [], "乖離"),
    ("一部", ["延期", "中止・縮小"], "乖離"), ("不明", [], "不明"), ("不明", ["予定どおり"], "一部")])
def test_plan_axis(mtp, outcomes, want):
    assert IV.plan_axis(mtp, outcomes)["rating"] == want


@pytest.mark.parametrize("classes,want", [
    (["合う", "合う", "一部"], "合う"), (["逆行"], "逆行"), (["合う", "逆行"], "一部"), (["不明"], "不明"),
    (["一部", "一部", "合う"], "一部")])
def test_trend_axis(classes, want):
    assert IV.trend_axis(classes)["rating"] == want


def _axes(**kw) -> dict:
    base = {"efficiency": "良好", "plan": "整合", "trend": "合う", "peer": "同等", "failure": IV.OK,
            "discipline": IV.OK}
    base.update(kw)
    return {k: {"rating": v} for k, v in base.items()}


def test_final_rules():
    assert IV.final(_axes())[0] == "良好"
    assert IV.final(_axes(peer="低い"))[0] == "普通"
    assert IV.final(_axes(failure=IV.BAD))[0] == "懸念"
    assert IV.final(_axes(discipline=IV.BAD, efficiency="不明"))[0] == "懸念"
    assert IV.final(_axes(trend="逆行"))[0] == "普通"
    assert IV.final(_axes(efficiency="不明", plan="不明", trend="不明"))[0] == "判定保留"
    assert IV.final(_axes(efficiency="不明", plan="不明"))[0] == "普通"  # one of three unknown


def test_efficiency_axis_downgrades():
    s5 = {"efficiency": {"rating": "良好", "basis": "増分 ROIC", "sentence": "x"}}
    ok = {"status": IV.OK}
    assert IV.efficiency_axis(s5, ok, None)["rating"] == "良好"
    assert IV.efficiency_axis(s5, {"status": IV.BAD}, None)["rating"] == "普通"
    assert IV.efficiency_axis(s5, ok, {"segment": "Robotics", "margin_change": -1.3})["rating"] == "普通"


def test_top_segment():
    seg = {y: {"A": 10.0, "B": 30.0} for y in YEARS}
    rev = {"B": {YEARS[3]: 100.0, YEARS[-1]: 200.0}}
    pro = {"B": {YEARS[3]: 10.0, YEARS[-1]: 30.0}}
    got = IV.top_segment(seg, rev, pro, YEARS)
    assert got["segment"] == "B" and got["share"] == 75.0 and got["margin_change"] == 5.0
    assert got["revenue_cagr"] == pytest.approx(18.9, abs=0.1)  # 2022→2026: 4 years to double


def test_segment_capex_skips_totals():
    invest = {"segments": [
        {"period_end": "2026-02-28", "segment": "Robotics", "metric": "capex", "value": "19799"},
        {"period_end": "2026-02-28", "segment": "ReportableSegments", "metric": "capex", "value": "49200"},
        {"period_end": "2026-02-28", "segment": "Other", "metric": "capex", "value": "2722"},
        {"period_end": "2026-02-28", "segment": "Robotics", "metric": "revenue", "value": "1"}]}
    assert IV.segment_capex(invest) == {"2026-02": {"Robotics": 19799.0, "その他": 2722.0}}


def test_combination_years_skip_empty_notes():
    invest = {"years": [
        {"period_end": "2025-02-28", "texts": {"business_combinations": {
            "element": "x:NotesBusinessCombinationsTextBlock", "text": "記載すべき重要な事項はありません。"}}},
        {"period_end": "2026-02-28", "texts": {"business_combinations": {
            "element": "x:NotesBusinessCombinationsTextBlock", "text": "東京ロボティクスを取得した"}}},
        {"period_end": "2024-03-31", "texts": {"business_combinations": {
            "element": "x:NotesBusinessCombinationsNATextBlock", "text": "該当なし"}}}]}
    assert IV.combination_years(invest) == ["2026-02"]
