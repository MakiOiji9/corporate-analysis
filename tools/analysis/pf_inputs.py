"""Pick the profitability inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins); only the
list of inputs differs. The yearly series behind the numbers are read by pf_series from every table of the
financial raw files and data/*.csv, not only from these sections.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import newer_trigger_files as ff_newer_trigger_files
from ff_inputs import raw_seen as ff_raw_seen

PEER_DUPONT_UNAVAILABLE = "収益性の分解"  # collect-peers-valuation reports what it could not get under this name

SPECS = (
    Spec("self_pl", "財務時系列: 損益（5〜10年）", "financials-historical", "損益", "collect-filings", True),
    Spec("self_return", "財務時系列: 株主還元", "financials-historical", "株主還元", "collect-filings", False),
    Spec("summary", "有報: 主要な経営指標等の推移", "yuho", "主要な経営指標", "collect-filings", True),
    Spec("special", "有報: 特別利益・特別損失", "yuho", "特別利益", "collect-filings", False),
    Spec("policy", "有報: 経営方針・資本政策", "yuho", "経営方針", "collect-filings", False),
    Spec("targets", "中期経営計画: 目標値", "mid-term-plan", "目標", "collect-ir", False),
    Spec("capital", "中期経営計画: 資本政策・株主還元方針", "mid-term-plan", "資本政策", "collect-ir", False),
    Spec("peers", "競合: 売上高・営業利益の推移", "competitors", "売上高・営業利益", "collect-peers-valuation",
         True),
    Spec("peer_roe", "競合: ROE・自己資本比率", "competitors", "ROE・自己資本比率", "collect-peers-valuation",
         False),
    Spec("peer_dupont", "競合: 収益性の分解（当期純利益・総資産・自己資本、最大5年）", "competitors",
         "収益性の分解", "collect-peers-valuation", True, (PEER_DUPONT_UNAVAILABLE,), thin_check=True),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "financials-historical", "mid-term-plan", "competitors")


def gather_profitability(company) -> dict[str, Found]:
    return gather(company, SPECS)


def newer_trigger_files(company, since: str, used: tuple[str, ...] | list[str] = (),
                        seen: tuple[str, ...] | list[str] = ()) -> list[str]:
    """ff_inputs.newer_trigger_files with the profitability trigger kinds."""
    return ff_newer_trigger_files(company, since, used, TRIGGER_KINDS, seen)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the profitability trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
