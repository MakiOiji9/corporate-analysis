import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
TOOLS = REPORT.parent
sys.path[:0] = [str(REPORT), str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import cr_strategy as ST  # noqa: E402


def _h(verdict: str, score: float, movers: list | None = None) -> dict:
    return {"verdict": verdict, "score": score, "rows": [], "knockout": [], "cautions": [],
            "sensitivity": {"movers": movers or []}}


def _facts(long: str = "投資検討", score: float = 0.4, price: float = 3773.0, **over) -> dict:
    analyses = {k: {"verdict": "普通", "detail": {}} for k in (
        "five_forces", "three_c", "moat", "swot", "profitability", "growth", "safety", "cash_flow", "valuation")}
    analyses["valuation"]["detail"] = {"flip_values": {"per_cheap": 3500.0, "per_rich": 4600.0, "pbr_cheap": 4360.0,
                                                       "pbr_fair": 5450.0, "pbr_rich": 6540.0},
                                       "eps_used": 135.88, "pbr_fair": {"average_per": 29.762},
                                       "peg_cases": {"standard": 10.8, "pessimistic": 5.4, "optimistic": 34.76}}
    facts = {"analyses": analyses, "price": {"value": price, "currency": "円"},
             "prices": {"ranges": [], "technicals": {"ok": True, "current": price, "levels": {
                 "supports": [{"label": "直近の安値", "price": 3600.0}, {"label": "52週安値", "price": 3351.0}],
                 "resistances": [{"label": "直近の高値", "price": 5018.0}], "stop": {"price": 3400.0}, "atr": 60.0}}},
             "horizons": {"short": _h("ウォッチ", 0.0), "mid": _h("ウォッチ", 0.1), "long": _h(long, score)},
             "step1": {"grade": "B"}, "step2": {"grade": "A", "flags": [], "cautions": []},
             "moves": {"split": {"beta": 1.0}}, "review": "2027-02-10 本決算",
             "outlook": {"rows": {"短期": {"watch": "日銀会合（12-18）"}, "中期": {"watch": "春闘"}}},
             "legends": {"buffett": {"name": "ウォーレン・バフェット", "verdict": "好む"},
                         "soros": {"name": "ジョージ・ソロス", "verdict": "避ける"},
                         "rogers": {"name": "ジム・ロジャーズ", "verdict": "保留"}}}
    facts.update(over)
    return facts


# ---------------------------------------------------------------- three scenario prices

def test_scenarios_bear_base_bull_from_the_price_band():
    s = ST.scenarios(_facts(price=4500.0))
    assert [r["name"] for r in s["rows"]] == ["弱気", "基本", "強気"]
    bear, base, bull = (r["price"] for r in s["rows"])
    assert bear == pytest.approx(3930.0) and bull == pytest.approx(5570.0)  # medians of the two bands' edges
    assert bear < base < bull and s["rows"][1]["change"] == pytest.approx((base / 4500 - 1) * 100)
    reading = s["rows"][1]["reading"]
    assert reading.startswith("指標ごとの帯の中央の中央値（") and f"→ {base:,.0f}）" in reading
    assert "適正" not in reading


def test_bear_stays_below_the_price_when_the_price_is_already_under_the_band():
    s = ST.scenarios(_facts(price=3000.0))  # stop 3,400 and 52-week low are above; 10% down is 2,700
    bear = s["rows"][0]
    assert bear["price"] == pytest.approx(2700.0) and bear["change"] < 0 and "さらに下" in bear["reading"]


def test_scenarios_need_a_valuation_band():
    facts = _facts()
    facts["analyses"]["valuation"]["detail"] = {}
    assert ST.scenarios(facts) is None


# ---------------------------------------------------------------- action matrix

@pytest.mark.parametrize("long, price, stance", [
    ("投資検討", 3000.0, "分割で買い始める"),
    ("投資検討", 4500.0, "押し目を待って分割で買う"),
    ("投資検討", 7000.0, "下がるのを待つ"),
    ("ウォッチ", 3000.0, "条件がそろうのを待つ"),
    ("ウォッチ", 4500.0, "価格と条件の両方を待つ"),
    ("見送り", 3000.0, "今は買わない"),
])
def test_action_follows_the_verdict_and_the_price_position(long, price, stance):
    assert ST.action(_facts(long=long, price=price))["stance"] == stance


def test_buying_in_three_parts_lists_three_prices():
    steps = ST.action(_facts(price=4500.0))["steps"]
    assert len(steps) == 3 and all("円" in s for s in steps) and "3,600" in steps[1]


def test_watch_lists_price_alerts_and_movers():
    mover = {"key": "growth", "label": "成長性", "direction": "1段良くなれば", "verdict": "投資検討", "to": 1.0}
    facts = _facts(long="ウォッチ", price=4500.0)
    facts["horizons"]["long"] = _h("ウォッチ", 0.1, [mover])
    alerts = ST.action(facts)["alerts"]
    assert any("以下になれば" in a for a in alerts) and any("成長性" in a for a in alerts)


# ---------------------------------------------------------------- sizing (a conditional guide, 3 levels)

def test_sizing_levels():
    assert ST.sizing(_facts())["level"] == "中"                    # 投資検討 + STEP 2 A
    strong = _facts(step1={"grade": "A"})
    assert ST.sizing(strong)["level"] == "大"
    assert ST.sizing(_facts(long="見送り", score=-0.4))["level"] == "0"


def test_sizing_steps_down_on_high_volatility():
    wild = _facts(moves={"split": {"beta": 1.9}})
    assert ST.sizing(wild)["level"] == "小" and any("値動き" in w for w in ST.sizing(wild)["why"])


def test_sizing_is_zero_with_a_red_flag():
    flagged = _facts(step2={"grade": "C", "flags": ["FCF の累計がマイナス"], "cautions": []})
    assert ST.sizing(flagged)["level"] == "0"


# ---------------------------------------------------------------- plans by horizon

SCENARIOS = {"ok": True, "buys": [{"basis": "今の株価", "price": 3773.0}, {"basis": "直近の安値", "price": 3600.0}],
             "holder": {"take": [{"label": "直近の高値", "price": 5018.0}],
                        "exit": [{"label": "損切りの目安（直近の安値の下）", "price": 3400.0}]}}


def test_short_plan_uses_the_chart_prices_of_the_scenarios():
    facts = _facts(scenarios=SCENARIOS)
    facts["horizons"]["short"] = _h("投資検討", 0.3)
    p = ST.short_plan(facts)
    assert p["verdict"] == "投資検討" and "押し目" in p["stance"]
    assert "3,600" in p["entries"][1] and "5,018" in p["exits"][0] and "3,400" in p["exits"][1]


def test_short_plan_falls_back_to_the_raw_lines_and_lists_no_entries_when_passed():
    facts = _facts()
    facts["horizons"]["short"] = _h("見送り", -0.4)
    p = ST.short_plan(facts)
    assert p["entries"] == [] and p["stance"] == "短期では手を出さない"
    assert "5,018" in p["exits"][0] and "3,400" in p["exits"][1]


@pytest.mark.parametrize("mid, price, stance", [
    ("投資検討", 3000.0, "指標の割安側にあり、買いを考えられる"),
    ("投資検討", 4500.0, "目安の帯の下側まで下がるのを待って買う"),
    ("ウォッチ", 4500.0, "次の決算の進み具合と株価の位置を確かめてから考える"),
    ("見送り", 4500.0, "今は買わない"),
])
def test_mid_plan_follows_the_mid_verdict_and_the_band(mid, price, stance):
    facts = _facts(price=price)
    facts["horizons"]["mid"] = _h(mid, 0.0)
    p = ST.mid_plan(facts)
    assert p["stance"] == stance and "90%" in p["exits"][-1]
    assert "5,570" in p["exits"][0]  # take profit at the band's high edge


def test_long_plan_sells_at_the_projected_levels():
    p = ST.long_plan(_facts())
    assert p["projection"]["ok"] and len(p["entries"]) == 3
    assert "基本ケースの3年後の水準 5,50" in p["exits"][0] and "楽観ケースの5年後の水準 8,5" in p["exits"][1]
    assert "5.4%" in p["exits"][2] and "判断が崩れる条件" in p["exits"][-1] and p["notes"] == []


def test_long_plan_notes_a_price_already_above_the_base_level():
    p = ST.long_plan(_facts(price=6000.0))
    assert any("すでに基本ケース" in n for n in p["notes"])


def test_long_plan_without_a_projection_falls_back_to_the_band_and_says_why():
    facts = _facts()
    facts["analyses"]["valuation"]["detail"]["peg_cases"] = {"standard": 2.0, "pessimistic": 1.0, "optimistic": 2.0}
    p = ST.long_plan(facts)
    assert not p["projection"]["ok"] and "5,570" in p["exits"][0] and "出していない" in p["notes"][0]


# ---------------------------------------------------------------- monitors, catalysts, legends


def test_catalysts_include_the_next_results_and_the_market_calendar():
    items = ST.catalysts(_facts())
    assert items[0].startswith("2027-02-10") and any("日銀会合" in i for i in items)


def test_legend_actions_and_split():
    out = ST.legend_actions(_facts())
    assert set(out["actions"]) == {"buffett", "soros", "rogers"}
    assert "円" in out["actions"]["buffett"] and out["split"] == "好む 1・保留 1・避ける 1"


def test_html_has_every_part_and_no_recommendation_words():
    html = ST.html(_facts(), ["【悪化】営業利益率が2期続けて8%を下回る"])
    for part in ("期間別の行動計画", "今の行動の目安", "売り・見直しの目安", "3年後の水準", "5年後の水準",
                 "配分の目安", "見ておく項目", "近い予定"):
        assert part in html
    assert html.index("短期（〜3ヶ月）") < html.index("中期（6ヶ月〜1年）") < html.index("長期（3年以上）")
    assert "推奨" not in html.replace("推奨ではない", "")


def test_strategy_words_are_conditions_not_forecasts_or_advice():
    import cr_technicals as T
    import outlook as O
    html = ST.html(_facts(scenarios=SCENARIOS), []) + ST.action_card(_facts())
    assert not T.FORECAST.search(html) and not any(w in html for w in O.FORBIDDEN)


def test_action_card_shows_the_three_horizons():
    card = ST.action_card(_facts())
    assert all(f"{h}: " in card for h in ("短期", "中期", "長期"))
