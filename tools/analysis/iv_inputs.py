"""Pick the investment inputs out of a company's raw/ files (same mechanism as ff_inputs).

The numbers come from data/financials.csv and data/investments.json (iv_metrics); these sections carry what the
writer reads to name the investments, their themes and how they fit the plan and the industry's changes.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, collect_requests, gather, input_digests, raw_files,  # noqa: F401 (re-exported)
                       unavailable_items)
from ff_inputs import raw_seen as ff_raw_seen

SPECS = (
    Spec("capex", "有報: 従業員数・設備投資", "yuho", "設備投資", "collect-filings", False),
    Spec("rnd", "有報: 研究開発・特許・許認可", "yuho", "研究開発", "collect-filings", False),
    Spec("policy", "有報: 経営方針・中期経営計画", "yuho", "経営方針", "collect-filings", False),
    Spec("targets", "中期経営計画: 目標値", "mid-term-plan", "目標", "collect-ir", False),
    Spec("measures", "中期経営計画: 重点施策", "mid-term-plan", "重点施策", "collect-ir", False),
    Spec("mtp_result", "中期経営計画: 前回計画の達成状況", "mid-term-plan", "達成状況", "collect-ir", False),
    Spec("structural", "業界: 構造を変えうる要因", "industry-overview", "構造を変え", "collect-market", False),
    Spec("ma", "財務時系列: M&A・連結範囲の変更", "financials-historical", "M&A", "collect-filings", False),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result (with freshness.py "annual")
TRIGGER_KINDS = ("yuho", "mid-term-plan", "industry-overview")


def gather_investment(company) -> dict[str, Found]:
    return gather(company, SPECS)


def raw_seen(company) -> list[str]:
    return ff_raw_seen(company, TRIGGER_KINDS)
