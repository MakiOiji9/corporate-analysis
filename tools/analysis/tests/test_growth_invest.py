"""成長性 手順5（成長投資）: the ratio, the efficiency and the verdict of gr_invest."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "collect"))

import gr_invest as V  # noqa: E402


def _values(**items) -> dict:
    base = {item: {} for item in V.CSV_ITEMS}
    base.update(items)
    return base


def _row(year: str, sales: float, growth: float, capex: float = 100.0, dep: float = 80.0) -> dict:
    # growth = net_capex + rnd (10) + working_capital (5) + acquisition (0)
    return {"year": year, "sales": sales, "growth": growth, "capex": capex, "depreciation": dep,
            "net_capex": growth - 15.0, "rnd": 10.0, "working_capital": 5.0, "acquisition": 0.0,
            "capex_to_dep": round(capex / dep, 2)}


def _years(n: int, start: int = 2017) -> list[str]:
    return [f"{start + i}-03" for i in range(n)]


# ---------- the yearly amounts ----------

def test_yearly_adds_net_capex_rnd_working_capital_and_acquisitions():
    years = ["2025-03", "2026-03"]
    values = _values(capex_tangible={"2025-03": -90.0, "2026-03": -120.0}, depreciation={"2025-03": 80.0, "2026-03": 90.0},
                     capex_intangible={"2026-03": -10.0}, research_and_development={"2026-03": 25.0},
                     receivables={"2025-03": 200.0, "2026-03": 230.0}, inventories={"2025-03": 50.0, "2026-03": 60.0},
                     trade_payables={"2025-03": 70.0, "2026-03": 75.0}, acquisition_of_subsidiaries={"2026-03": -40.0})
    rows = V.yearly(values, {"2025-03": 1000.0, "2026-03": 1100.0}, years)
    last = rows[-1]
    assert last["capex"] == 130.0 and last["net_capex"] == 40.0  # intangible added, depreciation taken off
    assert last["working_capital"] == 35.0  # (230 + 60 − 75) − (200 + 50 − 70)
    assert last["acquisition"] == 40.0 and last["growth"] == 40.0 + 25.0 + 35.0 + 40.0
    assert rows[0]["working_capital"] is None  # no year before within the window


def test_yearly_reads_us_payments_by_their_size():
    values = _values(capex_tangible={"2025-12": 90.0}, depreciation={"2025-12": 60.0})
    assert V.yearly(values, {"2025-12": 500.0}, ["2025-12"])[0]["net_capex"] == 30.0


def test_a_year_missing_a_working_capital_item_is_not_counted():
    years = ["2024-03", "2025-03", "2026-03"]
    values = _values(capex_tangible=dict.fromkeys(years, -10.0), depreciation=dict.fromkeys(years, 10.0),
                     receivables=dict.fromkeys(years, 100.0),
                     trade_payables={"2025-03": 60.0, "2026-03": 60.0})  # the 2024 payables tag is missing
    rows = V.yearly(values, dict.fromkeys(years, 1000.0), years)
    assert rows[1]["working_capital"] is None  # not a fake fall of 60
    assert rows[2]["working_capital"] == 0.0


def test_the_ratio_compares_only_parts_both_windows_have():
    old = [dict(_row(y, 1000.0, 30.0), rnd=None, net_capex=30.0, acquisition=0.0, working_capital=0.0)
           for y in _years(5)]
    new = [dict(_row(y, 1000.0, 80.0), rnd=50.0, net_capex=30.0, acquisition=0.0, working_capital=0.0)
           for y in _years(5, 2022)]
    r = V.ratio(old + new)
    assert r["recent"] == 8.0 and r["level"] == "標準"  # R&D only in the newer years is not a rise


def test_working_capital_is_not_compared_across_the_window():
    values = _values(capex_tangible={"2019-02": -10.0}, depreciation={"2019-02": 10.0},
                     receivables={"2018-02": 10.0, "2019-02": 500.0})
    row = V.yearly(values, {"2019-02": 1000.0}, ["2019-02"])[0]
    assert row["working_capital"] is None  # 2018-02 is outside the accounting-consistent years


# ---------- 投資比率 ----------

def test_ratio_is_high_when_the_recent_share_is_well_above_the_earlier_one():
    rows = [_row(y, 1000.0, 30.0) for y in _years(5)] + [_row(y, 1000.0, 80.0) for y in _years(5, 2022)]
    r = V.ratio(rows)
    assert (r["earlier"], r["recent"], r["level"]) == (3.0, 8.0, "高い")


def test_ratio_is_unknown_without_earlier_years():
    assert V.ratio([_row(y, 1000.0, 30.0) for y in _years(5)])["level"] == "不明"


def test_underinvestment_needs_three_years_below_depreciation():
    rows = [_row(y, 1000.0, 30.0, capex=70.0, dep=80.0) for y in _years(3)]
    assert V.ratio(rows)["underinvest"] is True
    rows[-1] = _row("2019-03", 1000.0, 30.0, capex=90.0, dep=80.0)
    assert V.ratio(rows)["underinvest"] is False


def test_asset_light_companies_skip_the_underinvestment_rule():
    rows = [_row(y, 10000.0, 30.0, capex=70.0, dep=80.0) for y in _years(3)]  # capex 0.7% of sales
    r = V.ratio(rows)
    assert r["asset_light"] is True and r["underinvest"] is False


def test_surge_compares_the_last_two_years_with_the_three_before():
    rows = [_row(y, 1000.0, 20.0) for y in _years(3)] + [_row(y, 1000.0, 40.0) for y in _years(2, 2020)]
    assert V.surge(rows) is True
    assert V.surge(rows[:-1]) is False


# ---------- 同業との比較 ----------

PEER_TABLE = """## 14. 成長投資の材料

| 会社 | 年度 | 売上高 | 設備投資 | 減価償却費 | 研究開発費 | 出典・確度 |
|---|---|---|---|---|---|---|
| 自社（6506） | 2026-02 | 1,000 | 90 | 50 | 40 | 有報 |
| アルファ | 2026-03 | 2,000 | 160 | 100 | 60 | 有報 |
| アルファ | 2025-03 | 2,000 | 140 | 100 | 60 | 有報 |
| ベータ | 2025-12 | 500 | 30 | 25 | — | 10-K（百万ドル） |
| ガンマ | 2026-03 | 800 | — | 40 | 20 | 有報 |
"""


def _found(body: str):
    from types import SimpleNamespace
    return SimpleNamespace(status="ok", body=body)


def test_peer_shares_read_capex_depreciation_and_rnd_per_peer():
    from types import SimpleNamespace
    company = SimpleNamespace(ticker="6506", name="自社", dirname="6506_self", display_name=lambda: "自社（6506）")
    peers = V.peer_shares(_found(PEER_TABLE), company)
    by_name = {p["name"]: p for p in peers}
    assert set(by_name) == {"アルファ", "ベータ"}  # the target's own row and a peer without capex are left out
    assert by_name["アルファ"]["share"] == 5.5  # (160 + 140 − 200 + 120) ÷ 4,000
    assert by_name["アルファ"]["share_capex"] == 2.5  # (160 + 140 − 200) ÷ 4,000
    assert by_name["アルファ"]["years"] == 2 and by_name["アルファ"]["has_rnd"] is True
    assert by_name["ベータ"]["share"] == 1.0 and by_name["ベータ"]["has_rnd"] is False


def test_peer_median_uses_rnd_only_when_every_peer_has_it():
    peers = [{"name": "a", "share": 4.0, "share_capex": 3.0, "has_rnd": True, "years": 2},
             {"name": "b", "share": 1.0, "share_capex": 1.0, "has_rnd": False, "years": 1}]
    assert V.peer_median(peers) == (2.0, False)  # the capex-only shares 3.0 and 1.0
    assert V.peer_median(peers[:1]) == (4.0, True)
    assert V.peer_median([]) == (None, False)


@pytest.mark.parametrize("past, peer, level", [
    ("高い", "高い", "高い"), ("低い", "低い", "低い"), ("高い", "標準", "標準"), ("高い", "低い", "標準"),
    ("不明", "高い", "高い"), ("低い", "不明", "低い"), ("不明", "不明", "不明"),
])
def test_level_is_high_or_low_only_when_both_comparisons_agree(past, peer, level):
    assert V.combined_level(past, peer) == level


def test_ratio_compares_with_the_peer_median():
    rows = [dict(_row(y, 1000.0, 80.0), net_capex=50.0, rnd=20.0) for y in _years(5, 2022)]
    peers = [{"name": "a", "share": 2.0, "share_capex": 1.0, "has_rnd": True, "years": 5},
             {"name": "b", "share": 3.0, "share_capex": 2.0, "has_rnd": True, "years": 5}]
    r = V.ratio(rows, peers)
    # own (net capex + R&D) ÷ sales = 7.0% vs the peers' median 2.5%; no earlier years: the peers decide
    assert (r["peer_own"], r["peer_median"], r["peer_level"], r["level"]) == (7.0, 2.5, "高い", "高い")
    assert r["peer_count"] == 2


def test_the_md_row_shows_the_peer_comparison():
    import gr_doc as D
    r = {"peer_median": 2.5, "peer_own": 7.0, "peer_level": "高い", "peer_count": 2, "peer_with_rnd": True,
         "past_level": "不明", "peers": [{"name": "a", "share": 2.0, "share_capex": 1.0, "years": 5}]}
    text = D._peer_text(r)
    assert "自社 7.0%" in text and "中央値 2.5%" in text and "a 2.0%" in text
    assert "同業の材料なし" in D._peer_text({"peer_median": None, "past_level": "標準"})


# ---------- 投資効率 ----------

def _roic_rows(operating: list[float], invested: list[float]) -> list[dict]:
    return [{"year": y, "operating": o, "invested": c} for y, o, c in zip(_years(len(operating)), operating, invested)]


def test_incremental_roic_with_the_two_year_lag():
    # NOPAT at a 0% tax: start mean 100, end mean 160 (+60); capital: start mean 1000, end (2 years earlier) 1500
    rows = _roic_rows([100, 100, 100, 130, 150, 160, 160, 160], [1000, 1000, 1000, 1500, 1500, 1500, 2000, 2000])
    r = V.incremental_roic(rows, 0.0, 7.0, "2017-03", "2024-03")
    assert r["lag"] == 2 and r["value"] == 12.0 and r["rating"] == "良好"


def test_incremental_roic_without_the_lag_when_the_window_is_short():
    rows = _roic_rows([100, 100, 100, 101, 102, 103], [1000, 1000, 1000, 1400, 1400, 1400])
    r = V.incremental_roic(rows, 0.0, 7.0, "2017-03", "2022-03")
    assert r["lag"] == 0 and r["value"] == 0.5 and r["rating"] == "問題あり"


def test_incremental_roic_needs_six_years():
    rows = _roic_rows([100] * 5, [1000] * 5)
    assert V.incremental_roic(rows, 0.0, 7.0, "2017-03", "2021-03")["rating"] == "不明"


def test_incremental_roic_when_capital_barely_grew():
    grew = _roic_rows([100, 100, 100, 120, 120, 120], [1000] * 6)
    assert V.incremental_roic(grew, 0.0, 7.0, "2017-03", "2022-03")["rating"] == "良好"
    flat = _roic_rows([100, 100, 100, 90, 90, 90], [1000] * 6)
    assert V.incremental_roic(flat, 0.0, 7.0, "2017-03", "2022-03")["rating"] == "不明"


def test_incremental_roic_between_half_and_the_cost_of_capital_is_ordinary():
    rows = _roic_rows([100, 100, 100, 150, 150, 150], [1000, 1000, 1000, 2000, 2000, 2000])
    assert V.incremental_roic(rows, 0.0, 7.0, "2017-03", "2022-03")["rating"] == "普通"  # 5.0%


# ---------- 人材 ----------

def test_people_detects_a_labour_intensive_company_and_falling_output_per_head():
    years = _years(5, 2022)
    values = _values(**{"summary.employees": dict(zip(years, [100.0, 120.0, 140.0, 160.0, 180.0])),
                        "summary.average_salary": {years[-1]: 6_000_000.0}})
    sales = dict.fromkeys(years, 2000.0)
    operating = dict(zip(years, [400.0, 420.0, 400.0, 380.0, 360.0]))
    p = V.people(values, sales, operating, years)
    assert p["people_share"] == 54.0 and p["intensive"] is True  # 180 × 6,000,000 ÷ 1e6 ÷ 2,000
    assert p["falling_years"] == 4  # 4.0 → 3.5 → 2.86 → 2.38 → 2.0 per head
    assert V.people_efficiency(p)[0] == "問題あり"


def test_people_efficiency_is_good_when_headcount_and_output_per_head_grow():
    p = {"employees_cagr": 10.0, "per_employee_cagr": 2.0, "falling_years": 0}
    assert V.people_efficiency(p)[0] == "良好"
    assert V.people_efficiency({**p, "per_employee_cagr": None})[0] == "不明"


# ---------- 成長性の結論への組み込み ----------

import gr_metrics as X  # noqa: E402


def _s1(rating: str = "安定成長") -> dict:
    return {"rating": rating, "basis": "売上 CAGR 4%", "sales": {"value": 4.0}, "eps": {"value": 8.0},
            "eps_key": "eps"}


def _s4(problems: list[str] = ()) -> dict:
    checks = [{"gaps": []}, {"gap": None}, {"gap": None}]
    return {"problems": list(problems), "unknown": [], "adjusted": None, "checks": checks}


def _s5(verdict: str) -> dict:
    return {"verdict": verdict, "sentence": f"成長投資は{verdict}"}


def test_a_problem_in_growth_investment_moves_the_verdict_one_step_down():
    assert X.decide(_s1(), [], _s4(), {}, _s5("問題あり"))[0] == "普通"
    assert X.decide(_s1(), [], _s4(["利益率が下がった"]), {}, _s5("問題あり"))[0] == "懸念"
    assert X.decide(_s1("停滞・縮小"), [], _s4(), {}, _s5("問題あり"))[0] == "懸念"


def test_good_growth_investment_moves_a_quality_problem_back_up():
    verdict, why, _ = X.decide(_s1(), [], _s4(["利益率が下がった"]), {}, _s5("良好"))
    assert verdict == "良好" and "成長の質に問題あり" in why and "成長投資" in why


def test_good_growth_investment_does_not_lift_a_concern_or_an_unknown_cause():
    assert X.decide(_s1("停滞・縮小"), [], _s4(), {}, _s5("良好"))[0] == "懸念"
    declines = [{"year": "2024-03"}]
    assert X.decide(_s1(), declines, _s4(), {"2024-03": "不明"}, _s5("良好"))[0] == "普通"


def test_good_growth_investment_does_not_lift_growth_bought_by_acquisitions():
    s4 = _s4(["売上増が M&A による"])
    s4["checks"][1] = {"status": "問題あり", "gap": 3.0}
    assert X.decide(_s1(), [], s4, {}, _s5("良好"))[0] == "普通"


def test_ordinary_unknown_or_excluded_growth_investment_leaves_the_verdict():
    for word in ("普通", "不明", "対象外"):
        assert X.decide(_s1(), [], _s4(), {}, _s5(word))[0] == "良好"
    assert X.decide(_s1(), [], _s4(), {})[0] == "良好"  # without 手順5


def test_banks_are_out_of_scope(tmp_path):
    import json
    from types import SimpleNamespace
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.json").write_text(json.dumps({"sector_name": "銀行業"}), encoding="utf-8")
    s5 = V.step5(SimpleNamespace(path=tmp_path, ticker="8306"), {"first": None, "last": None}, [], has_plan=False)
    assert s5["verdict"] == "対象外" and "銀行業" in s5["sentence"]


# ---------- 判定 ----------

def test_verdict_matrix():
    assert V.verdict("高い", "良好", False) == "良好"
    assert V.verdict("標準", "良好", False) == "良好"
    assert V.verdict("低い", "良好", False) == "普通"
    assert V.verdict("高い", "普通", False) == "普通"
    assert V.verdict("高い", "問題あり", False) == "問題あり"
    assert V.verdict("低い", "問題あり", False) == "問題あり"
    assert V.verdict("標準", "不明", False) == "不明"
    assert V.verdict("標準", "良好", True) == "普通"  # 投資不足 caps it
