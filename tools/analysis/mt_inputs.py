"""Pick the moat inputs out of a company's raw/ files (collect-company-info output).

Same mechanism as ff_inputs (one section of one raw kind per input, newest file with content wins);
only the list of inputs differs. Headings come from .ai/templates/collect-company-info/raw/.
"""
from __future__ import annotations

from ff_inputs import (Found, Spec, changed_input_files, collect_requests, gather, input_digests,  # noqa: F401
                       raw_files, unavailable_items)  # (re-exported)
from ff_inputs import newer_trigger_files as ff_newer_trigger_files
from ff_inputs import raw_seen as ff_raw_seen

SPECS = (
    Spec("self_financials", "財務時系列: 損益（5〜10年）", "financials-historical", "損益", "collect-filings", True),
    Spec("ip", "有報: 研究開発・特許・許認可", "yuho", "許認可", "collect-filings", True),
    Spec("risks", "有報: 事業等のリスク", "yuho", "事業等のリスク", "collect-filings", False),
    Spec("customer_base", "事業概要: 顧客層", "business-overview", "顧客層", "collect-ir", False),
    Spec("kpi", "事業概要: 主要KPI", "business-overview", "主要KPI", "collect-ir", False),
    Spec("retention", "事業概要: 継続率・解約率・ストック型売上の比率", "business-overview", "継続率", "collect-ir",
         True, ("解約率", "ストック型売上"), thin_check=True),  # not「継続率」: the peers' KPI rows use it too
    Spec("pricing", "事業概要: 値上げ・価格改定の実績", "business-overview", "価格改定", "collect-ir", True,
         ("価格改定", "値上げの実績"), thin_check=True),
    Spec("share", "業界: 上位企業とシェアの推移", "industry-overview", "シェア", "collect-market", True, ("シェア",)),
    Spec("industry_margin", "業界: 業界全体の利益率", "industry-overview", "利益率", "collect-market", False,
         ("利益率",)),
    Spec("structural", "業界: 構造を変えうる要因", "industry-overview", "構造を変え", "collect-market", True),
    Spec("peers", "競合: 売上高・営業利益の推移", "competitors", "売上高・営業利益", "collect-peers-valuation",
         True),
    Spec("peer_share", "競合: 市場シェア", "competitors", "市場シェア", "collect-peers-valuation", False,
         ("シェア",)),
    Spec("peer_cost", "競合: 売上原価率・販管費率（コスト構造）", "competitors", "コスト構造",
         "collect-peers-valuation", True, ("原価率", "販管費率", "コスト構造"), thin_check=True),
    Spec("peer_claims", "競合: 主力製品と強み", "competitors", "強み", "collect-peers-valuation", False, ("強み",)),
    Spec("peer_kpi", "競合: 顧客・人員の KPI と第三者評価", "competitors", "顧客・人員", "collect-peers-valuation",
         False, ("顧客・人員",)),
)
SPEC = {s.key: s for s in SPECS}
# a newer file of these kinds re-opens a valid result
TRIGGER_KINDS = ("yuho", "financials-historical", "business-overview", "industry-overview", "competitors")


def gather_moat(company) -> dict[str, Found]:
    return gather(company, SPECS)


def newer_trigger_files(company, since: str, used: tuple[str, ...] | list[str] = (),
                        seen: tuple[str, ...] | list[str] = ()) -> list[str]:
    """ff_inputs.newer_trigger_files with the moat trigger kinds."""
    return ff_newer_trigger_files(company, since, used, TRIGGER_KINDS, seen)


def raw_seen(company) -> list[str]:
    """ff_inputs.raw_seen with the moat trigger kinds."""
    return ff_raw_seen(company, TRIGGER_KINDS)
