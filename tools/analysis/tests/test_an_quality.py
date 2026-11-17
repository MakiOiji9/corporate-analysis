import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ANALYSIS)]

import an_quality as Q  # noqa: E402

YUHO = "2026-06-20_2026-03_yuho.md「事業の内容」p12"


def _item(conf: str | None, source: str = YUHO, rating: str = "強") -> dict:
    return {"confidence": conf, "source": source, "rating": rating}


@pytest.mark.parametrize("source, dated", [
    (YUHO, True), ("決算説明会資料 p.8", True), ("日経新聞 2025年3月", True), ("検索要約", False), ("", False),
    ("industry-overview.md の節「市場規模」", False), ("有価証券報告書p.12", True), ("決算短信p8", True),
])
def test_dated_sources(source, dated):
    assert Q.dated(source) is dated


def test_an_undated_primary_source_counts_as_reference():
    assert Q.effective("一次", "検索要約") == "参考" and Q.effective("一次", YUHO) == "一次"
    assert Q.effective("参考", YUHO) == "参考" and Q.effective(None, YUHO) is None


@pytest.mark.parametrize("items, level", [
    ([_item("一次")] * 4 + [_item("二次")], "高"),
    ([_item("一次")] * 2 + [_item("二次")] * 3, "中"),
    ([_item("参考")] * 3 + [_item("一次")], "低"),                       # mostly reference-only evidence
    ([_item("一次")] * 3 + [_item(None, "", "不明")] * 2, "低"),          # too many unknowns
    ([_item("一次", "検索要約")] * 4, "低"),                             # primary in name, but no date or page
    ([], "低"),
])
def test_confidence_levels(items, level):
    assert Q.confidence(items)["level"] == level


def test_confidence_explains_itself():
    result = Q.confidence([_item("一次")] * 3 + [_item(None, "", "不明")])
    assert result["why"] == "一次資料 3/3・参考 0・不明 1/4" and result["unknown"] == 1


def test_outdated_results_are_named_with_the_version():
    assert Q.outdated({"version": 2}, 3) == "判定の基準が新しくなった（版 2 → 3）。作り直す"
    assert Q.outdated({}, 3) == "判定の基準が新しくなった（版 1 → 3）。作り直す"
    assert Q.outdated({"version": 3}, 3) is None


def test_counter_argument_must_be_written():
    assert Q.counter_issue("") and Q.counter_issue("<!-- FILL:counter -->") and Q.counter_issue("なし")
    assert Q.counter_issue("ROIC は直近2年で資本コストを下回り、堀が細っている可能性がある。") is None
