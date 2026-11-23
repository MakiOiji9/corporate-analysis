"""investment.py end to end on a small company: prepare → fill → build, and the writer's classes."""
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
TOOLS = ANALYSIS.parent
REPO = TOOLS.parent
sys.path[:0] = [str(ANALYSIS), str(TOOLS / "report"), str(TOOLS / "collect" / "market"), str(TOOLS / "collect")]

import an_fill as AF  # noqa: E402
import investment as IN  # noqa: E402
import iv_doc as D  # noqa: E402

DAY = "2026-11-23"
YEARS = [f"{y}-03-31" for y in range(2018, 2027)]
FIELDS = "doc_id,period_end,item,value,unit,element,context"


def _financials() -> str:
    lines = [FIELDS]
    for i, y in enumerate(YEARS):
        sales = 1000 + 100 * i
        for item, value in (("summary.net_sales", sales), ("summary.operating_income", 100 + 15 * i),
                            ("summary.net_income", 70 + 10 * i), ("summary.eps", 70 + 10 * i),
                            ("capex_tangible", -(50 + 5 * i)), ("depreciation", 40), ("research_and_development", 30),
                            ("summary.net_assets", 2000 + 100 * i), ("summary.cfo", 150 + 10 * i),
                            ("property_plant_and_equipment", 500 + 10 * i), ("goodwill", 10)):
            lines.append(f"S1,{y},{item},{value},百万円,jppfs_cor:X,CurrentYearDuration")
    return "\n".join(lines) + "\n"


def _investments() -> dict:
    years = []
    for y in YEARS:
        years.append({"period_end": y, "doc_id": "S1", "filed": y, "segments": [], "texts": {
            "capex_overview": {"element": "x", "label": "設備投資等の概要", "text": f"{y[:4]} 年は工場を増設した", "truncated": False},
            "planned_facilities": {"element": "x", "label": "設備の新設、除却等の計画",
                                   "text": "当連結会計年度後1年間の設備投資計画は新工場の建設である。" * 10, "truncated": False}}})
    segs = [{"period_end": y, "segment": seg, "metric": "capex", "value": str(v), "unit": "百万円", "element": "x"}
            for y in YEARS for seg, v in (("A", 30), ("B", 20))]
    return {"as_of": YEARS[-1], "years": years, "segments": segs, "missing": {}, "elements": {}}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / ".ai" / "templates" / "investment", tmp_path / ".ai" / "templates" / "investment")
    (tmp_path / "market" / "report").mkdir(parents=True)
    company = tmp_path / "companies" / "7203_toyota"
    (company / "data").mkdir(parents=True)
    (company / "data" / "financials.csv").write_text(_financials(), encoding="utf-8")
    (company / "data" / "investments.json").write_text(json.dumps(_investments(), ensure_ascii=False), encoding="utf-8")
    (company / "raw" / "filings").mkdir(parents=True)
    (company / "raw" / "filings" / "2026-11-01_2026-03_yuho.md").write_text(
        "# 有報\n\n## 7. 従業員数・設備投資（p.1）\n\n- 設備投資は工場の増設\n", encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = IN.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _fills(keys: list[str], trend: str = "合う", mtp: str = "整合", outcome: str = "予定どおり") -> dict:
    out = {}
    for k in keys:
        if k.startswith("themes-"):
            out[k] = "T1" if k < "themes-2023" else "T1、T2"
        elif k == "theme-1":
            out[k] = "工場の増設"
        elif k == "theme-2":
            out[k] = "自動化"
        elif re.fullmatch(r"theme-[12]-trend", k):
            out[k] = trend
        elif re.fullmatch(r"theme-[12]-basis", k):
            out[k] = "業界の構造を変えうる要因に自動化の需要とある"
        elif k.startswith("theme-"):
            out[k] = "—"
        elif k == "mtp-class":
            out[k] = mtp
        elif k.startswith("plan-") and k.endswith("-class"):
            out[k] = outcome
        else:
            out[k] = "工場の増設に投資した"
    return out


def _write_and_build(root: Path, out: dict, capsys, **kw) -> tuple[int, dict]:
    md = root / out["md"]
    (root / out["fills_json"]).write_text(json.dumps(_fills(out["fill_keys"], **kw), ensure_ascii=False),
                                          encoding="utf-8")
    assert md.exists()
    return run(root, "fill", "--company", "7203", "--build", capsys=capsys)


def test_prepare_fill_build(repo, capsys):
    code, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["next"] == "prepare", out
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0, out
    assert out["years"][0] == "2018-03" and "content-2026-03" in out["fill_keys"]
    assert out["plan_years"]  # every report names a plan: the last three are compared with the next report
    code, built = _write_and_build(repo, out, capsys)
    assert code == 0, built
    result = json.loads((repo / built["json"]).read_text(encoding="utf-8"))
    assert result["axes"]["plan"]["rating"] == "整合" and result["axes"]["trend"]["rating"] == "合う"
    assert any(p["kind"] == "新しい投資テーマ" and p["text"] == "自動化" for p in result["points"])
    assert result["verdict"] in ("良好", "普通")
    text = (repo / built["md"]).read_text(encoding="utf-8")
    assert "（build が記入）" not in text and "新しい投資テーマ（build が 1章の主なテーマから抽出）: 2023-03 自動化" in text
    code, again = run(repo, "build", "--company", "7203", capsys=capsys)  # a rebuild does not repeat the note
    assert code == 0 and (repo / built["md"]).read_text(encoding="utf-8").count("新しい投資テーマ（build") == 1


def test_build_rejects_bad_classes(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    code, built = _write_and_build(repo, out, capsys, trend="たぶん合う", mtp="ほぼ整合")
    assert code == 1
    joined = " ".join(built["issues"])
    assert "潮流との照合は" in joined and "中期経営計画: 分類は" in joined


def test_plan_slips_make_divergence(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    code, built = _write_and_build(repo, out, capsys, outcome="延期")
    assert code == 0, built
    assert built["axes"]["plan"].startswith("乖離")


def test_unknown_theme_id_rejected():
    parsed = {"years": [{"year": "2026-03", "content": "x", "themes_cell": "T9", "themes": ["T9"]}], "themes": [],
              "mtp_class": "不明", "plans": [], "points": []}
    issues = D._check_classes(parsed, ["2026-03"], 0)
    assert any("3章に無いテーマ" in i for i in issues)


def test_numbers_must_come_from_brief(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fills = _fills(out["fill_keys"])
    fills["report-points"] = "設備投資は 98,765百万円 だった"
    (repo / out["fills_json"]).write_text(json.dumps(fills, ensure_ascii=False), encoding="utf-8")
    code, built = run(repo, "fill", "--company", "7203", "--build", capsys=capsys)
    assert code == 1 and any("98765" in i for i in built["issues"])


def test_list_shows_state(repo, capsys):
    code, out = run(repo, "list", capsys=capsys)
    assert code == 0 and out["companies"][0]["investment"] == "none" and out["companies"][0]["has_investments_json"]


def test_fill_keys_are_unique(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    keys = AF.fill_keys((repo / out["md"]).read_text(encoding="utf-8"))
    assert len(keys) == len(set(keys))
