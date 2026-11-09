import copy
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_legends as L  # noqa: E402


def _analysis(verdict, detail=None):
    return {"verdict": verdict, "detail": detail or {}}


def _facts(**over):
    """A company shaped like 6506 安川電機 on 2026-11-01 (moat なし, growth 懸念, price far below its high)."""
    facts = {
        "analyses": {
            "five_forces": _analysis("中", {"factors": [{"name": "新規参入の脅威", "rating": "中"}]}),
            "three_c": _analysis("あいまい"),
            "moat": _analysis("なし", {"risks": [{"factor": "中国の国産サーボの台頭", "timing": "5年以内"}]}),
            "swot": _analysis("No", {"quadrants": {"O": [{"id": "O1", "impact": "大"}, {"id": "O3", "impact": "不明"}]}}),
            "profitability": _analysis("普通", {"roe_average": 12.7, "source": "本業由来"}),
            "growth": _analysis("懸念", {"plan": "割り引いて扱う", "progress": {"quarter": 2, "items": {
                "sales": {"yoy": 9.8},
                "operating_income": {"progress": 38.4, "prior_progress": 49.3}}}}),
            "safety": _analysis("良好"),
            "cash_flow": _analysis("普通", {"ratio": 0.9, "rows": [{"fcf": 10}, {"fcf": 20}]}),
            "valuation": _analysis("妥当", {"items": {"PER": {"rating": "割高"}}}),
        },
        "step2": {"flags": []},
        "step3": {"verdict": "妥当"},
        "prices": {"ranges": [{"label": "52週", "position": 7.5, "from_high": -49.6},
                              {"label": "5年", "position": 26.4}, {"label": "10年", "position": 38.4}],
                   "averages": [{"label": "26週", "gap": -28.4}]},
        "outlook": {"overall": "警戒", "rows": {"長期": {"judgment": "平常"}}},
    }
    for path, value in over.items():
        target = facts
        keys = path.split("__")
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value
    return facts


def _verdicts(facts):
    return {k: v["verdict"] for k, v in L.evaluate(facts).items()}


def test_yaskawa_like_company_splits_the_three_views():
    assert _verdicts(_facts()) == {"buffett": L.AVOID, "soros": L.HOLD, "rogers": L.PREFER}


def test_buffett_prefers_a_wide_moat_at_a_fair_price_and_holds_when_expensive():
    good = {"analyses__moat": _analysis("広い", {"risks": []}), "analyses__three_c": _analysis("明確"),
            "analyses__profitability": _analysis("良好", {"roe_average": 18.0, "source": "本業由来"}),
            "analyses__cash_flow": _analysis("良好"), "analyses__growth": _analysis("良好")}
    assert L.buffett(_facts(**good))["verdict"] == L.PREFER
    expensive = L.buffett(_facts(**good, step3={"verdict": "割高"}))
    assert expensive["verdict"] == L.HOLD and "安全域" in expensive["why"]
    borrowed = L.buffett(_facts(**{**good, "analyses__profitability": _analysis("良好", {"source": "借入依存"})}))
    assert borrowed["verdict"] == L.HOLD  # ROE that leans on debt does not count


def test_buffett_avoids_a_red_flag_even_when_cheap():
    out = L.buffett(_facts(**{"analyses__moat": _analysis("広い"), "step2": {"flags": ["FCF の累計がマイナス"]},
                              "step3": {"verdict": "割安"}}))
    assert out["verdict"] == L.AVOID and "赤信号" in out["why"]


def test_buffett_pending_moat_is_material_shortage_not_avoid():
    out = L.buffett(_facts(**{"analyses__moat": _analysis("判定保留")}))
    assert out["verdict"] == L.HOLD
    assert next(c for c in out["checks"] if c["id"] == "B2")["ok"] is None


def test_soros_avoids_high_expectations_with_a_falling_business():
    facts = _facts(step3={"verdict": "割高"})
    facts["analyses"]["growth"]["detail"]["progress"]["items"]["sales"]["yoy"] = -8.0
    assert L.soros(facts)["verdict"] == L.AVOID


def test_soros_prefers_a_rising_business_the_market_has_not_priced():
    facts = _facts(outlook={"overall": "注意", "rows": {}})
    facts["analyses"]["growth"]["detail"]["progress"]["items"]["operating_income"]["progress"] = 60.0
    assert L.soros(facts)["verdict"] == L.PREFER
    calm_but_alarmed = _facts(outlook={"overall": "警戒", "rows": {}})
    calm_but_alarmed["analyses"]["growth"]["detail"]["progress"]["items"]["operating_income"]["progress"] = 60.0
    assert L.soros(calm_but_alarmed)["verdict"] == L.HOLD  # 警戒 can start a reversal


def test_soros_without_quarterly_progress_is_hold():
    out = L.soros(_facts(analyses__growth=_analysis("懸念")))
    assert out["verdict"] == L.HOLD and "材料が無い" in out["why"]


def test_rogers_avoids_euphoria_and_value_traps():
    hot = _facts(prices={"ranges": [{"label": "52週", "position": 90.0, "from_high": -2.0}], "averages": []})
    assert L.rogers(hot)["verdict"] == L.AVOID
    trap = _facts()
    trap["analyses"]["swot"]["detail"]["quadrants"]["O"] = []
    trap["analyses"]["growth"]["detail"]["progress"]["items"]["sales"]["yoy"] = 1.0
    out = L.rogers(trap)
    assert out["verdict"] == L.AVOID and "安い理由" in out["why"]


def test_rogers_short_term_drop_is_not_long_cheapness():
    facts = _facts()
    facts["prices"]["ranges"][1]["position"] = 60.0  # 5年
    facts["prices"]["ranges"][2]["position"] = 70.0  # 10年: only the 52-week range is low
    assert L.rogers(facts)["verdict"] == L.HOLD


def test_rows_and_validate_follow_the_script():
    facts = _facts()
    facts["legends"] = L.evaluate(facts)
    table = L.rows(facts)
    assert table.splitlines()[0].startswith("| ウォーレン・バフェット（長期） | 避ける |")
    good = {k: f"{v['short']}{L.PHRASE}: {v['verdict']}。理由。" for k, v in facts["legends"].items()}
    assert L.validate(good, table, facts) == []
    bad = copy.deepcopy(good)
    bad["soros"] = "ソロスは買う。"
    issues = L.validate(bad, table.replace("避ける", "好む", 1), facts)
    assert len(issues) == 4  # the table, the phrase, the verdict word, the claim


def test_brief_lists_every_check_with_its_mark():
    facts = _facts()
    facts["legends"] = L.evaluate(facts)
    text = "\n".join(L.brief_lines(facts))
    assert "### ウォーレン・バフェット: 避ける" in text and "| B2 長く続く競争優位（モート） | なし | × |" in text
