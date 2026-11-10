"""SEC EDGAR for US stocks: filing list and annual financials from XBRL companyfacts. Needs SEC_USER_AGENT.

Usage:
  edgar.py list  --ticker CBRS [--forms 10-K,10-Q,S-1,424B4,8-K] [--limit 40]   # filings with document URLs
  edgar.py facts --ticker CBRS [--company CBRS_cerebras] [--years 10]          # annual values; upsert data/financials.csv

facts reads the us-gaap annual (about 12-month) values of every filing (10-K, and S-1/424B4 before the
first 10-K) and the balance-sheet values at those fiscal year ends. A later filing wins for the same
(period_end, item). Amounts are stored in 百万ドル, EPS in ドル; summary.equity_ratio is computed
(StockholdersEquity / Assets) because US filings do not report it. Same columns and item names as
xbrl_financials.py, so render_tables.py and the analysis scripts read it unchanged.
Save the filing documents themselves with fetch.py (the URLs printed by `list`).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import CACHE_DIR, atomic_write_text, company_dir, http_get, utf8_stdout  # noqa: E402
from xbrl_financials import upsert  # noqa: E402

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
DEFAULT_FORMS = "10-K,10-K/A,10-Q,S-1,S-1/A,424B4,8-K,20-F,6-K"
USD_PER_MILLION = 1_000_000
ANNUAL_DAYS = (350, 380)  # a fiscal year of 52/53 weeks or 12 months
TICKER_CACHE_DAYS = 7

# item -> candidate us-gaap tags (first found per period wins). Items mirror xbrl_financials.py.
DURATION_ITEMS = {
    "summary.net_sales": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "cost_of_sales": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
    "sga": ["SellingGeneralAndAdministrativeExpense"],
    "research_and_development": ["ResearchAndDevelopmentExpense"],
    "operating_income": ["OperatingIncomeLoss"],
    "summary.net_income": ["NetIncomeLoss"],
    "summary.eps": ["EarningsPerShareBasic"],
    "summary.diluted_eps": ["EarningsPerShareDiluted"],
    "summary.cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "summary.cfi": ["NetCashProvidedByUsedInInvestingActivities"],
    "summary.cff": ["NetCashProvidedByUsedInFinancingActivities"],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    "capex_tangible": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "dividends_paid": ["PaymentsOfDividends", "PaymentsOfDividendsCommonStock"],
    "treasury_stock_purchase": ["PaymentsForRepurchaseOfCommonStock"],
    "gross_profit": ["GrossProfit"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "income_taxes": ["IncomeTaxExpenseBenefit"],
    "profit_before_tax": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "share_based_compensation": ["ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"],
    "lease_repayments": ["FinanceLeasePrincipalPayments"],
}
INSTANT_ITEMS = {
    "summary.total_assets": ["Assets"],
    "summary.net_assets": ["StockholdersEquity"],
    "liabilities": ["Liabilities"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "receivables": ["AccountsReceivableNetCurrent"],
    "inventories": ["InventoryNet"],
    "summary.cash_equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    # debt, leases and the EV items; the item names follow xbrl_financials.py so the analyses read both markets
    "short_term_loans": ["ShortTermBorrowings", "CommercialPaper"],
    "current_portion_long_term_loans": ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
    "long_term_loans": ["LongTermDebtNoncurrent", "LongTermDebtAndCapitalLeaseObligations"],
    "convertible_notes": ["ConvertibleNotesPayable", "ConvertibleDebtNoncurrent"],
    "lease_liabilities_current": ["OperatingLeaseLiabilityCurrent"],
    "lease_liabilities_noncurrent": ["OperatingLeaseLiabilityNoncurrent"],
    "finance_lease_liabilities": ["FinanceLeaseLiability"],
    "short_term_investments": ["ShortTermInvestments", "MarketableSecuritiesCurrent", "AvailableForSaleSecuritiesDebtSecuritiesCurrent"],
    "investment_securities": ["MarketableSecuritiesNoncurrent", "LongTermInvestments"],
    "non_controlling_interests": ["MinorityInterest"],
    "goodwill": ["Goodwill"],
    "intangible_assets": ["IntangibleAssetsNetExcludingGoodwill"],
    "shares_outstanding": ["CommonStockSharesOutstanding"],
}
# statement-level aliases that ff_metrics / tc_metrics read without the 'summary.' prefix
ALIASES = {"summary.net_sales": "net_sales"}


def _days(start: str, end: str) -> int:
    return (dt.date.fromisoformat(end) - dt.date.fromisoformat(start)).days


def _normalise(value: float, unit: str) -> tuple[str, str]:
    if unit == "USD":
        return f"{value / USD_PER_MILLION:.3f}".rstrip("0").rstrip("."), "百万ドル"
    if unit == "USD/shares":
        return f"{value:g}", "ドル"
    if unit == "shares":
        return f"{value:.0f}", "株"
    return f"{value:g}", unit


UNIT_ORDER = ("USD", "USD/shares", "shares")


def _facts_for(gaap: dict, tags: list[str]) -> list[tuple[str, dict]]:
    """(tag, fact) pairs of the first tag that has data, in unit order USD, USD/shares, shares."""
    for tag in tags:
        units = gaap.get(tag, {}).get("units", {})
        unit = next((u for u in UNIT_ORDER if units.get(u)), None)
        if unit:
            return [(tag, {**f, "_unit": unit}) for f in units[unit]]
    return []


def _latest(rows: list[tuple[str, dict]]) -> dict[str, tuple[str, dict]]:
    """end date -> (tag, fact) of the most recently filed fact."""
    best: dict[str, tuple[str, dict]] = {}
    for tag, fact in rows:
        end = fact["end"]
        if end not in best or fact.get("filed", "") > best[end][1].get("filed", ""):
            best[end] = (tag, fact)
    return best


def _row(item: str, end: str, tag: str, fact: dict) -> dict:
    value, unit = _normalise(float(fact["val"]), fact["_unit"])
    return {"doc_id": fact.get("accn", ""), "period_end": end, "item": item, "value": value, "unit": unit,
            "element": f"us-gaap:{tag}", "context": f"{fact.get('form', '')} filed {fact.get('filed', '')}"}


def annual_rows(companyfacts: dict, years: int = 10) -> list[dict]:
    gaap = companyfacts.get("facts", {}).get("us-gaap", {})
    out: list[dict] = []
    for item, tags in DURATION_ITEMS.items():
        annual = [(t, f) for t, f in _facts_for(gaap, tags)
                  if f.get("start") and ANNUAL_DAYS[0] <= _days(f["start"], f["end"]) <= ANNUAL_DAYS[1]]
        out += [_row(item, end, tag, fact) for end, (tag, fact) in _latest(annual).items()]
    fy_ends = sorted({r["period_end"] for r in out if r["item"] in ("summary.net_sales", "summary.net_income")})
    fy_ends = set(fy_ends[-years:])
    out = [r for r in out if r["period_end"] in fy_ends]
    for item, tags in INSTANT_ITEMS.items():
        instants = [(t, f) for t, f in _facts_for(gaap, tags) if not f.get("start") and f["end"] in fy_ends]
        out += [_row(item, end, tag, fact) for end, (tag, fact) in _latest(instants).items()]
    out += [{**r, "item": ALIASES[r["item"]]} for r in out if r["item"] in ALIASES]
    return out + equity_ratio_rows(out)


def equity_ratio_rows(rows: list[dict]) -> list[dict]:
    by_end: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_end.setdefault(r["period_end"], {})[r["item"]] = r
    out = []
    for end, items in by_end.items():
        equity, assets = items.get("summary.net_assets"), items.get("summary.total_assets")
        if equity and assets and float(assets["value"]):
            ratio = float(equity["value"]) / float(assets["value"]) * 100
            out.append({"doc_id": equity["doc_id"], "period_end": end, "item": "summary.equity_ratio",
                        "value": f"{ratio:.1f}", "unit": "%",
                        "element": "computed:StockholdersEquity/Assets", "context": equity["context"]})
    return out


def filing_rows(submissions: dict, forms: set[str], limit: int) -> list[dict]:
    recent = submissions.get("filings", {}).get("recent", {})
    cik = int(submissions.get("cik", 0))
    out = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in forms:
            continue
        acc = recent["accessionNumber"][i]
        base = ARCHIVE_URL.format(cik=cik, acc=acc.replace("-", ""))
        out.append({"form": form, "filed": recent["filingDate"][i], "report": recent.get("reportDate", [""])[i],
                    "accession": acc, "url": base + recent["primaryDocument"][i], "index": base})
        if len(out) >= limit:
            break
    return out


def lookup_cik(ticker: str) -> int:
    cache = CACHE_DIR / "edgar" / "company_tickers.json"
    fresh = cache.exists() and (dt.datetime.now().timestamp() - cache.stat().st_mtime) < TICKER_CACHE_DAYS * 86400
    if not fresh:
        atomic_write_text(cache, http_get(TICKERS_URL).text)
    for entry in json.loads(cache.read_text(encoding="utf-8")).values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return int(entry["cik_str"])
    raise SystemExit(f"ticker not found in {TICKERS_URL}: {ticker} (pass --cik)")


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("list", "facts"))
    ap.add_argument("--ticker")
    ap.add_argument("--cik", type=int)
    ap.add_argument("--forms", default=DEFAULT_FORMS)
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--company")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args()
    if not (args.cik or args.ticker):
        ap.error("--ticker or --cik is required")
    try:
        cik = args.cik or lookup_cik(args.ticker)
        if args.command == "list":
            subs = http_get(SUBMISSIONS_URL.format(cik=cik)).json()
            print(f"{subs.get('name', '')} CIK {cik:010d}\nform\tfiled\treport\taccession\turl")
            for r in filing_rows(subs, set(args.forms.split(",")), args.limit):
                print(f"{r['form']}\t{r['filed']}\t{r['report']}\t{r['accession']}\t{r['url']}")
            return
        rows = annual_rows(http_get(FACTS_URL.format(cik=cik)).json(), args.years)
    except RuntimeError as exc:  # SEC_USER_AGENT missing
        raise SystemExit(str(exc)) from exc
    for r in sorted(rows, key=lambda r: (r["item"], r["period_end"])):
        print(f"{r['period_end']}\t{r['item']}\t{r['value']}\t{r['unit']}\t{r['context']}")
    if args.company:
        if not rows:  # a header-only file would look like data to the analyses
            raise SystemExit("no annual values in companyfacts (no 10-K yet?): financials.csv not written; "
                             "copy the annual figures of the S-1/424B4 into raw instead")
        out = company_dir(args.company) / "data" / "financials.csv"
        upsert(out, rows)
        print(f"\nupserted {len(rows)} rows -> {out}")


if __name__ == "__main__":
    main()
