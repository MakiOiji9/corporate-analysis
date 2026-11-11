import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ANALYSIS)]

import va_guide as G  # noqa: E402
import va_rules as R  # noqa: E402

ROW = {"current_assets": 60000.0, "investment_securities": 10000.0, "liabilities": 30000.0}


def test_asset_net_cash_ratio_and_rating():
    out = G.ncr_step(ROW, {"value": 30000.0}, None)
    assert out["asset_net_cash"] == pytest.approx(37000.0)       # 60000 + 10000 × 0.7 − 30000
    assert out["value"] == pytest.approx(1.23, abs=0.01) and out["rating"] == R.LOW
    assert G.ncr_step(ROW, {"value": 80000.0}, None)["rating"] == R.FAIR
    assert G.ncr_step({**ROW, "liabilities": 90000.0}, {"value": 80000.0}, None)["rating"] == R.NA


def test_asset_net_cash_needs_every_part():
    out = G.ncr_step({**ROW, "investment_securities": None}, {"value": 30000.0}, None)
    assert out["rating"] == R.PENDING and "投資有価証券" in out["sentence"]
    assert G.ncr_step(ROW, {"value": 30000.0}, "金融業")["rating"] == R.NA


@pytest.mark.parametrize("kw, kind, guide", [
    ({"moat": "狭い"}, "ニッチトップ型", 20),
    ({"customer": 12.0}, "優良顧客型", 15),
    ({"customer": None, "no_major_customer": True}, "優良顧客型", 15),
    ({"customer": 35.0, "ncr": 1.2}, "下請け型", 7),
    ({"sector": "不動産業", "cap": 50000.0}, "中小の不動産", 10),
])
def test_business_type(kw, kind, guide):
    base = {"moat": "なし", "customer": None, "no_major_customer": False, "sector": "電気機器", "cap": 500000.0,
            "ncr": 0.5}
    out = G.business_type(**{**base, **kw})
    assert out["type"].startswith(kind) and out["guide"] == guide


def test_subcontractor_without_net_cash_has_no_guide():
    out = G.business_type(moat="なし", customer=35.0, no_major_customer=False, sector="機械", cap=1e5, ncr=0.3)
    assert out["guide"] is None and "1倍未満" in out["basis"]


def test_unknown_type():
    out = G.business_type(moat=None, customer=None, no_major_customer=False, sector="機械", cap=1e5, ncr=None)
    assert out["guide"] is None


def test_guide_axis_moves_an_opposite_rating_one_step():
    per = {"rating": R.LOW, "per_used": 30.0, "sentence": "予想PER 30.0倍: …", "borderline": []}
    out = G.apply_guide(per, {"type": "優良顧客型", "guide": 15, "basis": "b"})
    assert out["guide"]["zone"] == R.HIGH and out["rating"] == R.FAIR and "業態の目安" in out["sentence"]
    same = G.apply_guide({**per, "rating": R.FAIR}, {"type": "優良顧客型", "guide": 15, "basis": "b"})
    assert same["rating"] == R.FAIR
    cheap = G.apply_guide({**per, "per_used": 12.0}, {"type": "優良顧客型", "guide": 15, "basis": "b"})
    assert cheap["guide"]["zone"] == R.LOW and cheap["rating"] == R.LOW


def test_guide_does_not_touch_an_unrated_per():
    per = {"rating": R.NA, "per_used": None, "sentence": "評価対象外", "borderline": []}
    assert G.apply_guide(per, {"type": "x", "guide": 15, "basis": "b"})["rating"] == R.NA


def test_no_person_name_in_the_labels():
    import inspect
    assert "清原" not in inspect.getsource(G)
