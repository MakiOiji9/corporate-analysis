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

import cash_flow as CF  # noqa: E402
import cf_metrics as X  # noqa: E402
import cf_paths as P  # noqa: E402
import cf_series as S  # noqa: E402
import pf_series as PS  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
COLLECTED = "2026-10-01"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")

FINANCIALS = """# 財務データ時系列 — テスト

> 注意: 2020年3月期・2021年3月期は千円単位の有報から転記。

## 1. 10年サマリー（IRBANK、二次情報）

単位: 億円

| 年度 | 売上高 | 当期利益 | 営業CF | 投資CF（百万円） | 財務CF（百万円） |
|---|---|---|---|---|---|
| 2019/03 | 50 | 9 | 9 | -100 | -50 |
| 2020/03 | 99 | 99 | 99 | -999 | -999 |

## 4. キャッシュ・フロー（有価証券報告書の連結キャッシュ・フロー計算書）

### 4-1. 千円単位の年度

| 項目（千円） | 2020年3月期 | 2021年3月期 |
|---|---|---|
| 営業CF | 1,000,000 | 1,100,000 |
| 投資CF | △300,000 | △300,000 |
| 財務CF | △200,000 | △200,000 |
| 配当金の支払額 | △100,000 | △100,000 |
| 自己株式の取得による支出 | 記載なし | △50,000 |

### 4-2. 百万円単位の年度

| 項目（百万円） | {years_header} |
|---|{sep}
| 営業CF | {cfo} |
| 投資CF | {cfi} |
| 財務CF | {cff} |
| 有形固定資産の取得による支出 | {capex} |
| 配当金の支払額 | {div} |
| 売上債権回転日数 | {dummy} |

## 5. 株主還元

| 年度 | 1株配当 | 配当総額 | 配当性向 | 自社株買い（CF上の支出） | 出典 |
|---|---|---|---|---|---|
| 2022年3月期 | 10円 | 999百万円 | 20% | — | 短信 |

## 6. 会社計画（期初予想）と実績

| 年度 | 営業CF |
|---|---|
| 2027/03 | 9999 |
"""

YUHO = """# 有価証券報告書 抜粋 — テスト

> 単位は特記なき限り百万円。

## 1. 主要な経営指標等の推移（連結）（p.2）

| 項目 | {years_header} |
|---|{sep}
| 売上高 | {sales} |
| 親会社株主に帰属する当期純利益 | {ni} |

### 提出会社（単体）の参考指標

| 項目 | 2025年3月 | 2026年3月 |
|---|---|---|
| 当期純利益 | 1 | 1 |

## 8. 財務3表（連結、主要項目）

### 連結貸借対照表

| 項目 | 2025年3月末 | 2026年3月末 |
|---|---|---|
| 売上債権 | 2,000 | 2,100 |
| 棚卸資産 | 科目なし | 科目なし |

- 2026年3月期は大型案件の前受金が増えた

## 11. 経営方針・資本政策（p.7）

- 配当性向20%を目安とする
"""

LATER = (2022, 2023, 2024, 2025, 2026)


def _cells(values: dict) -> str:
    return " | ".join(str(values[y]) for y in LATER)


def _raw(cfo=None, cfi=None, cff=None, ni=None, sales=None, div=None) -> tuple[str, str]:
    cfo = cfo or {y: 1200 for y in LATER}
    cfi = cfi or {y: "△300" for y in LATER}
    cff = cff or {y: "△200" for y in LATER}
    ni = ni or {y: 1000 for y in LATER}
    sales = sales or {y: 10000 for y in LATER}
    div = div or {y: "△100" for y in LATER}
    sep = "---|" * len(LATER)
    financials = FINANCIALS.format(years_header=" | ".join(f"{y}年3月期" for y in LATER), sep=sep, cfo=_cells(cfo),
                                   cfi=_cells(cfi), cff=_cells(cff), capex=_cells({y: "△50" for y in LATER}),
                                   div=_cells(div), dummy=_cells({y: "△999" for y in LATER}))
    yuho = YUHO.format(years_header=" | ".join(f"{y}年3月" for y in LATER), sep=sep, sales=_cells(sales), ni=_cells(ni))
    return financials, yuho


def _company(root: Path, collected: str = COLLECTED, **raw) -> Path:
    company = root / "companies" / "7203_toyota"
    financials, yuho = _raw(**raw)
    for sub, name, text in (("filings", f"{collected}_2026-03_yuho.md", yuho),
                            ("ir", f"{collected}_financials-historical.md", financials)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _profitability(root: Path, verdict: str, source: str = "本業由来", date: str = "2026-10-05") -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / "profitability"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_profitability.md").write_text("# 完成\n", encoding="utf-8")
    result = {"verdict": verdict, "verdict_reason": "理由", "step3": {"source": source},
              "handoff": {"step2_checks": "純利益が営業CFで裏付けられるか"}}
    (directory / f"{date}_profitability.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _templates(root: Path) -> None:
    shutil.copytree(REPO / ".ai" / "templates" / "cash-flow", root / ".ai" / "templates" / "cash-flow")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    (tmp_path / "market" / "report").mkdir(parents=True)
    _company(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = CF.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def cands_of(root: Path) -> dict:
    return X.candidates(company_obj(root))


def prepared(root: Path, capsys, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", DAY, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def fill(md: Path) -> None:
    def answer(m: re.Match) -> str:
        return "- 初回の分析" if m.group(1) in ("changes", "gaps") else f"背景 {m.group(1)}（brief による）"
    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


# ---------- cells and series ----------

def test_paren_negative_and_labels():
    assert PS.amount("(164,402)", 1.0) == -164402
    assert PS.amount("(4.28)", 1.0) == pytest.approx(-4.28)
    assert PS.amount("△98", 1.0) == -98 and PS.amount("1,200（百万円）", 1e-3) == pytest.approx(1200)
    assert PS.field_of("営業CF") is None  # the profitability labels are unchanged
    assert PS.field_of("**営業CF**", S.CF_FIELDS) == "cfo"
    assert PS.field_of("売上債権の増減額", S.CF_FIELDS) == "receivables_change"
    assert PS.field_of("売上債権の増減額") is None and PS.field_of("税金等調整前当期純利益") is None  # profitability
    assert PS.field_of("税金等調整前当期純利益", S.CF_FIELDS) == "pretax"
    assert PS.field_of("売上債権", S.CF_FIELDS) == "receivables"
    assert PS.field_of("自社株買い（CF上の支出）", S.CF_FIELDS) == "buybacks"
    assert PS.field_of("連結範囲の変更を伴わない子会社株式の取得による支出", S.CF_FIELDS) is None


def test_series_units_primary_and_positive_outflows(repo):
    series = S.self_series(company_obj(repo))
    assert series["cfo"]["2020-03"].value == pytest.approx(1000) and series["cfo"]["2020-03"].primary  # 千円, not IRBANK
    assert series["cfi"]["2019-03"].value == -100 and not series["cfi"]["2019-03"].primary  # 百万円 column header
    assert series["cfo"]["2019-03"].value == 900  # 億円
    assert series["dividends"]["2022-03"].value == 100  # the CF line wins over 配当総額 999
    assert series["buybacks"]["2021-03"].value == pytest.approx(50) and "2020-03" not in series["buybacks"]
    assert series["capex"]["2026-03"].value == 50
    assert series["net_income"]["2026-03"].value == 1000  # not the 単体 1
    assert series["receivables"]["2026-03"].value == 2100 and "2026-03" not in series["inventories"]
    assert "2027-03" not in series["cfo"]  # plan section skipped


def test_tdnet_dividend_is_only_a_fallback(repo):
    data = repo / "companies" / "7203_toyota" / "data"
    data.mkdir()
    (data / "tdnet_facts.csv").write_text(
        "element,context,fiscal_year_end,value\n"
        "TotalDividendPaidAnnual,CurrentYearDuration_AnnualMember_NonConsolidatedMember_ResultMember,2026-03-31,555\n"
        "TotalDividendPaidAnnual,PriorYearDuration_AnnualMember_NonConsolidatedMember_ResultMember,2019-03-31,77\n"
        "CashFlowsFromOperatingActivities,CurrentYearDuration_ConsolidatedMember_ResultMember,2026-03-31,1300\n",
        encoding="utf-8")
    series = S.self_series(company_obj(repo))
    assert series["dividends"]["2026-03"].value == 100  # the CF line, not the declared 555
    assert series["dividends"]["2018-03"].value == 77  # nothing else for that year
    assert series["cfo"]["2026-03"].value == 1300  # 短信 first


# ---------- the steps ----------

def _rows(cfo: list, cfi: list | None = None, cff: list | None = None, ni: list | None = None,
          sales: list | None = None, div: list | None = None, buy: list | None = None) -> list[dict]:
    n = len(cfo)
    cfi = cfi or [-300.0] * n
    cff = cff or [-200.0] * n
    ni = ni or [1000.0] * n
    sales = sales or [10000.0] * n
    div = div or [100.0] * n
    buy = buy or [None] * n
    return [{"year": f"{2017 + i}-03", "cfo": cfo[i], "cfi": cfi[i], "cff": cff[i], "fcf": cfo[i] + cfi[i],
             "net_income": ni[i], "ratio": cfo[i] / ni[i] if ni[i] > 0 else None, "sales": sales[i],
             "capex": None, "acquisitions": None, "dividends": div[i], "buybacks": buy[i], "primary": True,
             "source": "t", "pretax": None, "depreciation": None, "receivables_change": None,
             "inventories_change": None, "taxes_paid": None} for i in range(n)]


def test_declared_dividend_in_an_earlier_file_does_not_beat_the_cash_paid(repo):
    yuho = repo / "companies" / "7203_toyota" / "raw" / "filings" / f"{COLLECTED}_2026-03_yuho.md"
    yuho.write_text(yuho.read_text(encoding="utf-8").replace(
        "| 親会社株主に帰属する当期純利益 |", "| 配当総額 | 888 | 888 | 888 | 888 | 888 |\n"
        "| 親会社株主に帰属する当期純利益 |"), encoding="utf-8")
    series = S.self_series(company_obj(repo))  # the yuho is read before the 財務時系列
    assert series["dividends"]["2026-03"].value == 100 and "dividends_declared" not in series


def test_recovery_must_be_the_next_fiscal_year():
    rows = _rows([1, -1, 1, 1, 1])
    gapped = rows[:2] + [dict(r, year=f"{2020 + i}-03") for i, r in enumerate(rows[2:])]  # 2018 -> 2020
    assert X.step1(gapped)["rating"] == "懸念"


@pytest.mark.parametrize("cfo, rating", [
    ([1, 1, 1, 1, 1], "良好"),
    ([1, -1, 1, 1, 1], "普通"),  # once, recovered the next year
    ([1, 1, 1, 1, -1], "懸念"),  # once, but the latest year
    ([1, -1, -1, 1, 1], "懸念"),  # twice
    ([1, 1, 1, 1], None)])
def test_step1_rules(cfo, rating):
    assert X.step1(_rows(cfo))["rating"] == rating


def test_step2_rules():
    assert X.step2(_rows([1200] * 5))["rating"] == "良好"
    # cumulative plus, but most years negative
    assert X.step2(_rows([1200] * 5, cfi=[-100, -1300, -1300, -1300, -100]))["rating"] == "普通"
    # cumulative minus: a growth phase (heavy investment, sales +10%/yr, rising operating CF) is 普通
    growth = _rows([500, 600, 700, 800, 900], cfi=[-1000] * 5, sales=[100 * 1.1 ** i for i in range(5)])
    s2 = X.step2(growth)
    assert s2["rating"] == "普通" and s2["growth"]["met"] and s2["growth"]["sales_cagr"] == 10.0
    # the same without sales growth is 懸念
    assert X.step2(_rows([500, 600, 700, 800, 900], cfi=[-1000] * 5))["rating"] == "懸念"
    assert X.step2(_rows([1] * 4))["rating"] is None


@pytest.mark.parametrize("cfo, ni, rating, loss", [
    ([1000] * 5, [1000] * 5, "良好", False),
    ([900] * 5, [1000] * 5, "普通", False),
    ([700] * 5, [1000] * 5, "懸念", False),
    ([1000] * 5, [1000, 1000, -500, 1000, 1000], "良好", False),  # a loss year: cumulative 5000 / 3500
    ([100] * 5, [-1000, -1000, 100, 100, 100], None, True)])
def test_step3_rules(cfo, ni, rating, loss):
    series = {"sales": {}, "receivables": {}, "inventories": {}}
    s3 = X.step3(_rows(cfo, ni=ni), series)
    assert s3["rating"] == rating and s3["loss"] is loss


def test_step3_flags_receivables_growing_faster_than_sales():
    rows = _rows([700] * 5)
    first, last = rows[0]["year"], rows[-1]["year"]
    series = {"sales": {first: PS.Value(100, "t", True), last: PS.Value(110, "t", True)},
              "receivables": {first: PS.Value(10, "t", True), last: PS.Value(20, "t", True)},
              "inventories": {}}
    s3 = X.step3(rows, series)
    assert s3["rating"] == "懸念" and s3["flagged"] == ["売上債権"]


def test_step4_patterns_and_ties():
    assert X.step4(_rows([1] * 5))["rating"] == "良好"
    # growth years (+,−,+) twice and 良好 twice: the tie goes to the more conservative 普通
    assert X.step4(_rows([1] * 4, cff=[1, 1, -1, -1]))["rating"] == "普通"
    assert X.step4(_rows([-1, -1, 1], cfi=[1, -1, -1], cff=[1, 1, -1]))["rating"] == "懸念"
    assert X.PATTERNS[("+", "+", "+")][0] == "普通"
    assert X.step4(_rows([1, 1]))["rating"] is None


def test_step5_rules():
    assert X.step5(_rows([1200] * 5))["rating"] == "問題なし"
    over = X.step5(_rows([500] * 5, div=[400] * 5))  # FCF 200, returns 400 every year
    assert over["rating"] == "注意" and len(over["over_years"]) == 5
    assert X.step5(_rows([1200] * 5, div=[0] * 5, buy=[0] * 5))["rating"] == "対象外"
    assert X.step5(_rows([1200] * 5, div=[None] * 5))["rating"] == "不明"
    # buybacks known, dividends missing: the missing line counts as 0
    assert X.step5(_rows([1200] * 5, div=[None] * 5, buy=[50] * 5))["total_return"] == 250


@pytest.mark.parametrize("ratings, s5, loss, verdict", [
    (("良好", "良好", "良好", "良好"), "問題なし", False, "良好"),
    (("良好", "良好", "良好", "良好"), "注意", False, "普通"),
    (("良好", "普通", "良好", "良好"), "問題なし", False, "普通"),
    (("良好", "良好", None, "良好"), "問題なし", True, "普通"),  # 純損失
    (("良好", "良好", None, "良好"), "問題なし", False, "判定保留"),  # 材料不足
    ((None, "良好", "良好", "良好"), "問題なし", False, "判定保留"),
    ((None, "良好", "良好", "懸念"), "問題なし", False, "懸念"),
    (("良好", "良好", "懸念", "良好"), "問題なし", False, "懸念")])
def test_judge(ratings, s5, loss, verdict):
    steps = [{"rating": r, "basis": "b"} for r in ratings]
    steps[2]["loss"] = loss
    got, _ = X.judge(*steps, {"rating": s5})
    assert got == verdict


def _wc(sales: float | None, receivables: float | None) -> list[dict]:
    return [{"field": "sales", "name": "売上高", "cagr": sales},
            {"field": "receivables", "name": "売上債権", "cagr": receivables},
            {"field": "inventories", "name": "棚卸資産", "cagr": None}]


def test_relation_rows():
    s3 = {"rating": "懸念", "ratio": 0.7, "working_capital": _wc(10.0, 15.0)}
    rows = X.relation({"rating": "懸念"}, s3, {"verdict": "良好", "step3": {"source": "本業由来"}},
                      {"rating": "注意"}, {"verdict": "良好"}, {"verdict": "良好", "step1": {"net_cash": -5.0}})
    assert [r["check"] for r in rows] == ["収益性が良好 ⇔ 利益の質", "ROE が本業由来 ⇔ 営業CF の安定",
                                          "成長性 ⇔ 運転資本", "安全性 ⇔ 還元・FCF"]
    assert rows[0]["result"].startswith("不整合") and rows[1]["result"].startswith("不整合")
    assert rows[2]["result"].startswith("要確認（成長が売上債権") and rows[3]["result"].startswith("不整合")
    rows = X.relation({"rating": "良好"}, {"rating": "良好", "ratio": 1.2, "working_capital": _wc(10.0, 5.0)}, None,
                      {"rating": "注意"}, {"verdict": "普通"}, {"verdict": "良好", "step1": {"net_cash": 100.0}})
    assert rows[2]["result"] == "整合" and rows[3]["result"].startswith("整合（手元資金")
    rows = X.relation({"rating": "良好"}, {"rating": "良好", "ratio": 1.2, "working_capital": _wc(10.0, 5.0)}, None)
    assert all(r["result"].startswith("未実施") for r in rows)


def test_cash_gap_rows_and_main_cause():
    rows = _rows([800] * 5)
    rows[-1] = {**rows[-1], "pretax": 1400.0, "depreciation": 100.0, "receivables_change": -350.0,
                "taxes_paid": -500.0}
    gaps = X.cash_gap_rows(rows, [r["year"] for r in rows])
    assert gaps[0]["items"] is None and gaps[0]["gap"] == -200
    last = gaps[-1]
    assert last["items"]["tax_gap"] == -100  # paid 500, booked 400 (1,400 - 1,000)
    assert last["other"] == pytest.approx(-200 - (100 - 350 - 100))
    assert last["main"] == "売上債権の増減"


def test_step3_takes_the_lower_of_average_and_cumulative():
    # a tiny net income in one year lifts the plain average (1000x) but not the cumulative ratio
    s3 = X.step3(_rows([1000, 300, 300, 300, 300], ni=[1, 500, 500, 500, 500]), {"sales": {}, "receivables": {},
                                                                                "inventories": {}})
    assert s3["average"] > 100 and s3["cumulative"] == pytest.approx(1.10, abs=0.01)
    assert s3["ratio"] == s3["cumulative"] and s3["rating"] == "良好" and "低い方" in s3["method"]
    s3 = X.step3(_rows([600, 700, 800, 1000, 1000], ni=[1000] * 5), {"sales": {}, "receivables": {},
                                                                      "inventories": {}})
    assert s3["below_text"] == "2017-03 0.60倍、2018-03 0.70倍"
    assert s3["without_oldest"] == 0.88 and "2017-03（0.60倍）を除いた4年の平均は 0.88倍" in s3["without_oldest_text"]
    assert s3["recent_text"].startswith("2020-03 1.00倍、2021-03 1.00倍（いずれも 1.0倍以上）")


def test_pattern_wording_follows_the_financing_outflow():
    rows = _rows([1000] * 3, cfi=[-100, 50, -100], cff=[-300, -300, -300], div=[250, 100, None], buy=[None, 0, None])
    states = [p["state"] for p in X.pattern_rows(rows)]
    assert "主に株主還元" in states[0] and "主に借入の返済など" in states[1] and "主に返済・還元" in states[2]
    assert "投資CF がプラス（資産の売却・回収）" in states[1] and "事業再編期の型" in states[1]
    assert [p["rating"] for p in X.pattern_rows(rows)] == ["良好", "普通", "良好"]  # the framework's ratings stay


def test_breakdown_request_only_when_step3_is_a_concern(tmp_path, capsys):
    company = _company(tmp_path, cfo={y: 700 for y in LATER})  # 0.70x: 懸念, no CF-statement breakdown
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    filings = next(r for r in out["missing_inputs"] if r["agent"] == "collect-filings")
    assert filings["items"] == [X.BREAKDOWN_ITEM]
    (company / "status.md").write_text("# s\n\n## 2. 未取得項目\n\n| 項目 | 理由 | 次回 |\n|---|---|---|\n"
                                       "| 営業CFの内訳（2年分のみ） | 有報未取得 | — |\n", encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_zero_filled_cells_are_labelled(repo, capsys):
    text = prepared(repo, capsys).read_text(encoding="utf-8")
    assert "| 2026-03 | 100 | 0（記載なし） | 100 |" in text


def test_build_rejects_new_numbers_and_approximations(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    md.write_text(text.replace("背景 relation（brief による）", "純利益の約2割が現金を伴わない"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("概数" in i for i in out["issues"])
    md.write_text(text.replace("背景 relation（brief による）", "比率は 0.91倍"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("0.91" in i for i in out["issues"])
    md.write_text(text.replace("背景 relation（brief による）", "比率は 1.20倍で FCF 累計 4,500"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out  # numbers quoted from the md tables pass


def _other_result(root: Path, kind: str, verdict: str, date: str, extra: dict | None = None) -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / kind
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_{kind}.md").write_text("# 完成\n", encoding="utf-8")
    result = {"verdict": verdict, "verdict_reason": "理由", **(extra or {})}
    (directory / f"{date}_{kind}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def test_growth_and_safety_feed_section_7_and_trigger(repo, capsys):
    _other_result(repo, "growth", "良好", "2026-10-05")
    _other_result(repo, "safety", "良好", "2026-10-05", {"step1": {"net_cash": 3000.0}})
    md = prepared(repo, capsys)
    text = md.read_text(encoding="utf-8")
    assert "（成長性 良好）" in text and "（安全性 良好）" in text
    assert "| 安全性 ⇔ 還元・FCF | 安全性 良好（ネットキャッシュ 3,000） | 手順5 問題なし | 整合 |" in text
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    _other_result(repo, "safety", "普通", "2026-10-15", {"step1": {"net_cash": 3000.0}})
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-16", capsys=capsys)
    assert out["result"] == "triggered" and out["safety"]["verdict"] == "普通"


def test_number_check_handles_bullets_dates_and_short_values(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    # two bullets: the second one's new number must still be caught
    md.write_text(text.replace("## 9. 前回からの変更点\n\n- 初回の分析",
                               "## 9. 前回からの変更点\n\n- 初回の分析\n- 比率が 0.95倍に改善"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("0.95" in i for i in out["issues"])
    # dates, periods and 契約 are not numbers to check; a short written value does not cut the tables
    md.write_text(text.replace("背景 relation（brief による）", "2026年3月31日の第15期、契約十分、FY24。1,200")
                  .replace("背景 investment（brief による）", "1"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out


def test_main_cause_is_other_when_the_residual_dominates():
    rows = _rows([500] * 5)
    rows[-1] = {**rows[-1], "pretax": 1000.0, "depreciation": 10.0, "receivables_change": -20.0, "taxes_paid": 0.0}
    last = X.cash_gap_rows(rows, [r["year"] for r in rows])[-1]
    assert last["other"] == pytest.approx(-490) and last["main"] == X.OTHER_MAIN


def test_relation_survives_partial_jsons():
    rows = X.relation({"rating": "良好"}, {"rating": "良好", "ratio": 1.2}, None, {"rating": "注意"},
                      {"verdict": "良好"}, {"verdict": "良好", "step1": {"net_cash": "n/a"}})
    assert rows[2]["result"].startswith("判断できない") and rows[3]["result"].startswith("不整合")


def test_brief_keeps_only_the_capex_subsection(repo, capsys):
    yuho = repo / "companies" / "7203_toyota" / "raw" / "filings" / f"{COLLECTED}_2026-03_yuho.md"
    yuho.write_text(yuho.read_text(encoding="utf-8") + "\n## 7. 従業員数・設備投資\n\n### 従業員\n\n| 区分 | 人数 |\n"
                    "|---|---|\n| 合計 | 820 |\n\n### 設備投資\n\n- 本社増床 283百万円\n", encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "本社増床 283百万円" in brief and "| 合計 | 820 |" not in brief


def test_borderline():
    s2 = {"total": 10.0, "window": ["2020-03"]}
    s5 = {"total_fcf": 100.0, "total_return": 105.0, "rating": "問題なし"}
    found = X.borderline(s2, {"ratio": 0.82}, s5, [{"year": "2020-03", "cfo": 1000.0}])
    assert [f[:3] for f in found] == ["手順3", "手順2", "手順5"]


# ---------- the whole series ----------

def test_candidates_from_the_raw(repo):
    cands = cands_of(repo)
    assert cands["rows"][0]["year"] == "2019-03" and len(cands["rows"]) == 8
    assert cands["step1"]["rating"] == "良好" and cands["step2"]["rating"] == "良好"
    assert cands["step3"]["ratio"] == 1.2 and cands["step4"]["rating"] == "良好"
    assert cands["step5"]["rating"] == "問題なし" and cands["verdict"] == "良好"
    assert X.warnings(cands) == ["二次情報（集計サイト）の値を使った年: 2019-03、2020-03"]


def test_unit_jump_warning():
    assert any("100倍超" in w for w in X.warnings({"rows": _rows([1000, 1, 1000, 1000, 1000])}))


# ---------- check ----------

def test_check_goes_to_prepare(repo, capsys):
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare" and out["missing_inputs"] == [] and out["profitability"] is None


def test_short_history_requests_filings_once(tmp_path, capsys):
    company = _company(tmp_path)
    (company / "raw" / "ir" / f"{COLLECTED}_financials-historical.md").unlink()
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"
    filings = next(r for r in out["missing_inputs"] if r["agent"] == "collect-filings")
    assert X.OWN_ITEM in filings["items"] and X.RETURN_ITEM in filings["items"]
    (company / "status.md").write_text("# s\n\n## 2. 未取得項目\n\n| 項目 | 理由 | 次回 |\n|---|---|---|\n"
                                       "| 収益性の財務時系列（0年分のみ） | 上場前 | — |\n"
                                       "| 株主還元（配当なし） | 無配 | — |\n", encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_prepare_refuses_until_collected_then_skip_collect(tmp_path, capsys):
    _templates(tmp_path)
    company = _company(tmp_path)
    (company / "raw" / "ir" / f"{COLLECTED}_financials-historical.md").unlink()
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "collect"
    text = prepared(tmp_path, capsys, "--skip-collect").read_text(encoding="utf-8")
    assert "営業CF が取れた年が 0 年" in text


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / "7203_toyota").mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_list_shows_state_and_profitability(repo, capsys):
    _profitability(repo, "良好")
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert row["cash_flow"] == "none" and row["profitability"]["verdict"] == "良好"


# ---------- prepare / build ----------

def test_skeleton_has_numbers_and_fill_only_for_background(repo, capsys):
    text = prepared(repo, capsys).read_text(encoding="utf-8")
    assert "| 手順1の判定 | 良好（確定）" in text and "| 手順4の判定 | 良好（確定）" in text
    assert "| 営業CF がマイナスの年の背景 | 該当なし" in text
    assert sorted(set(FILL_ANY.findall(text))) == sorted(
        ["investment", "quality-gap", "relation", "report-points", "capital-policy", "step2-checks", "triggers",
         "changes", "gaps"])
    assert "| 2026-03 | + | − | − | 本業で稼ぎ" in text


def test_negative_year_gets_a_fill(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, cfo={2022: 1200, 2023: "△100", 2024: 1200, 2025: 1200, 2026: 1200})
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["fill_keys"][0] == "negative-cfo" and out["negative_years"] == ["2023-03"]
    assert out["candidate"]["step1"] == "普通"


def test_brief_has_notes_not_tables(repo, capsys):
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "大型案件の前受金" in brief and "配当性向20%を目安" in brief
    assert "| 営業CF |" not in brief


def test_full_cycle_then_fresh_and_triggered(repo, capsys):
    _profitability(repo, "良好")
    md = prepared(repo, capsys)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and "FILL" in out["issues"][0]
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "良好" and out["relation"][0] == "収益性が良好 ⇔ 利益の質: 整合"
    assert "| キャッシュフロー | **良好**:" in md.read_text(encoding="utf-8")
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["step3"]["ratio"] == 1.2 and result["handoff"]["triggers"].startswith("背景")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "report_existing"
    # a later 財務時系列 with a corrected operating CF re-opens the result
    later = repo / "companies" / "7203_toyota" / "raw" / "ir" / "2026-10-20_financials-historical.md"
    later.write_text(_raw(cfo={y: 900 for y in LATER})[0], encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-21", capsys=capsys)
    assert out["result"] == "triggered" and out["next"] == "prepare"


def test_newer_profitability_result_triggers(repo, capsys):
    fill(prepared(repo, capsys))
    run(repo, "build", "--company", "7203", capsys=capsys)
    _profitability(repo, "普通", date="2026-10-15")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-16", capsys=capsys)
    assert out["result"] == "triggered"


def test_expired_after_180_days(repo, capsys):
    fill(prepared(repo, capsys))
    run(repo, "build", "--company", "7203", capsys=capsys)
    later = (dt.date.fromisoformat(DAY) + dt.timedelta(days=181)).isoformat()
    _, out = run(repo, "check", "--company", "7203", "--date", later, capsys=capsys)
    assert out["result"] == "expired"


def test_build_rejects_forbidden_words_and_blank_cells(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    md.write_text(text.replace("背景 report-points（brief による）", "おそらく強い"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("おそらく" in i for i in out["issues"])
    md.write_text(text.replace("背景 investment（brief による）", "—"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("投資の中身が空" in i for i in out["issues"])


def test_edited_table_cannot_change_the_verdict(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    md.write_text(md.read_text(encoding="utf-8").replace("良好（確定）", "懸念（確定）"), encoding="utf-8")
    _, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert out["verdict"] == "良好"


def test_fresh_result_is_not_redone_without_redo(repo, capsys):
    fill(prepared(repo, capsys))
    run(repo, "build", "--company", "7203", capsys=capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", capsys=capsys)
    assert code == 1 and "redo" in out["error"]


def test_untouched_skeleton_is_regenerated_and_draft_is_kept(repo, capsys):
    prepared(repo, capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-13", capsys=capsys)
    assert code == 0 and out["regenerated"] and out["date"] == "2026-10-13"
    md = repo / out["md"]
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:triggers", "書きかけ <!-- FILL:triggers"),
                  encoding="utf-8")
    code, out = run(repo, "prepare", "--company", "7203", "--date", "2026-10-14", capsys=capsys)
    assert code == 0 and out["kept"] and out["date"] == "2026-10-13"


def test_write_guard_protects_cash_flow_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_cash-flow.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    tomorrow = (dt.date.fromisoformat(DAY) + dt.timedelta(days=1)).isoformat()
    assert "完成済み分析（cash-flow）" in G.decide("Edit", rel, repo, tomorrow)
