import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import ff_doc as D  # noqa: E402
import ff_inputs as I  # noqa: E402
import ff_metrics as X  # noqa: E402
import ff_paths as P  # noqa: E402
import five_forces as FF  # noqa: E402

DAY = "2026-10-12"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")

YUHO = """# 有価証券報告書（第10期 2026年3月期）抜粋 — テスト

## 2. 事業の内容・セグメント情報（p.5）

- 自動車事業の単一セグメント

## 3. 主要な販売先（売上高の10%以上）（p.22）

| 相手先 | 2025年3月期 金額 | 比率 | 2026年3月期 金額 | 比率 |
|---|---|---|---|---|
| A社 | 100 | 9.0% | 150 | {ratio} |

## 5. 主要な原材料・調達先（p.23）

- 鋼材を複数社から調達

## 6. 研究開発・特許・許認可（p.18）

- 特許 120件

## 8. 財務3表（連結、主要項目）（p.72）

| 項目（百万円） | 2024年3月期 | 2025年3月期 | 2026年3月期 |
|---|---|---|---|
| 売上高 | 1,000 | 1,000 | 1,000 |
| 売上原価 | 600 | 630 | 640 |
| 売上総利益 | 400 | 370 | 360 |
"""

INDUSTRY = """# 業界概要（自動車） — テスト

## 1. 市場規模と成長率

| 市場 | 実績 | 予測 | CAGR | 予測主体・公表日 | 出典 | 確度 |
|---|---|---|---|---|---|---|
| 国内自動車 | 10兆円 | 11兆円 | 2.0% | 業界団体 | x | 一次 |

## 2. 上位企業とシェア分布・推移

{share}

## 3. 参入に必要な条件・過去5年の主な新規参入

| 項目 | 内容 | 出典 |
|---|---|---|
| 初期投資 | 数千億円 | x |

## 4. 代替製品・代替手段と普及状況

| 代替手段 | 状況 | 出典 |
|---|---|---|
| 公共交通 | 普及 | x |

## 6. 原材料・部品の調達構造、価格高騰の事例

- 鋼材価格が2022年に上昇
"""

COMPETITORS = """# 競合情報 — テスト

## 2. 売上高・営業利益・営業利益率（5年推移）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2026/03 | 500 | 50 |
"""

STATUS = """# データ鮮度・未取得項目 — テスト

## 2. 未取得項目（次回優先して取りにいく）

| 項目 | 理由 | 次回試す取得方法 |
|---|---|---|
| {item} | 公表統計が見つからない | — |
"""

OUTLOOK = """# 地合い判断

## 1. 総合判断

| 市場 | 地合い判断 | 前回（なし） | 判断の要約 |
|---|---|---|---|
| 日本 | 中立 | — | 要約 |
"""

ANSWERS = {
    "industry": "自動車業界（単一セグメント）", "industry-source": "brief.md 1.",
    "changes": "- 初回の分析", "gaps": "- なし",
}
ALL_MID = {"entry": "中", "substitutes": "中", "buyers": "中", "suppliers": "中", "rivalry": "中"}


def _company(root: Path, ratio: str = "12.0%", share: str = "- 上位3社で60%", status_item: str = "なし",
             collected: str = "2026-10-01") -> Path:
    company = root / "companies" / "7203_toyota"
    for sub, name, text in (("filings", f"{collected}_2026-03_yuho.md", YUHO.format(ratio=ratio)),
                            ("market", f"{collected}_industry-overview.md", INDUSTRY.format(share=share)),
                            ("market", f"{collected}_competitors.md", COMPETITORS)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n\n## 基本情報\n\n| 項目 | 内容 |\n|---|---|\n"
                                         "| 主力事業 | 自動車 |\n", encoding="utf-8")
    (company / "status.md").write_text(STATUS.format(item=status_item), encoding="utf-8")
    return company


def _templates(root: Path) -> None:
    shutil.copytree(REPO / ".ai" / "templates" / "five-forces", root / ".ai" / "templates" / "five-forces")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    (tmp_path / "market" / "report").mkdir(parents=True)
    (tmp_path / "market" / "report" / "2026-10-05_outlook.md").write_text(OUTLOOK, encoding="utf-8")
    _company(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = FF.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def fill(md: Path, ratings: dict[str, str], reasons: dict[str, str] | None = None,
         confidences: dict[str, str] | None = None) -> None:
    reasons, confidences = reasons or {}, confidences or {}

    def answer(m: re.Match) -> str:
        key = m.group(1)
        if key in ANSWERS:
            return ANSWERS[key]
        factor, field = key.rsplit("-", 1)
        if field == "rating":
            return ratings[factor]
        if field == "reason":
            return reasons.get(factor, "判断基準の中に当たる")
        if field == "confidence":
            return confidences.get(factor, "一次")
        if field == "triggers":
            return "最大顧客比率が20%以上になれば強"
        return "brief.md 2." if field == "source" else "数値と時点"

    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


# ---------- resolution ----------

def test_resolve_company_by_ticker_name_and_part(repo):
    for arg in ("7203", "7203_toyota", "companies/7203_toyota", "toyo"):
        company, _ = P.resolve_company(repo, arg)
        assert company and company.dirname == "7203_toyota", arg
    assert P.resolve_company(repo, "9999") == (None, [])


def test_resolve_company_ambiguous_returns_candidates(repo):
    (repo / "companies" / "7201_toyo-motor").mkdir()
    company, candidates = P.resolve_company(repo, "toyo")
    assert company is None and sorted(candidates) == ["7201_toyo-motor", "7203_toyota"]


# ---------- metrics ----------

@pytest.mark.parametrize("ratio, rating, fixed", [("12.0%", "中", False), ("25.0%", "強", True), ("8.0%", "弱", False)])
def test_buyer_candidate_uses_latest_ratio_column(tmp_path, ratio, rating, fixed):
    company = P.Company(tmp_path, _company(tmp_path, ratio=ratio))
    cand = X.buyer(I.gather(company)["customers"])
    assert (cand["rating"], cand["fixed"]) == (rating, fixed)


def test_buyer_candidate_without_major_customer_table():
    found = I.Found(I.SPEC["customers"], "ok", Path("x"), "3. 主要な販売先", "- 該当事項なし（10%以上の販売先なし）")
    assert X.buyer(found)["rating"] == "弱"


def test_supplier_candidate_from_raw_pl_table(repo):
    cand = X.supplier(company_obj(repo))
    assert [s["gross_margin"] for s in cand["series"]] == [40.0, 37.0, 36.0]
    assert cand["max_drop"] == 3.0 and cand["rating"] == "中"


def test_supplier_prefers_financials_csv(repo):
    data = repo / "companies" / "7203_toyota" / "data"
    data.mkdir()
    rows = ["doc_id,period_end,item,value,unit,element,context"]
    for year, cost in (("2024", 500), ("2025", 560)):
        rows += [f"d,{year}-03-31,net_sales,1000,円,e,c", f"d,{year}-03-31,cost_of_sales,{cost},円,e,c"]
    (data / "financials.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    margins, sources = X.gross_margins(company_obj(repo))
    assert margins["2024-03"] == 50.0 and margins["2026-03"] == 36.0  # csv first, raw fills the rest
    assert sources[0].endswith("data/financials.csv")
    assert X.supplier(company_obj(repo))["rating"] == "強"  # 50.0 -> 44.0 is a 6pt fall


def test_market_growth_reads_cagr_column_and_rows():
    body = "### 1-1. 市場A\n\n| 項目 | 値 |\n|---|---|\n| 2024〜29年 CAGR | 9.1% |\n"
    found = I.Found(I.SPEC["market_size"], "ok", Path("x"), "1.", body)
    assert X.market_growth(found) == ["1-1. 市場A: 2024〜29年 CAGR 9.1%"]
    column = I.Found(I.SPEC["market_size"], "ok", Path("x"), "1.", INDUSTRY.split("## 2.")[0])
    assert X.market_growth(column) == ["国内自動車: 2.0%"]


# ---------- inputs ----------

def test_blank_and_unavailable_sections(tmp_path):
    company = P.Company(tmp_path, _company(tmp_path, share="—", status_item="市場シェア（公表値なし）"))
    found = I.gather(company)
    assert found["share"].status == "unavailable"
    assert found["kbf"].status == "missing"  # optional input, not requested
    assert I.collect_requests(found) == []


def test_missing_required_input_requests_collect_agent(tmp_path):
    company = P.Company(tmp_path, _company(tmp_path, share="—"))
    assert I.collect_requests(I.gather(company)) == [{"agent": "collect-market", "items": ["業界: 上位企業とシェア"]}]


def test_newest_raw_with_content_wins(repo):
    diff = repo / "companies" / "7203_toyota" / "raw" / "market" / "2026-10-11_industry-overview.md"
    diff.write_text("# 差分\n\n## 3. 参入に必要な条件・過去5年の主な新規参入\n\n| 項目 | 内容 | 出典 |\n"
                    "|---|---|---|\n| 新規参入 | EV 専業2社 | y |\n", encoding="utf-8")
    found = I.gather(company_obj(repo))
    assert found["entry"].path == diff
    assert found["substitutes"].path.name == "2026-10-01_industry-overview.md"


# ---------- check / prepare / build ----------

def test_check_new_company_goes_to_prepare(repo, capsys):
    code, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["result"] == "none" and out["next"] == "prepare"


def test_check_requests_collect_but_never_market_report(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, share="—")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["missing_inputs"][0]["agent"] == "collect-market"
    _company(tmp_path)  # share collected now; no outlook at all
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare" and out["outlook_stale"]


def test_check_unknown_company(repo, capsys):
    code, out = run(repo, "check", "--company", "6758", capsys=capsys)
    assert code == 1 and out["company_missing"]


def test_full_cycle_then_fresh_triggered_expired(repo, capsys):
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["fill"] == 34 and out["candidates"]["buyers"] == "中"
    md = repo / out["md"]
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("FILL" in i for i in out["issues"])

    fill(md, ALL_MID)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["total"] == 5 and out["attractiveness"] == "中"
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["valid_until"] == "2027-10-12" and result["outlook"] == "market/report/2026-10-05_outlook.md"
    assert "| **合計 / 業界の魅力度** | **中** | 5/10 |" in md.read_text(encoding="utf-8")
    code, again = run(repo, "build", "--company", "7203", capsys=capsys)  # idempotent
    assert code == 0 and again["total"] == 5

    _, out = run(repo, "check", "--company", "7203", "--date", "2027-10-12", capsys=capsys)
    assert out["result"] == "fresh" and out["next"] == "report_existing"
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-12-01", capsys=capsys)
    assert code == 1 and "--redo" in out["error"]
    _, out = run(repo, "check", "--company", "7203", "--date", "2027-10-13", capsys=capsys)
    assert out["result"] == "expired" and out["next"] == "prepare" and out["outlook_stale"]

    _company(repo, collected="2026-11-01")  # a newer yuho / industry / competitors
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-12-01", capsys=capsys)
    assert out["result"] == "triggered" and len(out["newer_raw"]) == 3


def test_raw_collected_later_on_the_analysis_day_triggers(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], ALL_MID)
    run(repo, "build", "--company", "7203", capsys=capsys)
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "fresh"  # the analysis used every raw there is
    market = repo / "companies" / "7203_toyota" / "raw" / "market"
    (market / f"{DAY}_competitors.md").write_text(
        (market / "2026-10-01_competitors.md").read_text(encoding="utf-8"), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "triggered" and out["newer_raw"] == [f"companies/7203_toyota/raw/market/{DAY}_competitors.md"]


def test_second_analysis_shows_previous_and_requires_change_reason(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], ALL_MID)
    run(repo, "build", "--company", "7203", capsys=capsys)
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2027-11-01", capsys=capsys)
    assert out["previous"] == DAY
    md = repo / out["md"]
    assert f"| 前回の評価 | 中（{DAY}） |" in md.read_text(encoding="utf-8")
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert f"前回の結果: {DAY}（業界の魅力度 中" in brief

    fill(md, dict(ALL_MID, entry="強"))
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("前回から変更" in i for i in out["issues"])


def test_prepare_keeps_draft_unless_redo(repo, capsys):
    _, first = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / first["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:changes", "- 途中\n<!-- FILL:changes"),
                  encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", capsys=capsys)
    assert out["kept"] and out["date"] == DAY and "- 途中" in md.read_text(encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "draft"
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", "--redo", capsys=capsys)
    assert not out["kept"] and out["date"] == "2026-10-13"


def test_favourable_deviation_needs_reason_and_fixed_cannot_move(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, ratio="25.0%")
    _, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = tmp_path / out["md"]
    original = md.read_text(encoding="utf-8")
    fill(md, dict(ALL_MID, suppliers="弱"))  # buyers 中 vs 強（確定）, suppliers 弱 vs 中 without reason
    _, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert any("確定" in i for i in out["issues"]) and any("候補と異なる理由" in i for i in out["issues"])

    md.write_text(original, encoding="utf-8")
    fill(md, dict(ALL_MID, buyers="強", suppliers="弱"), {"suppliers": "候補と異なる理由: 原材料高騰の年ではない"})
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["swot_threats"] == ["買い手の交渉力"] and out["total"] == 5


def test_forbidden_phrases_are_rejected(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], ALL_MID, {"rivalry": "おそらく競争は緩い"})
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("おそらく" in i for i in out["issues"])


def test_list_shows_companies_and_state(repo, capsys):
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert (row["dir"], row["five_forces"], row["name"]) == ("7203_toyota", "none", "トヨタ（7203）")


# ---------- review regressions ----------

def _found(key: str, body: str) -> I.Found:
    return I.Found(I.SPEC[key], "ok", Path("x"), "h", body)


def test_buyer_ignores_total_rows_and_does_not_guess_from_prose():
    table = "| 相手先 | 比率 |\n|---|---|\n| A社 | 12.0% |\n| 合計 | 100.0% |\n"
    assert X.buyer(_found("customers", table))["rating"] == "中"
    assert X.buyer(_found("customers", "- A社向けが売上の25.3%"))["rating"] is None


def test_gross_margin_ignores_ratio_rows_and_year_gaps():
    table = [["項目", "2024年3月期", "2025年3月期"], ["売上高総利益率", "40%", "38%"],
             ["売上高", "1,000", "1,000"], ["売上総利益", "400", "380"]]
    assert X._margins_from_table(table) == {"2024-03": 40.0, "2025-03": 38.0}
    assert X._months_apart("2018-03", "2021-03") == 36


def test_supplier_drop_skips_multi_year_gaps(repo):
    yuho = next((repo / "companies" / "7203_toyota" / "raw" / "filings").glob("*.md"))
    yuho.write_text(yuho.read_text(encoding="utf-8").replace("2025年3月期 |", "2021年3月期 |"), encoding="utf-8")
    cand = X.supplier(company_obj(repo))  # years 2021, 2024, 2026: no year-on-year pair at all
    assert cand["rating"] is None and "除外" in cand["basis"]


def test_build_recomputes_candidate_so_edited_cells_cannot_bypass(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, ratio="25.0%")
    _, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = tmp_path / out["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("強（確定）:", "弱:"), encoding="utf-8")
    fill(md, dict(ALL_MID, buyers="弱"))
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("確定" in i for i in out["issues"])


def test_stale_draft_behind_built_result_is_abandoned(repo, capsys):
    run(repo, "prepare", "--company", "7203", "--date", "2026-10-01", capsys=capsys)  # left as a draft
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, "--redo", capsys=capsys)
    fill(repo / out["md"], ALL_MID)
    run(repo, "build", "--company", "7203", "--date", DAY, capsys=capsys)
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2027-11-01", capsys=capsys)
    assert out["date"] == "2027-11-01" and not out["kept"] and out["previous"] == DAY


def test_same_day_redo_after_build_is_refused(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], ALL_MID)
    run(repo, "build", "--company", "7203", capsys=capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, "--redo", capsys=capsys)
    assert code == 1 and "Edit" in out["error"]


def test_replace_section_without_trailing_newline():
    assert D.replace_section("## 3. x", "3.", "body") == "## 3. x\nbody\n\n"


# ---------- improvements after the first run (2026-10-12) ----------

def test_buyer_basis_shows_change_from_previous_year(tmp_path):
    company = P.Company(tmp_path, _company(tmp_path, ratio="12.0%"))
    cand = X.buyer(I.gather(company)["customers"])
    assert cand["previous_value"] == 9.0 and "前期 9.0% から +3.0pt" in cand["basis"]


@pytest.mark.parametrize("cell, yen", [
    ("140億2,433万円", 140e8 + 2433e4), ("7.93億円", 7.93e8), ("7,367百万円", 7367e6), ("500", 500.0),
    ("△1,000百万円", -1000e6), ("—（経常利益32億円予想との報道）", None), ("—", None),
    ("23,831百万円（前期比 -9.4%）", 23831e6),  # a note after the amount is dropped
])
def test_yen_reads_japanese_amounts(cell, yen):
    assert X._yen(cell) == pytest.approx(yen) if yen is not None else X._yen(cell) is None


def test_peer_margins_per_company_with_forecast():
    body = ("### A社（1111）\n\n| 年度 | 売上高 | 営業利益 | 営業利益率 |\n|---|---|---|---|\n"
            "| 2025/03 | 100億円 | 10億円 | — |\n| 2026/03 | 120億円 | 18億円 | — |\n"
            "| 2027/03（会社予想） | 130億円 | 13億円 | — |\n\n"
            "### B社（2222）\n\n| 年度 | 売上高 | 営業利益 |\n|---|---|---|\n| 2026/02 | 84億2,118万円 | 17億320万円 |\n")
    peers = X.peer_margins(_found("peers", body))
    assert [p["name"] for p in peers] == ["A社（1111）", "B社（2222）"]
    assert [s["margin"] for s in peers[0]["series"]] == [10.0, 15.0, 10.0]
    line = X.peer_margin_line(peers[0])
    assert "2026-03 15.0%（最新実績の前年差 +5.0pt）" in line and "2027-03 予想 10.0%" in line
    assert X.peer_margin_line(peers[1]) == "B社（2222）: 2026-02 20.2%"


def test_operating_margin_from_pl_table():
    table = [["項目（百万円）", "2025年3月期", "2026年3月期"], ["売上高", "1,000", "2,000"],
             ["営業利益", "100", "300"], ["営業利益率", "10%", "15%"]]
    assert X._margins_from_table(table, "operating") == {"2025-03": 10.0, "2026-03": 15.0}


def test_brief_has_margins_and_no_outlook_table(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "| 年度末 | 粗利率 | 営業利益率 |" in brief and "| 2026-03 | 36.0% | — |" in brief
    assert "営業利益率の推移" in brief and "2026-03 10.0%" in brief  # COMPETITORS: 50 / 500
    assert "| 市場 | 地合い判断 |" not in brief and "7 日前の週" in brief
    md = (repo / out["md"]).read_text(encoding="utf-8")
    assert "**地合い**: market/report/2026-10-05_outlook.md（7 日前の週）" in md


def test_build_reports_all_gaps_tie_breaks_and_low_confidence(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / out["md"]
    fill(md, dict(ALL_MID, entry="強"), {"entry": "迷った: 中と強で迷い不利な方を採った"}, {"substitutes": "参考"})
    md.write_text(md.read_text(encoding="utf-8").replace(
        "## 6. 判定に効く欠損\n\n- なし", "## 6. 判定に効く欠損\n\n- 一\n- 二\n- 三\n- 四"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and len(out["gaps"]) == 4
    assert out["tie_breaks"] == ["新規参入の脅威"] and out["low_confidence"] == ["代替品の脅威"]
    factor = json.loads((repo / out["json"]).read_text(encoding="utf-8"))["factors"][0]
    assert factor["tie_break"] and factor["confidence"] == "一次" and factor["triggers"]


def test_build_rejects_bad_confidence_and_blank_triggers(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / out["md"]
    fill(md, ALL_MID, confidences={"buyers": "高い"})
    md.write_text(md.read_text(encoding="utf-8").replace(
        "| 評価が変わる条件 | 最大顧客比率が20%以上になれば強 |", "| 評価が変わる条件 | — |", 1), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("根拠の確度" in i for i in out["issues"])
    assert any("評価が変わる条件が空" in i for i in out["issues"])


def test_result_made_before_new_rows_still_parses():
    row = "| 項目 | 内容 |\n|---|---|\n| 見たもの | x |\n| 情報源 | y |\n| 評価 | 中 |\n| 理由 | z |\n"
    text = "## 1. 業界の定義\n\n| 項目 | 内容 |\n|---|---|\n| 業界の定義 | a |\n\n## 2. 5つの要因\n\n" + "".join(
        f"### {number} {name}\n\n{row}\n" for _, number, name in D.FACTORS) + "## 5. 変更\n\n- なし\n\n## 6. 欠損\n\n- なし\n"
    parsed = D.parse(text)
    assert all(f["confidence"] is None and f["triggers"] is None for f in parsed["factors"])
    assert not [i for f in parsed["factors"] for i in D._check_factor(f)]


# ---------- scoring ----------

@pytest.mark.parametrize("ratings, total, level, downgraded", [
    (["弱", "弱", "弱", "中", "強"], 7, "高", False),
    (["弱", "弱", "弱", "不明", "不明"], 8, "中", True),
    (["中", "中", "中", "中", "不明"], 5, "中", False),
    (["中", "中", "不明", "不明", "強"], 4, "低", True),
    (["強", "強", "中", "中", "中"], 3, "低", False),
])
def test_score(ratings, total, level, downgraded):
    parsed = {"factors": [{"name": n, "rating": r, "reason": ""} for (_, _, n), r in zip(D.FACTORS, ratings)]}
    scored = D.score(parsed)
    assert (scored["total"], scored["attractiveness"], scored["downgraded"]) == (total, level, downgraded)
