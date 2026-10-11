"""Extract key financials from an EDINET 'XBRL->CSV' package (edinet.py fetch --kind csv).

Usage:
  xbrl_financials.py <extracted_dir_or_zip> --company <dir> [--doc-id ID]   # upsert data/financials.csv
  xbrl_financials.py <extracted_dir_or_zip> --dump <regex>                  # inspect raw rows (element/label)

Reads the jpcrp*.csv (UTF-16, tab separated) of the main document. Extracts the
5-year 「主要な経営指標等の推移」(summary, split-adjusted as reported) and the
2-year consolidated statements. JPY is stored in 百万円, ratios in %.
Process filings oldest -> newest: a later filing overwrites the same (period_end, item).
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import company_dir, file_lock, read_csv_rows, utf8_stdout, write_csv_atomic  # noqa: E402

FIELDS = ["doc_id", "period_end", "item", "value", "unit", "element", "context"]
JPY_PER_MILLION = 1_000_000
RELATIVE_YEARS = {"CurrentYear": 0, "Prior1Year": 1, "Prior2Year": 2, "Prior3Year": 3, "Prior4Year": 4}

# item -> candidate element local names (first found wins). Summary items come from
# 主要な経営指標等の推移 (5 years); statement items from the consolidated statements (2 years).
SUMMARY_ITEMS = {
    "net_sales": ["NetSalesSummaryOfBusinessResults", "RevenueSummaryOfBusinessResults",
                  "OperatingRevenue1SummaryOfBusinessResults"],
    "ordinary_income": ["OrdinaryIncomeLossSummaryOfBusinessResults"],
    "net_income": ["ProfitLossAttributableToOwnersOfParentSummaryOfBusinessResults"],
    "net_assets": ["NetAssetsSummaryOfBusinessResults"],
    "total_assets": ["TotalAssetsSummaryOfBusinessResults"],
    "bps": ["NetAssetsPerShareSummaryOfBusinessResults"],
    "eps": ["BasicEarningsLossPerShareSummaryOfBusinessResults"],
    "diluted_eps": ["DilutedEarningsPerShareSummaryOfBusinessResults"],
    "equity_ratio": ["EquityToAssetRatioSummaryOfBusinessResults"],
    "roe": ["RateOfReturnOnEquitySummaryOfBusinessResults"],
    "per": ["PriceEarningsRatioSummaryOfBusinessResults"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivitiesSummaryOfBusinessResults"],
    "cfi": ["NetCashProvidedByUsedInInvestingActivitiesSummaryOfBusinessResults"],
    "cff": ["NetCashProvidedByUsedInFinancingActivitiesSummaryOfBusinessResults"],
    "cash_equivalents": ["CashAndCashEquivalentsSummaryOfBusinessResults"],
    "employees": ["NumberOfEmployees"],
}
NONCONSOLIDATED_SUMMARY_ITEMS = {  # reported only for the parent company
    "dps": ["DividendPaidPerShareSummaryOfBusinessResults"],
    "payout_ratio": ["PayoutRatioSummaryOfBusinessResults"],
    "issued_shares": ["TotalNumberOfIssuedSharesSummaryOfBusinessResults"],
}
STATEMENT_ITEMS = {
    "net_sales": ["NetSales", "Revenue", "OperatingRevenue1"],
    "cost_of_sales": ["CostOfSales"],
    "sga": ["SellingGeneralAndAdministrativeExpenses"],
    "operating_income": ["OperatingIncome"],
    "ordinary_income": ["OrdinaryIncome"],
    "extraordinary_income": ["ExtraordinaryIncome"],
    "extraordinary_loss": ["ExtraordinaryLoss"],
    "net_income": ["ProfitLossAttributableToOwnersOfParent"],
    "cash_and_deposits": ["CashAndDeposits"],
    "receivables": ["NotesAndAccountsReceivableTradeAndContractAssets",
                    "AccountsReceivableTradeAndContractAssets",
                    "NotesAndAccountsReceivableTrade", "AccountsReceivableTrade"],
    "inventories": ["Inventories"],
    "work_in_process": ["WorkInProcess"],
    "current_assets": ["CurrentAssets"],
    "total_assets": ["Assets"],
    "current_liabilities": ["CurrentLiabilities"],
    "liabilities": ["Liabilities"],
    "net_assets": ["NetAssets"],
    "short_term_loans": ["ShortTermLoansPayable", "ShortTermBorrowings"],
    "current_portion_long_term_loans": ["CurrentPortionOfLongTermLoansPayable"],
    "long_term_loans": ["LongTermLoansPayable", "LongTermBorrowings"],
    "bonds": ["BondsPayable"],
    "cfo": ["NetCashProvidedByUsedInOperatingActivities"],
    "cfi": ["NetCashProvidedByUsedInInvestmentActivities"],
    "cff": ["NetCashProvidedByUsedInFinancingActivities"],
    "depreciation": ["DepreciationAndAmortizationOpeCF"],
    "capex_tangible": ["PurchaseOfPropertyPlantAndEquipmentInvCF"],
    "capex_intangible": ["PurchaseOfIntangibleAssetsInvCF"],
    "acquisition_of_subsidiaries": [
        "PurchaseOfSharesOfSubsidiariesResultingInChangeInScopeOfConsolidationInvCF",
        "PurchaseOfInvestmentsInSubsidiariesResultingInChangeInScopeOfConsolidationInvCF"],
    "dividends_paid": ["CashDividendsPaidFinCF"],
    "treasury_stock_purchase": ["PurchaseOfTreasuryStockFinCF"],
    "cash_equivalents": ["CashAndCashEquivalents"],
}


@dataclass(frozen=True)
class Row:
    element: str
    label: str
    context: str
    unit: str
    value: str


def _read_csv_text(text: str) -> list[Row]:
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    header = next(reader, [])
    col = {name: i for i, name in enumerate(header)}
    need = ("要素ID", "項目名", "コンテキストID", "ユニットID", "値")
    if not all(k in col for k in need):
        return []
    return [Row(r[col["要素ID"]], r[col["項目名"]], r[col["コンテキストID"]],
                r[col["ユニットID"]], r[col["値"]]) for r in reader if len(r) >= len(header)]


def load_rows(source: Path) -> list[Row]:
    """Read the main jpcrp*.csv from an extracted dir or the zip itself."""
    def pick(names: list[str]) -> list[str]:
        main = [n for n in names if re.search(r"(^|/)jpcrp[^/]*\.csv$", n)]
        return main or [n for n in names if n.endswith(".csv")]

    if source.suffix == ".zip":
        with zipfile.ZipFile(source) as zf:
            names = pick(zf.namelist())
            return [row for n in names for row in _read_csv_text(zf.read(n).decode("utf-16"))]
    files = pick([p.as_posix() for p in source.rglob("*.csv")])
    return [row for f in files for row in _read_csv_text(Path(f).read_text(encoding="utf-16"))]


def fiscal_year_end(rows: list[Row]) -> str:
    for r in rows:
        if r.element.endswith("CurrentFiscalYearEndDateDEI"):
            return r.value
    raise SystemExit("CurrentFiscalYearEndDateDEI not found (is this an annual report CSV?)")


def _shift_year(date_iso: str, back: int) -> str:
    year, rest = date_iso[:4], date_iso[4:]
    return f"{int(year) - back}{rest}"


def _normalise(value: str, unit: str) -> tuple[str, str]:
    try:
        number = float(value)
    except ValueError:
        return value, unit
    if unit == "JPY":
        return f"{number / JPY_PER_MILLION:.3f}".rstrip("0").rstrip("."), "百万円"
    if unit.lower() == "pure":
        return f"{number * 100:.4f}".rstrip("0").rstrip("."), "%"
    if unit == "JPYPerShares":
        return value, "円"
    return value, unit


def _pick(rows: list[Row], candidates: list[str], context: str) -> Row | None:
    by_local = {}
    for r in rows:
        if r.context == context:
            by_local.setdefault(r.element.split(":")[-1], r)
    return next((by_local[c] for c in candidates if c in by_local), None)


def extract(rows: list[Row], doc_id: str) -> list[dict]:
    fy_end = fiscal_year_end(rows)
    out = []

    def add(item: str, row: Row | None, back: int) -> None:
        if row is None or row.value in ("", "－", "-"):
            return
        value, unit = _normalise(row.value, row.unit)
        out.append({"doc_id": doc_id, "period_end": _shift_year(fy_end, back), "item": item,
                    "value": value, "unit": unit, "element": row.element, "context": row.context})

    for rel, back in RELATIVE_YEARS.items():
        for kind in ("Duration", "Instant"):
            ctx = f"{rel}{kind}"
            for item, cands in SUMMARY_ITEMS.items():
                add(f"summary.{item}", _pick(rows, cands, ctx), back)
            for item, cands in NONCONSOLIDATED_SUMMARY_ITEMS.items():
                add(f"summary.{item}", _pick(rows, cands, f"{ctx}_NonConsolidatedMember"), back)
            if back <= 1:
                for item, cands in STATEMENT_ITEMS.items():
                    add(item, _pick(rows, cands, ctx), back)
    return out


def upsert(csv_path: Path, rows: list[dict]) -> None:
    """Replace rows with the same (period_end, item), keep others (process-safe)."""
    keys = {(r["period_end"], r["item"]) for r in rows}
    with file_lock(csv_path):
        kept = [r for r in read_csv_rows(csv_path) if (r["period_end"], r["item"]) not in keys]
        merged = sorted(kept + rows, key=lambda r: (r["item"], r["period_end"]))
        write_csv_atomic(csv_path, FIELDS, merged)


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--company")
    ap.add_argument("--doc-id", default="")
    ap.add_argument("--dump")
    args = ap.parse_args()

    source = Path(args.source)
    rows = load_rows(source)
    if args.dump:
        rx = re.compile(args.dump)
        for r in rows:
            if rx.search(r.element) or rx.search(r.label):
                print(f"{r.element}\t{r.label}\t{r.context}\t{r.unit}\t{r.value[:60]}")
        return
    doc_id = args.doc_id or source.name.split("_")[0].removesuffix(".zip")
    extracted = extract(rows, doc_id)
    for r in extracted:
        print(f"{r['period_end']}\t{r['item']}\t{r['value']}\t{r['unit']}")
    if args.company:
        out = company_dir(args.company) / "data" / "financials.csv"
        upsert(out, extracted)
        print(f"\nupserted {len(extracted)} rows -> {out}")


if __name__ == "__main__":
    main()
