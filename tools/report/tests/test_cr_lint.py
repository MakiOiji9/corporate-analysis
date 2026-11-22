import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import cr_lint as LT  # noqa: E402


def _facts(target=488.0, resistance=488.0, scored="もみ合い（方向感なし）", daily="方向感のないもみ合い"):
    return {"scenarios": {"buys": [{"label": "今の株価", "target1": {"label": "以前の安値", "price": target}}]},
            "prices": {"technicals": {"state": scored,
                                      "levels": {"resistances": [{"label": "x", "price": resistance}]}}},
            "technical_analysis": {"daily": {"aspects": {"trend": {"state": daily}}}},
            "horizons": {}}


def test_take_profits_agree_or_are_warned():
    assert LT.take_profits(_facts()) == []
    assert "03章の売買シナリオは 488" in LT.take_profits(_facts(resistance=549.0))[0]
    fair = _facts(resistance=549.0)
    fair["scenarios"]["buys"][0]["target1"]["label"] = "適正PBR の株価"
    assert LT.take_profits(fair) == []  # a valuation target is not a chart line


def test_trend_readings_that_differ_are_named():
    assert LT.trend(_facts()) == []
    assert "下降トレンド" in LT.trend(_facts(daily="下降トレンド"))[0]


def test_verdict_words_catch_a_mover_that_names_another_word():
    rows = [{"key": "growth", "score": 0.0, "value": "懸念"}]  # a row whose score and word disagree
    mover = {"key": "growth", "label": "成長性", "direction": "1段良くなれば", "verdict": "投資検討", "to": 1.0}
    facts = {"horizons": {"long": {"rows": rows, "sensitivity": {"movers": [mover]}}}}
    assert "成長性の判定は「懸念」" in LT.verdict_words(facts)[0]
    rows[0]["value"] = "普通"
    assert LT.verdict_words(facts) == []


def test_wording_finds_internal_words_repeats_and_nested_brackets():
    page = ("<main><p>競合の特許件数: raw に無い。スクリプトの判定候補（中）と一致</p>"
            "<p>投資検討まであと +0.20 点、投資検討まであと +0.20 点</p>"
            "<p>懸念（利益の質（0.77倍））</p><p>判定ルールの改定 2</p></main>")
    found = LT.wording(page)
    assert any("raw" in x for x in found) and any("スクリプト" in x for x in found)
    assert any(x.startswith("同じ文の繰り返し") for x in found)
    assert any(x.startswith("2重の括弧が 1 か所") for x in found)
    assert not any("版N" in x for x in found)
    assert LT.wording("<main><p>普通（内訳から +0.5）。良好、良好</p></main>") == []
