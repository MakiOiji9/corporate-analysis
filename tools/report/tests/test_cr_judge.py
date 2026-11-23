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
    ("中", "明確", "狭い", "Yes", "A", False),  # a narrow moat is enough for A (a wide one is rare)
    ("中", "明確", "なし", "Yes", "B", False),
])
def test_step1_rules(attr, win, moat, swot, grade, pending):
    result = J.step1(attr, win, moat, swot)
    assert (result["grade"], result["pending"]) == (grade, pending)


def test_long_horizon_weighs_growth_more_than_the_moat():
    long = J.WEIGHTS["long"]
    # 判定ルールの改定 4: growth 15 and the investment quality 10 (growth's 手順5 moved there), 3C 15 → 10
    assert (long["growth"], long["investment"], long["moat"], long["cash_flow"]) == (15, 10, 10, 5)
    assert long["five_forces"] + long["three_c"] + long["moat"] + long["swot"] == 35
    assert J.WEIGHTS["mid"]["growth"] == 10 and J.WEIGHTS["mid"]["investment"] == 5
    assert all(sum(w.values()) == 100 for w in J.WEIGHTS.values())


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


BURNING = [{"year": "2022", "cfo": -164.0, "fcf": -27.0}, {"year": "2023", "cfo": -79.0, "fcf": 3.0},
           {"year": "2024", "cfo": 452.0, "fcf": 435.0}, {"year": "2025", "cfo": -10.0, "fcf": -678.0}]
UNJUDGED = [{"rating": None}, {"rating": None}]


def test_cash_burn_reads_the_raw_rows_when_the_steps_could_not_be_judged():
    burn = J.cash_burn(BURNING, UNJUDGED)
    assert len(burn) == 2 and "3/4年" in burn[0] and "FCF の累計" in burn[1]
    assert J.cash_burn(BURNING, [{"rating": "普通"}, {"rating": "良好"}]) == []  # judged steps decide instead
    assert J.cash_burn(BURNING[2:3], UNJUDGED) == []  # one year is not a pattern
    healthy = [{"year": y, "cfo": 10.0, "fcf": 5.0} for y in ("2023", "2024", "2025")]
    assert J.cash_burn(healthy, UNJUDGED) == []


def test_cash_burn_is_a_red_flag_unless_the_balance_sheet_is_strong():
    burn = J.cash_burn(BURNING, UNJUDGED)
    assert J.red_flags(UNJUDGED, "普通", "悪化傾向なし", burn) == burn
    assert J.red_flags(UNJUDGED, "良好", "悪化傾向なし", burn) == []


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


@pytest.mark.parametrize("score, verdict", [(1.0, "投資検討"), (0.25, "投資検討"), (0.24, "ウォッチ"),
                                            (-0.24, "ウォッチ"), (-0.25, "見送り"), (-1.0, "見送り")])
def test_thresholds(score, verdict):
    assert J.horizon_score("mid", _all(score))["verdict"] == verdict


def test_missing_factors_are_left_out_and_reweighted():
    factors = {**_all(1.0), "trend_daily": _f(None), "progress": _f(None)}
    result = J.horizon_score("short", factors)
    assert result["score"] == pytest.approx(1.0) and set(result["unknown"]) == {"株価のテクニカル（日足のトレンド）", "直近の決算の進捗"}
    assert J.horizon_score("short", {k: _f(None) for k in factors})["verdict"] == "判定保留"


def test_a_single_known_factor_is_not_enough_for_a_verdict():
    # 改善案.md P0: only 安全性 (10% of the short horizon) known used to give +1.00 and 投資検討
    factors = {k: _f(None) for k in _all(0.0)}
    factors["safety"] = _f(1.0)
    result = J.horizon_score("short", factors)
    assert result["verdict"] == "判定保留" and result["provisional"] == "投資検討"
    assert result["coverage"] == pytest.approx(0.10) and "10%" in result["why"]


def test_coverage_at_the_minimum_still_gives_a_verdict():
    # short: market 25 + price 25 + valuation 20 known = 70%; progress 20 + safety 10 missing
    factors = {**_all(1.0), "progress": _f(None), "safety": _f(None)}
    result = J.horizon_score("short", factors)
    assert result["verdict"] == "投資検討" and result["coverage"] == pytest.approx(0.70)
    assert "判定に使えた材料 70%" in result["why"]
    below = {**factors, "valuation": _f(None)}  # 50%
    assert J.horizon_score("short", below)["verdict"] == "判定保留"


def test_pending_analyses_do_not_count_as_material():
    # a 判定保留 analysis scores 0 but is no evidence: STEP 1's four (35% of the long horizon) and the valuation (15%)
    # pending leave 50%, so the horizon is pending too
    factors = _all(1.0)
    for key in ("five_forces", "three_c", "moat", "swot", "valuation"):
        factors[key] = _f(0.0, pending=True)
    result = J.horizon_score("long", factors)
    assert result["coverage"] == pytest.approx(0.50) and result["verdict"] == "判定保留"
    assert "勝てる理由（3C）（判定保留）" in result["why"]


def test_a_pending_horizon_has_no_nearest_boundary_or_movers():
    factors = {k: _f(None) for k in _all(0.0)}
    factors["safety"] = _f(1.0)
    out = J.sensitivity("short", factors)
    assert out["nearest"] is None and out["movers"] == []


def test_the_matrix_note_is_left_out_for_a_pending_long_horizon():
    long = {"verdict": "判定保留", "score": 0.30, "knockout": []}
    assert J.matrix_note({"verdict": "ウォッチ"}, long) == ""


def test_full_coverage_does_not_mention_it():
    result = J.horizon_score("mid", _all(0.0))
    assert result["coverage"] == 1.0 and "判定に使えた材料" not in result["why"]


def test_horizons_weigh_different_factors():
    factors = {**_all(0.0), "moat": _f(-1.0), "three_c": _f(-1.0), "growth": _f(-1.0), "market": _f(1.0),
               "price": _f(1.0)}
    assert J.horizon_score("long", factors)["verdict"] == "見送り"      # weak business that does not grow
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


def test_step1_c_is_weighed_not_a_knockout():
    # STEP 1 C already scores −1 through 3C and SWOT; it no longer overrides the long horizon's score
    factors = {**_all(0.5), "swot": _f(-1.0)}
    result = J.horizon_score("long", factors, [], "C")
    assert result["knockout"] == [] and result["verdict"] == "投資検討"
    assert "STEP 1 が C" in result["why"]
    assert "STEP 1 が C" not in J.horizon_score("short", factors, [], "C")["why"]


def test_cautions_are_shown_but_do_not_stop_the_horizon():
    result = J.horizon_score("short", _all(1.0), [], None, ["営業CF がマイナスの年が多い"])
    assert result["verdict"] == "投資検討" and result["cautions"] == ["営業CF がマイナスの年が多い"]
    assert "注意: 営業CF" in result["why"]


def test_pending_analysis_counts_as_zero():
    factors = {**_all(1.0), "three_c": _f(0.0, pending=True)}
    result = J.horizon_score("long", factors)
    assert result["score"] == pytest.approx(0.90) and any(r["pending"] for r in result["rows"])


def test_uls_like_case():
    factors = {"market": _f(-1.0), "price": _f(0.5), "progress": _f(0.0), "valuation": _f(0.75), "safety": _f(1.0),
               "growth": _f(0.0), "profitability": _f(1.0), "cash_flow": _f(-1.0), "swot": _f(0.0),
               "five_forces": _f(0.0), "three_c": _f(0.0), "moat": _f(-1.0)}
    assert J.horizon_score("short", factors)["verdict"] == "ウォッチ"                       # +0.125
    assert J.horizon_score("mid", {**factors, "market": _f(0.0)})["verdict"] == "投資検討"   # +0.25
    assert J.horizon_score("long", {**factors, "market": _f(1.0)})["verdict"] == "ウォッチ"  # +0.05


@pytest.mark.parametrize("score, to, gap", [
    (-0.28, "ウォッチ", 0.03),   # 見送り: the next verdict up is ウォッチ, just above −0.25
    (-0.5, "ウォッチ", 0.25),
    (0.2, "投資検討", 0.05),     # ウォッチ: the nearer of the two boundaries
    (-0.15, "見送り", -0.1),
    (0.4, "ウォッチ", -0.15),    # 投資検討: how far it can fall before it becomes ウォッチ
])
def test_nearest_boundary(score, to, gap):
    near = J.nearest(score)
    assert near["to"] == to and near["gap"] == pytest.approx(gap)
    assert J.nearest(None) is None


def test_nearest_at_the_exact_thresholds_says_which_way():
    down = J.nearest(J.DOWN)  # exactly −0.25 is still 見送り: it has to rise above it
    assert down["to"] == "ウォッチ" and down["text"] == "見送りの境目（-0.25）ちょうど（上回るとウォッチ）"
    up = J.nearest(J.UP)  # exactly +0.25 is 投資検討 until it falls below it
    assert up["to"] == "ウォッチ" and up["text"] == "投資検討の境目（+0.25）ちょうど（下回るとウォッチ）"


def test_why_names_the_nearest_boundary():
    factors = {**_all(0.0), "market": _f(-1.0), "safety": _f(0.5)}  # short: −0.20
    why = J.horizon_score("short", factors)["why"]
    assert "見送りの境目（-0.25）まであと 0.05 点" in why and "-0.05" not in why


def test_sensitivity_lists_single_movers():
    factors = {**_all(0.0), "valuation": _f(1.0)}   # mid: +0.2
    result = J.sensitivity("mid", factors)
    assert result["to_up"] == pytest.approx(0.05) and result["nearest"]["to"] == "投資検討"
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


def test_matrix_note_explains_a_disagreement_with_the_long_horizon():
    matrix = {"verdict": "見送り", "note": "", "why": "STEP 1 が C のため見送り（判定マトリクス）"}
    note = J.matrix_note(matrix, {"verdict": "ウォッチ", "score": 0.03})
    assert "長期の判定はウォッチ" in note and "+0.03" in note and "マトリクスは見送り" in note
    assert J.matrix_note(matrix, {"verdict": "見送り", "score": -0.4}) == ""
    assert J.matrix_note({}, {"verdict": "見送り", "score": -0.4}) == ""
    knocked = {"verdict": "見送り", "score": 0.4, "knockout": ["FCF の累計がマイナス"]}
    assert J.matrix_note({**matrix, "verdict": "投資検討"}, knocked) == ""


# ---------------------------------------------------------------- movers as concrete conditions

def _rows(**scores):
    return [{"key": k, "score": v} for k, v in scores.items()]


def test_mover_text_names_the_next_word():
    m = {"key": "growth", "label": "成長性", "direction": "1段良くなれば", "verdict": "投資検討"}
    assert J.mover_text(m, _rows(growth=0.0)) == "成長性が「良好」になれば（今は「普通」）投資検討"
    m = {"key": "market", "label": "地合い", "direction": "1段良くなれば", "verdict": "ウォッチ"}
    assert J.mover_text(m, _rows(market=-1.0)) == "地合いが「注意」になれば（今は「警戒」）ウォッチ"


def test_mover_text_for_numeric_factors():
    m = {"key": "progress", "label": "直近の決算の進捗", "direction": "1段悪くなれば", "verdict": "見送り"}
    assert J.mover_text(m, _rows(progress=0.0)) == "次の決算で営業利益の進捗が前年同期の90%を下回れば見送り"


def test_half_scores_move_to_the_next_whole_word():
    factors = {**_all(0.0), "cash_flow": _f(-0.5), "valuation": _f(1.0)}  # mid: +0.15
    ups = {m["key"]: m for m in J.sensitivity("mid", factors)["movers"] if m["direction"] == "1段良くなれば"}
    assert ups["growth"]["to"] == 1.0
    m = {**ups.get("cash_flow", {"key": "cash_flow", "label": "キャッシュフロー", "direction": "1段良くなれば",
                                 "verdict": "投資検討"}), "to": 0.0}
    text = J.mover_text(m, _rows(cash_flow=-0.5))
    assert text.startswith("キャッシュフローが「普通」になれば（今は -0.5 点）")


def test_mover_text_with_a_fractional_valuation_score():
    m = {"key": "valuation", "label": "株価の割安さ（STEP 3）", "direction": "1段良くなれば", "verdict": "投資検討"}
    assert J.mover_text(m, _rows(valuation=0.6)) == "株価の割安さ（STEP 3）が「割安」で揃えば投資検討"


def test_half_score_text_names_the_verdict_word():
    m = {"key": "growth", "label": "成長性", "direction": "1段悪くなれば", "verdict": "ウォッチ", "to": 0.0}
    rows = [{"key": "growth", "score": 0.5, "value": "普通（内訳から +0.5）"}]
    assert J.mover_text(m, rows) == "成長性の内訳の寄りが無くなれば（今は「普通」を +0.5 点で数えている）ウォッチ"
    m = {"key": "cash_flow", "label": "キャッシュフロー", "direction": "1段良くなれば", "verdict": "投資検討", "to": 0.0}
    rows = [{"key": "cash_flow", "score": -0.5, "value": "懸念（内訳から -0.5）"}]
    assert J.mover_text(m, rows) == "キャッシュフローが「普通」になれば（今は「懸念」を -0.5 点で数えている）投資検討"


def test_moat_moves_on_its_own_four_steps():
    factors = {**_all(0.0), "valuation": _f(1.0), "growth": _f(0.5)}
    moves = {(m["key"], m["direction"]): m for m in J.sensitivity("long", factors)["movers"]}
    for (key, _), m in moves.items():
        if key == "moat":
            assert m["to"] in (-1.0, 0.5)
    assert J._next_word(0.0, 1, "moat") == 0.5 and J._next_word(0.0, -1, "moat") == -1.0
    assert J._next_word(0.5, 1, "moat") == 1.0 and J._next_word(1.0, 1, "moat") == 1.0
    rows = [{"key": "moat", "score": 0.0, "value": "なし（超過収益は強い。それを守る源泉は特定できない）"}]
    down = {"key": "moat", "label": "強みの持続性（モート）", "direction": "1段悪くなれば", "verdict": "ウォッチ", "to": -1.0}
    text = J.mover_text(down, rows)
    assert "狭い" not in text and text.startswith("資本コストを上回る利益（超過収益）が無くなれば")
    up = {**down, "direction": "1段良くなれば", "verdict": "投資検討", "to": 0.5}
    assert J.mover_text(up, rows) == "強みの持続性（モート）が「狭い」になれば（今は「なし」）投資検討"


def _distance(score):
    return {"nearest": J.nearest(score), "to_up": round(J.UP - score, 3) if score < J.UP else None,
            "to_down": round(score - J.DOWN, 3) if score > J.DOWN else None}


def test_distance_text_has_no_signs_or_repeats():
    watch = J.distance_text(_distance(0.05))
    assert watch == "投資検討の境目（+0.25）まであと 0.20 点。見送りの境目（-0.25）までは 0.30 点の余裕がある"
    consider = J.distance_text(_distance(0.28))
    assert consider.startswith("投資検討の境目（+0.25）を 0.03 点上回っている（下回るとウォッチ）")
    assert J.distance_text(_distance(-0.4)).startswith("見送りの境目（-0.25）を 0.15 点下回っている")
    assert J.distance_text({}) == ""


def test_half_step_dependence_names_the_verdict_without_the_half_points():
    factors = {**_all(0.0), "valuation": _f(1.0), "growth": {**_f(0.5), "whole": 0.0}}  # mid +0.275
    assert J.horizon_score("mid", factors)["verdict"] == J.CONSIDER
    dep = J.half_step_dependence("mid", factors)
    assert dep["verdict"] == J.WATCH and dep["labels"] == ["成長性"] and dep["score"] == pytest.approx(0.2)
    assert J.half_step_text(dep) == "この判定は成長性の内訳による半点の加減に頼っている（半点を外すとウォッチ、点数 +0.20）"
    assert J.half_step_dependence("mid", {**factors, "growth": _f(0.0)}) is None
    assert J.half_step_text(None) == ""


def test_daily_trend_moves_name_the_trend():
    rows = [{"key": "trend_daily", "score": -1.0, "value": "下降トレンド（確度 中）"}]
    up = {"key": "trend_daily", "label": "株価のテクニカル（日足のトレンド）", "direction": "1段良くなれば", "verdict": "ウォッチ"}
    assert J.mover_text(up, rows) == "日足のトレンドが下降トレンドでなくなれば（今は「下降トレンド（確度 中）」）ウォッチ"
    rows = [{"key": "trend_daily", "score": 0.0, "value": "方向感のないもみ合い（確度 低）"}]
    down = {**up, "direction": "1段悪くなれば", "verdict": "見送り"}
    assert J.mover_text(down, rows).startswith("日足のトレンドが下降トレンドに変われば")
