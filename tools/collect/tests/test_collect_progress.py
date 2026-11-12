import json
import sys
from pathlib import Path

COLLECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COLLECT))

import collect_progress as CP  # noqa: E402

DIR = "1234_example"
STATUS_TEMPLATE = "**最終更新**: 2026-11-12（mode=full）\n\n| 株価 | YYYY-MM-DD 終値 |\n"
STATUS_DONE = "**最終更新**: 2026-11-12（mode=full）\n\n| 株価 | 2026-11-11 終値 |\n"


def _company(root: Path) -> Path:
    company = root / "companies" / DIR
    (company / "raw").mkdir(parents=True)
    return company


def _write(company: Path, rel: str, text: str = "x\n") -> None:
    path = company / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _all_raw(company: Path) -> None:
    for rel in ("raw/ir/2026-11-12_business-overview.md", "raw/ir/2026-11-12_mid-term-plan.md",
                "raw/ir/2026-11-12_ir-materials-index.md", "raw/ir/2026-11-12_management.md",
                "raw/news/2026-11-12_press-releases.md", "raw/filings/2026-11-12_2026-03_yuho.md",
                "raw/ir/2026-11-12_financials-historical.md", "raw/market/2026-11-12_industry-overview.md",
                "raw/market/2026-11-12_competitors.md", "raw/ir/2026-11-12_valuation-data.md"):
        _write(company, rel)


def test_new_company_starts_with_the_first_agent(tmp_path):
    out = CP.progress(tmp_path / "companies" / DIR)
    assert out["exists"] is False and out["next"] == "collect-ir" and len(out["pending"]) == 4


def test_agent_with_one_file_missing_is_pending(tmp_path):
    company = _company(tmp_path)
    _all_raw(company)
    (company / "raw" / "ir" / "2026-11-12_management.md").unlink()
    _write(company, "raw/market/2026-11-12_competitors.md", "")  # empty files do not count
    out = CP.progress(company)
    assert out["pending"] == ["collect-ir", "collect-peers-valuation"]
    assert out["agents"]["collect-ir"]["missing"] == ["ir/*_management.md"]


def test_all_raw_but_not_aggregated(tmp_path):
    company = _company(tmp_path)
    _all_raw(company)
    _write(company, "status.md", STATUS_TEMPLATE)  # Phase 0 fills only the date line
    _write(company, "summaries/business.md", "## 2. 主力事業の定義\n<!-- 雛形 -->\n## 3. 次\n")
    assert CP.progress(company)["next"] == "aggregate"


def test_aggregated_company_is_done(tmp_path):
    company = _company(tmp_path)
    _all_raw(company)
    _write(company, "status.md", STATUS_DONE)
    _write(company, "summaries/business.md", "# 要約\n\n## 1. 主力事業の定義\n\nコンサルティング（売上の100%）\n")
    out = CP.progress(company)
    assert out["aggregated"] and out["next"] == "done"


def test_cli(tmp_path, capsys):
    _company(tmp_path)
    assert CP.main(["--company", DIR], tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["next"] == "collect-ir"
