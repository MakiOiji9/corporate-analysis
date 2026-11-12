"""Write raw/ir/{date}_financials-historical.md from data/*.csv so the agent does not copy tables by hand.

Usage:
  raw_financials.py --company <dir> [--date YYYY-MM-DD] [--years 10]

Chapters 1 (render_tables financials), 4 (forecasts), 5 (quarterly) and 8 (the safety rows: total assets, equity,
interest-bearing debt, cash and equivalents, current assets / liabilities, the three cash flows) are written from
data/financials.csv and data/tdnet_facts.csv. What needs reading the filings (chapters 2, 3, 6, 7, the sources,
a debt year with no loan / bond line, chapters 4 / 5 without tdnet_facts.csv) is left as <!-- FILL:... --> for
the agent (collect-filings), which then only Edits those parts. The chapter order and the guidance comments come
from .ai/templates/collect-company-info/raw/financials-historical.md.
An existing file of the same date is never overwritten (exists: true): a same-day rerun keeps the agent's text.
stdout is one JSON line. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
import render_tables as RT  # noqa: E402
from common import REPO_ROOT, atomic_write_text, utf8_stdout  # noqa: E402

TEMPLATE = Path(".ai") / "templates" / "collect-company-info" / "raw" / "financials-historical.md"
SECTION = re.compile(r"^## (\d+)\. ", re.M)
TITLE = re.compile(r"^#\s+(.+?)\s*$", re.M)
FILL_MARK = "<!-- FILL:"
YEAR_CELL = re.compile(r"(?<=\| )(\d{4})-(\d{2})(?= \|)")  # render_tables' '2026-03'; the analyses read '2026年3月期'
SAFETY_YEARS = 10
# (row label, items tried in order; the first present per year wins)
SAFETY_ROWS = (
    ("総資産", ("total_assets", "summary.total_assets")),
    ("流動資産", ("current_assets",)),
    ("流動負債", ("current_liabilities",)),
    ("営業CF", ("cfo", "summary.cfo")),
    ("投資CF", ("cfi", "summary.cfi")),
    ("財務CF", ("cff", "summary.cff")),
)
NET_ASSETS = ("net_assets", "summary.net_assets")
EQUITY_RATIO = ("summary.equity_ratio", "equity_ratio")
OWNERS_EQUITY_CTX = "CurrentYearInstant_ConsolidatedMember_ResultMember"
PRIOR_EQUITY_CTX = "PriorYearInstant_ConsolidatedMember_ResultMember"
CASH = ("cash_equivalents", "summary.cash_equivalents")
DEBT_PARTS = ("short_term_loans", "current_portion_long_term_loans", "long_term_loans", "bonds", "convertible_notes")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def _grid(rows: list[dict]) -> dict[str, dict[str, float]]:
    grid: dict[str, dict[str, float]] = defaultdict(dict)
    for r in rows:
        try:
            grid[r["item"]][r["period_end"]] = float(r["value"])
        except (TypeError, ValueError):
            continue
    return grid


def _first(grid: dict, items: tuple[str, ...], period: str) -> float | None:
    return next((grid[i][period] for i in items if period in grid.get(i, {})), None)


def _cell(value: float | None) -> str:
    return "—" if value is None else RT._fmt(str(value))


def owners_equity(tdnet: list[dict]) -> dict[str, float]:
    """{fiscal year end: 自己資本} from the earnings releases (the consolidated year-end OwnersEquity). A year's own
    release wins; the next year's release (its prior-year column) fills a year whose release is not collected."""
    own, prior = {}, {}
    for r in tdnet:
        if r["element"] != "OwnersEquity" or r["context"] not in (OWNERS_EQUITY_CTX, PRIOR_EQUITY_CTX):
            continue
        try:
            value = float(r["value"])
        except (TypeError, ValueError):
            continue
        fy = r["fiscal_year_end"]
        if r["context"] == OWNERS_EQUITY_CTX:
            own[fy] = value
        elif fy[:4].isdigit():
            prior.setdefault(f"{int(fy[:4]) - 1}{fy[4:]}", value)
    return {**prior, **own}


def _equity(grid: dict, released: dict[str, float], period: str) -> float | None:
    """自己資本 as the safety analysis reads it: the release's OwnersEquity, else total assets × equity ratio
    (both exclude subscription rights and minority interests), else net assets − non-controlling interests."""
    if period in released:
        return released[period]
    assets, ratio = _first(grid, SAFETY_ROWS[0][1], period), _first(grid, EQUITY_RATIO, period)
    if assets is not None and ratio is not None:
        return round(assets * ratio / 100)
    net = _first(grid, NET_ASSETS, period)
    return None if net is None else net - grid.get("non_controlling_interests", {}).get(period, 0.0)


def safety_table(rows: list[dict], tdnet: list[dict] | None = None,
                 years: int = SAFETY_YEARS) -> tuple[str, list[str]]:
    """(chapter 8 table, the periods with no loan / bond line)."""
    grid = _grid(rows)
    released = owners_equity(tdnet or [])
    periods = sorted({r["period_end"] for r in rows})[-years:]
    unit = RT.money_unit(rows)
    no_debt: list[str] = []
    body = {label: [_cell(_first(grid, items, p)) for p in periods] for label, items in SAFETY_ROWS}
    equity, debt, cash = [], [], []
    for p in periods:
        equity.append(_cell(_equity(grid, released, p)))
        parts = [grid[i][p] for i in DEBT_PARTS if p in grid.get(i, {})]
        if not parts:
            no_debt.append(p[:7])
        debt.append(_cell(sum(parts)) if parts else "—")
        cash.append(_cell(_first(grid, CASH, p)))
    order = [("総資産", body["総資産"]), ("自己資本", equity), ("有利子負債", debt), ("現金及び現金同等物", cash),
             ("流動資産", body["流動資産"]), ("流動負債", body["流動負債"]),
             ("営業CF", body["営業CF"]), ("投資CF", body["投資CF"]), ("財務CF", body["財務CF"])]
    lines = [f"| 項目（{unit}） | " + " | ".join(p[:7] for p in periods) + " |", "|---|" + "---|" * len(periods)]
    lines += [f"| {label} | " + " | ".join(cells) + " |" for label, cells in order]
    lines.append("| 出典 | " + " | ".join("data/financials.csv" for _ in periods) + " |")
    return "\n".join(lines), no_debt


def _period_label(period_end: str) -> str:
    return f"{int(period_end[:4])}年{int(period_end[5:7])}月期"


def fiscal_years(table: str) -> str:
    """'| 2026-03 |' cells as '| 2026年3月期 |' (the year label the analysis scripts' table readers parse)."""
    return YEAR_CELL.sub(lambda m: _period_label(f"{m.group(1)}-{m.group(2)}"), table)


def _company_name(company: Path) -> str:
    overview = company / "overview.md"
    if overview.exists():
        m = TITLE.search(overview.read_text(encoding="utf-8"))
        if m and "{" not in m.group(1):
            return m.group(1)
    return company.name


def _sections(template: str) -> dict[int, str]:
    """{chapter number: its text from the heading to the next one} of the template."""
    marks = list(SECTION.finditer(template))
    return {int(m.group(1)): template[m.start():marks[i + 1].start() if i + 1 < len(marks) else len(template)]
            for i, m in enumerate(marks)}


def _with(section: str, body: str) -> str:
    return section.rstrip("\n") + "\n\n" + body.strip("\n") + "\n\n"


def _fill(key: str, what: str) -> str:
    return f"{FILL_MARK}{key} {what} -->"


def _header(company: Path, date: str, fin: list[dict], tdnet: list[dict], periods: list[str]) -> str:
    title = f"# 財務データ時系列（{_period_label(periods[0])}〜{_period_label(periods[-1])}） — {_company_name(company)}"
    source = "SEC EDGAR" if RT.money_unit(fin) == "百万ドル" else "EDINET XBRL"
    return "\n".join([
        title, "",
        "<!-- 1・4・5・8章の表は tools/collect/raw_financials.py が data/*.csv から記入済み。表は手で直さず、"
        "FILL の欄だけを書く（書いたら FILL のコメントは消す） -->", "",
        f"**収集日**: {date}",
        "**情報源**:",
        f"- data/financials.csv（{source}）— 確度: 一次",
        *(["- data/tdnet_facts.csv（決算短信 iXBRL）— 確度: 一次"] if tdnet else []),
        _fill("sources", "2・3・6・7章で使った資料（資料名・URL・ページ・確度）を1行ずつ"),
        "**原本**: " + _fill("originals", "使った有報・短信の原本（sources/YYYY-MM-DD/...）。無ければ「なし」"), "",
        "> 確度の定義: 一次＝会社・取引所・官公庁の原本 / 二次＝IRBANK・株探・EDINET DB 等の転載・集計 / "
        "検索要約＝Web検索結果の要約のみで原本未確認",
        f"> 単位: {RT.money_unit(fin)}（data/financials.csv）。1株指標は有報「主要な経営指標等の推移」の値（株式分割考慮後）。", "",
    ])


def build(company: Path, date: str, years: int, template: str) -> tuple[str, dict]:
    data = company / "data"
    fin = RT._read(data / "financials.csv")
    tdnet_path = data / "tdnet_facts.csv"
    tdnet = RT._read(tdnet_path) if tdnet_path.exists() else []
    periods = sorted({r["period_end"] for r in fin})[-years:]
    safety, no_debt = safety_table(fin, tdnet)
    if no_debt:
        safety += "\n\n" + _fill("debt", f"有利子負債が「—」の年（{'・'.join(no_debt)}）は有報の借入金等明細表・"
                                 "貸借対照表で確かめ、借入・社債が無ければ「0（科目なし）」、あれば合計を表に書く。根拠を年ごとに表の下へ")
    else:
        safety += "\n\n" + _fill("debt", "有利子負債の根拠（有報の借入金等明細表など）を年ごとに1行。リース債務を含めた場合はその旨")
    bodies = {
        1: RT.financials_table(fin, years),
        2: _fill("supplement", "EDINET/有報で取れなかった年があれば上の表に1行ずつ。無ければ「— | 該当なし | — | — | —」"),
        3: _fill("returns", "年度ごとの株主還元を上の表に（1株配当・配当総額・配当性向・自社株買い・出典）"),
        4: RT.forecasts_table(tdnet) if tdnet else _fill("forecasts", "短信 iXBRL が無い。上のコメントに従って会社計画と実績の表を書く"),
        5: RT.quarterly_table(tdnet) if tdnet else _fill("quarterly", "短信 iXBRL が無い。上の表の空欄を最新の四半期累計で埋める"),
        6: _fill("declines", "上のコメントに従い、減収・減益の年ごとに会社の説明を1行"),
        7: _fill("mna", "上のコメントに従い、連結範囲が広がった年ごとに1行"),
        8: safety,
    }
    sections = _sections(template)
    out = _header(company, date, fin, tdnet, periods) + "\n" + "".join(
        _with(sections[n], fiscal_years(bodies.get(n, ""))) for n in sorted(sections))
    info = {"periods": [periods[0][:7], periods[-1][:7]], "tdnet": bool(tdnet), "debt_unknown": no_debt}
    return out.rstrip("\n") + "\n", info


def main(argv: list[str] | None = None, root: Path = REPO_ROOT) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", required=True, help="企業ディレクトリ名（companies/ の下）")
    ap.add_argument("--date", help="YYYY-MM-DD（今日の代わり）")
    ap.add_argument("--years", type=int, default=10)
    args = ap.parse_args(argv)
    date = args.date or dt.date.today().isoformat()
    company = root / "companies" / Path(args.company).name
    target = company / "raw" / "ir" / f"{date}_financials-historical.md"
    rel = target.relative_to(root).as_posix()
    if target.exists():
        return emit({"ok": True, "exists": True, "path": rel})
    if not (company / "data" / "financials.csv").exists():
        return emit({"ok": False, "error": f"{company.name}/data/financials.csv が無い。先に xbrl_financials.py "
                                           "（米国株は edgar.py facts）を実行する"})
    text, info = build(company, date, args.years, (root / TEMPLATE).read_text(encoding="utf-8"))
    atomic_write_text(target, text)
    return emit({"ok": True, "exists": False, "path": rel, "fill": text.count(FILL_MARK), **info})


if __name__ == "__main__":
    sys.exit(main())
