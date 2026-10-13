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

import pf_inputs as I  # noqa: E402
import pf_metrics as X  # noqa: E402
import pf_paths as P  # noqa: E402
import pf_series as S  # noqa: E402
import profitability as PF  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
COLLECTED = "2026-10-01"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
YEARS = range(2020, 2027)
NET_INCOME = {2024: 8}  # 億円; the other years 6 (ROE 12%, 2024 16%)

FINANCIALS = """# 財務データ時系列 — テスト

## 1. 損益・貸借・CF（10年サマリー、IRBANK、二次情報）

単位: 億円

| 年度 | 売上高 | 営業利益 | 当期利益 | 総資産 | 自己資本比率 | ROE |
|---|---|---|---|---|---|---|
{rows}

## 3. 株主還元

| 年度 | 1株配当 | 配当総額 | 配当性向 | 自社株買い | 出典 |
|---|---|---|---|---|---|
| 2026/03 | 10円 | 1億円 | 20% | — | 短信 |

## 4. 会社計画（期初予想）と実績

| 年度 | 売上高 | 当期純利益 |
|---|---|---|
| 2027/03 | 200 | 50 |
"""

YUHO = """# 有価証券報告書 抜粋 — テスト

> 単位は特記なき限り百万円。

## 1. 主要な経営指標等の推移（連結）（p.2）

| 項目 | 2025年3月 | 2026年3月 |
|---|---|---|
| 売上高 | 10,000 | 10,000 |
| 親会社株主に帰属する当期純利益 | 600 | 600 |
| 総資産額 | 10,000 | 10,000 |
| 自己資本比率（%） | 50.0 | 50.0 |
| 自己資本利益率（%） | 12.0 | 12.0 |

### 提出会社（単体）の参考指標

| 項目 | 2025年3月 | 2026年3月 |
|---|---|---|
| 売上高 | 1 | 1 |
| 当期純利益 | 999 | 999 |

## 9. 特別利益・特別損失（p.72）

| 項目 | 2025年3月期 | 2026年3月期 |
|---|---|---|
| 特別利益 | 0 | 100 |
| 特別損失 | 計上なし | 計上なし |

## 11. 経営方針・資本政策（p.7）

- 自己資本を厚く持つ方針
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

## 5. ROE・自己資本比率

| 会社 | 年度 | ROE | 自己資本比率 | 出典 |
|---|---|---|---|---|
| アルファ社 | 2026/03 | 6.0% | 50% | 短信 |

{dupont}
"""

DUPONT = """## 10. 収益性の分解（最大5年。ROE・デュポン分解の材料）

| 会社 | 年度 | 売上高 | 当期純利益 | 総資産 | 自己資本 | ROE | 自己資本比率 | 出典・確度 |
|---|---|---|---|---|---|---|---|---|
{rows}
"""

ALPHA_ROW = "| アルファ社（1111） | {y}/03 | 100億円 | {ni}億円 | {assets}億円 | {equity}億円 | — | — | 短信（一次） |"
BETA_ROW = "| ベータ社（2222） | {y}/02 | 10,000 | 400 | 12,500 | — | 8.0% | 40.0% | IRBANK（二次） |"
SELF_ROW = "| トヨタ（7203） | 2026/03 | 999 | 999 | 999 | 999 | — | — | 有報（一次） |"


def _ni(y: int) -> int:
    return NET_INCOME.get(y, 6)


def _financials() -> str:
    rows = "\n".join(f"| {y}/03 | 100 | 20 | {_ni(y)} | 100 | 50.0% | 11.0% |" for y in YEARS)
    return FINANCIALS.format(rows=rows)


def dupont_rows(alpha_ni: float = 3, alpha_assets: float = 100, alpha_equity: float = 50) -> str:
    rows = [ALPHA_ROW.format(y=y, ni=alpha_ni, assets=alpha_assets, equity=alpha_equity) for y in range(2021, 2027)]
    rows += [BETA_ROW.format(y=y) for y in range(2021, 2027)] + [SELF_ROW]
    return DUPONT.format(rows="\n".join(rows))


def _peer_margins(month: int, profit: float) -> str:
    return "\n".join(f"| {y}/{month:02d} | 100億円 | {profit}億円 |" for y in range(2022, 2027))


def _company(root: Path, dupont: str | None = None, financials: str | None = None,
             collected: str = COLLECTED) -> Path:
    company = root / "companies" / "7203_toyota"
    competitors = COMPETITORS.format(alpha=_peer_margins(3, 5), beta=_peer_margins(2, 7),
                                     dupont=dupont_rows() if dupont is None else dupont)
    for sub, name, text in (("filings", f"{collected}_2026-03_yuho.md", YUHO),
                            ("ir", f"{collected}_financials-historical.md",
                             _financials() if financials is None else financials),
                            ("market", f"{collected}_competitors.md", competitors)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _upstream(root: Path, kind: str, verdict: str, date: str = "2026-10-05") -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / kind
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_{kind}.md").write_text("# 完成\n", encoding="utf-8")
    result = {"verdict": verdict, "verdict_reason": "理由", "win_reason": "品質", "handoff": {"step2_checks": "利益率"}}
    (directory / f"{date}_{kind}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _templates(root: Path) -> None:
    shutil.copytree(REPO / ".ai" / "templates" / "profitability", root / ".ai" / "templates" / "profitability")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    (tmp_path / "market" / "report").mkdir(parents=True)
    _company(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = PF.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def cands_of(root: Path) -> dict:
    company = company_obj(root)
    return X.candidates(company, I.gather_profitability(company))


def prepared(root: Path, capsys, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", DAY, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def fill(md: Path) -> None:
    def answer(m: re.Match) -> str:
        return "- 初回の分析" if m.group(1) in ("changes", "gaps") else f"背景 {m.group(1)}（brief による）"
    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


# ---------- cells and series ----------

@pytest.mark.parametrize("cell, factor, expected", [
    ("1,748,986", 1e-3, 1748.986), ("1,748,986（売掛金）", 1e-3, 1748.986), ("7.93億円", 1.0, 793.0),
    ("23,831百万円（前期比 -9.4%）", 1.0, 23831.0), ("△98", 1.0, -98.0), ("**13,570**", 1.0, 13570.0),
    ("計上なし", 1.0, None), ("—", 1.0, None)])
def test_amount_in_millions(cell, factor, expected):
    assert S.amount(cell, factor) == (pytest.approx(expected) if expected is not None else None)


def test_percent_period_and_labels():
    assert S.percent("18.8%（有報）/ 17.27%（IRBANK）") == 18.8
    assert S.period("2026年3月期") == "2026-03" and S.period("2026/03") == "2026-03"
    assert S.period("2027/03（会社予想）") is None
    assert S.field_of("自己資本利益率（%）") == "roe" and S.field_of("自己資本比率（%）") == "equity_ratio"
    assert S.field_of("自己資本（決算短信）") == "equity" and S.field_of("**資産合計**") == "total_assets"
    assert S.field_of("1株当たり当期純利益（円）") is None and S.field_of("非支配株主に帰属する当期純利益") is None
    assert S.field_of("特別利益: 新株予約権戻入益") is None
    assert S.field_of("売上高総利益") is None and S.field_of("売上高（百万円）") == "sales"
    for header in ("2027年3月期（予）", "2027/03E", "2026年3月期 第3四半期", "2026年3月期 中間", "2027年3月期（見込）"):
        assert S.period(header) is None, header
    assert S.period("2026年3月期（第26期）") == "2026-03"


def test_odd_cells_do_not_crash_or_vanish():
    assert S.amount(",", 1.0) is None
    assert S.amount("1,200（百万円）", 1e-3) == pytest.approx(1200)


def test_table_in_thousand_yen_and_parent_profit_wins():
    text = ("# x\n\n## 2. 損益\n\n### 2-1. 千円単位の年度\n\n| 項目（千円） | 2017年3月期 | 2018年3月期 |\n|---|---|---|\n"
            "| 売上高 | 4,677,085 | 5,085,038 |\n| 当期純利益 | 1 | 1 |\n"
            "| 親会社株主に帰属する当期純利益 | 539,681 | 555,713 |\n")
    got = {(f, y): v.value for f, y, v in S.from_raw_text(text, "f.md")}
    assert got[("sales", "2017-03")] == pytest.approx(4677.085)
    assert got[("net_income", "2018-03")] == pytest.approx(555.713)


def test_self_series_prefers_primary_and_derives_equity(repo):
    company = company_obj(repo)
    series = S.self_series(company, I.gather_profitability(company)["peer_dupont"])
    assert series["equity"]["2026-03"].value == pytest.approx(5000)  # 10,000 × 50%
    assert series["equity"]["2026-03"].primary and not series["equity"]["2020-03"].primary
    assert series["roe"]["2026-03"].value == 12.0 and series["roe"]["2026-03"].primary
    assert series["net_income"]["2026-03"].value == 600  # not the 単体 999 nor the target's row in competitors
    assert "2027-03" not in series["sales"]  # plan section skipped
    assert series["extra_gain"]["2026-03"].value == 100


# ---------- ROE and the factors ----------

def test_roe_is_the_product_of_the_three_factors(repo):
    rows = cands_of(repo)["dupont"]
    for r in rows:
        assert r["margin"] / 100 * r["turnover"] * r["leverage"] * 100 == pytest.approx(r["roe"])
    assert rows[0]["year"] == "2020-03" and not rows[0]["averaged"] and rows[1]["averaged"]


def test_roe_row_choice_primary_then_computed_then_secondary(repo):
    rows = {r["year"]: r for r in cands_of(repo)["roe_rows"]}
    assert rows["2026-03"]["basis"] == "開示（一次）"
    assert rows["2021-03"]["basis"] == "計算" and rows["2021-03"]["roe"] == 12.0  # not IRBANK's 11.0
    assert rows["2024-03"]["roe"] == 16.0


def _roe_rows(values: list[float], loss_year: int | None = None) -> list[dict]:
    return [{"year": f"{2016 + i}-03", "roe": v, "net_income": -1 if i == loss_year else 1}
            for i, v in enumerate(values)]


@pytest.mark.parametrize("values, loss, rating", [
    ([10, 10, 10, 10, 10], None, "良好"), ([5, 15, 15, 5, 10], None, "良好"),
    ([4, 16, 10, 10, 10], None, "普通"), ([9, 9, 9, 9, 9], None, "普通"), ([8, 8, 8, 8, 8], None, "普通"),
    ([7.9] * 5, None, "懸念"), ([12, 12, 12, 12, 12], 2, "懸念"), ([12, 12, 12, 12], None, None)])
def test_step1_rules(values, loss, rating):
    assert X.step1(_roe_rows(values, loss))["rating"] == rating


def _own(leverage: float = 2.0, margin: float = 6.0, turnover: float = 1.0) -> list[dict]:
    return [{"year": f"{y}-03", "margin": margin, "turnover": turnover, "leverage": leverage,
             "roe": margin * turnover * leverage, "net_income": 1, "primary": True} for y in range(2022, 2027)]


def _comparison(own: list[dict], **peer: float) -> dict:
    values = {"margin": 3.0, "turnover": 1.0, "leverage": 2.0, **peer}
    values["roe"] = values["margin"] * values["turnover"] * values["leverage"]
    peers = [{"name": "アルファ", "years": [r["year"] for r in own], "primary": True, **values}]
    self_avg = {k: own[-1][k] for k in ("margin", "turnover", "leverage", "roe")}
    return {"years": [r["year"] for r in own], "self": self_avg, "peers": peers, "peer_avg": values, "peer_rows": []}


EMPTY = {"years": [], "self": {}, "peers": [], "peer_avg": {}, "peer_rows": []}


@pytest.mark.parametrize("own_kw, peer_kw, source", [
    ({}, {}, "本業由来"),
    ({"margin": 2.0, "turnover": 0.9}, {}, "特定できず"),
    ({"leverage": 3.5}, {"leverage": 2.0}, "借入依存"),
    ({"leverage": 3.5}, {"leverage": 4.0}, "本業由来"),  # over 3x but below the peers: not 借入依存
])
def test_step3_rules(own_kw, peer_kw, source):
    own = _own(**own_kw)
    assert X.step3(own, _comparison(own, **peer_kw))["source"] == source


@pytest.mark.parametrize("own_kw, peer_kw, source", [
    ({"margin": 3.5}, {}, "特定できず"),  # +0.5pt is within ±1pt: 同等
    ({"margin": 4.5}, {}, "本業由来"),  # +1.5pt
    ({"margin": 2.0, "turnover": 1.04}, {}, "特定できず"),  # turnover 4% above: 同等
    ({"margin": 2.0, "turnover": 1.10}, {}, "本業由来"),
    ({"leverage": 3.5, "margin": 2.0}, {"leverage": 3.4}, "特定できず"),  # 3% above the peers: not 借入依存
])
def test_step3_needs_a_lead_beyond_the_band(own_kw, peer_kw, source):
    own = _own(**own_kw)
    assert X.step3(own, _comparison(own, **peer_kw))["source"] == source


def test_borderline_lists_close_comparisons():
    own = _own(margin=3.5)
    s3 = X.step3(own, _comparison(own))
    s1 = X.step1(_roe_rows([11, 11, 11, 11, 11]))
    found = X.borderline(s1, {"rating": "上回る", "diff": 1.5}, s3)
    assert any(f.startswith("手順1: ROE の平均") for f in found)
    assert any(f.startswith("手順2") for f in found)
    assert any("売上高純利益率" in f for f in found if f.startswith("手順3"))


def test_adjusted_step1_can_change_the_rating():
    roes = _roe_rows([10, 10, 10, 10, 30])
    one_off = [{"year": "2020-03", "adjusted_roe": -5.0}]
    result = X.adjusted_step1(roes, one_off)
    assert result["years"] == ["2020-03"] and result["rating"] == "懸念"
    assert X.adjusted_step1(roes, [{"year": "2020-03", "adjusted_roe": None}]) is None


@pytest.mark.parametrize("leverage, source", [(3.5, "借入依存"), (2.0, "不明")])
def test_step3_without_peers(leverage, source):
    assert X.step3(_own(leverage=leverage), EMPTY)["source"] == source


@pytest.mark.parametrize("s1, s2, s3, verdict", [
    ("良好", "上回る", "本業由来", "良好"), ("良好", "同等", "本業由来", "良好"),
    ("良好", "下回る", "本業由来", "普通"), ("良好", "上回る", "特定できず", "普通"),
    ("良好", None, "本業由来", "判定保留"), ("良好", "上回る", "不明", "判定保留"),
    ("普通", None, "不明", "普通"), ("懸念", "上回る", "本業由来", "懸念"),
    ("良好", "上回る", "借入依存", "懸念"), (None, "上回る", "本業由来", "判定保留")])
def test_judge(s1, s2, s3, verdict):
    got, _ = X.judge({"rating": s1, "basis": "b"}, {"rating": s2}, {"source": s3, "basis": "b"})
    assert got == verdict


def test_change_years_name_the_factor_that_moved(repo):
    changes = cands_of(repo)["changes"]
    assert [c["year"] for c in changes] == ["2024-03", "2025-03"]
    assert all(c["main"] == "売上高純利益率" for c in changes)
    assert "営業利益率 20.0%→20.0%" in changes[0]["moves"]
    assert "特別損益の純額 —→0百万円" in changes[1]["moves"]


def test_one_off_roe_without_the_extraordinary_items(repo):
    cands = cands_of(repo)
    row = next(r for r in cands["one_off"] if r["year"] == "2026-03")
    assert row["check"] and row["adjusted_roe"] == 10.0  # (600 - 100) / 5,000
    assert cands["one_off_step1"]["rating"] == "良好"


def test_peer_comparison_and_one_off(repo):
    cands = cands_of(repo)
    comparison = cands["step3"]["comparison"]
    assert [p["name"] for p in comparison["peers"]] == ["アルファ社（1111）", "ベータ社（2222）"]
    beta = comparison["peers"][1]
    assert beta["leverage"] == pytest.approx(2.5) and not beta["primary"]  # equity from the ratio, IRBANK
    assert cands["step3"]["source"] == "本業由来" and cands["step2"]["rating"] == "上回る"
    assert cands["verdict"] == "良好"
    assert [r["year"] for r in cands["one_off"] if r["check"]] == ["2026-03"]


def test_consistency_rows():
    s2 = {"rating": "同等"}
    s3 = {"comparison": {"self": {"roe": 12.0}, "peer_avg": {"roe": 7.0}}}
    rows = X.consistency(s2, s3, {"verdict": "広い"}, {"verdict": "明確"})
    assert rows[0]["result"].startswith("不整合") and rows[1]["result"] == "整合"
    rows = X.consistency(s2, s3, None, {"verdict": "あいまい"})
    assert rows[0]["result"].startswith("未実施") and rows[1]["result"].startswith("対象外")


# ---------- check ----------

def test_check_goes_to_prepare_without_step1(repo, capsys):
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare" and out["moat"] is None and out["missing_inputs"] == []


def test_check_requests_peer_dupont(tmp_path, capsys):
    _company(tmp_path, dupont="")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"
    assert out["missing_inputs"] == [{"agent": "collect-peers-valuation", "items": [X.PEER_ITEM]}]


def test_unavailable_peer_dupont_is_not_recollected(tmp_path, capsys):
    company = _company(tmp_path, dupont="")
    (company / "status.md").write_text("# s\n\n## 2. 未取得項目\n\n| 項目 | 理由 | 次回 |\n|---|---|---|\n"
                                       "| 収益性の分解（アルファ社、0期分のみ） | 開示なし | — |\n", encoding="utf-8")
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "prepare"


def test_short_own_history_requests_filings(tmp_path, capsys):
    rows = "\n".join(f"| {y}/03 | 100 | 20 | 6 | 100 | 50.0% | — |" for y in (2021, 2022))
    _company(tmp_path, financials=FINANCIALS.format(rows=rows))
    (tmp_path / "companies" / "7203_toyota" / "raw" / "filings" / f"{COLLECTED}_2026-03_yuho.md").unlink()
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    filings = next(r for r in out["missing_inputs"] if r["agent"] == "collect-filings")
    assert X.OWN_ITEM in filings["items"]


def test_prepare_refuses_until_collected_then_skip_collect(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path, dupont="")
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "collect"
    md = prepared(tmp_path, capsys, "--skip-collect")
    text = md.read_text(encoding="utf-8")
    assert "競合の3要素が無く同業と比べられない" in text


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / "7203_toyota").mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_list_shows_state_and_upstream(repo, capsys):
    _upstream(repo, "moat", "広い")
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert row["profitability"] == "none" and row["moat"]["verdict"] == "広い" and row["three_c"] is None


# ---------- prepare / build ----------

def test_skeleton_has_numbers_and_fill_only_for_background(repo, capsys):
    text = prepared(repo, capsys).read_text(encoding="utf-8")
    assert "| 手順1の判定 | 良好（確定）" in text and "| 手順3の判定 | 本業由来（確定）" in text
    assert sorted(set(FILL_ANY.findall(text))) == sorted(
        ["peer-gap", "bg-2024-03", "bg-2025-03", "one-off", "consistency", "report-points", "targets",
         "step2-checks", "triggers", "changes", "gaps"])
    assert "16.7%（要確認） | 10.0% |" in text
    assert "手順1の判定は変わらない" in text


def test_prepare_returns_fill_keys_and_brief_has_no_peer_table(repo, capsys):
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["fill_keys"][0] == "peer-gap" and len(out["fill_keys"]) == out["fill"]
    assert out["peer_summary"]["self"]["margin"] == 6.4  # 2022-2026: 6, 6, 8 (2024), 6, 6 億円 of 100
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "| 会社 | 年度 | 売上高 | 当期純利益" not in brief and "raw の情報源" not in brief
    assert "| アルファ社 | 2026/03 | 6.0%" not in brief  # peer_roe table left out too


def test_full_cycle_then_fresh_and_triggered(repo, capsys):
    _upstream(repo, "moat", "広い")
    md = prepared(repo, capsys)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and "FILL" in out["issues"][0]
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == "良好"
    assert out["consistency"][0] == "モートが広い ⇔ 高い利益率: 整合"
    assert isinstance(out["borderline"], list) and "| 境界に近い比較 |" in md.read_text(encoding="utf-8")
    assert "| 収益性 | **良好**:" in md.read_text(encoding="utf-8")
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["step1"]["rating"] == "良好" and result["change_years"][0]["background"].startswith("背景")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "report_existing"
    # a later collection that changes the peers' numbers re-opens the result
    newer = repo / "companies" / "7203_toyota" / "raw" / "market" / "2026-10-20_competitors.md"
    newer.write_text(COMPETITORS.format(alpha=_peer_margins(3, 5), beta=_peer_margins(2, 7),
                                        dupont=dupont_rows(alpha_ni=9)), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-21", capsys=capsys)
    assert out["result"] == "triggered" and out["next"] == "prepare"


def test_expired_after_180_days(repo, capsys):
    fill(prepared(repo, capsys))
    run(repo, "build", "--company", "7203", capsys=capsys)
    later = (dt.date.fromisoformat(DAY) + dt.timedelta(days=181)).isoformat()
    _, out = run(repo, "check", "--company", "7203", "--date", later, capsys=capsys)
    assert out["result"] == "expired"


def test_build_rejects_removed_change_row_and_forbidden_words(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8")
    md.write_text("\n".join(line for line in text.splitlines() if not line.startswith("| 2025-03 | 16.0%")),
                  encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("3.3 の年度" in i for i in out["issues"])
    md.write_text(text.replace("背景 report-points（brief による）", "おそらく高い"), encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("おそらく" in i for i in out["issues"])


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


def test_write_guard_protects_profitability_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_profitability.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
    fill(md)
    run(repo, "build", "--company", "7203", capsys=capsys)
    tomorrow = (dt.date.fromisoformat(DAY) + dt.timedelta(days=1)).isoformat()
    assert "完成済み分析（profitability）" in G.decide("Edit", rel, repo, tomorrow)
