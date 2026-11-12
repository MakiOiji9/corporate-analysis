import csv
import json
import shutil
import sys
from pathlib import Path

COLLECT = Path(__file__).resolve().parents[1]
REPO = COLLECT.parents[1]
sys.path[:0] = [str(COLLECT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "report"),
                str(COLLECT / "market")]

import an_common as A  # noqa: E402
import raw_financials as RF  # noqa: E402
import sf_series  # noqa: E402

DATE = "2026-11-12"
DIR = "1234_example"
YEARS = ("2024-03-31", "2025-03-31", "2026-03-31")
ITEMS = {  # item -> values per YEARS (百万円)
    "summary.net_sales": (1000, 1100, 1200), "operating_income": (100, 120, 130),
    "summary.net_income": (60, 70, 80), "summary.eps": (60, 70, 80),
    "total_assets": (2000, 2100, 2300), "net_assets": (1200, 1300, 1400), "non_controlling_interests": (20, 20, 30),
    "cash_equivalents": (500, 550, 600), "current_assets": (900, 950, 1000), "current_liabilities": (400, 420, 450),
    "cfo": (150, 160, 170), "cfi": (-50, -60, -70), "cff": (-30, -40, -50),
    "short_term_loans": (100, 0, 50),
}


def _repo(tmp_path: Path, with_debt: bool = True) -> Path:
    template = tmp_path / RF.TEMPLATE
    template.parent.mkdir(parents=True)
    shutil.copy(REPO / RF.TEMPLATE, template)
    company = tmp_path / "companies" / DIR
    (company / "data").mkdir(parents=True)
    (company / "overview.md").write_text("# 例示株式会社（1234）\n", encoding="utf-8")
    with (company / "data" / "financials.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["doc_id", "period_end", "item", "value", "unit", "element", "context"])
        for item, values in ITEMS.items():
            if item == "short_term_loans" and not with_debt:
                continue
            for year, value in zip(YEARS, values):
                w.writerow(["S100TEST", year, item, value, "百万円", "x", "CurrentYearInstant"])
    return tmp_path


def _run(root: Path, capsys) -> tuple[int, dict]:
    code = RF.main(["--company", DIR, "--date", DATE], root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_writes_tables_and_leaves_fill_only_for_judgement(tmp_path, capsys):
    root = _repo(tmp_path)
    code, out = _run(root, capsys)
    text = (root / out["path"]).read_text(encoding="utf-8")
    assert code == 0 and out["path"] == f"companies/{DIR}/raw/ir/{DATE}_financials-historical.md"
    assert text.startswith("# 財務データ時系列（2024年3月期〜2026年3月期） — 例示株式会社（1234）")
    assert "| 売上高 | 1,000 | 1,100 | 1,200 |" in text
    assert "| 自己資本 | 1,180 | 1,280 | 1,370 |" in text            # net assets − non-controlling interests
    assert "| 有利子負債 | 100 | 0 | 50 |" in text
    for key in ("sources", "originals", "supplement", "returns", "forecasts", "quarterly", "declines", "mna", "debt"):
        assert f"<!-- FILL:{key} " in text, key
    assert out["tdnet"] is False and out["debt_unknown"] == []


def test_debt_without_loan_lines_is_left_to_the_agent(tmp_path, capsys):
    root = _repo(tmp_path, with_debt=False)
    _, out = _run(root, capsys)
    text = (root / out["path"]).read_text(encoding="utf-8")
    assert "| 有利子負債 | — | — | — |" in text and out["debt_unknown"] == ["2024-03", "2025-03", "2026-03"]
    assert "| 項目（百万円） | 2024年3月期 | 2025年3月期 | 2026年3月期 |" in text


def test_same_day_file_is_not_overwritten(tmp_path, capsys):
    root = _repo(tmp_path)
    _, out = _run(root, capsys)
    target = root / out["path"]
    target.write_text("written by the agent\n", encoding="utf-8")
    code, again = _run(root, capsys)
    assert code == 0 and again["exists"] and target.read_text(encoding="utf-8") == "written by the agent\n"


def test_missing_financials_csv(tmp_path, capsys):
    root = _repo(tmp_path)
    (root / "companies" / DIR / "data" / "financials.csv").unlink()
    code, out = _run(root, capsys)
    assert code == 1 and "financials.csv" in out["error"]


def test_owners_equity_prefers_the_years_own_release():
    rows = [{"element": "OwnersEquity", "context": RF.OWNERS_EQUITY_CTX, "fiscal_year_end": "2026-03-31", "value": "110"},
            {"element": "OwnersEquity", "context": RF.PRIOR_EQUITY_CTX, "fiscal_year_end": "2026-03-31", "value": "90"},
            {"element": "OwnersEquity", "context": RF.OWNERS_EQUITY_CTX, "fiscal_year_end": "2024-03-31", "value": "80"},
            {"element": "OwnersEquity", "context": RF.PRIOR_EQUITY_CTX, "fiscal_year_end": "2025-03-31", "value": "79"},
            {"element": "NetSales", "context": RF.OWNERS_EQUITY_CTX, "fiscal_year_end": "2026-03-31", "value": "1"}]
    assert RF.owners_equity(rows) == {"2026-03-31": 110.0, "2025-03-31": 90.0, "2024-03-31": 80.0}


def test_safety_analysis_reads_the_written_tables(tmp_path, capsys):
    """Without data/ the safety series falls back to the raw tables: chapter 8 must be readable as written."""
    root = _repo(tmp_path)
    _run(root, capsys)
    shutil.rmtree(root / "companies" / DIR / "data")
    series = sf_series.self_series(A.Company(root, root / "companies" / DIR))
    assert series["total_assets"]["2026-03"].value == 2300
    assert series["equity"]["2026-03"].value == 1370
    assert series["debt"]["2025-03"].value == 0
    assert series["cash"]["2024-03"].value == 500
    assert series["cfo"]["2026-03"].value == 170
