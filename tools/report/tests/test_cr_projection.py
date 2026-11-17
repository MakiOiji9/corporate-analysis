import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
TOOLS = REPORT.parent
sys.path[:0] = [str(REPORT), str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import cr_projection as PJ  # noqa: E402
import cr_technicals as T  # noqa: E402
import outlook as O  # noqa: E402


def _facts(standard: float | None = 10.8, optimistic: float | None = 34.7586, eps: float | None = 135.88,
           per: float | None = 29.762, price: float = 3773.0) -> dict:
    cases = None if standard is None else {"standard": standard, "pessimistic": standard / 2,
                                           "optimistic": optimistic}
    return {"price": {"value": price, "currency": "円"},
            "analyses": {"valuation": {"detail": {"eps_used": eps, "peg_cases": cases,
                                                  "pbr_fair": {"average_per": per,
                                                               "average_basis": "有報の期末PER 5 期の平均"}}},
                         "growth": {"detail": {"cagr": {"eps": 10.8}}}}}


def _case(p: dict, name: str) -> dict:
    return next(c for c in p["cases"] if c["name"] == name)


def _row(p: dict, name: str, years: int) -> dict:
    return next(r for r in p["rows"] if r["case"] == name and r["years"] == years)


# ---------------------------------------------------------------- growth rates of the three cases

def test_rates_reuse_the_peg_cases_and_cap_the_optimistic_case_at_one_and_a_half_times():
    p = PJ.build(_facts())
    assert _case(p, "悲観")["rate"] == pytest.approx(5.4)
    assert _case(p, "基本")["rate"] == pytest.approx(10.8)
    assert _case(p, "楽観")["rate"] == pytest.approx(16.2)  # company plan 34.8% capped at 10.8 × 1.5
    assert "上限" in _case(p, "楽観")["basis"]


def test_optimistic_cap_of_25_percent():
    p = PJ.build(_facts(standard=20.0, optimistic=40.0))
    assert _case(p, "楽観")["rate"] == pytest.approx(25.0)


def test_optimistic_uses_the_company_plan_when_it_is_below_the_caps():
    p = PJ.build(_facts(standard=10.0, optimistic=12.0))
    assert _case(p, "楽観")["rate"] == pytest.approx(12.0) and "上限" not in _case(p, "楽観")["basis"]


def test_optimistic_without_a_plan_is_one_and_a_half_times_the_base():
    p = PJ.build(_facts(standard=10.0, optimistic=None))
    assert _case(p, "楽観")["rate"] == pytest.approx(15.0)


# ---------------------------------------------------------------- levels in 3 and 5 years

def test_levels_are_eps_grown_at_the_rate_times_the_five_year_average_per():
    p = PJ.build(_facts())
    assert p["ok"] and p["years"] == [3, 5] and p["per"] == pytest.approx(29.762)
    base3 = _row(p, "基本", 3)
    assert base3["eps"] == pytest.approx(135.88 * 1.108 ** 3)
    assert base3["price"] == pytest.approx(135.88 * 1.108 ** 3 * 29.762)
    assert 5490 < base3["price"] < 5510 and 6740 < _row(p, "基本", 5)["price"] < 6760
    assert 4720 < _row(p, "悲観", 3)["price"] < 4745 and 8550 < _row(p, "楽観", 5)["price"] < 8590


def test_annual_return_from_the_current_price():
    p = PJ.build(_facts())
    r = _row(p, "基本", 3)
    assert r["change"] == pytest.approx((r["price"] / 3773 - 1) * 100)
    assert r["annual"] == pytest.approx(((r["price"] / 3773) ** (1 / 3) - 1) * 100)


# ---------------------------------------------------------------- when no level is drawn

@pytest.mark.parametrize("facts, word", [
    (_facts(eps=-10.0), "EPS"),
    (_facts(eps=None), "EPS"),
    (_facts(per=None), "平均PER"),
    (_facts(standard=3.0), "成長率"),
    (_facts(standard=None), "成長率"),
])
def test_no_levels_without_positive_eps_an_average_per_or_enough_growth(facts, word):
    if word == "成長率" and facts["analyses"]["valuation"]["detail"]["peg_cases"] is None:
        facts["analyses"]["growth"]["detail"]["cagr"]["eps"] = None
    p = PJ.build(facts)
    assert not p["ok"] and p["rows"] == [] and word in p["reason"]


def test_growth_falls_back_to_the_growth_analysis_cagr_without_peg_cases():
    facts = _facts(standard=None)
    facts["analyses"]["growth"]["detail"]["cagr"]["eps"] = 8.0
    p = PJ.build(facts)
    assert p["ok"] and _case(p, "基本")["rate"] == pytest.approx(8.0) and _case(p, "悲観")["rate"] == 4.0


# ---------------------------------------------------------------- the words

def test_the_note_is_a_condition_not_a_forecast():
    p = PJ.build(_facts())
    text = p["note"] + "".join(c["basis"] for c in p["cases"])
    assert "予想ではない" in p["note"]
    assert not T.FORECAST.search(text) and not any(w in text for w in O.FORBIDDEN)
