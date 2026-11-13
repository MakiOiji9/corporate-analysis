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
                                                       "pbr_fair": 5450.0, "pbr_rich": 6540.0}}
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


# ---------------------------------------------------------------- holders, monitors, catalysts, legends

def test_holder_guide_uses_the_band_and_the_stop():
    h = ST.holder(_facts())
    assert "3,930" in h["add"] and "5,570" in h["take"] and "3,400" in h["exit"]


def test_catalysts_include_the_next_results_and_the_market_calendar():
    items = ST.catalysts(_facts())
    assert items[0].startswith("2027-02-10") and any("日銀会合" in i for i in items)


def test_legend_actions_and_split():
    out = ST.legend_actions(_facts())
    assert set(out["actions"]) == {"buffett", "soros", "rogers"}
    assert "円" in out["actions"]["buffett"] and out["split"] == "好む 1・保留 1・避ける 1"


def test_html_has_every_part_and_no_recommendation_words():
    html = ST.html(_facts(), ["【悪化】営業利益率が2期続けて8%を下回る"])
    for part in ("3つのシナリオ", "今の行動の目安", "配分の目安", "保有している場合", "見ておく項目", "近い予定"):
        assert part in html
    assert "推奨" not in html.replace("推奨ではない", "")
