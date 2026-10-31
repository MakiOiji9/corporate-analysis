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

import gr_doc as D  # noqa: E402
import gr_facts as F  # noqa: E402
import gr_inputs as I  # noqa: E402
import gr_metrics as X  # noqa: E402
import gr_paths as P  # noqa: E402
import gr_series as S  # noqa: E402
import growth as GR  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-19"
COLLECTED = "2026-10-01"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
YEARS = list(range(2020, 2027))
SALES = [1000, 1100, 1200, 1150, 1300, 1450, 1600]  # 2023 falls, 2024 recovers
OP = [100, 112, 125, 118, 140, 160, 180]
NI = [60, 67, 75, 70, 85, 97, 110]
EPS = [120, 134, 150, 140, 170, 194, 220]  # 0.5 million shares every year
PLAN_OP = {2021: 110, 2022: 120, 2023: 130, 2024: 125, 2025: 150, 2026: 170}

DECLINE = """## 6. 減収・減益の年の会社説明

| 年度 | 指標 | 会社の説明 | 出典 |
|---|---|---|---|
| 2023/03 | 売上高・営業利益 | 大口案件の終了（決算説明資料） | 短信 |
"""

MA = """## 7. M&A・連結範囲の変更

| 年度 | 対象 | 取得額 | 取得時の売上高（年間） | 出典 |
|---|---|---|---|---|
{rows}
"""
NO_DEAL = "| — | 該当なし（期間内の子会社取得なし） | — | — | 有報 |"


def _cols(values: list) -> str:
    return " | ".join(f"{v:,}" for v in values)


def financials(sales=SALES, eps=EPS, decline: str = DECLINE, ma: str | None = None, years=YEARS) -> str:
    head = " | ".join(f"{y}年3月期" for y in years)
    plan = []
    for y, f in PLAN_OP.items():
        if y in years:
            i = years.index(y)
            plan += [f"| {y}年3月期 | 期初予想 | {sales[i] - 50:,} | {f} | {f} | {NI[i] - 5} | {y - 1}-05-10 | 短信 |",
                     f"| | 実績 | {sales[i]:,} | {OP[i]} | {OP[i]} | {NI[i]} | | 短信 |"]
    n = len(years)
    return f"""# 財務データ時系列 — テスト

> 単位: 百万円

## 1. 損益・貸借・CF

| 項目（百万円） | {head} |
|---|{'---|' * n}
| 売上高 | {_cols(sales[:n])} |
| 営業利益 | {_cols(OP[:n])} |
| 親会社株主に帰属する当期純利益 | {_cols(NI[:n])} |
| EPS（円） | {_cols(eps[:n])} |
| 潜在株式調整後1株当たり当期純利益（円） | {_cols([1] * n)} |

## 3. 株主還元

| 年度 | 1株配当 | 配当総額 | 配当性向 | 自社株買い | 出典 |
|---|---|---|---|---|---|
| 2026/03 | 10円 | 1億円 | 20% | — | 短信 |

## 4. 会社計画（期初予想）と実績

| 対象年度 | 区分 | 売上高 | 営業利益 | 経常利益 | 純利益 | 公表日 | 出典 |
|---|---|---|---|---|---|---|---|
{chr(10).join(plan)}
| 2027年3月期 | 期初予想 | 1,800 | 200 | 200 | 120 | 2026-05-10 | 短信 |

{decline}
{MA.format(rows=NO_DEAL) if ma is None else ma}
"""


YUHO = """# 有価証券報告書 抜粋 — テスト

## 1. 主要な経営指標等の推移（連結）（p.2）

| 項目 | 2025年3月 | 2026年3月 |
|---|---|---|
| 売上高（百万円） | 1,450 | 1,600 |
| 親会社株主に帰属する当期純利益（百万円） | 97 | 110 |

## 4. 事業等のリスク（要旨）（p.10）

- 大口顧客への依存
"""


def _company(root: Path, text: str | None = None, yuho: str = YUHO) -> Path:
    company = root / "companies" / "7203_toyota"
    for sub, name, body in (("filings", f"{COLLECTED}_2026-03_yuho.md", yuho),
                            ("ir", f"{COLLECTED}_financials-historical.md", financials() if text is None else text)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(body, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _three_c(root: Path, rating: str, reason: str, date: str = "2026-10-05") -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / "three-c"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_three-c.md").write_text("# 完成\n", encoding="utf-8")
    result = {"verdict": "明確", "growth": {"rating": rating, "reason": reason}}
    (directory / f"{date}_three-c.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / ".ai" / "templates" / "growth", tmp_path / ".ai" / "templates" / "growth")
    (tmp_path / "market" / "report").mkdir(parents=True)
    _company(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = GR.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def cands_of(root: Path) -> dict:
    company = company_obj(root)
    return X.candidates(company, I.gather_growth(company))


def prepared(root: Path, capsys, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", DAY, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def fill(md: Path, cls: str = "一時") -> None:
    def answer(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("class-"):
            return cls
        return "- 初回の分析" if key in ("changes", "gaps") else f"背景 {key}（brief による）"
    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


# ---------- cells and series ----------

@pytest.mark.parametrize("label, field", [
    ("営業利益（損失）", "operating_income"), ("営業利益率", None), ("EPS（円）", "eps"),
    ("1株当たり当期純利益（円）", "eps"), ("潜在株式調整後1株当たり当期純利益", None), ("基本EPS（米ドル）", "eps"),
    ("連結範囲の変更を伴う子会社株式の取得", "acquisition"), ("連結範囲の変更を伴わない子会社株式の取得による支出", None),
    ("子会社株式の取得（連結範囲変更）", "acquisition"), ("自社株買い（CF上の支出）", "buyback"),
    ("当期純利益（損失）（親会社に帰属）", "net_income"), ("売上高の前年比", None)])
def test_field_of(label, field):
    assert S.field_of(label) == field


def test_parentheses_and_dollar_units():
    assert S.amount("(178,821)", 1e-3) == pytest.approx(-178.821)
    assert S.plain("(4.28)") == -4.28 and S.plain("94.02（分割前）") == 94.02 and S.plain("1,234.5") == 1234.5
    assert S.unit_of("項目（千米ドル）") == 1e-3 and S.unit_of("単位: 百万円") == 1.0


def test_self_series_reads_the_table_and_skips_plan(repo):
    series = S.self_series(company_obj(repo))
    assert series["sales"]["2023-03"].value == 1150 and series["eps"]["2026-03"].value == 220
    assert "2027-03" not in series["sales"]  # the plan section is not an actual


def _series(eps: dict[str, float], ni: dict[str, float]) -> S.Series:
    def values(d: dict) -> dict:
        return {y: S.Value(v, "t", True) for y, v in d.items()}
    return {"eps": values(eps), "net_income": values(ni)}


def test_split_adjustment_puts_eps_on_the_newest_basis():
    eps = {"2020-03": 100.0, "2021-03": 110.0, "2022-03": 12.0, "2023-03": 13.0}
    ni = {"2020-03": 50.0, "2021-03": 55.0, "2022-03": 60.0, "2023-03": 65.0}
    adjusted, splits, odd = S.adjusted_eps(_series(eps, ni))
    assert splits == [{"before": "2021-03", "after": "2022-03", "factor": 10.0}] and odd == []
    assert adjusted["2020-03"] == pytest.approx(10.0) and adjusted["2023-03"] == 13.0


def test_split_detection_ignores_loss_years_and_small_changes():
    eps = {"2023-12": -9.9, "2024-12": 1.64, "2025-12": 1.8}
    ni = {"2023-12": -481.6, "2024-12": 237.8, "2025-12": 280.0}
    assert S.adjusted_eps(_series(eps, ni))[1] == []


def test_three_for_two_split_and_a_loss_year_inside_it():
    eps = {"2020-03": 30.0, "2021-03": -5.0, "2022-03": 22.0}  # 3:2 split between 2020 and 2022
    ni = {"2020-03": 30.0, "2021-03": -5.0, "2022-03": 33.0}
    adjusted, splits, _ = S.adjusted_eps(_series(eps, ni))
    assert splits[0]["factor"] == 1.5
    assert adjusted["2021-03"] == pytest.approx(-5.0 / 1.5)  # the loss year is pre-split too


def test_implausible_share_jump_is_not_adjusted():
    eps = {"2020-03": 100.0, "2021-03": 0.1}
    ni = {"2020-03": 50.0, "2021-03": 55.0}
    adjusted, splits, odd = S.adjusted_eps(_series(eps, ni))
    assert splits == [] and odd[0]["before"] == "2020-03" and adjusted["2020-03"] == 100.0


def test_plan_rows_from_raw_carry_the_year(repo):
    cands = cands_of(repo)
    rows = {r["year"]: r for r in cands["step3"]["rows"]}
    assert list(rows) == [f"{y}-03" for y in PLAN_OP]
    assert rows["2023-03"]["rate"] == pytest.approx(118 / 130 * 100) and rows["2023-03"]["metric"] == "営業利益"
    assert "2027-03" not in rows  # no actual yet
    assert cands["step3"]["rating"] == "信頼できる"


# ---------- 手順1 ----------

def _rows(sales: list, eps: list, op: list | None = None, ni: list | None = None, start: int = 2020) -> list[dict]:
    op = op or sales
    ni = ni or eps
    return [{"year": f"{start + i}-03", "sales": s, "operating_income": o, "net_income": n, "eps": e,
             "acquisition": None, "buyback": None} for i, (s, e, o, n) in enumerate(zip(sales, eps, op, ni))]


@pytest.mark.parametrize("sales, eps, rating", [
    ([100, 106, 112, 119, 126], [100, 108, 117, 126, 136], "高成長"),
    ([100, 102, 104, 106, 108], [100, 101, 102, 103, 104], "安定成長"),
    ([100, 110, 120, 130, 140], [100, 101, 102, 103, 104], "安定成長"),  # sales high, EPS below 7%
    ([100, 98, 96, 95, 94], [100, 110, 120, 130, 140], "停滞・縮小"),
    ([100, 110, 120, 130, 140], [-5, 1, 2, 3, 4], None),  # the first EPS is a loss
    ([100, 110, 120, 130], [100, 110, 120, 130], None),  # 4 years
])
def test_step1_rules(sales, eps, rating):
    assert X.step1(_rows(sales, eps))["rating"] == rating


def test_step1_uses_one_window_for_every_cagr():
    rows = _rows([100, 110, 121, 133, 146, 161, 177], [None, None, 10, 11, 12, 13, 14],
                 ni=[1, 1, 10, 11, 12, 13, 14])
    for r in rows[:2]:
        r["net_income"] = None
    s1 = X.step1(rows)
    assert s1["first"] == "2022-03" and s1["sales"]["first"] == "2022-03" and s1["years"] == 5


def test_small_acquisition_outflow_is_not_material():
    rows = _rows([100, 110, 121, 133, 146], [100, 110, 121, 133, 146])
    rows[2]["acquisition"] = -0.5  # 0.4% of sales
    assert X.step4(X.step1(rows), rows, [], "ok")["checks"][1]["status"] == "問題なし"


def test_market_growth_reads_approximate_figures():
    assert X.market_growth({"growth": {"reason": "国内市場は CAGR 約5.5% の予測"}})[0] == 5.5
    assert X.market_growth({"growth": {"reason": "CAGR の記載なし"}})[0] == X.MARKET_DEFAULT


def test_step1_uses_net_income_when_eps_is_short():
    rows = _rows([100, 106, 112, 119, 126], [100, 108, 117, 126, 136])
    for r in rows[:3]:
        r["eps"] = None
    s1 = X.step1(rows)
    assert s1["eps_key"] == "net_income" and s1["rating"] == "高成長" and s1["stand_in"]


# ---------- 手順2 ----------

def test_decline_years_and_recovery():
    rows = _rows([100, 90, 95, 101, 80, 85], [10, 11, 12, 13, 14, 15])
    assert X.decline_years(rows)[0]["metrics"][0]["recovery"] == "回復"  # back above 100 two years later
    rows = _rows([100, 90, 95, 98, 101, 80, 85], [10, 11, 12, 13, 14, 15, 16])
    declines = {d["year"]: d for d in X.decline_years(rows)}
    assert list(declines) == ["2021-03", "2025-03"]
    assert declines["2021-03"]["metrics"][0]["recovery"] == "遅れて回復"  # back above 100 only in 2024
    assert declines["2025-03"]["recovery"] == "未確認"  # only one later year
    rows = _rows([100, 90, 92, 93, 94], [10, 11, 12, 13, 14])
    assert X.decline_years(rows)[0]["recovery"] == "未回復"


# ---------- 手順3 / 4 ----------

def _plan(rates: list[float]) -> list[dict]:
    return [{"year": f"{2020 + i}-03", "rate": r} for i, r in enumerate(rates)]


@pytest.mark.parametrize("rates, rating", [
    ([95, 100, 92, 88, 110], "信頼できる"), ([80, 85, 95, 70, 120], "割り引いて扱う"),
    ([100, 100, 100, 85, 80], "割り引いて扱う"), ([], None)])
def test_step3_rules(rates, rating):
    assert X.step3(_plan(rates))["rating"] == rating


def test_buyback_dependence_rejudges_with_net_income():
    rows = _rows([100, 103, 106, 109, 112], [100, 110, 121, 133, 146], ni=[100, 101, 102, 103, 104])
    s1 = X.step1(rows)
    s4 = X.step4(s1, rows, [], "ok")
    assert s4["checks"][2]["status"] == "問題あり" and s4["adjusted"]["rating"] == "安定成長"
    verdict, _ = X.judge(s1, [], s4, {})
    assert verdict == "普通"


def test_ma_dependence_uses_the_organic_cagr():
    rows = _rows([100, 110, 121, 133, 300], [100, 110, 121, 133, 146], op=[10, 11, 12, 14, 40])
    rows[4]["acquisition"] = -500.0
    s1 = X.step1(rows)
    deals = [{"year": "2024-03", "target": "買収先", "sales": 150.0}]
    check = X.step4(s1, rows, deals, "ok")["checks"][1]
    assert check["status"] == "問題あり" and check["organic"] == pytest.approx(((150 / 100) ** 0.25 - 1) * 100)
    unknown = X.step4(s1, rows, [], "ok")["checks"][1]
    assert unknown["status"] == "不明"  # an outflow without the acquired company's sales


def test_margin_check_for_losses():
    rows = _rows([100, 110, 121, 133, 146], [1, 2, 3, 4, 5], op=[-10, -8, -6, -4, -2])
    assert X.step4(X.step1(rows), rows, [], "ok")["checks"][0]["status"] == "問題あり"
    rows = _rows([100, 110, 121, 133, 146], [1, 2, 3, 4, 5], op=[-10, -8, 1, 4, 9])
    assert X.step4(X.step1(rows), rows, [], "ok")["checks"][0]["status"] == "問題なし"


# ---------- 手順5 ----------

GOOD_S1 = {"rating": "高成長", "basis": "b"}
CLEAN_S4 = {"adjusted": None, "problems": [], "unknown": []}
DECLINE_2023 = [{"year": "2023-03"}]


@pytest.mark.parametrize("s1, s4, classes, verdict", [
    (GOOD_S1, CLEAN_S4, {"2023-03": "一時"}, "良好"),
    (GOOD_S1, CLEAN_S4, {"2023-03": "構造"}, "懸念"),
    (GOOD_S1, CLEAN_S4, {"2023-03": "不明"}, "懸念"),       # an unknown cause is read as 構造
    ({"rating": "停滞・縮小", "basis": "b"}, CLEAN_S4, {"2023-03": "一時"}, "懸念"),
    ({"rating": None, "basis": "b"}, CLEAN_S4, {"2023-03": "一時"}, "判定保留"),
    ({"rating": None, "basis": "b"}, CLEAN_S4, {"2023-03": "構造"}, "懸念"),
    (GOOD_S1, {**CLEAN_S4, "problems": ["p"]}, {"2023-03": "不明"}, "懸念"),
    (GOOD_S1, {**CLEAN_S4, "unknown": ["M&A"]}, {"2023-03": "一時"}, "普通"),  # unchecked quality: 問題あり
    (GOOD_S1, {"adjusted": {"rating": "停滞・縮小", "basis": "b"}, "problems": ["p"], "unknown": []}, {}, "懸念"),
])
def test_judge(s1, s4, classes, verdict):
    assert X.judge(s1, DECLINE_2023, s4, classes)[0] == verdict


def test_consistency_with_the_market_growth():
    s1 = X.step1(_rows([100, 102, 104, 106, 108], [100, 101, 102, 103, 104]))
    rows = X.consistency(s1, {"growth": {"rating": "高", "reason": "国内市場の CAGR 9.1%予測"}})
    assert rows[0]["result"].startswith("不整合") and "9.1%" in rows[0]["step1"]
    assert X.consistency(s1, None)[0]["result"].startswith("未実施")
    assert X.consistency(s1, {"growth": {"rating": "中"}})[0]["result"].startswith("対象外")


# ---------- check ----------

def test_check_goes_to_prepare(repo, capsys):
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare" and out["missing_inputs"] == [] and out["three_c"] is None


def test_check_requests_ma_and_decline_notes(tmp_path, capsys):
    _company(tmp_path, financials(decline="", ma=""))
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    items = next(r for r in out["missing_inputs"] if r["agent"] == "collect-filings")["items"]
    assert I.SPEC["ma"].label in items and f"{X.DECLINE_ITEM}（2023-03）" in items


def test_unavailable_ma_and_decline_notes_are_not_recollected(tmp_path, capsys):
    company = _company(tmp_path, financials(decline="", ma=""))
    (company / "status.md").write_text("# s\n\n## 2. 未取得項目\n\n| 項目 | 理由 | 次回 |\n|---|---|---|\n"
                                       "| M&A・連結範囲の変更 | 開示なし | — |\n"
                                       "| 減収・減益の説明（2023年3月期） | 開示なし | — |\n", encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_short_history_requests_filings_then_holds(tmp_path, capsys):
    shutil.copytree(REPO / ".ai" / "templates" / "growth", tmp_path / ".ai" / "templates" / "growth")
    _company(tmp_path, financials(years=YEARS[-4:], sales=SALES[-4:], eps=EPS[-4:]))
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert X.OWN_ITEM in next(r for r in out["missing_inputs"] if r["agent"] == "collect-filings")["items"]
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "collect"
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, "--skip-collect", capsys=capsys)
    assert code == 0 and out["candidate"]["verdict"] == "判定保留"


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / "7203_toyota").mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_list_shows_state_and_upstream(repo, capsys):
    _three_c(repo, "高", "CAGR 9.1%")
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert row["growth"] == "none" and row["three_c"]["market_growth"] == "高" and row["swot"] is None


# ---------- prepare / build ----------

def test_skeleton_has_numbers_and_fill_keys(repo, capsys):
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["decline_years"] == ["2023-03"]
    assert out["fill_keys"][:3] == ["reason-2023-03", "class-2023-03", "swot-2023-03"]
    assert out["cagr"]["sales"] == pytest.approx(8.1, abs=0.05) and out["candidate"]["step1"] == "高成長"
    text = (repo / out["md"]).read_text(encoding="utf-8")
    assert "| 手順1の判定 | 高成長（確定）" in text and "| 手順3の判定 | 信頼できる（確定）" in text
    assert "売上高 回復（2024-03）" in text
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "大口案件の終了" in brief and "| 項目（百万円） |" not in brief


def test_full_cycle_then_fresh_and_triggered(repo, capsys):
    _three_c(repo, "高", "CAGR 5.0%")
    md = prepared(repo, capsys)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and "FILL" in out["issues"][0]
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "良好" and out["temporary_years"] == ["2023-03"]
    assert out["consistency"] == ["市場成長性が高い ⇔ 売上成長: 整合"]
    text = md.read_text(encoding="utf-8")
    assert "| 成長性 | **良好**:" in text and "一時 2023-03" in text
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["step1"]["rating"] == "高成長" and result["declines"][0]["class"] == "一時"
    assert result["step3"]["rating"] == "信頼できる"
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "report_existing"
    newer = repo / "companies" / "7203_toyota" / "raw" / "ir" / "2026-10-25_financials-historical.md"
    newer.write_text(financials(sales=SALES[:-1] + [1500]), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-26", capsys=capsys)
    assert out["result"] == "fresh", out  # a correction inside the same period waits for the next results
    filings = repo / "companies" / "7203_toyota" / "raw" / "filings"
    filings.mkdir(parents=True, exist_ok=True)
    (filings / "2026-10-27_2027-03_yuho.md").write_text("# 有価証券報告書\n", encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-28", capsys=capsys)
    assert out["result"] == "triggered" and out["next"] == "prepare"


@pytest.mark.parametrize("cls, verdict", [("構造", "懸念"), ("不明", "懸念")])
def test_class_decides_the_verdict(repo, capsys, cls, verdict):
    fill(prepared(repo, capsys), cls)
    _, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert out["verdict"] == verdict
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert bool(result["conservative"]) == (cls == "不明")


def test_build_rejects_bad_class_removed_row_and_words(repo, capsys):
    md = prepared(repo, capsys)
    fill(md, "たぶん一時")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("分類は" in i for i in out["issues"])
    text = md.read_text(encoding="utf-8").replace("たぶん一時", "一時")
    md.write_text("\n".join(line for line in text.splitlines() if not line.startswith("| 2023-03 | 売上高")),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("表に行がない" in i or "2章の年度" in i for i in out["issues"])
    md.write_text(text.replace("背景 report-points（brief による）", "おそらく伸びる"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("おそらく" in i for i in out["issues"])


def test_build_rejects_temporary_for_an_unrecovered_year(tmp_path, capsys):
    shutil.copytree(REPO / ".ai" / "templates" / "growth", tmp_path / ".ai" / "templates" / "growth")
    sales = [1000, 1100, 1200, 1150, 1160, 1170, 1180]  # never back to 1,200
    _company(tmp_path, financials(sales=sales), yuho=YUHO.replace("| 売上高（百万円） | 1,450 | 1,600 |\n", ""))
    md = prepared(tmp_path, capsys)
    fill(md)
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("未回復" in i for i in out["issues"])


# ---------- improvements: recent trend, conservative rule, progress, provenance, splits ----------

def test_recent_margin_decline_is_a_quality_problem():
    sales = [100, 110, 121, 133, 146, 176, 212]  # the last 3 years grow faster than before
    op = [10, 12, 14, 17, 20, 23, 26]  # long-term op CAGR above sales, the last 3 years below
    rows = _rows(sales, [10, 12, 14, 17, 20, 23, 26], op=op)
    s1 = X.step1(rows)
    check = X.step4(s1, rows, [], "ok")["checks"][0]
    assert check["status"] == "問題あり" and "直近3年" in check["problem"] and len(check["gaps"]) == 2


@pytest.mark.parametrize("op_last, verdict, moved", [(149.0, "普通", True), (160.0, "良好", False)])
def test_close_margin_comparison_moves_good_to_fair(op_last, verdict, moved):
    sales = [100, 110, 121, 133, 146]
    rows = _rows(sales, [100, 110, 121, 135, 150], op=[100, 110, 121, 133.5, op_last])
    s1 = X.step1(rows)
    s4 = X.step4(s1, rows, [], "ok")
    got, why, reasons = X.decide(s1, [], s4, {})
    assert got == verdict and bool(reasons) == moved
    if moved:
        assert "保守的に 良好 から1段階下げた" in why


def test_close_to_zero_growth_moves_fair_to_concern():
    s1 = X.step1(_rows([100, 100.1, 100.2, 100.3, 100.4], [100, 101, 102, 103, 104]))
    assert X.conservative("普通", s1, {"checks": [{}, {}, {}]}) != []


def test_near_zero_growth_moves_good_to_fair_too():
    s1 = X.step1(_rows([100, 100.1, 100.2, 100.3, 100.4], [100, 101, 102, 103, 104]))
    assert any("0% に近い" in r for r in X.conservative("良好", s1, {"checks": [{}, {}, {}]}))


def test_progress_rates_need_a_positive_base():
    assert F._change(-5, -10) is None and F._change(5, -10) is None and round(F._change(110, 100), 1) == 10.0
    assert F._share(-1, 100) is None and F._share(10, -50) is None and F._share(25, 100) == 25.0


def test_progress_is_none_once_the_full_year_is_reported(tmp_path):
    company = tmp_path / "companies" / "7203_toyota"
    (company / "data").mkdir(parents=True)
    (company / "data" / "tdnet_facts.csv").write_text(
        "doc_id,document,filing_date,fiscal_year_end,context,element,value,unit\n"
        "1,短信,2026-02-10,2026-03-31,CurrentAccumulatedQ3Duration_ConsolidatedMember_ResultMember,NetSales,90,百万円\n"
        "2,短信,,,CurrentAccumulatedQ1Duration_ConsolidatedMember_ResultMember,NetSales,10,百万円\n",
        encoding="utf-8")
    c = P.Company(tmp_path, company)
    assert F.current_progress(c, {"sales": {}})["quarter"] == 3  # the blank fiscal year row is skipped
    assert F.current_progress(c, {"sales": {"2026-03": S.Value(120, "t", True)}}) is None


def test_number_check_reads_full_width_digits():
    parsed = {"declines": [], "structural": "", "mtp": "", "drivers": "１２．５％", "consistency_comment": "",
              "report_points": "", "step3_hint": "", "step2_checks": "", "triggers": "", "changes": [], "gaps": []}
    assert D.check_numbers(parsed, "なし") and not D.check_numbers(parsed, "12.5")


def test_number_check_refuses_numbers_not_in_the_brief():
    parsed = {"declines": [], "structural": "変化なし", "mtp": "—", "drivers": "受注高 18,135百万円 +27.3%",
              "consistency_comment": "整合", "report_points": "売上 CAGR 15.1%", "step3_hint": "予想 3,700百万円",
              "step2_checks": "採用費 848百万円", "triggers": "5% を下回れば", "changes": ["初回"], "gaps": ["なし"]}
    issues = D.check_numbers(parsed, "受注高 18,135 (+27.3%) 売上 CAGR 15.1% 経常利益 3,700")
    assert len(issues) == 1 and "848" in issues[0] and issues[0].startswith("7. STEP 2")


def test_split_records_and_matching(tmp_path):
    company = tmp_path / "companies" / "7203_toyota"
    (company / "raw" / "ir").mkdir(parents=True)
    (company / "status.md").write_text("| 2025-10-01 | 株式分割（1株→10株） | 1株指標は分割考慮後 |\n", encoding="utf-8")
    (company / "raw" / "ir" / "2026-10-01_financials-historical.md").write_text(
        "注: 2013年10月の1:100分割後の値\n", encoding="utf-8")
    records = F.split_records(P.Company(tmp_path, company))
    assert {(r["factor"], r["date"]) for r in records} == {(10.0, "2025-10-01"), (100.0, "2013-10")}
    note = X.split_note({"before": "2018-03", "after": "2019-03", "factor": 10.0},
                        F.match_split({"factor": 10.0}, records))
    assert note["matched"] and "2025-10-01 の株式分割（1株→10株、status.md）" in note["text"]
    assert not X.split_note({"before": "a", "after": "b", "factor": 3.0}, None)["matched"]


# ---------- regression on the real ULS data (tests/fixtures/growth_uls, frozen 2026-10-21) ----------

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "growth_uls"


@pytest.fixture
def uls(tmp_path: Path) -> Path:
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    shutil.copytree(REPO / ".ai" / "templates" / "growth", tmp_path / ".ai" / "templates" / "growth")
    return tmp_path


def test_uls_regression(uls, capsys):
    company = P.Company(uls, uls / "companies" / "3798_uls-group")
    cands = X.candidates(company, I.gather_growth(company))
    s1, s4 = cands["step1"], cands["step4"]
    assert round(s1["sales"]["value"], 1) == 15.1 and round(s1["eps"]["value"], 1) == 16.2
    assert s1["rating"] == "高成長" and [d["year"] for d in cands["declines"]] == ["2024-03"]
    assert cands["split_notes"][0]["matched"] and cands["split_notes"][0]["record"]["date"] == "2025-10-01"
    assert round(s4["checks"][1]["organic"], 1) == 14.9 and s4["checks"][1]["status"] == "問題なし"
    assert s4["checks"][0]["status"] == "問題あり" and "直近3年" in s4["checks"][0]["problem"]
    assert cands["verdict"] == "普通" and cands["step3"]["rating"] == "信頼できる"
    progress = cands["progress"]["items"]["operating_income"]
    assert cands["progress"]["quarter"] == 1 and round(progress["yoy"], 1) == 9.5
    _, out = run(uls, "prepare", "--company", "3798", "--date", "2026-10-22", capsys=capsys)
    brief = (uls / out["brief"]).read_text(encoding="utf-8")
    assert "（減収・減益の年が無い、または2年以内に回復しているため省略）" in brief  # risks left out
    assert "採用費" in brief and "売上債権（百万）" in brief


def test_collect_hints_name_the_chapter_and_the_originals(uls, capsys):
    raw = uls / "companies" / "3798_uls-group" / "raw" / "ir" / "2026-10-21_financials-historical.md"
    raw.unlink()  # back to before the growth collection: 6・7章 missing
    _, out = run(uls, "check", "--company", "3798", "--date", "2026-10-22", capsys=capsys)
    hints = out["missing_inputs"][0]["hints"]
    assert "雛形 financials-historical.md「6. 減収・減益の年の会社説明」" in hints
    assert any(h.startswith("取得済みの原本: presentation 2024-03") for h in hints)


def test_edited_table_cannot_change_the_verdict(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    md.write_text(md.read_text(encoding="utf-8").replace("高成長（確定）", "停滞・縮小（確定）"), encoding="utf-8")
    _, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert out["verdict"] == "良好"


def test_fresh_result_is_not_redone_and_expires(repo, capsys):
    fill(prepared(repo, capsys))
    run(repo, "build", "--company", "7203", capsys=capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-20", capsys=capsys)
    assert code == 1 and "redo" in out["error"]
    later = (dt.date.fromisoformat(DAY) + dt.timedelta(days=181)).isoformat()
    _, out = run(repo, "check", "--company", "7203", "--date", later, capsys=capsys)
    assert out["result"] == "expired"


def test_untouched_draft_is_regenerated_and_started_one_kept(repo, capsys):
    md = prepared(repo, capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["regenerated"] and not out["kept"]
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:mtp", "書いた <!-- FILL:mtp"), encoding="utf-8")
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["kept"] and "書いた" in md.read_text(encoding="utf-8")


def test_write_guard_protects_growth_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_growth.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    tomorrow = (dt.date.fromisoformat(DAY) + dt.timedelta(days=1)).isoformat()
    assert "完成済み分析（growth）" in G.decide("Edit", rel, repo, tomorrow)
