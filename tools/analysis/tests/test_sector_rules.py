import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import pf_metrics as PF  # noqa: E402
import sector_rules as SR  # noqa: E402
import sf_metrics as SF  # noqa: E402
import va_metrics as VA  # noqa: E402
from company_profile import parse_codelist, parse_submissions  # noqa: E402

CODELIST = ("ダウンロード実行日,2026年11月10日現在,件数,2件\n"
            "ＥＤＩＮＥＴコード,提出者種別,上場区分,連結の有無,資本金,決算日,提出者名,提出者名（英字）,提出者名（ヨミ）,"
            "所在地,提出者業種,証券コード,提出者法人番号\n"
            "E99999,内国法人・組合,上場,有,1000,3月31日,テスト銀行,Test Bank,テストギンコウ,東京都,銀行業,99990,1\n"
            "E99998,内国法人・組合,非上場,有,1000,3月31日,非上場社,X,X,東京都,サービス業,,2\n")


def _company(tmp_path: Path, profile: dict | None) -> SimpleNamespace:
    (tmp_path / "data").mkdir(parents=True, exist_ok=True)
    if profile is not None:
        (tmp_path / "data" / "profile.json").write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
    return SimpleNamespace(path=tmp_path, ticker="9999")


def test_parse_codelist_and_submissions():
    found = parse_codelist(CODELIST, "9999")
    assert found["sector_name"] == "銀行業" and found["edinet_code"] == "E99999"
    assert parse_codelist(CODELIST, "1234") is None
    us = parse_submissions({"cik": "0000000001", "name": "X", "sic": "6022", "sicDescription": "State Banks"})
    assert us["sic"] == 6022 and us["sector_name"] == "State Banks"


@pytest.mark.parametrize("profile, group", [
    ({"market": "japan", "sector_name": "銀行業"}, SR.FINANCIAL),
    ({"market": "japan", "sector_name": "その他金融業"}, SR.FINANCIAL),
    ({"market": "japan", "sector_name": "不動産業"}, SR.REAL_ESTATE),
    ({"market": "japan", "sector_name": "卸売業"}, SR.TRADING),
    ({"market": "japan", "sector_name": "電気・ガス業"}, SR.UTILITY),
    ({"market": "japan", "sector_name": "電気機器"}, SR.GENERAL),
    ({"market": "us", "sic": 6022}, SR.FINANCIAL),
    ({"market": "us", "sic": 6798}, SR.REAL_ESTATE),
    ({"market": "us", "sic": 4911}, SR.UTILITY),
    ({"market": "us", "sic": 3674}, SR.GENERAL),
    ({"market": "us", "sic": None}, None),
    (None, None),
])
def test_group_of(profile, group):
    assert SR.group_of(profile) == group


def test_safety_uses_the_profile_before_the_business_text(tmp_path):
    bank = _company(tmp_path / "a", {"market": "japan", "sector_name": "銀行業"})
    maker = _company(tmp_path / "b", {"market": "japan", "sector_name": "電気機器"})
    assert SF.sector_excluded(bank) and not SF.sector_excluded(maker)


def test_profitability_leverage_is_not_borrowing_dependence_for_banks():
    own = [{"year": "2026-03", "leverage": 18.0, "margin": 20.0, "turnover": 0.02, "roe": 7.0}]
    no_peers = {"peers": [], "self": None, "peer_avg": None}
    assert PF.step3(own, no_peers)["source"] == "借入依存"
    s3 = PF.step3(own, no_peers, "業種（銀行業）は借入が事業の一部")
    assert s3["source"] == "不明" and "銀行業" in s3["basis"]


def _wc(sales: float | None, receivables: float | None, inventories: float | None = None) -> list[dict]:
    return [{"field": f, "name": n, "cagr": c} for f, n, c in (("sales", "売上高", sales),
                                                               ("receivables", "売上債権", receivables),
                                                               ("inventories", "棚卸資産", inventories))]


@pytest.mark.parametrize("rating, ratio, wc, adjusted", [
    ("懸念", 0.77, _wc(25.0, 20.0), True),          # fast growth, receivables in step with sales
    ("懸念", 0.77, _wc(25.0, 30.0), False),         # receivables outgrow sales: the flag stays
    ("懸念", 0.77, _wc(6.0, 4.0), False),           # growth too slow to explain the gap
    ("懸念", 0.40, _wc(25.0, 20.0), False),         # too little cash even for a grower
    ("懸念", 0.77, _wc(25.0, None, None), False),   # no working-capital line to check
    ("普通", 0.85, _wc(25.0, 20.0), False),         # only a 懸念 is corrected
])
def test_cash_flow_growth_correction(rating, ratio, wc, adjusted):
    import cf_metrics as CF
    assert bool(CF.growth_absorbed(rating, ratio, wc)) is adjusted


def test_margin_gap_uses_three_years():
    rows = [{"year": f"202{i}-03", "diff": d} for i, d in enumerate([5.0, -3.0, 0.5, 2.0, -1.8])]
    gap, recent, rating = PF.margin_gap(rows)
    assert [r["year"] for r in recent] == ["2022-03", "2023-03", "2024-03"] and gap == 0.2 and rating == "同等"
    assert PF.margin_gap(rows[:1])[2] == "上回る"  # one year only: that year decides


def test_safety_peer_average_is_the_median():
    rows = [{"equity_ratio": 40.0, "de": 0.2, "current_ratio": 150.0},
            {"equity_ratio": 50.0, "de": 0.3, "current_ratio": 160.0},
            {"equity_ratio": 90.0, "de": 3.0, "current_ratio": None}]  # one outlier peer
    avg = SF.peer_average(rows)
    assert avg["equity_ratio"] == 50.0 and avg["de"] == 0.3 and avg["current_ratio"] == 155.0


@pytest.mark.parametrize("coverage, word", [
    (15.4, "余裕あり"), (3.0, "賄えている"), (1.2, "余裕が小さい"), (None, "不明"),
])
def test_interest_coverage_text(coverage, word):
    assert word in SF.coverage_text(coverage)


def test_roic_capital_adds_leases_and_deducts_capped_excess_cash():
    import mt_returns as MR
    import pf_series as PS

    def series(**years: dict) -> dict:
        fields = ("equity", "debt", "lease", "cash", "short_investments", "sales")
        return {f: {y: PS.Value(v[f], "t", True) for y, v in years.items() if f in v} for f in fields}

    # equity 100 + debt 20 + lease 10 = 130; cash 30 − 5% of sales 200 = 20 excess -> 110
    assert MR._capital(series(**{"2026-03": {"equity": 100, "debt": 20, "lease": 10, "cash": 30, "sales": 200}})) \
        == {"2026-03": 110.0}
    # cash 500 would leave nothing: the deduction stops at half of 130 -> 65
    assert MR._capital(series(**{"2026-03": {"equity": 100, "debt": 20, "lease": 10, "cash": 500, "sales": 200}})) \
        == {"2026-03": 65.0}
    # no sales: no excess cash is assumed
    assert MR._capital(series(**{"2026-03": {"equity": 100, "debt": 20, "cash": 500}})) == {"2026-03": 120.0}


def _prices(path: Path, days: list[tuple[str, float, float]]) -> None:
    (path / "data").mkdir(parents=True, exist_ok=True)
    lines = ["date,open,high,low,close,adj_close,volume,retrieved"]
    lines += [f"{d},{h},{h},{lo},{lo},{lo},100,2026-11-10" for d, h, lo in days]
    (path / "data" / "prices.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_price_history_from_daily_prices_and_eps(tmp_path):
    import datetime as dt

    import va_series as V
    start = dt.date(2024, 4, 1)
    days = [((start + dt.timedelta(days=i)).isoformat(), 120.0 if i == 100 else 100.0, 80.0 if i == 200 else 90.0)
            for i in range(730)]
    company = SimpleNamespace(path=tmp_path, ticker="9999")
    _prices(tmp_path, days)
    years = {"rows": [{"year": "2024-03", "eps": 5.0, "net_income": 50.0, "equity": 500.0},   # before the prices
                      {"year": "2025-03", "eps": 10.0, "net_income": 100.0, "equity": 1000.0},
                      {"year": "2026-03", "eps": -1.0, "net_income": -10.0, "equity": 900.0}]}  # a loss year
    got = V.price_history(company, years)
    # 2025-03: high 120 and low 80 within the year; EPS 10 -> PER 12 / 8; BPS = 1000 × 10 ÷ 100 = 100 -> PBR 1.2 / 0.8
    assert got == [{"year": "2025-03", "per_high": 12.0, "per_low": 8.0, "pbr_high": 1.2, "pbr_low": 0.8,
                    "source": V.COMPUTED_SOURCE}]
    merged = V.merged_history(got, [{"year": "2024-03", "per_high": 30.0, "per_low": 20.0, "pbr_high": 3.0,
                                     "pbr_low": 2.0, "per_end": 25.0},
                                    {"year": "2025-03", "per_high": 99.0, "per_low": 1.0, "pbr_high": None,
                                     "pbr_low": None, "per_end": 11.0}])
    assert [(h["year"], h["per_high"], h["per_end"], h["source"]) for h in merged] == [
        ("2024-03", 30.0, 25.0, V.RAW_SOURCE), ("2025-03", 12.0, 11.0, V.COMPUTED_SOURCE)]


def test_ev_claims_adds_leases_minority_and_short_investments():
    row = {"debt": 100.0, "cash": 50.0, "lease": 15.0, "nci": 10.0, "short_investments": 5.0}
    debt, cash, added = VA.ev_claims(row)
    assert (debt, cash) == (125.0, 55.0) and len(added) == 3
    assert VA.ev_claims({"debt": 100.0, "cash": 50.0}) == (100.0, 50.0, [])
    assert VA.ev_claims({"debt": None, "cash": 50.0, "lease": 15.0}) == (None, 50.0, [])
