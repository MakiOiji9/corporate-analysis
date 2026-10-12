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

import tc_doc as D  # noqa: E402
import tc_inputs as I  # noqa: E402
import tc_metrics as X  # noqa: E402
import tc_paths as P  # noqa: E402
import three_c as TC  # noqa: E402

DAY = "2026-10-12"
FF_DAY = "2026-10-05"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")

YUHO = """# 有価証券報告書 抜粋 — テスト

## 2. 事業の内容・セグメント情報（p.5）

- 自動車事業の単一セグメント

## 3. 主要な販売先（売上高の10%以上）（p.22）

- 該当事項なし
"""

BUSINESS = """# 事業概要 — テスト

## 3. 主力製品・サービスと会社が主張する特徴

- 高品質な小型車

## 4. 顧客層

- 個人顧客が中心
"""

INDUSTRY = """# 業界概要（自動車） — テスト

## 1. 市場規模と成長率

| 市場 | 実績 | CAGR | 出典 |
|---|---|---|---|
| 国内自動車 | 10兆円 | {cagr} | x |

## 5. 顧客の購買決定要因

{kbf}
"""

COMPETITORS = """# 競合情報 — テスト

## 1. 選定した同業他社と選定理由

| 会社 | コード・市場 | 決算期 | 選定理由 |
|---|---|---|---|
| アルファ社 | 1111 | 3月 | 近い |

## 2. 売上高・営業利益・営業利益率（5年推移）

### アルファ社（1111）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2023/03 | 100億円 | 5億円 |
| 2026/03 | 120億円 | {alpha_profit} |

### ベータ社（2222）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2026/03 | 50億円 | 2億円 |

### 参考: トヨタ（7203）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2023/03 | 80億円 | 8億円 |
| 2026/03 | 100億円 | 10億円 |

## 4. 市場シェア

{shares}

## 7. 主力製品と強み

| 会社 | 主張 | 出典 |
|---|---|---|
| アルファ社 | 品質 | x |
"""

SHARES = "| 会社 | シェア |\n|---|---|\n| トヨタ | {self_share} |\n| アルファ社 | 20% |\n| ベータ社 | 10% |"
NO_SHARES = "| 会社 | シェア |\n|---|---|\n| 全社 | —（公表値なし） |"

OUTLOOK = "# 地合い判断\n\n## 1. 総合判断\n\n- 中立\n"

KBF_ROWS = "| 品質 | {top} | {a} | × | — | 有報 p.5 |\n| 価格 | △ | △ | △ | — | 価格表 |"
ANSWERS = {
    "segment": "自動車（単一セグメント）", "customers": "個人顧客が中心", "kbf": "品質、価格",
    "kbf-basis": "brief.md 2.", "market-seen": "国内自動車 CAGR 5.0%", "market-source": "brief.md 2.",
    "market-confidence": "一次", "growth-rating": "高", "growth-reason": "3%以上",
    "customer-conclusion": "顧客は個人で、最も重視するのは品質。市場の成長性は高",
    "competitor-seen": "2.1 の表", "competitor-source": "brief.md 1.", "competitor-confidence": "一次",
    "competitor-rating": "優位", "competitor-reason": "両方上位", "competitor-conclusion": "競合と比べて優位",
    "company-conclusion": "品質で ○", "win-reason": "個人顧客が重視する品質において、生産方式により、競合より優れている",
    "triggers": "営業利益率が競合平均を下回れば劣位", "strengths": "品質", "weaknesses": "なし",
    "moat-checks": "利益率の10年推移", "changes": "- 初回の分析", "gaps": "- なし",
}


def _company(root: Path, cagr: str = "5.0%", kbf: str = "- 品質と価格が重視される（業界団体調査）",
             shares: str = SHARES.format(self_share="30%"), alpha_profit: str = "6億円",
             collected: str = "2026-10-01") -> Path:
    company = root / "companies" / "7203_toyota"
    for sub, name, text in (
            ("filings", f"{collected}_2026-03_yuho.md", YUHO),
            ("ir", f"{collected}_business-overview.md", BUSINESS),
            ("market", f"{collected}_industry-overview.md", INDUSTRY.format(cagr=cagr, kbf=kbf)),
            ("market", f"{collected}_competitors.md", COMPETITORS.format(shares=shares, alpha_profit=alpha_profit))):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _five_forces(root: Path, date: str = FF_DAY) -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / "five-forces"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_five-forces.md").write_text("# ファイブフォース\n\n完成\n", encoding="utf-8")
    result = {"attractiveness": "中", "total": 5, "industry": "自動車業界", "valid_until": "2027-10-05",
              "factors": [{"key": "rivalry", "name": "業界内の競争", "rating": "中", "reason": "拮抗"}]}
    (directory / f"{date}_five-forces.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _templates(root: Path) -> None:
    for name in ("three-c", "five-forces"):
        shutil.copytree(REPO / ".ai" / "templates" / name, root / ".ai" / "templates" / name)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    (tmp_path / "market" / "report").mkdir(parents=True)
    (tmp_path / "market" / "report" / "2026-10-05_outlook.md").write_text(OUTLOOK, encoding="utf-8")
    _company(tmp_path)
    _five_forces(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = TC.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def fill(md: Path, top: str = "○", a: str = "△", **answers: str) -> None:
    values = dict(ANSWERS, **{k.replace("_", "-"): v for k, v in answers.items()})
    values["kbf-rows"] = KBF_ROWS.format(top=top, a=a)
    md.write_text(FILL_ANY.sub(lambda m: values[m.group(1)], md.read_text(encoding="utf-8")), encoding="utf-8")


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def _found(key: str, body: str) -> I.Found:
    return I.Found(I.SPEC[key], "ok", Path("x"), "h", body)


# ---------- metrics ----------

@pytest.mark.parametrize("cagr, rating", [("9.1%", "高"), ("3.0%", "高"), ("2.0%", "中"), ("0.0%", "中"),
                                          ("-1.5%", "低")])
def test_growth_candidate_thresholds(cagr, rating):
    body = f"| 市場 | CAGR |\n|---|---|\n| 国内 | {cagr} |\n"
    cand = X.growth(_found("market_size", body))
    assert cand["rating"] == rating and not cand["fixed"]


def test_growth_candidate_without_cagr():
    assert X.growth(_found("market_size", "| 市場 | 規模 |\n|---|---|\n| 国内 | 10兆円 |\n"))["rating"] is None
    assert X.growth(I.Found(I.SPEC["market_size"], "missing"))["rating"] is None


def test_comparison_table_self_first_with_cagr_and_share(repo):
    rows = X.comparison(company_obj(repo), I.gather_3c(company_obj(repo)))
    assert [r["self"] for r in rows] == [True, False, False]
    target, alpha, beta = rows
    assert (target["margin"], target["share"], target["year"]) == (10.0, 30.0, "2026-03")
    assert target["cagr"] == pytest.approx(7.7, abs=0.05)  # 80 -> 100 over 3 years
    assert (alpha["margin"], alpha["share"], beta["margin"], beta["cagr"]) == (5.0, 20.0, 4.0, None)
    assert X.peer_names(rows) == ["アルファ社（1111）", "ベータ社（2222）"]


def test_comparison_prefers_company_data_csv(repo):
    data = repo / "companies" / "7203_toyota" / "data"
    data.mkdir()
    (data / "tdnet_facts.csv").write_text(
        "doc_id,document,filing_date,fiscal_year_end,context,element,value,unit\n"
        "d,短信,2026年5月1日,2026-03-31,CurrentYearDuration_ResultMember,NetSales,10000,百万円\n"
        "d,短信,2026年5月1日,2026-03-31,CurrentYearDuration_ResultMember,OperatingIncome,500,百万円\n"
        "d,短信,2026年5月1日,2026-03-31,NextYearDuration_ForecastMember,NetSales,99999,百万円\n"
        "d,短信,2026年5月1日,2026-03-31,CurrentYearDuration_NonConsolidatedMember_ResultMember,NetSales,1,百万円\n",
        encoding="utf-8")
    target = X.comparison(company_obj(repo), I.gather_3c(company_obj(repo)))[0]
    assert target["margin"] == 5.0 and "data/*.csv" in target["source"]


def test_target_heading_without_code_is_not_counted_as_peer(repo):
    raw = next((repo / "companies" / "7203_toyota" / "raw" / "market").glob("*_competitors.md"))
    raw.write_text(raw.read_text(encoding="utf-8").replace("### 参考: トヨタ（7203）", "### 参考: トヨタ"),
                   encoding="utf-8")
    rows = X.comparison(company_obj(repo), I.gather_3c(company_obj(repo)))
    assert X.peer_names(rows) == ["アルファ社（1111）", "ベータ社（2222）"] and rows[0]["margin"] == 10.0


@pytest.mark.parametrize("self_share, alpha_profit, rating, fixed", [
    ("30%", "6億円", "優位", True),    # margin 10% top, share top
    ("15%", "6億円", "同等", True),    # margin top, share middle
    ("5%", "18億円", "同等", True),    # margin middle (alpha 15%), share bottom
])
def test_competitor_candidate_with_share(tmp_path, self_share, alpha_profit, rating, fixed):
    company = P.Company(tmp_path, _company(tmp_path, shares=SHARES.format(self_share=self_share),
                                           alpha_profit=alpha_profit))
    cand = X.candidates(company, I.gather_3c(company))["competitor"]
    assert (cand["rating"], cand["fixed"]) == (rating, fixed)


def test_competitor_candidate_bottom_on_both_is_inferior():
    rows = [{"name": "自社", "self": True, "margin": 1.0, "share": 1.0, "year": "2026-03"},
            {"name": "A", "self": False, "margin": 5.0, "share": 9.0, "year": "2026-03"}]
    assert X.competitor(rows)["rating"] == "劣位"


@pytest.mark.parametrize("alpha_profit, rating", [("6億円", "同等"), ("30億円", "同等")])
def test_competitor_candidate_margin_only_is_never_fixed(tmp_path, alpha_profit, rating):
    company = P.Company(tmp_path, _company(tmp_path, shares=NO_SHARES, alpha_profit=alpha_profit))
    cand = X.candidates(company, I.gather_3c(company))["competitor"]
    assert (cand["rating"], cand["fixed"], cand["share_position"]) == (rating, False, None)


def test_competitor_candidate_margin_bottom_without_share_takes_the_unfavourable_side():
    rows = [{"name": "自社", "self": True, "margin": 1.0, "share": None, "year": "2026-03"},
            {"name": "A", "self": False, "margin": 5.0, "share": None, "year": "2026-03"}]
    cand = X.competitor(rows)
    assert (cand["rating"], cand["fixed"]) == ("劣位", False)


def test_competitor_candidate_notes_stale_years():
    rows = [{"name": "自社", "self": True, "margin": 9.0, "share": 5.0, "year": "2026-03"},
            {"name": "A", "self": False, "margin": 5.0, "share": 3.0, "year": "2024-03"}]
    cand = X.competitor(rows)
    assert cand["rating"] == "優位" and not cand["fixed"] and "2024-03" in cand["basis"]


@pytest.mark.parametrize("a, b, same", [("シグマクシスHD", "シグマクシス・ホールディングス（6088）", True),
                                        ("A（1111）", "A（2222）", False), ("全社", "トヨタ（7203）", False)])
def test_same_company(a, b, same):
    assert X.same_company(a, b) is same


# ---------- check ----------

def test_check_goes_to_prepare_when_five_forces_is_fresh(repo, capsys):
    code, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["result"] == "none" and out["next"] == "prepare"
    assert out["five_forces"]["result"] == "fresh" and not out["outlook_stale"]


def test_check_runs_five_forces_first(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "five_forces" and out["five_forces"]["result"] == "none"


def test_check_requests_collect_for_missing_inputs(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, kbf="—")
    _five_forces(tmp_path)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and not out["needs_full_collect"]
    assert out["missing_inputs"] == [{"agent": "collect-market", "items": ["業界: 購買決定要因"]}]


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / "7203_toyota").mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_check_unknown_company(repo, capsys):
    code, out = run(repo, "check", "--company", "6758", capsys=capsys)
    assert code == 1 and out["company_missing"]


def test_list_shows_three_c_and_five_forces_state(repo, capsys):
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert (row["dir"], row["three_c"], row["five_forces"], row["name"]) == ("7203_toyota", "none", "fresh",
                                                                            "トヨタ（7203）")


# ---------- prepare / build ----------

def test_full_cycle_then_fresh_expired_and_triggered(repo, capsys):
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["candidates"] == {"growth": "高", "competitor": "優位", "competitor_fixed": True}
    assert out["five_forces"] == FF_DAY and out["peers"] == ["アルファ社（1111）", "ベータ社（2222）"]
    md = repo / out["md"]
    text = md.read_text(encoding="utf-8")
    assert "- 競合A: アルファ社（1111）" in text and "- 競合C: —" in text
    assert "| **トヨタ（7203）（対象）** | 2026-03 | 100.0億円 | 10.0% | 30.0% |" in text
    assert "業界の魅力度 中。業界: 自動車業界" in text
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "### 業界: 購買決定要因" in brief and "業界の定義: 自動車業界" in brief

    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("FILL" in i for i in out["issues"])
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["verdict"] == "明確" and out["top_kbf_win"]
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["valid_until"] == "2027-04-10" and result["kbf"] == ["品質", "価格"]
    assert result["kbf_table"][0]["peers"] == {"アルファ社（1111）": "△", "ベータ社（2222）": "×"}
    assert result["five_forces"]["attractiveness"] == "中" and result["outlook"] == "market/report/2026-10-05_outlook.md"
    assert "| 勝てる理由 | **明確**:" in md.read_text(encoding="utf-8")
    code, again = run(repo, "build", "--company", "7203", capsys=capsys)  # idempotent
    assert code == 0 and again["verdict"] == "明確"

    _, out = run(repo, "check", "--company", "7203", "--date", "2027-04-10", capsys=capsys)
    assert out["result"] == "fresh" and out["next"] == "report_existing"
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-12-01", capsys=capsys)
    assert code == 1 and "--redo" in out["error"]
    _, out = run(repo, "check", "--company", "7203", "--date", "2027-04-11", capsys=capsys)
    assert out["result"] == "expired"

    _five_forces(repo, "2026-11-01")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-12-01", capsys=capsys)
    assert out["result"] == "triggered" and out["newer_raw"][-1].endswith("2026-11-01_five-forces.json")


def test_newer_business_overview_triggers(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"])
    run(repo, "build", "--company", "7203", capsys=capsys)
    path = repo / "companies" / "7203_toyota" / "raw" / "ir" / "2026-11-01_business-overview.md"
    path.write_text(BUSINESS, encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-12-01", capsys=capsys)
    assert out["result"] == "triggered" and out["newer_raw"] == [
        "companies/7203_toyota/raw/ir/2026-11-01_business-overview.md"]


@pytest.mark.parametrize("top, a, competitor, win, verdict", [
    ("○", "△", "優位", None, "明確"),
    ("○", "△", "同等", None, "あいまい"),
    ("○", "○", "優位", None, "あいまい"),   # a competitor is as good on the top KBF
    ("○", "？", "優位", None, "あいまい"),  # unknown competitor mark is never read as inferior
    ("×", "△", "優位", None, "あいまい"),
    ("○", "△", "劣位", None, "なし"),
    ("○", "△", "優位", "なし（テンプレートが埋まらない）", "なし"),
])
def test_verdict(repo, capsys, top, a, competitor, win, verdict):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    reason = "候補と異なる理由: 年度差" if competitor == "優位" else "迷った: 下位寄り"
    extra = {"win_reason": win} if win else {}
    fill(repo / out["md"], top=top, a=a, competitor_rating=competitor, competitor_reason=reason, **extra)
    shares = SHARES.format(self_share="30%") if competitor == "優位" else NO_SHARES  # 劣位/同等 need a free candidate
    _company(repo, shares=shares)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == verdict


def test_kbf_table_must_match_chapter_one(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], kbf="価格、品質")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("同じ名前・同じ順番" in i for i in out["issues"])


def test_kbf_marks_and_unused_peer_column(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / out["md"]
    fill(md, top="◎")
    md.write_text(md.read_text(encoding="utf-8").replace("| △ | △ | △ | — | 価格表 |", "| △ | △ | △ | △ | 価格表 |"),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("自社の列" in i for i in out["issues"])
    assert any("競合C は比較対象が無い" in i for i in out["issues"])


def test_kbf_count_is_limited(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"], kbf="品質")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("2〜5個" in i for i in out["issues"])


def test_fixed_candidate_cannot_move_and_favourable_needs_reason(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, cagr="1.0%")  # growth candidate 中, competitor 優位（確定）
    _five_forces(tmp_path)
    _, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = tmp_path / out["md"]
    original = md.read_text(encoding="utf-8")
    fill(md, competitor_rating="同等")
    _, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert any("確定" in i for i in out["issues"]) and any("1. 成長性" in i and "候補と異なる理由" in i
                                                          for i in out["issues"])
    md.write_text(original, encoding="utf-8")
    fill(md, growth_reason="候補と異なる理由: 主力の市場は別の統計で5%成長")
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["growth"] == "高"


def test_second_analysis_requires_change_reason(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    fill(repo / out["md"])
    run(repo, "build", "--company", "7203", capsys=capsys)
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2027-05-01", capsys=capsys)
    assert out["previous"] == DAY
    md = repo / out["md"]
    assert f"| 前回の評価 | 高（{DAY}） |" in md.read_text(encoding="utf-8")
    assert f"前回の結果: {DAY}（勝てる理由 明確" in (repo / out["brief"]).read_text(encoding="utf-8")
    fill(md, growth_rating="中", growth_reason="迷った: 3%付近")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("前回から変更" in i for i in out["issues"])


def test_prepare_keeps_draft_unless_redo(repo, capsys):
    _, first = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / first["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:changes", "- 途中\n<!-- FILL:changes"),
                  encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", capsys=capsys)
    assert out["kept"] and out["date"] == DAY and "- 途中" in md.read_text(encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", "--redo", capsys=capsys)
    assert not out["kept"] and out["date"] == "2026-10-13"


def test_forbidden_phrases_and_flags(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = repo / out["md"]
    original = md.read_text(encoding="utf-8")
    fill(md, company_conclusion="おそらく品質で勝る")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("おそらく" in i for i in out["issues"])
    md.write_text(original, encoding="utf-8")
    fill(md, a="？", market_confidence="参考", competitor_reason="迷った: 年度差")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["verdict"] == "あいまい"
    assert (out["tie_breaks"], out["low_confidence"], out["unknown_kbf"]) == (["競合との比較"], ["成長性"], ["品質"])


def test_build_recomputes_candidate_so_edited_cells_cannot_bypass(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, shares=SHARES.format(self_share="5%"), alpha_profit="18億円")  # 同等（確定）
    _five_forces(tmp_path)
    _, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    md = tmp_path / out["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("同等（確定）:", "優位:"), encoding="utf-8")
    fill(md)
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("確定" in i for i in out["issues"])


def test_split_kbf():
    assert D.split_kbf("品質、価格,サポート， ブランド") == ["品質", "価格", "サポート", "ブランド"]
    assert D.split_kbf("—") == []
