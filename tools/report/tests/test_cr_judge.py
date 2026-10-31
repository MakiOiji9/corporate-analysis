import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_judge as J  # noqa: E402

GOOD4 = {"収益性": "良好", "成長性": "良好", "安全性": "良好", "キャッシュフロー": "良好"}


def _s(grade: str, pending: bool = False) -> dict:
    return {"grade": grade, "pending": pending}


def _f(score: float | None, pending: bool = False) -> dict:
    return {"score": score, "value": "v", "reason": "r", "source": "s", "pending": pending}


# ---------------------------------------------------------------- STEP 1

@pytest.mark.parametrize("attr, win, moat, swot, grade, pending", [
    ("中", "明確", "広い", "Yes", "A", False),
    ("低", "明確", "広い", "Yes", "B", False),
    ("中", "あいまい", "広い", "Yes", "B", False),
    ("高", "なし", "広い", "Yes", "C", False),
    ("高", "明確", "広い", "No", "C", False),
    ("中", "判定保留", "なし", "条件付き", "B", True),
    ("中", "判定保留", "広い", "No", "C", False),
])
def test_step1_rules(attr, win, moat, swot, grade, pending):
    result = J.step1(attr, win, moat, swot)
    assert (result["grade"], result["pending"]) == (grade, pending)


# ---------------------------------------------------------------- STEP 2 (score + red flags)

@pytest.mark.parametrize("items, mismatch, flags, grade", [
    (GOOD4, [], [], "A"),
    ({**GOOD4, "成長性": "普通"}, [], [], "A"),                                      # +0.75
    ({**GOOD4, "成長性": "普通", "安全性": "普通"}, [], [], "A"),                      # +0.5
    ({**GOOD4, "成長性": "普通"}, ["食い違い"], [], "B"),
    ({**GOOD4, "成長性": "普通", "キャッシュフロー": "懸念"}, [], [], "B"),             # 3798: +0.25
    ({**GOOD4, "キャッシュフロー": "懸念"}, [], [], "A"),                              # +0.5: one concern is not C
    ({**GOOD4, "成長性": "懸念", "安全性": "懸念"}, [], [], "C"),                      # two concerns
    ({"収益性": "普通", "成長性": "普通", "安全性": "普通", "キャッシュフロー": "懸念"}, [], [], "C"),  # −0.25
    (GOOD4, [], ["営業CF がマイナス"], "C"),                                          # a serious red flag
])
def test_step2_score_rules(items, mismatch, flags, grade):
    assert J.step2(items, mismatch, flags)["grade"] == grade


def test_step2_pending_items():
    result = J.step2({**GOOD4, "安全性": "判定保留"}, [])
    assert result["grade"] == "B" and result["pending"]
    assert J.step2({k: None for k in GOOD4}, [])["pending"]


def test_red_flags():
    assert J.red_flags([{"rating": "良好"}, {"rating": "良好"}, {"rating": "懸念"}], "良好", "悪化傾向なし") == []
    assert len(J.red_flags([{"rating": "懸念"}, {"rating": "懸念"}], "懸念", "悪化傾向")) == 3


@pytest.mark.parametrize("moat, win, prof, diff, count", [
    ("広い", "明確", "良好", 2.0, 0), ("広い", "明確", "良好", -0.5, 1), ("広い", "明確", "懸念", 2.0, 2),
    ("狭い", "あいまい", "懸念", -3.0, 0), ("狭い", "明確", "懸念", None, 1),
])
def test_mismatches(moat, win, prof, diff, count):
    assert len(J.mismatches(moat, win, prof, diff)) == count


# ---------------------------------------------------------------- horizons

def _all(score: float) -> dict:
    keys = set().union(*(set(w) for w in J.WEIGHTS.values()))
    return {k: _f(score) for k in keys}


def test_weights_sum_to_100():
    assert all(sum(w.values()) == 100 for w in J.WEIGHTS.values())


@pytest.mark.parametrize("score, verdict", [(1.0, "投資検討"), (0.3, "投資検討"), (0.29, "ウォッチ"),
                                            (-0.19, "ウォッチ"), (-0.2, "見送り"), (-1.0, "見送り")])
def test_thresholds(score, verdict):
    assert J.horizon_score("mid", _all(score))["verdict"] == verdict


def test_missing_factors_are_left_out_and_reweighted():
    factors = {**_all(1.0), "price": _f(None), "progress": _f(None)}
    result = J.horizon_score("short", factors)
    assert result["score"] == pytest.approx(1.0) and set(result["unknown"]) == {"株価の位置・勢い", "直近の決算の進捗"}
    assert J.horizon_score("short", {k: _f(None) for k in factors})["verdict"] == "判定保留"


def test_horizons_weigh_different_factors():
    factors = {**_all(0.0), "moat": _f(-1.0), "three_c": _f(-1.0), "market": _f(1.0), "price": _f(1.0)}
    assert J.horizon_score("long", factors)["verdict"] == "見送り"      # weak business
    assert J.horizon_score("short", factors)["verdict"] == "投資検討"    # good market and price position


def test_good_and_bad_points_follow_the_contributions():
    factors = {**_all(0.0), "valuation": _f(1.0), "cash_flow": _f(-1.0)}
    result = J.horizon_score("mid", factors)
    assert [r["key"] for r in result["good"]] == ["valuation"] and [r["key"] for r in result["bad"]] == ["cash_flow"]
    assert result["good"][0]["contribution"] == pytest.approx(0.2)


def test_knockouts():
    good = _all(1.0)
    flagged = J.horizon_score("short", good, ["FCF の累計がマイナス"])
    assert flagged["verdict"] == "見送り" and "足切り" in flagged["why"]
    assert J.horizon_score("long", good, [], "C")["verdict"] == "見送り"
    assert J.horizon_score("short", good, [], "C")["verdict"] == "投資検討"   # STEP 1 C only stops the long horizon


def test_pending_analysis_counts_as_zero():
    factors = {**_all(1.0), "three_c": _f(0.0, pending=True)}
    result = J.horizon_score("long", factors)
    assert result["score"] == pytest.approx(0.85) and any(r["pending"] for r in result["rows"])


def test_uls_like_case_is_watch_on_every_horizon():
    factors = {"market": _f(-1.0), "price": _f(0.5), "progress": _f(0.0), "valuation": _f(0.75), "safety": _f(1.0),
               "growth": _f(0.0), "profitability": _f(1.0), "cash_flow": _f(-1.0), "swot": _f(0.0),
               "five_forces": _f(0.0), "three_c": _f(0.0), "moat": _f(-1.0)}
    assert J.horizon_score("short", factors)["verdict"] == "ウォッチ"
    assert J.horizon_score("mid", {**factors, "market": _f(0.0)})["verdict"] == "ウォッチ"
    assert J.horizon_score("long", {**factors, "market": _f(1.0)})["verdict"] == "ウォッチ"


def test_sensitivity_lists_single_movers():
    factors = {**_all(0.0), "valuation": _f(1.0)}   # mid: +0.2
    result = J.sensitivity("mid", factors)
    assert result["to_up"] == pytest.approx(0.1)
    ups = [m for m in result["movers"] if m["direction"] == "1段良くなれば"]
    assert "growth" in {m["key"] for m in ups} and all(m["verdict"] == "投資検討" for m in ups)
    assert J.sensitivity("mid", factors, ["赤信号"])["movers"] == []


# ---------------------------------------------------------------- the framework's matrix (reference)

@pytest.mark.parametrize("g1, g2, s3, verdict", [
    ("A", "A", "割安", "投資検討"), ("A", "A", "妥当", "投資検討"), ("A", "A", "割高", "ウォッチ"),
    ("A", "B", "割安", "投資検討"), ("B", "A", "妥当", "ウォッチ"), ("B", "B", "割高", "見送り"),
    ("C", "A", "割安", "見送り"), ("A", "C", "妥当", "見送り"),
])
def test_matrix_reference(g1, g2, s3, verdict):
    assert J.matrix_reference(_s(g1), _s(g2), s3)["verdict"] == verdict


def test_matrix_reference_without_valuation_caps_at_watch():
    assert J.matrix_reference(_s("A"), _s("A"), "判定保留")["verdict"] == "ウォッチ"
