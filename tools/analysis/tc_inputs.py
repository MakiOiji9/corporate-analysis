"""Pick the 3C inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins);
only the list of inputs differs. Headings come from .ai/templates/collect-company-info/raw/.
"""
from __future__ import annotations

from ff_inputs import Found, Spec, collect_requests, gather, raw_files  # noqa: F401  (re-exported)

SPECS = (
    Spec("segment", "有報: 事業の内容・セグメント情報", "yuho", "事業の内容", "collect-filings", True),
    Spec("customers", "有報: 主要な販売先", "yuho", "主要な販売先", "collect-filings", False),
    Spec("products", "事業概要: 主力製品・サービスと特徴", "business-overview", "主力製品", "collect-ir", True),
    Spec("customer_base", "事業概要: 顧客層", "business-overview", "顧客層", "collect-ir", True),
    Spec("kpi", "事業概要: 主要KPI", "business-overview", "主要KPI", "collect-ir", False),
    Spec("strategy", "事業概要: 成長戦略", "business-overview", "成長戦略", "collect-ir", False),
    Spec("market_size", "業界: 市場規模と成長率", "industry-overview", "市場規模", "collect-market", True),
    Spec("share", "業界: 上位企業とシェア", "industry-overview", "シェア", "collect-market", False, ("シェア",)),
    Spec("kbf", "業界: 購買決定要因", "industry-overview", "購買決定要因", "collect-market", True,
         ("購買決定要因",)),
    Spec("peer_selection", "競合: 選定した同業他社", "competitors", "選定", "collect-peers-valuation", True),
    Spec("peers", "競合: 売上高・営業利益の推移", "competitors", "売上高・営業利益", "collect-peers-valuation",
         True),
    Spec("peer_share", "競合: 市場シェア", "competitors", "市場シェア", "collect-peers-valuation", False,
         ("シェア",)),
    Spec("peer_claims", "競合: 主力製品と強み", "competitors", "強み", "collect-peers-valuation", True),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "business-overview", "industry-overview", "competitors")


def gather_3c(company) -> dict[str, Found]:
    return gather(company, SPECS)


def newer_trigger_files(company, since: str) -> list[str]:
    """Raw files of the trigger kinds collected after the analysis date."""
    return [company.rel(p) for kind in TRIGGER_KINDS for d, p in raw_files(company, kind) if d > since]
