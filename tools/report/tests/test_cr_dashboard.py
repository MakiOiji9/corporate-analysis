import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
TOOLS = REPORT.parent
sys.path[:0] = [str(REPORT), str(TOOLS / "analysis"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import charts as C  # noqa: E402
import cr_dashboard as DB  # noqa: E402


def _analysis(key: str, verdict: str | None, label: str = "x", step: str = "2-1", detail: dict | None = None) -> dict:
    return {"key": key, "label": label, "step": step, "verdict": verdict, "detail": detail or {}}


def _facts(**over) -> dict:
    analyses = {k: _analysis(k, v) for k, v in (
        ("five_forces", "中"), ("three_c", "あいまい"), ("moat", "なし"), ("swot", "No"), ("profitability", "良好"),
        ("growth", "普通"), ("safety", "良好"), ("cash_flow", "判定保留"), ("valuation", "妥当"))}
    analyses["valuation"]["detail"] = {"flip_values": {"per_cheap": 3500.0, "per_rich": 4600.0, "pbr_cheap": 4360.0,
                                                       "pbr_fair": 5450.0, "pbr_rich": 6540.0},
                                       "peg_standard": 2.5, "per_forecast": 28.0}
    facts = {"analyses": analyses, "price": {"value": 3773.0, "currency": "円", "date": "2026-11-10"},
             "prices": {"ranges": [{"label": "52週", "low": 3000.0, "high": 5000.0}]}}
    facts.update(over)
    return facts


# ---------------------------------------------------------------- the nine analyses at a glance

def test_strip_colours_each_analysis_by_its_verdict():
    html = DB.analysis_strip(_facts())
    assert html.count('class="cell ') == 9
    assert 'class="cell v-consider"' in html and 'class="cell v-pass"' in html and 'class="cell v-pending"' in html
    assert "モート" in html and "判定保留" in html and 'href="#step2"' in html


def test_tone_of_verdict_words():
    assert DB.tone("良好") == "v-consider" and DB.tone("普通") == "v-watch" and DB.tone("No") == "v-pass"
    assert DB.tone("判定保留") == "v-pending" and DB.tone(None) == "v-pending"


# ---------------------------------------------------------------- fair value range (football field)

def test_fair_rows_come_from_the_flip_prices_and_the_52_week_range():
    rows = DB.fair_rows(_facts())
    labels = [r["label"] for r in rows]
    assert labels[0].startswith("PER") and labels[1].startswith("PBR") and labels[2].startswith("PEG")
    assert labels[-1].startswith("52週")
    pbr = rows[1]
    assert (pbr["low"], pbr["mid"], pbr["high"]) == (4360.0, 5450.0, 6540.0)
    peg = rows[2]  # PEG 1x and 2x: price / PEG and 2 × price / PEG
    assert peg["low"] == pytest.approx(3773 / 2.5) and peg["high"] == pytest.approx(2 * 3773 / 2.5)


def test_fair_band_is_the_median_of_the_valuation_rows():
    band = DB.fair_band(DB.fair_rows(_facts()), 3773.0)
    assert band["low"] == pytest.approx(3500.0) and band["high"] == pytest.approx(4600.0)
    assert band["position"] == "帯の中"


def test_fair_rows_drop_bands_below_zero_or_reversed():
    facts = _facts()
    facts["analyses"]["valuation"]["detail"]["flip_values"].update(per_cheap=-500.0, pbr_cheap=7000.0)
    assert [r["label"] for r in DB.fair_rows(facts)] == ["PEG（1倍〜2倍）", "52週の安値〜高値"]


def test_fair_rows_skip_missing_values():
    facts = _facts()
    facts["analyses"]["valuation"]["detail"] = {"flip_values": {}, "peg_standard": None}
    assert [r["label"] for r in DB.fair_rows(facts)] == ["52週の安値〜高値"]
    assert DB.fair_band(DB.fair_rows(facts), 3773.0) is None


def test_range_chart_draws_a_band_per_row_and_the_current_price():
    rows = DB.fair_rows(_facts())
    svg = C.range_chart(rows, 3773.0, "適正株価の目安")
    assert svg.startswith("<svg") and svg.count('class="rng') == len(rows)
    assert 'class="now"' in svg and "3,773" in svg
    assert C.range_chart([], 3773.0, "x") == C.EMPTY


# ---------------------------------------------------------------- key figures

def test_key_figures_skip_unknown_values():
    facts = _facts()
    facts["analyses"]["profitability"]["detail"] = {"roe_average": 12.7, "margin": {"self": 8.7}}
    facts["analyses"]["safety"]["detail"] = {"items": [{"name": "自己資本比率", "value": 59.5}]}
    facts["analyses"]["growth"]["detail"] = {"cagr": {"sales": None}}
    tiles = DB.key_figures(facts)
    names = [t["name"] for t in tiles]
    assert names == ["ROE（平均）", "営業利益率", "自己資本比率", "予想PER"]
    assert tiles[0]["value"] == "12.7%" and tiles[-1]["value"] == "28.0倍"
