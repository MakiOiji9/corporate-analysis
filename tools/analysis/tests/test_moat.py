import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect"), str(REPO / "tools" / "guard")]

import moat as MT  # noqa: E402
import mt_doc as D  # noqa: E402
import mt_inputs as I  # noqa: E402
import mt_metrics as X  # noqa: E402
import mt_paths as P  # noqa: E402
import mt_returns as R  # noqa: E402
import sf_series as SS  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
TC_DAY = "2026-10-05"
COLLECTED = "2026-10-01"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")

YUHO = """# 有価証券報告書 抜粋 — テスト

## 4. 事業等のリスク（要旨）（p.10）

- EV への移行

## 6. 研究開発・特許・許認可（p.18）

- 主要特許 2035年まで有効
"""

FINANCIALS = """# 財務時系列 — テスト

## 1. 損益・貸借・CF（10年サマリー）

{table}

## 4. 会社計画（期初予想）と実績

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2027/03 | 100 | 50 |
"""

BUSINESS = """# 事業概要 — テスト

## 4. 顧客層

- 個人顧客が中心

## 5. 主要KPI（決算説明会資料・質疑応答）

| 項目 | 前期 | 当期 | 出典 |
|---|---|---|---|
| 販売台数 | 100 | 110 | 説明会資料 |
{retention}
{pricing}
"""

RETENTION = """
## 7. 継続率・解約率・ストック型売上の比率

| 指標 | 前期 | 当期 | 出典・確度 |
|---|---|---|---|
| 継続率 | 92% | 93% | 説明会資料 p.5（一次） |
"""

PRICING = """
## 8. 値上げ・価格改定の実績と販売数量への影響

| 時期 | 製品・サービス | 改定内容 | 改定後の販売数量の変化 | 出典・確度 |
|---|---|---|---|---|
| 2024/04 | 全車種 | +5% | 前年比 +2% | 短信（一次） |
"""

INDUSTRY = """# 業界概要（自動車） — テスト

## 2. 上位企業とシェア分布・推移

| 会社 | 2021 | 2026 |
|---|---|---|
| トヨタ | 30% | 32% |

## 3. 参入に必要な条件・過去10年の新規参入と撤退

- 新規参入 0社、撤退 2社

## 7. 業界全体の利益率の推移

- 5〜8%

## 8. 業界構造を変えうる要因（技術革新・規制変更・特許切れ）

- EV 化
"""

COMPETITORS = """# 競合情報 — テスト

## 2. 売上高・営業利益・営業利益率（最大10年推移）

### アルファ社（1111）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
{alpha}

### ベータ社（2222）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
{beta}

### 参考: トヨタ（7203）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2026/03 | 100億円 | 10億円 |

## 4. 市場シェア

| 会社 | シェア | 出典 |
|---|---|---|
| トヨタ | 32% | x |

## 7. 主力製品と強み

| 会社 | 主張 | 出典 |
|---|---|---|
| アルファ社 | 品質 | x |

{cost}
"""

COST = """## 9. 売上原価率・販管費率（コスト構造の比較）

| 会社 | 年度 | 売上原価率 | 販管費率 | 営業利益率 | 出典・確度 |
|---|---|---|---|---|---|
| トヨタ（7203） | 2026/03 | 70.0% | 20.0% | 10.0% | 有報（一次） |
| アルファ社（1111） | 2026/03 | 80.0% | 15.0% | 5.0% | 短信（一次） |
| ベータ社（2222） | 2026/02 | 78.0% | 15.0% | 7.0% | 短信（一次） |
"""

OUTLOOK = "# 地合い判断\n\n## 1. 総合判断\n\n- 中立\n"
SELF_MARGIN = 10  # 億円 of 100
EQUITY, DEBT = 40, 10  # invested capital 50: ROIC = 10 × (1 − 30.6%) ÷ 50 = 13.9%, 6.9pt above the 7% cost of capital
YEARS = range(2017, 2027)


def _rows(years, month: int, profit: float, unit: str = "") -> str:
    return "\n".join(f"| {y}/{month:02d} | 100{unit} | {profit}{unit} |" for y in years)


def _financials(profit: float, balance: bool = True, years=YEARS) -> str:
    if not balance:
        return FINANCIALS.format(table="| 年度 | 売上高 | 営業利益 |\n|---|---|---|\n" + _rows(years, 3, profit))
    rows = "\n".join(f"| {y}/03 | 100 | {profit} | {EQUITY} | {DEBT} |" for y in years)
    return FINANCIALS.format(table="| 年度 | 売上高 | 営業利益 | 自己資本 | 有利子負債 |\n|---|---|---|---|---|\n" + rows)


def _company(root: Path, self_profit: float = SELF_MARGIN, alpha_years=YEARS, beta_years=YEARS,
             retention: str = RETENTION, pricing: str = PRICING, cost: str = COST,
             collected: str = COLLECTED, balance: bool = True) -> Path:
    company = root / "companies" / "7203_toyota"
    for sub, name, text in (
            ("filings", f"{collected}_2026-03_yuho.md", YUHO),
            ("ir", f"{collected}_financials-historical.md", _financials(self_profit, balance)),
            ("ir", f"{collected}_business-overview.md", BUSINESS.format(retention=retention, pricing=pricing)),
            ("market", f"{collected}_industry-overview.md", INDUSTRY),
            ("market", f"{collected}_competitors.md",
             COMPETITORS.format(alpha=_rows(alpha_years, 3, 5, "億円"), beta=_rows(beta_years, 2, 7, "億円"),
                                cost=cost))):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _three_c(root: Path, date: str = TC_DAY, verdict: str = "明確") -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / "three-c"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_three-c.md").write_text("# 3C\n\n完成\n", encoding="utf-8")
    result = {"verdict": verdict, "verdict_reason": "理由", "win_reason": "品質で優れる",
              "valid_until": "2099-01-01", "inputs": [],
              "handoff": {"strengths": "品質", "weaknesses": "なし", "moat_checks": "利益率の10年推移"}}
    (directory / f"{date}_three-c.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _templates(root: Path) -> None:
    shutil.copytree(REPO / ".ai" / "templates" / "moat", root / ".ai" / "templates" / "moat")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    (tmp_path / "market" / "report").mkdir(parents=True)
    (tmp_path / "market" / "report" / "2026-10-05_outlook.md").write_text(OUTLOOK, encoding="utf-8")
    _company(tmp_path)
    _three_c(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = MT.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


MOAT_KEYS = ("brand", "license", "switching", "network", "cost", "scale")


def moat_rows(**ratings: str) -> str:
    """The six source rows in MOAT_TYPES order; keyword args (MOAT_KEYS) override 該当なし."""
    lines = []
    for key, name in zip(MOAT_KEYS, D.MOAT_TYPES):
        rating = ratings.get(key, "該当なし")
        if rating in D.HITS:
            cells = (f"仕組み {name}", f"数値 {name}", "brief.md 2.", "一次")
        elif rating == "弱":
            cells = (f"仕組み {name}", "—", "brief.md 2.", "—")
        else:
            cells = (f"確認した資料 {name}", "—", "—", "—")
        lines.append(f"| {name} | {rating} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


ANSWERS = {
    "strength": "品質", "share-seen": "30%→32%", "share-source": "brief.md 6.", "share-confidence": "一次",
    "share-trend": "安定", "share-reason": "シェアは5年で微増", "durability": "モートは10年程度持続する見込み。リスク要因は EV 化",
    "depth-rating": "深い", "depth-reason": "設置台数 10万台の置き換えに10年かかる", "reach-rating": "限定的",
    "reach-reason": "新領域で同じ仕組みが効くかは未確認",
    "strengths": "スイッチングコスト", "threats": "EV 化", "step2-checks": "ROIC が資本コストを上回り続けるか",
    "triggers": "ROIC が2年続けて資本コストを下回れば なし", "changes": "- 初回の分析", "gaps": "- なし",
}
RISK = "| EV 化 | {category} | {timing} | ブランド | 業界概要 | brief.md 7. |"
NO_RISK = "| なし | — | — | — | 業界概要・有報のリスクを確認 | — |"


def risk(timing: str = "5〜10年", category: str = "技術") -> str:
    return RISK.format(timing=timing, category=category)


def fill(md: Path, rows: str | None = None, risks: str | None = None, **answers: str) -> None:
    values = dict(ANSWERS, **{k.replace("_", "-"): v for k, v in answers.items()})
    values["moat-rows"] = rows if rows is not None else moat_rows(switching="強", license="中")
    values["risk-rows"] = risks if risks is not None else risk()
    md.write_text(FILL_ANY.sub(lambda m: values[m.group(1)], md.read_text(encoding="utf-8")), encoding="utf-8")


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def prepared(root: Path, capsys, date: str = DAY, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", date, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def built(root: Path, capsys, **fill_args) -> dict:
    md = prepared(root, capsys)
    fill(md, **fill_args)
    code, out = run(root, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    return out


# ---------- ROIC and pricing power (mt_returns) ----------

def _value(v: float) -> SS.S.Value:
    return SS.S.Value(v, "test", True)


def test_roic_rows_average_capital_and_untaxed_losses():
    series = {"operating_income": {"2025-03": _value(10.0), "2026-03": _value(-5.0)},
              "equity": {"2025-03": _value(40.0), "2026-03": _value(60.0)},
              "debt": {"2025-03": _value(10.0), "2026-03": _value(10.0)}}
    first, second = R.roic_rows(series, 30.0, 7.0)
    assert (first["invested"], first["roic"], first["spread"]) == (50.0, 14.0, 7.0)
    assert (second["invested"], second["roic"]) == (60.0, -8.3)  # (70 + 50) / 2; a loss is not reduced by the tax


def test_roic_skips_years_without_debt_or_positive_capital():
    series = {"operating_income": {"2025-03": _value(10.0), "2026-03": _value(10.0)},
              "equity": {"2025-03": _value(-40.0), "2026-03": _value(40.0)},
              "debt": {"2025-03": _value(10.0)}}
    assert R.roic_rows(series, 30.0, 7.0) == []


def _spreads(values: list[float]) -> list[dict]:
    return [{"year": f"{2016 + i}-03", "spread": s} for i, s in enumerate(values)]


@pytest.mark.parametrize("spreads, rating", [
    ([6.0] * 10, "強い"),
    ([3.0] * 10, "弱い"),  # above every year, but the median spread is under 5pt
    ([6.0] * 6, "弱い"),  # too few years for 強い
    ([6.0] * 7 + [-1.0] * 3, "なし"),  # the last 3 years at or below the cost of capital
    ([-1.0] * 6 + [6.0] * 4, "なし"),  # above in fewer than half of the years
    ([6.0] * 4, None),
    ([-1.0] * 4, "なし"),  # a short history can still show no excess return
])
def test_rate_returns(spreads, rating):
    assert R.rate_returns(_spreads(spreads), 7.0)["rating"] == rating


def test_operating_losses_mean_no_excess_return_without_roic():
    result = R.rate_returns([], 9.0, [-3.0, -2.0, -1.0])
    assert result["rating"] == "なし" and "営業赤字" in result["basis"]
    assert R.rate_returns([], 9.0, [-3.0, 2.0])["rating"] is None


def test_border_years_are_listed():
    result = R.rate_returns(_spreads([6.0] * 9 + [1.5]), 7.0)
    assert result["border_years"] == ["2025-03"] and "境界" in result["basis"]


@pytest.mark.parametrize("spreads, trend", [
    ([0.0] * 5 + [3.0] * 5, "拡大"), ([3.0] * 5 + [0.0] * 5, "縮小"), ([3.0] * 10, "安定"),
    ([0.0] * 3 + [3.0] * 3, "拡大"), ([1.0] * 4, "不明"),
])
def test_trend(spreads, trend):
    assert R.trend(spreads) == trend


@pytest.mark.parametrize("recent, word", [(12.0, "大"), (5.0, "中"), (1.0, "小"), (0.0, "なし"), (None, "不明")])
def test_width(recent, word):
    assert R.width(recent) == word


def _gross(values: dict[int, float]) -> dict[str, float]:
    return {f"{y}-03": v for y, v in values.items()}


@pytest.mark.parametrize("margins, peer, rating", [
    ({y: 40.0 for y in range(2017, 2027)}, 35.0, "強い"),
    ({y: 40.0 for y in range(2017, 2027)}, 45.0, "普通"),  # stable but below the peers
    ({**{y: 40.0 for y in range(2017, 2027)}, 2023: 37.0}, None, "弱い"),  # fell 3pt through the cost inflation
    ({y: 30.0 + 2 * (y - 2017) for y in range(2017, 2027)}, None, "弱い"),  # a range of 18pt
    ({y: 40.0 for y in range(2023, 2027)}, None, None),
])
def test_rate_pricing(margins, peer, rating):
    assert R.rate_pricing(_gross(margins), peer)["rating"] == rating


def test_peer_gross_is_the_median_of_each_peers_first_row():
    costs = [{"name": "a", "self": False, "cost": 60.0}, {"name": "a", "self": False, "cost": 90.0},
             {"name": "b", "self": False, "cost": 70.0}, {"name": "me", "self": True, "cost": 10.0}]
    assert R.peer_gross(costs) == 35.0


@pytest.mark.parametrize("spread, share, trend", [
    ("縮小", "安定", "縮小"), ("安定", "低下", "縮小"), ("拡大", "拡大", "拡大"), ("拡大", "不明", "安定"),
    ("不明", "不明", "不明"), ("安定", "横ばい〜微減", "安定"),
])
def test_moat_trend(spread, share, trend):
    assert D.moat_trend(spread, share) == trend


# ---------- margin comparison (mt_metrics) ----------

def test_self_series_reads_row_table_and_skips_forecasts(repo):
    margins, sources = X.self_series(company_obj(repo), [])
    assert list(margins) == [f"{y}-03" for y in YEARS]  # 2027/03 is in the plan section: skipped
    assert margins["2026-03"] == 10.0
    assert sources == ["raw の財務時系列・有報"]


def test_non_consolidated_sub_table_is_skipped(tmp_path):
    company = _company(tmp_path)
    yuho = company / "raw" / "filings" / f"{COLLECTED}_2026-03_yuho.md"
    yuho.write_text(YUHO + "\n## 1. 主要な経営指標等の推移\n\n### 提出会社\n\n| 年度 | 売上高 | 営業利益 |\n"
                    "|---|---|---|\n| 2015/03 | 100 | 90 |\n", encoding="utf-8")
    margins, _ = X.self_series(company_obj(tmp_path), [])
    assert "2015-03" not in margins


def test_comparison_uses_the_peer_median_and_matches_fiscal_years_within_six_months(repo):
    company = company_obj(repo)
    cands = X.candidates(company, I.gather_moat(company))
    last = cands["rows"][-1]
    assert last["avg"] == 6.0 and last["mean"] == 6.0 and last["diff"] == 4.0
    assert [m["year"] for m in last["peers"]] == ["2026-03", "2026-02"]
    assert cands["margin"]["rating"] == "強い" and cands["margin"]["years_above"] == 10
    assert cands["returns"]["rating"] == "強い" and cands["returns"]["years"] == 10


def test_median_is_not_pulled_by_one_outlier_peer():
    peers = [{"name": n, "series": [{"year": "2026-03", "margin": m}]} for n, m in (("a", 5.0), ("b", 6.0), ("c", 30.0))]
    row = X.comparison_rows({"2026-03": 8.0}, peers)[0]
    assert (row["avg"], row["mean"], row["diff"]) == (6.0, 13.7, 2.0)


def test_seven_month_gap_is_not_matched():
    rows = X.comparison_rows({"2026-03": 10.0}, [{"name": "a", "series": [{"year": "2026-10", "margin": 5.0}]}])
    assert rows[0]["avg"] is None


def _peer(values: dict) -> list[dict]:
    return [{"name": "a", "series": [{"year": y, "margin": 5.0} for y in values]}]


@pytest.mark.parametrize("values, rating, years", [
    ({f"{y}-03": 10.0 for y in range(2020, 2027)}, "強い", 7),
    ({f"{y}-03": 10.0 for y in range(2021, 2027)}, "弱い", 6),
    ({"2025-03": 10.0, "2026-03": 4.0}, "なし", 0),
    ({"2024-03": 10.0, "2025-03": 2.0, "2026-03": 10.0}, "弱い", 1),
])
def test_margin_candidate(values, rating, years):
    cand = X.margin_candidate(X.comparison_rows(values, _peer(values)))
    assert (cand["rating"], cand["years_above"]) == (rating, years)


def test_missing_year_ends_the_run():
    values = {"2012-03": 10.0, **{f"{y}-03": 10.0 for y in range(2020, 2027)}}
    assert X.consecutive_above(X.comparison_rows(values, _peer(values))) == (7, "2026-03")


def test_no_peers_means_no_candidate():
    cand = X.margin_candidate(X.comparison_rows({"2026-03": 10.0}, []))
    assert cand["rating"] is None and not cand["fixed"]


def test_cost_rows_and_peer_average(repo):
    company = company_obj(repo)
    rows = X.cost_rows(company, I.gather_moat(company)["peer_cost"])
    assert [r["self"] for r in rows] == [True, False, False]
    assert X.cost_average(rows, "cost") == 79.0
    assert "| 競合の単純平均 | — | 79.0% | 15.0% | 6.0% |" in X.cost_table_rows(rows)


def test_cost_rows_read_ratio_columns_next_to_amount_columns(repo):
    body = ("| 会社 | 年度 | 売上高 | 売上原価 | 販管費 | 営業利益 | 売上原価率 | 販管費率 | 営業利益率 | 出典・確度 |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
            "| アルファ社（1111） | 2026/03 | 16,600 | 9,990 | 3,562 | 3,046 | 60.2%（算出 9,990÷16,600） "
            "| 21.5%（算出 3,562÷16,600） | 18.3% | 有報（一次） |\n")
    found = I.Found(I.SPEC["peer_cost"], "ok", Path("x"), "9.", body)
    [row] = X.cost_rows(company_obj(repo), found)
    assert (row["cost"], row["sga"], row["margin"]) == (60.2, 21.5, 18.3)


# ---------- check ----------

def test_check_goes_to_prepare(repo, capsys):
    code, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["next"] == "prepare" and out["result"] == "none"


def test_check_runs_three_c_first(repo, capsys):
    shutil.rmtree(repo / "companies" / "7203_toyota" / "analysis" / "three-c")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "three_c" and out["three_c"]["result"] == "none"


def test_three_c_verdict_does_not_stop(repo, capsys):
    shutil.rmtree(repo / "companies" / "7203_toyota" / "analysis" / "three-c")
    _three_c(repo, verdict="判定保留")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_check_requests_collect_for_new_sections(tmp_path, capsys):
    _company(tmp_path, retention="", pricing="", cost="")
    _three_c(tmp_path)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"
    assert {r["agent"]: r["items"] for r in out["missing_inputs"]} == {
        "collect-ir": ["事業概要: 継続率・解約率・ストック型売上の比率", "事業概要: 値上げ・価格改定の実績"],
        "collect-peers-valuation": ["競合: 売上原価率・販管費率（コスト構造）"]}


def test_new_sources_are_optional(repo, capsys):
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"  # インストールベース・セグメント・外部の評価 are not in the raw: not collected


def test_unavailable_retention_is_not_recollected_and_peer_kpi_rows_do_not_count(tmp_path, capsys):
    company = _company(tmp_path, retention="")
    _three_c(tmp_path)
    status = ("# 収集状況\n\n## 3. 未取得項目\n\n| 項目 | 理由 | 試した経路 |\n|---|---|---|\n"
              "| 顧客・人員の KPI（アルファ社）継続率 | 開示なし | 有報 |\n")
    (company / "status.md").write_text(status, encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"  # the peer's 継続率 row is not about the target's retention
    (company / "status.md").write_text(status + "| 解約率・ストック型売上の比率 | 開示なし | 説明会資料 |\n",
                                       encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"
    assert "事業概要: 継続率・解約率・ストック型売上の比率" in out["unavailable"]


def test_missing_balance_history_requests_collection_once(tmp_path, capsys):
    company = _company(tmp_path, balance=False)
    _three_c(tmp_path)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"
    assert out["missing_inputs"] == [{"agent": "collect-filings", "items": [X.ROIC_ITEM]}]
    (company / "status.md").write_text(
        "# 収集状況\n\n## 3. 未取得項目\n\n| 項目 | 理由 | 試した経路 |\n|---|---|---|\n"
        "| ROIC の財務時系列（自己資本・有利子負債） | 有報に無い | EDINET |\n", encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / "7203_toyota").mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_check_unknown_company(repo, capsys):
    code, out = run(repo, "check", "--company", "9999", capsys=capsys)
    assert code == 1 and out["company_missing"]


def test_list_shows_moat_and_three_c_state(repo, capsys):
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert (row["dir"], row["moat"], row["three_c"]) == ("7203_toyota", "none", "fresh")


# ---------- cycle ----------

def test_full_cycle_then_fresh_triggered_and_expired(repo, capsys):
    md = prepared(repo, capsys)
    text = md.read_text(encoding="utf-8")
    assert "| 2026-03 | 10 | 50 | 13.9% | +6.9pt | — | — |" in text
    assert "| 2026-03 | 10.0% | 6.0% | +4.0pt |" in text and "強い（確定）" in text
    assert "| 幅（超過利潤の大きさ） | 中 |" in text and "明確: 品質で優れる" in text
    brief = (md.parent / f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "| 継続率 | 92% | 93% |" in brief and "モート分析で確かめること: 利益率の10年推移" in brief
    assert "超過収益（入口）: 強い" in brief and "新規参入 0社、撤退 2社" in brief
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "広い" and out["backing"] == "強い" and out["trend"] == "安定"
    assert out["effective_moats"] == ["規制・特許・許認可", "スイッチングコスト"]
    result = json.loads((md.parent / f"{DAY}_moat.json").read_text(encoding="utf-8"))
    assert result["valid_until"] == "2027-10-12" and result["three_c"]["verdict"] == "明確"
    assert result["version"] == D.VERSION and result["returns"]["rating"] == "強い"
    assert result["axes"]["depth"]["rating"] == "深い"
    assert {m["type"]: m["group"] for m in result["moats"]}["ブランド"] == "無形資産"
    assert "**広い**" in md.read_text(encoding="utf-8")

    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "report_existing"
    _, out = run(repo, "check", "--company", "7203", "--date", "2027-10-13", capsys=capsys)
    assert out["result"] == "expired"

    _three_c(repo, date="2026-10-20")  # the same conclusion again
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-21", capsys=capsys)
    assert out["result"] == "fresh", out
    _three_c(repo, date="2026-10-21", verdict="あいまい")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-22", capsys=capsys)
    assert out["result"] == "triggered" and "明確 → あいまい" in out["newer_raw"][-1]


def test_newer_financials_of_the_same_period_do_not_trigger(repo, capsys):
    built(repo, capsys)
    (repo / "companies" / "7203_toyota" / "raw" / "ir" / "2026-10-15_financials-historical.md").write_text(
        _financials(SELF_MARGIN, years=range(2017, 2028)), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-16", capsys=capsys)
    assert out["result"] == "fresh", out  # STEP 1 waits for the next 有報


@pytest.mark.parametrize("moats, answers, timing, verdict", [
    (dict(switching="強", license="中"), {}, "5〜10年", "広い"),
    (dict(switching="強"), {}, "5〜10年", "広い"),  # one 強 is enough
    (dict(switching="中", license="中"), {}, "5〜10年", "広い"),
    (dict(switching="強", license="中"), {}, "5年以内", "狭い"),
    (dict(switching="強", license="中"), {"share_trend": "低下"}, "5〜10年", "狭い"),  # the trend is 縮小
    (dict(switching="強", license="中"), {"depth_rating": "浅い"}, "5〜10年", "狭い"),
    (dict(switching="中"), {}, "5〜10年", "狭い"),
    (dict(switching="弱"), {}, "5〜10年", "なし"),
    (dict(switching="不明"), {}, "5〜10年", "判定保留"),
])
def test_verdict(repo, capsys, moats, answers, timing, verdict):
    out = built(repo, capsys, rows=moat_rows(**moats), risks=risk(timing), **answers)
    assert out["verdict"] == verdict, out["verdict_reason"]


def test_no_excess_return_removes_claimed_moats(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, self_profit=4)  # ROIC 5.6% under the 7% cost of capital
    _three_c(tmp_path)
    out = built(tmp_path, capsys)
    assert out["verdict"] == "なし" and out["corrected"] and out["effective_moats"] == []
    assert out["backing"] == "なし" and out["width"] == "なし"
    md = tmp_path / out["md"]
    assert "超過収益に表れていないため除いた" in md.read_text(encoding="utf-8")


def test_pending_when_the_roic_cannot_be_computed(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, balance=False)
    _three_c(tmp_path)
    md = prepared(tmp_path, capsys, DAY, "--skip-collect")
    fill(md)
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "判定保留" and out["backing"] == "不明" and out["effective_moats"] == []


def test_no_risk_row(repo, capsys):
    out = built(repo, capsys, risks=NO_RISK)
    assert out["near_risks"] == []


# ---------- validation ----------

@pytest.mark.parametrize("rows, risks, answers, message", [
    (moat_rows().replace("ブランド", "ブランド力"), None, {}, "この順・この名前"),
    (moat_rows(brand="ある"), None, {}, "判定は 強/中/弱/該当なし/不明"),
    (moat_rows(brand="強").replace("| brief.md 2. |", "| — |", 1), None, {}, "情報源が空"),
    (moat_rows(brand="強").replace("| 数値 ブランド |", "| — |"), None, {}, "数値の痕跡が空"),
    (None, risk("3年"), {}, "時期は"),
    (None, risk(category="天災"), {}, "分類は"),
    (None, NO_RISK + "\n" + risk("5年以内"), {}, "1行だけ"),
    (None, None, {"depth_rating": "ある"}, "深さの評価は"),
    (None, None, {"reach_reason": "—"}, "拡張性の根拠が空"),
])
def test_validation(repo, capsys, rows, risks, answers, message):
    md = prepared(repo, capsys)
    fill(md, rows=rows, risks=risks, **answers)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any(message in issue for issue in out["issues"]), out


def test_forbidden_phrase_and_flags(repo, capsys):
    md = prepared(repo, capsys)
    fill(md, share_reason="おそらく安定")
    _, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert any("おそらく" in issue for issue in out["issues"])
    md.write_text(md.read_text(encoding="utf-8").replace("おそらく安定", "迷った: 安定か拡大"), encoding="utf-8")
    _, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert out["tie_breaks"] == ["シェアの推移"]


def test_second_analysis_requires_change_reason(repo, capsys):
    built(repo, capsys)
    later = "2026-11-01"
    _three_c(repo, date="2026-10-20", verdict="あいまい")  # a changed upstream conclusion re-opens the moat
    md2 = prepared(repo, capsys, later)
    assert "スイッチングコスト 強" in md2.read_text(encoding="utf-8")
    fill(md2, rows=moat_rows(switching="該当なし", license="中"))
    _, out = run(repo, "build", "--company", "7203", "--date", later, capsys=capsys)
    assert any("前回から変更" in issue for issue in out["issues"])
    md2.write_text(md2.read_text(encoding="utf-8").replace("確認した資料 スイッチングコスト", "前回から変更: 継続率が低下"),
                   encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", "--date", later, capsys=capsys)
    assert code == 0 and out["previous"]["verdict"] == "広い"


def test_results_on_the_old_scale_are_not_compared(repo, capsys):
    old = repo / "companies" / "7203_toyota" / "analysis" / "moat"
    old.mkdir(parents=True)
    (old / "2026-10-08_moat.md").write_text("# 旧\n", encoding="utf-8")
    (old / "2026-10-08_moat.json").write_text(json.dumps({
        "verdict": "なし", "valid_until": "2099-01-01", "inputs": [],
        "moats": [{"type": "スイッチングコスト", "rating": "該当なし"}], "share": {"trend": "不明"}},
        ensure_ascii=False), encoding="utf-8")
    md = prepared(repo, capsys, DAY, "--redo")
    assert "旧基準" in md.read_text(encoding="utf-8")
    values = dict(ANSWERS, **{"moat-rows": moat_rows(switching="強"), "risk-rows": risk()})
    md.write_text(FILL_ANY.sub(lambda m: m.group(0) if m.group(1) in D.BUILD_KEYS else values[m.group(1)],
                               md.read_text(encoding="utf-8")), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert "判定の基準を改めた" in md.read_text(encoding="utf-8")


def test_prepare_keeps_draft_unless_redo_and_supersedes_on_same_day_redo(repo, capsys):
    md = prepared(repo, capsys)
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:strength", "品質 <!-- FILL:strength"),
                  encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["kept"] and "品質 <!--" in md.read_text(encoding="utf-8")
    md = prepared(repo, capsys)
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and "有効" in out["error"]
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, "--redo", capsys=capsys)
    assert code == 0 and out["superseded"].endswith(f"_superseded/{DAY}-1")
    assert (repo / out["superseded"] / f"{DAY}_moat.json").exists()


# ---------- write guard ----------

def test_write_guard_protects_moat_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_moat.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    tomorrow = (dt.date.fromisoformat(DAY) + dt.timedelta(days=1)).isoformat()
    assert "完成済み分析（moat）" in G.decide("Edit", rel, repo, tomorrow)


# ---------- improvements after the 3798 run (2026-10-13) ----------

def _raw(root: Path, sub: str, name: str, text: str) -> Path:
    path = root / "companies" / "7203_toyota" / "raw" / sub / name
    path.write_text(text, encoding="utf-8")
    return path


def test_prepare_refuses_until_three_c_is_fresh(repo, capsys):
    shutil.rmtree(repo / "companies" / "7203_toyota" / "analysis" / "three-c")
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "three_c"
    assert not (repo / "companies" / "7203_toyota" / "analysis" / "moat").exists()


def test_prepare_refuses_missing_inputs_unless_collection_was_given_up(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, retention="")
    _three_c(tmp_path)
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "collect"
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, "--skip-collect", capsys=capsys)
    assert code == 0 and out["skipped_collect"] == [
        {"agent": "collect-ir", "items": ["事業概要: 継続率・解約率・ストック型売上の比率"]}]


def test_untouched_skeleton_is_regenerated_without_redo(repo, capsys):
    md = prepared(repo, capsys)
    assert "| 70.0% | 20.0% |" in md.read_text(encoding="utf-8")
    _raw(repo, "market", "2026-10-11_competitors.md",
         COST.replace("| 70.0% | 20.0% |", "| 71.0% | 19.0% |"))
    _three_c(repo, date="2026-10-11")  # the 3C has seen the new raw
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert not out["kept"] and out["regenerated"]
    assert "| 71.0% | 19.0% |" in md.read_text(encoding="utf-8")


def test_peer_updates_do_not_trigger(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    assert "input_digests" in json.loads((md.parent / f"{DAY}_moat.json").read_text(encoding="utf-8"))
    _raw(repo, "market", "2026-10-16_competitors.md", COST.replace("70.0%", "69.0%"))
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-17", capsys=capsys)
    assert out["result"] == "fresh", out


def test_new_fiscal_year_yuho_triggers(repo, capsys):
    built(repo, capsys)
    _raw(repo, "filings", "2026-10-15_2027-03_yuho.md", YUHO + "\n## 1. 主要な経営指標等の推移\n\n"
         "| 年度 | 売上高 | 営業利益 |\n|---|---|---|\n| 2027/03 | 100 | 12 |\n")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-16", capsys=capsys)
    assert out["result"] == "triggered" and any("新しい期の有報" in p for p in out["newer_raw"]), out


def test_resuming_a_started_draft_is_not_gated(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, retention="")
    _three_c(tmp_path)
    _, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, "--skip-collect", capsys=capsys)
    md = tmp_path / out["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:strength", "品質 <!-- FILL:strength"),
                  encoding="utf-8")
    shutil.rmtree(tmp_path / "companies" / "7203_toyota" / "analysis" / "three-c")  # upstream gone mid-draft
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["kept"]


@pytest.mark.parametrize("year", ["2026/03", "2026/3", "2026年3月期"])
def test_mismatch_warning_reads_year_forms(year):
    cands = {"rows": [{"year": "2026-03", "self": 10.0}],
             "costs": [{"name": "トヨタ", "self": True, "year": year, "cost": 70.0, "sga": 20.0, "margin": 10.5}]}
    assert any("2026-03" in w for w in X.warnings(cands))


def test_no_margin_column_is_not_a_warning():
    cands = {"rows": [], "costs": [{"name": "a", "self": False, "year": "2026/03", "cost": 70.0, "sga": 20.0,
                                    "margin": None}]}
    assert X.warnings(cands) == []


def test_brief_is_lighter_and_warns(tmp_path, capsys):
    _templates(tmp_path)
    cost = (COST.replace("| 販管費率 |", "| 販管費 |").replace("| 20.0% |", "| 2,000 |")
            .replace("| 15.0% |", "| 1,500 |").replace("| 10.0% | 有報（一次） |", "| 10.5% | 有報（一次） |"))
    _company(tmp_path, cost=cost)  # amounts only (no 販管費率), self margin 10.5% vs 10.0% in 2.2
    _three_c(tmp_path)
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0
    brief = (tmp_path / out["brief"]).read_text(encoding="utf-8")
    assert "| 年度 | 自社 | 同業中央値 |" not in brief and "md の 2.1" in brief
    assert any("販管費率" in w for w in out["warnings"])
    assert any("2026-03" in w and "10.0%" in w and "10.5%" in w for w in out["warnings"])
    assert "## 警告" in brief


def test_build_fills_swot_candidates_changes_and_gaps_from_the_rows(repo, capsys):
    md = prepared(repo, capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["filled_at_build"] == ["strengths", "threats", "changes", "gaps"]
    assert not set(out["fill_keys"]) & set(D.BUILD_KEYS)
    values = dict(ANSWERS, **{"moat-rows": moat_rows(switching="強", license="中"), "risk-rows": risk()})
    md.write_text(FILL_ANY.sub(lambda m: m.group(0) if m.group(1) in D.BUILD_KEYS else values[m.group(1)],
                               md.read_text(encoding="utf-8")), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    text = md.read_text(encoding="utf-8")
    assert "| SWOT の強み（S）候補 | 規制・特許・許認可（中。" in text and "／スイッチングコスト（強。" in text
    assert "（5〜10年。影響するモート:" in text and "## 10. 前回からの変更点\n\n- 初回の分析" in text
