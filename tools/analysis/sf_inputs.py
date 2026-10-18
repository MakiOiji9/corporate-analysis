"""Pick the safety inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins); only the
list of inputs differs. The yearly balance-sheet and cash-flow series are read by sf_series from every table of
the financial raw files and data/*.csv, not only from these sections.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import raw_seen as ff_raw_seen

PEER_SAFETY_UNAVAILABLE = "安全性の指標"  # collect-peers-valuation reports what it could not get under this name
PEER_SAFETY_SECTION = "安全性の指標"

SPECS = (
    Spec("self_bs", "財務時系列: 貸借（5〜10年）", "financials-historical", "貸借", "collect-filings", False),
    Spec("self_cf", "財務時系列: キャッシュ・フロー", "financials-historical", "キャッシュ", "collect-filings", False),
    Spec("self_return", "財務時系列: 株主還元", "financials-historical", "株主還元", "collect-filings", False),
    Spec("summary", "有報: 主要な経営指標等の推移", "yuho", "主要な経営指標", "collect-filings", False),
    Spec("statements", "有報: 財務3表", "yuho", "財務3表", "collect-filings", False),
    Spec("risks", "有報: 事業等のリスク", "yuho", "事業等のリスク", "collect-filings", False),
    Spec("policy", "有報: 経営方針・資本政策", "yuho", "経営方針", "collect-filings", False),
    Spec("capital", "中期経営計画: 資本政策・株主還元方針", "mid-term-plan", "資本政策", "collect-ir", False),
    Spec("peer_safety", "競合: 安全性の指標（総資産・自己資本・有利子負債・現金・流動資産・流動負債、最大5期）",
         "competitors", PEER_SAFETY_SECTION, "collect-peers-valuation", True, (PEER_SAFETY_UNAVAILABLE,),
         thin_check=True),
    Spec("peer_roe", "競合: ROE・自己資本比率", "competitors", "ROE・自己資本比率", "collect-peers-valuation",
         False),
    Spec("peer_dupont", "競合: 収益性の分解", "competitors", "収益性の分解", "collect-peers-valuation", False),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "financials-historical", "mid-term-plan", "competitors")


def gather_safety(company) -> dict[str, Found]:
    return gather(company, SPECS)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the safety trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
