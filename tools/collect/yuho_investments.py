"""What the company invested in, from every annual report's XBRL (EDINET 'XBRL->CSV' packages under sources/).

Usage:
  yuho_investments.py --company <dir>     # every own annual report (第三号様式) under sources/ -> data/investments.json

data/investments.json (one JSON, rewritten each run; read by the investment analysis, 投資の質):
  as_of                 the newest annual report's fiscal year end
  years                 one entry per annual report, oldest first:
    period_end, doc_id, filed
    texts               {key: {element, label, text, truncated}} of the text blocks below (HTML tags removed,
                        table cells joined with " | ", rows on their own line)
    segments            [{period_end, segment, metric, value, unit, element}] from the segment note, the current and
                        the prior year (a later report's restated prior year wins in `segments` at the top level)
  segments              the merged segment figures of every report [{period_end, segment, metric, value, unit,
                        element, doc_id}]
  missing               {key: [period_end, ...]} the reports where a text block was not found
  elements              {key: [element, ...]} the element names that matched (to check the names on real filings)

Text blocks (found by the label first, so a company extension with the standard label is taken too):
  capex_overview        設備投資等の概要（第3 設備の状況 1）
  major_facilities      主要な設備の状況（第3 2）
  planned_facilities    設備の新設、除却等の計画（第3 3）
  research_and_development  研究開発活動（第2）
  business_combinations 企業結合等関係（経理の状況の注記。連結を優先）
  shareholdings         株式の保有状況（第4。政策保有株）
Segment metrics: capex（有形固定資産及び無形固定資産の増加額）, depreciation, assets, revenue, profit.
Only what the reports state. The element names are unverified on real filings: `elements` and `missing` show what
matched. stdout is one JSON line.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
import xbrl_financials as XF  # noqa: E402
from common import atomic_write_text, company_dir, utf8_stdout  # noqa: E402

ANNUAL_FORM = "第三号様式"
MAX_TEXT = 20000  # characters kept per text block (the shareholding tables can be long)
# key -> (labels that identify the block, element local-name patterns as a fallback)
TEXT_BLOCKS = {
    "capex_overview": (("設備投資等の概要",), (r"^OverviewOfCapitalExpendituresEtc\w*TextBlock$",)),
    "major_facilities": (("主要な設備の状況",), (r"^MajorFacilities\w*TextBlock$",)),
    "planned_facilities": (("設備の新設、除却等の計画",), (r"^PlannedAdditionsRetirementsEtcOfFacilities\w*TextBlock$",)),
    "research_and_development": (("研究開発活動",), (r"^ResearchAndDevelopmentActivities\w*TextBlock$",)),
    "business_combinations": (("企業結合",), (r"BusinessCombination\w*TextBlock$",)),
    "shareholdings": (("株式の保有状況",), (r"^Shareholdings\w*TextBlock$",)),
}
# segment metric -> element local-name patterns, in priority order (first match wins for a segment and year)
SEGMENT_METRICS = {
    "capex": (r"^IncreaseInPropertyPlantAndEquipmentAndIntangibleAssets", r"CapitalExpenditure"),
    "depreciation": (r"^DepreciationAndAmortization", r"^Depreciation"),
    "assets": (r"^SegmentAssets", r"^AssetsIFRS$", r"^Assets$"),
    "revenue": (r"^RevenuesFromExternalCustomers", r"^NetSalesToExternalCustomers", r"^RevenueIFRS$", r"^NetSales$",
                r"^Revenue$", r"^OperatingRevenue1$"),
    "profit": (r"^SegmentProfitLoss", r"^ProfitLossOfReportableSegment", r"^OperatingProfitLossIFRS$",
               r"^OperatingIncome$"),
}
REL = {"CurrentYear": 0, "Prior1Year": 1}
# one member only (a company's own member carries '_' in its prefix: jpcrp030000-asr_E01741-000XxxMember)
SEGMENT_CONTEXT = re.compile(r"^(CurrentYear|Prior1Year)(Duration|Instant)_(.+Member)$")
SEGMENT_WORDS = ("Segment", "ReconcilingItems", "UnallocatedAmounts", "Elimination")
TAG = re.compile(r"<[^>]+>")
SPACES = re.compile(r"[ \t\u3000\xa0]+")


def _value(rows: list[XF.Row], element: str) -> str | None:
    hit = next((r.value for r in rows if r.element.endswith(":" + element) and r.value not in ("", "－", "-")), None)
    return hit.strip() if hit else None


def plain_text(value: str) -> str:
    """A text block's HTML as plain text: rows on their own line, cells joined with ' | '."""
    text = re.sub(r"(?i)</t[dh]>\s*", " | ", value)
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|li|h\d)>", "\n", text)
    text = html.unescape(TAG.sub("", text))
    lines = [SPACES.sub(" ", line).strip(" |") for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def _block(rows: list[XF.Row], labels: tuple[str, ...], patterns: tuple[str, ...]) -> XF.Row | None:
    blocks = [r for r in rows if r.element.endswith("TextBlock") and r.value.strip()]
    by_label = [r for r in blocks if any(w in r.label for w in labels)]
    by_name = [r for r in blocks if any(re.search(p, r.element.split(":")[-1]) for p in patterns)]
    found = by_label or by_name
    if not found:
        return None
    # the consolidated note before the parent's own (個別) one
    return sorted(found, key=lambda r: ("NonConsolidated" in r.element or "個別" in r.label or "NonConsolidated"
                                        in r.context))[0]


def texts(rows: list[XF.Row]) -> dict[str, dict]:
    out = {}
    for key, (labels, patterns) in TEXT_BLOCKS.items():
        row = _block(rows, labels, patterns)
        if row is None:
            continue
        text = plain_text(row.value)
        out[key] = {"element": row.element, "label": row.label, "text": text[:MAX_TEXT],
                    "truncated": len(text) > MAX_TEXT}
    return out


def _segment_name(member: str) -> str:
    """'jpcrp030000-asr_E01741-000MotionControlReportableSegmentMember' -> 'MotionControl'."""
    name = re.sub(r"^.*-\d{3}", "", member)
    name = re.sub(r"ReportableSegmentMember$|Member$", "", name)
    return name or member


def segments(rows: list[XF.Row], fy_end: str) -> list[dict]:
    found: dict[tuple[str, str, str], dict] = {}
    for r in rows:
        m = SEGMENT_CONTEXT.match(r.context)
        if (not m or r.unit != "JPY" or m.group(3).count("Member") != 1
                or not any(w in m.group(3) for w in SEGMENT_WORDS)):
            continue
        local = r.element.split(":")[-1]
        for metric, patterns in SEGMENT_METRICS.items():
            rank = next((i for i, p in enumerate(patterns) if re.search(p, local)), None)
            if rank is None:
                continue
            period = XF._shift_year(fy_end, REL[m.group(1)])
            key = (period, _segment_name(m.group(3)), metric)
            if key in found and found[key]["_rank"] <= rank:
                break
            value, unit = XF._normalise(r.value, r.unit)
            found[key] = {"period_end": period, "segment": key[1], "metric": metric, "value": value, "unit": unit,
                          "element": r.element, "_rank": rank}
            break
    return [{k: v for k, v in row.items() if k != "_rank"} for row in sorted(found.values(), key=lambda x: (
        x["period_end"], x["segment"], x["metric"]))]


def build(filings: list[tuple[str, list[XF.Row]]]) -> dict | None:
    """filings: [(doc_id, rows)] of the company's own reports, any order; None without an annual report."""
    annual = [(d, r) for d, r in filings if _value(r, "DocumentTypeDEI") == ANNUAL_FORM]
    if not annual:
        return None
    annual.sort(key=lambda f: (_value(f[1], "CurrentFiscalYearEndDateDEI") or "", f[0]))
    years, merged = [], {}
    missing: dict[str, list[str]] = {k: [] for k in TEXT_BLOCKS}
    elements: dict[str, list[str]] = {k: [] for k in TEXT_BLOCKS}
    for doc_id, rows in annual:
        fy_end = _value(rows, "CurrentFiscalYearEndDateDEI")
        found = texts(rows)
        segs = segments(rows, fy_end)
        for key in TEXT_BLOCKS:
            if key in found:
                if found[key]["element"] not in elements[key]:
                    elements[key].append(found[key]["element"])
            else:
                missing[key].append(fy_end)
        for s in segs:  # oldest report first: a later report's restated prior year wins
            merged[(s["period_end"], s["segment"], s["metric"])] = {**s, "doc_id": doc_id}
        years.append({"period_end": fy_end, "doc_id": doc_id, "filed": _value(rows, "FilingDateCoverPage") or fy_end,
                      "texts": found, "segments": segs})
    return {"as_of": years[-1]["period_end"], "years": years,
            "segments": [merged[k] for k in sorted(merged)],
            "missing": {k: v for k, v in missing.items() if v}, "elements": elements}


def main() -> None:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="企業ディレクトリ（companies/{ticker}_{name} またはその一部）")
    args = parser.parse_args()
    path = company_dir(args.company)
    ticker = path.name.split("_")[0]
    filings = []
    for source in XF.filing_sources(path / "sources"):
        rows = XF.load_rows(source)
        if XF.security_code(rows) == ticker.upper():
            filings.append((source.name.split("_")[0], rows))
    result = build(filings)
    if result is None:
        print(json.dumps({"ok": False, "error": "sources/ に自社の有価証券報告書（XBRL→CSV）が無い。"
                          "edinet.py fetch --kind csv で取得してから実行する"}, ensure_ascii=False))
        sys.exit(1)
    out = path / "data" / "investments.json"
    atomic_write_text(out, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"ok": True, "path": str(out), "as_of": result["as_of"], "years": len(result["years"]),
                      "segments": len({s["segment"] for s in result["segments"]}),
                      "missing": {k: len(v) for k, v in result["missing"].items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
