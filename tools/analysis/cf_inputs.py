"""Pick the cash-flow inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins); only the
list of inputs differs. The yearly series behind the numbers are read by cf_series from every table of the
financial raw files and data/*.csv, not only from these sections; the sections here feed the brief (the notes
that explain the numbers) and the change detection.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import raw_seen as ff_raw_seen

SPECS = (
    Spec("cf_table", "財務時系列: 損益・貸借・CF", "financials-historical", "CF", "collect-filings", False),
    Spec("cf_section", "財務時系列: キャッシュ・フロー", "financials-historical", "キャッシュ", "collect-filings", False),
    Spec("self_return", "財務時系列: 株主還元", "financials-historical", "株主還元", "collect-filings", False),
    Spec("summary", "有報: 主要な経営指標等の推移", "yuho", "主要な経営指標", "collect-filings", True),
    Spec("statements", "有報: 財務3表", "yuho", "財務3表", "collect-filings", False),
    Spec("capex", "有報: 従業員数・設備投資", "yuho", "設備投資", "collect-filings", False),
    Spec("policy", "有報: 経営方針・資本政策", "yuho", "経営方針", "collect-filings", False),
    Spec("targets", "中期経営計画: 目標値", "mid-term-plan", "目標", "collect-ir", False),
    Spec("capital", "中期経営計画: 資本政策・株主還元方針", "mid-term-plan", "資本政策", "collect-ir", False),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "financials-historical", "mid-term-plan")


def gather_cash_flow(company) -> dict[str, Found]:
    return gather(company, SPECS)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the cash-flow trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
