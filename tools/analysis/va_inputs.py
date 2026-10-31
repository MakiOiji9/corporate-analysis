"""Pick the valuation inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins); only the
list of inputs differs. The yearly numbers (net income, extraordinary items, operating income, depreciation,
debt, cash, EPS) are read by va_series through the series of the STEP 2 analyses, not only from these sections.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import raw_seen as ff_raw_seen

VALUATION_KIND = "valuation-data"
PEER_EBITDA_SECTION = "EV/EBITDA の材料"
PEER_EBITDA_UNAVAILABLE = "EV/EBITDA の材料"  # collect-peers-valuation reports what it could not get under this name

SPECS = (
    Spec("price", "株価データ 1章: 株価（確定終値と基準日）・時価総額・発行済株式数（自己株式を除く）", VALUATION_KIND,
         "株価・時価総額", "collect-peers-valuation", True),
    Spec("per_share", "株価データ 2章: EPS（実績・会社予想）・BPS", VALUATION_KIND, "EPS・BPS",
         "collect-peers-valuation", True),
    Spec("current", "株価データ 3章: 現在の株価指標", VALUATION_KIND, "現在の株価指標", "collect-peers-valuation", False),
    Spec("history", "株価データ 4章: PER・PBR の過去推移（年次の高値・安値、5年以上）", VALUATION_KIND, "過去推移",
         "collect-peers-valuation", True),
    Spec("analyst", "株価データ 5章: アナリスト予想", VALUATION_KIND, "アナリスト予想", "collect-peers-valuation", False),
    Spec("peer_valuation", "競合 6章: PER・PBR（自社と同じ基準日の株価・時価総額・PER・PBR）", "competitors", "PER・PBR",
         "collect-peers-valuation", True),
    Spec("peer_cagr", "競合 3章: 売上高の3年CAGR計算用データ", "competitors", "CAGR", "collect-peers-valuation", False),
    Spec("peer_roe", "競合: ROE・自己資本比率", "competitors", "ROE・自己資本比率", "collect-peers-valuation", False),
    Spec("peer_dupont", "競合: 収益性の分解", "competitors", "収益性の分解", "collect-peers-valuation", False),
    Spec("peer_safety", "競合 11章: 安全性の指標（有利子負債・現金及び現金同等物）", "competitors", "安全性の指標",
         "collect-peers-valuation", False),
    Spec("peer_ebitda", f"競合 12章「{PEER_EBITDA_SECTION}」: 自社と競合の直近期の営業利益・減価償却費（CF 計算書）",
         "competitors", PEER_EBITDA_SECTION, "collect-peers-valuation", False, (PEER_EBITDA_UNAVAILABLE,),
         thin_check=True),
    Spec("special", "有報: 特別利益・特別損失", "yuho", "特別利益", "collect-filings", False),
    Spec("policy", "有報: 経営方針・資本政策", "yuho", "経営方針", "collect-filings", False),
    Spec("capital", "中期経営計画: 資本政策・株主還元方針", "mid-term-plan", "資本政策", "collect-ir", False),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = (VALUATION_KIND, "competitors", "yuho", "financials-historical", "mid-term-plan")


def gather_valuation(company) -> dict[str, Found]:
    return gather(company, SPECS)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the valuation trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
