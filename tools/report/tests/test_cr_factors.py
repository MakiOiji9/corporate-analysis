import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_factors as F  # noqa: E402


def _analysis(verdict: str | None, subs: list | None = None) -> dict:
    return {"verdict": verdict, "reason": "r", "step": "2-1", "label": "収益性", "date": "2026-11-01",
            "subs": subs or []}


# ---------------------------------------------------------------- half steps from the analysis' own sub-ratings

@pytest.mark.parametrize("verdict, subs, score", [
    ("普通", ["良好", "下回る", "本業由来"], 0.5),           # ROE good, margin behind peers: leans good
    ("普通", ["懸念", "同等", "借入依存"], -0.5),            # leans bad
    ("普通", ["良好", "下回る"], 0.0),                       # balanced
    ("懸念", ["良好", "良好", "懸念", "良好", "問題なし"], -0.5),  # one narrow concern among good steps
    ("懸念", ["懸念", "懸念", "普通"], -1.0),
    ("良好", ["良好", "同等", "本業由来"], 1.0),             # a 良好 is not pulled down by a 同等 it allows
    ("良好", ["普通", "下回る", "特定できず"], 0.5),
    ("普通", ["良好"], 0.0),                                 # one known sub-rating is not enough
    ("普通", ["不明", None, "対象外"], 0.0),
])
def test_sub_ratings_move_the_score_half_a_step(verdict, subs, score):
    assert F.analysis_factor(_analysis(verdict, subs))["score"] == score


def test_pending_and_missing_analyses_are_not_moved():
    pending = F.analysis_factor(_analysis("判定保留", ["良好", "良好"]))
    assert pending["score"] == 0.0 and pending["pending"]
    assert F.analysis_factor(_analysis(None, ["良好", "良好"]))["score"] is None


def test_the_reason_says_when_the_score_was_moved():
    factor = F.analysis_factor(_analysis("普通", ["良好", "下回る", "本業由来"]))
    assert "+0.5" in factor["value"] and "内訳" in factor["reason"]


def test_cash_burn_keeps_a_cash_flow_concern_at_minus_one():
    a = {**_analysis("懸念", ["懸念", "問題なし"]), "label": "キャッシュフロー"}
    assert F.analysis_factor(a)["score"] == -0.5
    assert F.analysis_factor(a, hold=True)["score"] == -1.0


# ---------------------------------------------------------------- valuation

def _valuation(scores: dict, verdict: str = "割安") -> dict:
    average = sum(scores.values()) / len(scores) if scores else None
    return {"verdict": verdict, "date": "2026-11-01", "reason": "",
            "detail": {"average": average, "scored": len(scores), "scores": scores, "sheet": "s"}}


def test_valuation_leaves_the_one_sided_net_cash_ratio_out_of_the_average():
    factor = F.valuation_factor(_valuation({"PER": 0, "PBR": 1, "PEG": -1, "EV/EBITDA": 1, "ネットキャッシュ比率": 1}))
    assert factor["score"] == pytest.approx(0.25) and "4指標" in factor["value"]


def test_valuation_on_a_single_indicator_is_pending():
    factor = F.valuation_factor(_valuation({"PBR": 1}))
    assert factor["score"] == 0.0 and factor["pending"] and "1指標" in factor["value"]


def test_valuation_with_only_the_net_cash_ratio_is_pending():
    factor = F.valuation_factor(_valuation({"ネットキャッシュ比率": 1}))
    assert factor["score"] == 0.0 and factor["pending"]


def test_valuation_without_scores_falls_back_to_the_verdict():
    factor = F.valuation_factor({"verdict": "割高", "date": "2026-11-01", "detail": {}})
    assert factor["score"] == -1.0


# ---------------------------------------------------------------- price

def test_price_without_a_year_of_trend_is_left_out():
    short = {"source": "prices", "technicals": {"ok": True, "score": 0.75, "state": "x",
                                                "trend": {"score": None, "value": "トレンド 不明"},
                                                "momentum": {"score": 0.5, "value": "m"},
                                                "position": {"score": 1.0, "value": "p"}}}
    assert F.price_factor(short)["score"] is None
    full = {**short, "technicals": {**short["technicals"], "trend": {"score": 0.5, "value": "t"}}}
    assert F.price_factor(full)["score"] == 0.75
