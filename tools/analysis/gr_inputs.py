"""Pick the growth inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins); only the
list of inputs differs. The yearly series behind the numbers are read by gr_series from every table of the
financial raw files and data/*.csv, not only from these sections.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import raw_seen as ff_raw_seen

DECLINE_UNAVAILABLE = "減収・減益の説明"  # collect-filings reports what it could not get under these names
MA_UNAVAILABLE = "M&A"

SPECS = (
    Spec("self_pl", "財務時系列: 損益（5〜10年）", "financials-historical", "損益", "collect-filings", True),
    Spec("summary", "有報: 主要な経営指標等の推移", "yuho", "主要な経営指標", "collect-filings", True),
    Spec("plan", "財務時系列: 会社計画（期初予想）と実績", "financials-historical", "会社計画", "collect-filings",
         True),
    Spec("decline", "財務時系列: 減収・減益の年の会社説明", "financials-historical", "減収・減益", "collect-filings",
         False, (DECLINE_UNAVAILABLE,)),
    Spec("ma", "財務時系列: M&A・連結範囲の変更", "financials-historical", "M&A", "collect-filings", True,
         (MA_UNAVAILABLE,)),
    Spec("self_return", "財務時系列: 株主還元", "financials-historical", "株主還元", "collect-filings", False),
    Spec("segment", "有報: 事業の内容・セグメント情報", "yuho", "事業の内容", "collect-filings", False),
    Spec("risks", "有報: 事業等のリスク", "yuho", "事業等のリスク", "collect-filings", False),
    Spec("policy", "有報: 経営方針・中期経営計画", "yuho", "経営方針", "collect-filings", False),
    Spec("targets", "中期経営計画: 目標値", "mid-term-plan", "目標", "collect-ir", False),
    Spec("mtp_result", "中期経営計画: 前回計画の達成状況", "mid-term-plan", "達成状況", "collect-ir", False),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "financials-historical", "mid-term-plan")


def gather_growth(company) -> dict[str, Found]:
    return gather(company, SPECS)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the growth trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
