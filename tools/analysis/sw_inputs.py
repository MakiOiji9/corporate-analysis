"""Pick the SWOT inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins);
only the list of inputs differs. Headings come from .ai/templates/collect-company-info/raw/.
The mid-term plan is read section by section because a company without a plan has its substitute
disclosure (方針・目標とする経営指標) under a heading of its own.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)

SPECS = (
    Spec("segment", "有報: 事業の内容・セグメント情報", "yuho", "事業の内容", "collect-filings", True),
    Spec("customers", "有報: 主要な販売先", "yuho", "主要な販売先", "collect-filings", False),
    Spec("risks", "有報: 事業等のリスク", "yuho", "事業等のリスク", "collect-filings", True),
    Spec("policy", "有報: 経営方針・中期経営計画・資本政策", "yuho", "経営方針", "collect-filings", False),
    Spec("mtp", "中計: 中期経営計画の有無・期間", "mid-term-plan", "中期経営計画の有無", "collect-ir", True),
    Spec("mtp_alt", "中計: 中期経営計画に代わる開示", "mid-term-plan", "代わる", "collect-ir", False),
    Spec("mtp_targets", "中計: 目標値", "mid-term-plan", "目標値", "collect-ir", False),
    Spec("mtp_actions", "中計: 重点施策", "mid-term-plan", "重点施策", "collect-ir", False),
    Spec("mtp_review", "中計: 前回計画の達成状況", "mid-term-plan", "達成状況", "collect-ir", False),
    Spec("strategy", "事業概要: 成長戦略", "business-overview", "成長戦略", "collect-ir", False),
    Spec("market_size", "業界: 市場規模と成長率", "industry-overview", "市場規模", "collect-market", True),
    Spec("substitutes", "業界: 代替手段", "industry-overview", "代替", "collect-market", False),
    Spec("structural", "業界: 構造を変えうる要因", "industry-overview", "構造を変え", "collect-market", True),
)
SPEC = {s.key: s for s in SPECS}


def gather_swot(company) -> dict[str, Found]:
    return gather(company, SPECS)
