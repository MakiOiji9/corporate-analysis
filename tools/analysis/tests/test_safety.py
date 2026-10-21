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

import safety as SF  # noqa: E402
import sf_doc as D  # noqa: E402
import sf_inputs as I  # noqa: E402
import sf_metrics as X  # noqa: E402
import sf_paths as P  # noqa: E402
import sf_series as SS  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
COLLECTED = "2026-10-01"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
YEARS = range(2022, 2027)
DEBT = {2022: 1000, 2023: 1000, 2024: 1000, 2025: 2000, 2026: 2000}
SALES = {2026: 12000}  # the other years 10,000
OPERATING = {2026: 1300}  # the other years 1,000

BALANCE = """## 3. 貸借対照表（有価証券報告書の連結貸借対照表）

| 項目（百万円） | {heads} |
|---|{seps}
| 総資産 | {assets} |
| 自己資本 | {equity} |
{debt_rows}| 現金及び現金同等物 | {cash} |
| 流動資産合計 | {current_assets} |
| 流動負債合計 | {current_liabilities} |
"""

FINANCIALS = """# 財務データ時系列 — テスト

## 2. 損益

| 項目（百万円） | {heads} |
|---|{seps}
| 売上高 | {sales} |
| 営業利益 | {operating} |
| 親会社株主に帰属する当期純利益 | {net_income} |

{balance}
## 4. キャッシュ・フロー

| 項目（百万円） | {heads} |
|---|{seps}
| 営業CF | {cfo} |
| 投資CF | {cfi} |
| 財務CF | {cff} |

## 5. 株主還元

| 年度 | 1株配当 | 配当総額 | 配当性向 | 自社株買い | 出典 |
|---|---|---|---|---|---|
| 2026/03 | 10円 | 1億円 | 20% | — | 短信 |
"""

YUHO = """# 有価証券報告書 抜粋 — テスト

> 単位は特記なき限り百万円。

## 1. 主要な経営指標等の推移（連結）（p.2）

| 項目 | 2025年3月 | 2026年3月 |
|---|---|---|
| 総資産額 | 10,000 | 10,000 |
| 自己資本比率（%） | 60.0 | 60.0 |

## 4. 事業等のリスク（要旨）

- 金利上昇で借入コストが増える
- 人材の確保が難しくなる

## 11. 経営方針・中期経営計画・資本政策（p.7）

- 有利子負債は設備投資の範囲にとどめる方針
"""

COMPETITORS = """# 競合情報 — テスト

## 5. ROE・自己資本比率

| 会社 | 年度 | ROE | 自己資本比率 | 出典 |
|---|---|---|---|---|
| ガンマ社 | 2026/03 | 6.0% | 30% | 短信 |

{safety}
"""

SAFETY_SECTION = """## 11. 安全性の指標（最大5期）

| 会社 | 年度 | 総資産 | 自己資本 | 自己資本比率 | 有利子負債 | 現金及び現金同等物 | 流動資産 | 流動負債 | 出典・確度 |
|---|---|---|---|---|---|---|---|---|---|
{rows}
"""
PEER_ROWS = ("| アルファ社（1111） | 2026/03 | 100億円 | 50億円 | — | 30億円 | 20億円 | 60億円 | 40億円 | 短信（一次） |\n"
             "| ベータ社（2222） | 2026/02 | 20,000 | — | 40.0% | 12,000 | 3,000 | 9,000 | 8,000 | IRBANK（二次） |\n"
             "| トヨタ（7203） | 2026/03 | 999 | 999 | — | 999 | 999 | 999 | 999 | 有報（一次） |")


def _cells(values: dict[int, float]) -> str:
    return " | ".join(f"{values[y]:,.0f}" for y in YEARS)


def financials(debt: dict[int, float] | None = DEBT, parts: bool = False, cfo: float = 800,
               equity: float = 6000, current_liabilities: float = 2500) -> str:
    heads = " | ".join(f"{y}年3月期" for y in YEARS)
    seps = "---|" * len(YEARS)
    flat = {y: 0 for y in YEARS}
    debt_rows = ""
    if debt is not None and parts:
        debt_rows = (f"| 短期借入金 | {_cells({y: v / 2 for y, v in debt.items()})} |\n"
                     f"| 長期借入金 | {_cells({y: v / 2 for y, v in debt.items()})} |\n")
    elif debt is not None:
        debt_rows = f"| 有利子負債 | {_cells(debt)} |\n"
    balance = BALANCE.format(heads=heads, seps=seps, assets=_cells({y: 10000 for y in YEARS}),
                             equity=_cells({y: equity for y in YEARS}), debt_rows=debt_rows,
                             cash=_cells({y: 3000 for y in YEARS}),
                             current_assets=_cells({y: 5000 for y in YEARS}),
                             current_liabilities=_cells({y: current_liabilities for y in YEARS}))
    return FINANCIALS.format(
        heads=heads, seps=seps, balance=balance,
        sales=_cells({y: SALES.get(y, 10000) for y in YEARS}),
        operating=_cells({y: OPERATING.get(y, 1000) for y in YEARS}),
        net_income=_cells({y: 600 for y in YEARS}),
        cfo=_cells({y: cfo for y in YEARS}), cfi=_cells({**{y: -100 for y in YEARS}, 2025: -900}),
        cff=_cells({**flat, 2025: 500}))


def _company(root: Path, fin: str | None = None, safety: str | None = None, yuho: str = YUHO) -> Path:
    company = root / "companies" / "7203_toyota"
    competitors = COMPETITORS.format(safety=SAFETY_SECTION.format(rows=PEER_ROWS) if safety is None else safety)
    for sub, name, text in (("filings", f"{COLLECTED}_2026-03_yuho.md", yuho),
                            ("ir", f"{COLLECTED}_financials-historical.md", financials() if fin is None else fin),
                            ("market", f"{COLLECTED}_competitors.md", competitors)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n\n## 基本情報\n\n| 項目 | 内容 |\n|---|---|\n"
                                         "| 主力事業 | 自動車 |\n", encoding="utf-8")
    return company


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / ".ai" / "templates" / "safety", tmp_path / ".ai" / "templates" / "safety")
    (tmp_path / "market" / "report").mkdir(parents=True)
    _company(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = SF.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def cands_of(root: Path) -> dict:
    company = company_obj(root)
    return X.candidates(company, I.gather_safety(company))


def prepared(root: Path, capsys, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", DAY, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def fill(md: Path) -> None:
    def answer(m: re.Match) -> str:
        return "- 初回の分析" if m.group(1) in ("changes", "gaps") else f"背景 {m.group(1)}（brief による）"
    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


# ---------- series ----------

def test_series_reads_balance_sheet_and_cash_flows(repo):
    company = company_obj(repo)
    series = SS.self_series(company, I.gather_safety(company))
    assert series["debt"]["2025-03"].value == 2000 and series["cash"]["2026-03"].value == 3000
    assert series["current_liabilities"]["2026-03"].value == 2500
    assert series["cfi"]["2025-03"].value == -900 and series["operating_income"]["2026-03"].value == 1300
    assert series["equity"]["2026-03"].value == 6000  # not the target's 999 row in competitors


def test_debt_is_the_sum_of_its_lines_without_a_debt_row(tmp_path):
    _company(tmp_path, fin=financials(parts=True))
    series = SS.self_series(company_obj(tmp_path))
    assert series["debt"]["2025-03"].value == 2000
    assert series["debt"]["2025-03"].source.startswith("借入金・社債の内訳")


def test_no_debt_line_means_unknown_not_zero(tmp_path):
    _company(tmp_path, fin=financials(debt=None))
    assert SS.self_series(company_obj(tmp_path))["debt"] == {}


def test_cash_falls_back_to_deposits():
    text = ("# x\n\n## 3. 貸借\n\n| 項目（千円） | 2025年3月期 | 2026年3月期 |\n|---|---|---|\n"
            "| 現金及び預金 | 1,000,000 | 2,000,000 |\n| 流動資産合計 | 3,000,000 | 4,000,000 |\n")
    series = SS.finish(SS.S.merge(SS.S.from_raw_text(text, "f.md", None, SS.SAFETY), SS.FIELDS))
    assert series["cash"]["2026-03"].value == pytest.approx(2000)
    assert series["current_assets"]["2025-03"].value == pytest.approx(3000)


def test_labels_do_not_catch_neighbouring_lines():
    for label in ("長期借入金の返済による支出", "現金及び現金同等物の増減額", "営業利益率", "自己資本比率（%）"):
        assert SS.S.field_of(label, SS.SAFETY) in (None, "equity_ratio"), label
    assert SS.S.field_of("1年内返済予定の長期借入金", SS.SAFETY) == "debt_current_long"
    assert SS.S.field_of("投資CF（百万円）", SS.SAFETY) == "cfi"


def test_peers_merge_sections_by_name(repo):
    company = company_obj(repo)
    peers = SS.peer_series(company, I.gather_safety(company))
    assert [p["name"] for p in peers] == ["アルファ社（1111）", "ベータ社（2222）", "ガンマ社"]
    beta = peers[1]["series"]
    assert beta["equity"]["2026-02"].value == pytest.approx(8000)  # 20,000 × 40%
    assert not beta["equity"]["2026-02"].primary


# ---------- 手順1 ----------

def _own(**kw) -> dict:
    row = {"year": "2026-03", "equity_ratio": 60.0, "de": 0.3, "current_ratio": 200.0, "net_cash": -100.0,
           "insolvent": False, "total_assets": 10000.0, "equity": 6000.0}
    return {**row, **kw}


@pytest.mark.parametrize("key, own, peer, excluded, rating", [
    ("equity_ratio", _own(), None, False, "クリア"),
    ("equity_ratio", _own(equity_ratio=35.0), 36.0, False, "クリア"),  # within 2pt of the peers
    ("equity_ratio", _own(equity_ratio=35.0), 38.0, False, "未達"),
    ("equity_ratio", _own(equity_ratio=35.0), None, False, "不明"),
    ("de", _own(de=1.5), 1.45, False, "クリア"),  # within x1.05
    ("de", _own(de=1.5), 1.0, False, "未達"),
    ("de", _own(de=1.5, net_cash=10.0), 1.0, False, "クリア"),  # 実質無借金
    ("de", _own(de=None), None, False, "不明"),
    ("current_ratio", _own(current_ratio=110.0), 112.0, False, "クリア"),  # within 5pt
    ("current_ratio", _own(current_ratio=130.0), 150.0, True, "未達"),  # 業種が対象外: the peers only
    ("equity_ratio", _own(equity_ratio=-5.0, insolvent=True, de=None), 30.0, False, "未達"),
])
def test_assess(key, own, peer, excluded, rating):
    assert X.assess(key, own, peer, excluded)["rating"] == rating


def test_sector_exclusion_by_main_business(tmp_path):
    company = _company(tmp_path)
    (company / "overview.md").write_text("# x\n\n## 基本情報\n\n| 項目 | 内容 |\n|---|---|\n| 主力事業 | 銀行業 |\n",
                                         encoding="utf-8")
    assert X.sector_excluded(company_obj(tmp_path))
    (company / "overview.md").write_text("# x\n\n## 基本情報\n\n| 項目 | 内容 |\n|---|---|\n"
                                         "| 主力事業 | プレスリリース配信 |\n", encoding="utf-8")
    assert not X.sector_excluded(company_obj(tmp_path))


# ---------- 手順2 / 手順3 ----------

def _rows(ratios: list[float], des: list[float | None] | None = None) -> list[dict]:
    des = des or [0.2] * len(ratios)
    return [{"year": f"{2022 + i}-03", "equity_ratio": r, "de": d, "insolvent": False}
            for i, (r, d) in enumerate(zip(ratios, des))]


@pytest.mark.parametrize("ratios, des, rating", [
    ([60, 58, 56, 55, 55], None, "悪化傾向なし"),
    ([60, 58, 55, 52, 50], None, "悪化傾向"),  # 10pt
    ([60, 60, 60, 60, 60], [0.2, 0.3, 0.4, 0.5, 0.6], "悪化傾向"),  # 3 rises in a row
    ([60, 60, 60, 60, 60], [0.5, 0.3, 0.4, 0.5, 0.45], "悪化傾向なし"),
    ([60, 50], None, "不明"),
])
def test_step2_rules(ratios, des, rating):
    assert X.step2(_rows(ratios, des))["rating"] == rating


def _debt_rows(cfo: float = 800, ni: float = 600, cfi: float = -900, later_sales: float = 12000) -> list[dict]:
    base = {"total_assets": 10000.0, "cff": 0.0, "operating_income": 1000.0, "sales": 10000.0}
    return [{**base, "year": "2024-03", "debt": 1000.0, "cfo": 800.0, "cfi": -100.0, "net_income": 600.0},
            {**base, "year": "2025-03", "debt": 2000.0, "cfo": cfo, "cfi": cfi, "net_income": ni},
            {**base, "year": "2026-03", "debt": 2000.0, "cfo": 800.0, "cfi": -100.0, "net_income": 600.0,
             "sales": later_sales, "operating_income": 1300.0 if later_sales > 10000 else 900.0}]


@pytest.mark.parametrize("kw, kind, rating", [
    ({}, "成長投資（成果あり）", "許容"),
    ({"later_sales": 9000}, "成長投資（売上高・営業利益の伸びが見えない）", "要確認"),
    ({"cfo": -100}, "赤字補填・運転資金不足", "懸念"),
    ({"ni": -10}, "赤字補填・運転資金不足", "懸念"),
    ({"cfi": -100}, "その他（投資CF の支出が増加額の半分未満）", "要確認"),
])
def test_step3_classifies_the_debt_increase(kw, kind, rating):
    s3 = X.step3(_debt_rows(**kw))
    assert [y["year"] for y in s3["years"]] == ["2025-03"]
    assert s3["years"][0]["kind"] == kind and s3["rating"] == rating


def test_step3_without_debt_series():
    assert X.step3([{"year": "2026-03", "debt": None}])["rating"] == "不明"


# ---------- 手順4 ----------

def _s1(*ratings: str) -> dict:
    return {"items": [{"key": k, "name": X.NAMES[k], "rating": r} for (k, _), r in zip(X.INDICATORS, ratings)]}


@pytest.mark.parametrize("ratings, trend, purpose, verdict", [
    (("クリア", "クリア", "クリア"), "悪化傾向なし", "許容", "良好"),
    (("クリア", "クリア", "クリア"), "悪化傾向", "許容", "普通"),
    (("クリア", "クリア", "クリア"), "悪化傾向", "懸念", "懸念"),
    (("未達", "クリア", "クリア"), "悪化傾向なし", "許容", "普通"),
    (("未達", "未達", "クリア"), "悪化傾向なし", "許容", "懸念"),
    (("不明", "不明", "クリア"), "悪化傾向なし", "許容", "判定保留"),
    (("不明", "クリア", "クリア"), "悪化傾向なし", "許容", "判定保留"),  # 良好 or 普通
    (("不明", "未達", "未達"), "悪化傾向なし", "許容", "懸念"),  # 懸念 either way
    (("未達", "不明", "クリア"), "悪化傾向", "許容", "判定保留"),  # 普通 or 懸念
    (("クリア", "クリア", "クリア"), "悪化傾向なし", "不明", "良好"),  # the purpose only matters with 悪化傾向
    (("クリア", "クリア", "クリア"), "不明", "許容", "判定保留"),
])
def test_judge(ratings, trend, purpose, verdict):
    got, why = X.judge(_s1(*ratings), {"rating": trend, "basis": "b"}, {"rating": purpose, "basis": "b"})
    assert got == verdict, why


def test_candidates_end_to_end(repo):
    cands = cands_of(repo)
    s1 = cands["step1"]
    assert [i["rating"] for i in s1["items"]] == ["クリア", "クリア", "クリア"]
    assert s1["debt_free"] and s1["net_cash"] == 1000
    assert [p["name"] for p in s1["peers"]] == ["アルファ社（1111）", "ベータ社（2222）", "ガンマ社"]
    assert s1["peer_avg"]["de"] == pytest.approx((0.6 + 1.5) / 2)  # ガンマ has no debt
    assert cands["step2"]["rating"] == "悪化傾向なし"
    assert [y["kind"] for y in cands["step3"]["years"]] == ["成長投資（成果あり）"]
    assert cands["verdict"] == "良好"


def test_borderline_lists_close_comparisons(tmp_path):
    _company(tmp_path, fin=financials(equity=4200, current_liabilities=4000), yuho=YUHO.replace("60.0", "42.0"))
    found = cands_of(tmp_path)["borderline"]
    # 42.0% is near the 40% 目安 but also clears the peer average (40.0%): a second path, nothing to flag
    assert not any("自己資本比率" in f for f in found)
    # 125.0% clears only the 目安 (peer average 131.3%) and sits within twice the band of it
    assert any("流動比率 125.0% が目安 120%以上に近い（クリア）" in f for f in found)


def test_borderline_skips_indicators_cleared_with_room(repo):
    assert cands_of(repo)["borderline"] == []


def test_borderline_lists_a_near_miss():
    item = {"key": "equity_ratio", "name": "自己資本比率", "value": 39.0, "peer_avg": 42.0, "rating": "未達",
            "by_target": False, "by_peer": False, "target": "40%以上"}
    s1 = {"items": [item], "own": None, "excluded": False, "debt_free": False, "unit": "百万円"}
    found = X.borderline(s1, {"drop": None})
    assert any("目安 40%以上に近い（未達）" in f for f in found) and any("同業平均 42.0%" in f for f in found)


# ---------- check / prepare / build ----------

def test_check_goes_to_prepare(repo, capsys):
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare" and out["missing_inputs"] == [] and out["profitability"] is None


def test_check_requests_peers_and_own_debt(tmp_path, capsys):
    shutil.copytree(REPO / ".ai" / "templates" / "safety", tmp_path / ".ai" / "templates" / "safety")
    _company(tmp_path, fin=financials(debt=None), safety="")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    agents = {r["agent"] for r in out["missing_inputs"]}
    assert out["next"] == "collect" and agents == {"collect-peers-valuation", "collect-filings"}
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "collect"


def test_unavailable_items_stop_the_requests(tmp_path, capsys):
    company = _company(tmp_path, fin=financials(debt=None), safety="")
    (company / "status.md").write_text("# s\n\n## 未取得項目\n\n| 項目 | 理由 |\n|---|---|\n"
                                       "| 安全性の財務時系列（有利子負債） | 開示なし |\n| 安全性の指標（全社） | 開示なし |\n",
                                       encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["missing_inputs"] == [] and out["next"] == "prepare"


def test_prepare_fill_build(repo, capsys):
    md = prepared(repo, capsys)
    text = md.read_text(encoding="utf-8")
    assert "| 自己資本比率 | 60.0% | 40%以上 |" in text and "FILL:bg-2025-03" in text
    brief = md.with_name(f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "金利上昇で借入コストが増える" in brief and "有利子負債は設備投資の範囲" in brief
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("FILL" in i for i in out["issues"])
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "良好" and out["debt_years"] == ["2025-03"]
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["step3"]["years"][0]["background"].startswith("背景 bg-2025-03")
    assert "**良好**" in md.read_text(encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "fresh" and out["next"] == "report_existing"


def test_build_rejects_a_removed_purpose_row(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    md.write_text("\n".join(line for line in text.splitlines() if not line.startswith("| 2025-03 | 1,000")),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("3章の年度" in i or "表に行がない" in i for i in out["issues"])


def test_new_numbers_trigger_a_reanalysis(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    assert run(repo, "build", "--company", "7203", capsys=capsys)[0] == 0
    path = repo / "companies" / "7203_toyota" / "raw" / "ir" / f"{COLLECTED}_financials-historical.md"
    path.write_text(financials(current_liabilities=6000), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "triggered"


def test_untouched_draft_is_regenerated(repo, capsys):
    prepared(repo, capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["regenerated"] and not out["kept"]


def test_validate_requires_the_handoff(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8").replace("背景 report-points（brief による）", "—")
    issues = D.validate(text, (repo / ".ai" / "templates" / "safety" / "safety.md").read_text(encoding="utf-8"),
                        cands_of(repo)["step3"]["years"])
    assert "5. レポートで使う要点が空" in issues


NEW_BSCF = """# 財務データ時系列（差分） — テスト

## 8. 貸借・CF の主要項目（安全性）

注: 新しい注記（有利子負債は借入金・社債の合計）

| 項目（百万円） | 2025年3月期 | 2026年3月期 |
|---|---|---|
| 有利子負債 | 2,000 | 2,000 |
"""


def test_brief_drops_an_older_cash_flow_section(repo, capsys):
    ir = repo / "companies" / "7203_toyota" / "raw" / "ir"
    old = ir / f"{COLLECTED}_financials-historical.md"
    old.write_text(financials().replace("## 4. キャッシュ・フロー\n", "## 4. キャッシュ・フロー\n\n注: 2019年の有報は未取得\n"),
                   encoding="utf-8")
    (ir / "2026-10-05_financials-historical.md").write_text(NEW_BSCF, encoding="utf-8")
    brief = prepared(repo, capsys).with_name(f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "新しい注記" in brief and "2019年の有報は未取得" not in brief
    assert brief.count("新しい注記") == 1  # the 貸借 section is the same section: shown once
    assert "に含まれるため省略" in brief


def test_brief_keeps_only_finance_lines_of_the_risks(repo, capsys):
    brief = prepared(repo, capsys).with_name(f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "金利上昇で借入コストが増える" in brief and "人材の確保" not in brief


def test_explicit_equity_beats_the_one_derived_in_a_table(tmp_path):
    _company(tmp_path, yuho=YUHO.replace("60.0", "59.9"))  # 有報: 10,000 × 59.9% = 5,990 (derived, primary)
    series = SS.self_series(company_obj(tmp_path))
    assert series["equity"]["2026-03"].value == 6000  # the explicit 自己資本 row of the 財務時系列 (primary)


def test_derived_primary_beats_explicit_secondary():
    series = {"total_assets": {}, "equity_ratio": {},
              "equity": {"2026-03": SS.S.Value(999, "IRBANK", False)},
              "equity_derived": {"2026-03": SS.S.Value(5000, "有報", True)}}
    got = SS.S.with_equity(series)["equity"]["2026-03"]
    assert got.value == 5000 and got.primary and got.source.startswith("総資産 × 自己資本比率")


def test_build_rejects_numbers_not_in_the_brief(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    md.write_text(text.replace("背景 report-points（brief による）", "自己資本比率 61.3% に低下する（p.24）"),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("61.3" in i and "brief・md に無い" in i for i in out["issues"])
    md.write_text(text.replace("背景 report-points（brief による）", "自己資本比率 60.0%、2026年3月期（p.24）"),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out


PEER_SPLIT = SAFETY_SECTION.format(
    rows="| デルタ社（4444） | 2026/03 | —（10章） | —（10章） | —（10章） | 10億円 | 5億円 | 60億円 | 30億円 | 短信（一次） |")
DUPONT_FOR_DELTA = """## 10. 収益性の分解（最大5年。ROE・デュポン分解の材料）

| 会社 | 年度 | 売上高 | 当期純利益 | 総資産 | 自己資本 | ROE | 自己資本比率 | 出典・確度 |
|---|---|---|---|---|---|---|---|---|
| デルタ社 | 2026/03 | 100億円 | 5億円 | 100億円 | 50億円 | — | — | 短信（一次） |
"""


def test_peer_assets_and_equity_come_from_chapter_10(tmp_path):
    _company(tmp_path, safety=PEER_SPLIT + "\n" + DUPONT_FOR_DELTA)
    peers = {p["name"]: p for p in cands_of(tmp_path)["step1"]["peers"]}
    delta = peers["デルタ社（4444）"]
    assert delta["equity_ratio"] == pytest.approx(50.0) and delta["de"] == pytest.approx(0.2)
    assert delta["current_ratio"] == pytest.approx(200.0)


def test_us_unit_label_and_insolvency(tmp_path):
    company = tmp_path / "companies" / "ABCD_test"
    (company / "raw" / "ir").mkdir(parents=True)
    (company / "raw" / "ir" / f"{COLLECTED}_financials-historical.md").write_text(
        "# 財務データ時系列 — テスト\n\n> 単位: 千米ドル（USD thousands）\n", encoding="utf-8")
    assert SS.unit_label(P.Company(tmp_path, company)) == "千米ドル"
    assert SS.unit_label(company_obj(tmp_path)) == "百万円"
    _company(tmp_path, fin=financials(equity=-500), yuho=YUHO.replace("| 自己資本比率（%） | 60.0 | 60.0 |\n", ""))
    cands = cands_of(tmp_path)
    assert cands["step1"]["items"][0]["rating"] == "未達"
    assert any("債務超過" in w for w in X.warnings(cands))


def test_guard_protects_the_safety_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_safety.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
