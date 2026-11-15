"""status.md 未取得項目 expire when a newer annual report of the company arrives (ff_inputs.unavailable_items)."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "collect"))

import ff_inputs as I  # noqa: E402

STATUS = """# データ鮮度・未取得項目 — テスト

**最終更新**: {updated}（mode=update）

## 2. 未取得項目（次回優先して取りにいく）

| 項目 | 理由 | 次回試す取得方法 | 時点（自社の決算期） |
|---|---|---|---|
{rows}
"""


def _company(tmp_path: Path, updated: str, rows: list[str], yuho: list[str]) -> SimpleNamespace:
    (tmp_path / "status.md").write_text(STATUS.format(updated=updated, rows="\n".join(rows)), encoding="utf-8")
    filings = tmp_path / "raw" / "filings"
    filings.mkdir(parents=True)
    for name in yuho:
        (filings / name).write_text("# 有報\n", encoding="utf-8")
    return SimpleNamespace(path=tmp_path)


def test_a_record_holds_while_the_company_has_no_newer_annual_report(tmp_path):
    company = _company(tmp_path, "2026-11-11", ["| 解約率 | 開示なし | 統合報告書 | 2026-02期 |"],
                       ["2026-11-01_2026-02_yuho.md"])
    assert I.unavailable_items(company) == ["解約率"]


def test_a_record_expires_when_a_newer_annual_report_arrives(tmp_path):
    company = _company(tmp_path, "2026-11-11", ["| 解約率 | 開示なし | 統合報告書 | 2026-02期 |",
                                                "| 世界シェア | 有償のみ | 調査会社 | 2027-02期 |"],
                       ["2026-11-01_2026-02_yuho.md", "2027-05-30_2027-02_yuho.md"])
    assert I.unavailable_items(company) == ["世界シェア"]  # 解約率 is asked for once more in the new year


def test_a_record_without_a_period_is_dated_by_the_last_update(tmp_path):
    # older status.md files have no 時点 column: the annual report known at 最終更新 dates the record
    rows = ["| 解約率 | 開示なし | 統合報告書 | |"]
    company = _company(tmp_path, "2026-11-11", rows, ["2026-11-01_2026-02_yuho.md"])
    assert I.unavailable_items(company) == ["解約率"]
    (tmp_path / "raw" / "filings" / "2027-05-30_2027-02_yuho.md").write_text("# 有報\n", encoding="utf-8")
    assert I.unavailable_items(company) == []


def test_three_column_tables_still_read(tmp_path):
    text = STATUS.replace(" | 時点（自社の決算期） |", " |").replace("|---|---|---|---|", "|---|---|---|")
    (tmp_path / "status.md").write_text(text.format(updated="2026-11-11", rows="| 解約率 | 開示なし | 統合報告書 |"),
                                        encoding="utf-8")
    assert I.unavailable_items(SimpleNamespace(path=tmp_path)) == ["解約率"]  # no annual report: nothing expires


def test_a_us_10k_counts_as_the_annual_report(tmp_path):
    company = _company(tmp_path, "2026-03-01", ["| 継続率 | 開示なし | 10-K | 2025-12期 |"], [])
    filings = tmp_path / "raw" / "filings"
    (filings / "2027-02-20_2026-12_10k.md").write_text("# 10-K\n", encoding="utf-8")
    assert I.unavailable_items(company) == []
