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

import va_doc as D  # noqa: E402
import va_inputs as I  # noqa: E402
import va_metrics as X  # noqa: E402
import va_paths as P  # noqa: E402
import va_rules as R  # noqa: E402
import va_series as V  # noqa: E402
import valuation as VA  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
COLLECTED = "2026-10-01"
PRICE_DATE = "2026-10-09"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
YEARS = range(2022, 2027)
NET_INCOME = {2022: 600, 2023: 660, 2024: 720, 2025: 780, 2026: 840}
OPERATING = {2022: 1000, 2023: 1100, 2024: 1200, 2025: 1300, 2026: 1400}

FINANCIALS = """# 財務データ時系列 — テスト

## 2. 損益

| 項目（百万円） | {heads} |
|---|{seps}
| 売上高 | {sales} |
| 営業利益 | {operating} |
| 親会社株主に帰属する当期純利益 | {net_income} |
| EPS（円） | {eps} |
| 特別利益 | {gain} |
| 特別損失 | {loss} |

## 3. 貸借対照表

| 項目（百万円） | {heads} |
|---|{seps}
| 総資産 | {assets} |
| 自己資本 | {equity} |
| 有利子負債 | {debt} |
| 現金及び現金同等物 | {cash} |

## 4. キャッシュ・フロー

| 項目（百万円） | {heads} |
|---|{seps}
| 営業CF | {cfo} |
| 減価償却費 | {depreciation} |
"""

VALUATION = """# 株価・バリュエーションデータ — テスト

**収集日**: {collected}

## 1. 現在の株価・時価総額・株式数

| 項目 | 値 | 基準日時・出典 |
|---|---|---|
| 株価 | {price}円（終値） | {price_date} 終値（株探） |
| 時価総額 | 100億円 | {price_date}（株探） |
| 発行済株式数（自己株式を除く） | 10,000,000株 | 短信 |

注: 期末後に株式交換の予定がある。

## 2. EPS・BPS（実績・会社予想）

| 項目 | 値 | 出典 |
|---|---|---|
| EPS 実績（2026年3月期） | 84.00円 | 短信 |
| EPS 会社予想（2027年3月期） | {forecast}円 | 短信 |
| EPS 第1四半期（2027年3月期 1Q） | 20.00円 | 短信 |
| BPS（2025年3月末） | 540.00円 | 短信 |
| BPS（2026年3月末） | 600.00円 | 短信 |

## 3. 現在の株価指標

| 指標 | 値 |
|---|---|
| PER（実績／予想） | 11.9倍 ／ 10.8倍 |
| PBR | 1.67倍 |
| EV/EBITDA | — |

## 4. PER・PBR・EV/EBITDA の過去推移（年次の最高・最低・平均）

| 年度 | PER 高値 | PER 安値 | PER 平均 | PBR 高 | PBR 低 | PBR 平均 |
|---|---|---|---|---|---|---|
{history}

## 5. アナリスト予想

| 項目 | 値 | 出典・確度 |
|---|---|---|
| アナリスト予想のEPS成長率 | — | — |
"""

COMPETITORS = """# 競合情報 — テスト

## 3. 売上高の3年CAGR計算用データ

| 会社 | 3年前の売上高 | 直近の売上高 |
|---|---|---|
| アルファ社（1111） | 1,000 | 1,331 |
| ベータ社（2222） | 1,000 | 1,331 |
| トヨタ（7203） | 1,000 | 1,331 |

## 5. ROE・自己資本比率

| 会社 | 年度 | ROE | 自己資本比率 | 出典 |
|---|---|---|---|---|
| アルファ社（1111） | 2026/03 | 12.0% | 50% | 短信 |
| ベータ社（2222） | 2026/03 | 14.0% | 50% | 短信 |
| トヨタ（7203） | 2026/03 | 14.0% | 60% | 短信 |

## 6. PER・PBR・EV/EBITDA（基準日 {price_date}）

| 会社 | 株価 | 時価総額 | PER（実績） | PER（予想） | PBR | EV/EBITDA |
|---|---|---|---|---|---|---|
| アルファ社（1111） | 500円 | 100億円 | 12.0倍 | 11.0倍 | 1.8倍 | — |
| ベータ社（2222） | 800円 | 200億円 | 13.0倍 | 12.0倍 | 2.0倍 | — |
| トヨタ（7203） | 1,000円 | 100億円 | 11.9倍 | 10.8倍 | 1.67倍 | — |

## 11. 安全性の指標（最大5期）

| 会社 | 年度 | 総資産 | 自己資本 | 自己資本比率 | 有利子負債 | 現金及び現金同等物 | 流動資産 | 流動負債 | 出典・確度 |
|---|---|---|---|---|---|---|---|---|---|
| アルファ社（1111） | 2026/03 | 20,000 | 10,000 | — | 2,000 | 1,000 | 8,000 | 4,000 | 短信（一次） |
| ベータ社（2222） | 2026/03 | 30,000 | 15,000 | — | 0（科目なし） | 5,000 | 9,000 | 5,000 | 短信（一次） |
{ebitda}
"""

EBITDA_SECTION = """## 12. EV/EBITDA の材料（直近期。営業利益・減価償却費）

| 会社 | 年度 | 営業利益 | 減価償却費 | 出典・確度 |
|---|---|---|---|---|
| アルファ社（1111） | 2026/03 | 1,000 | 300 | 短信（一次） |
| ベータ社（2222） | 2026/03 | 2,000 | 500 | 短信（一次） |
"""

CAPITAL = """# 中期経営計画 — テスト

## 4. 資本政策・株主還元方針

- ROE 15%以上を目標とし、配当性向30%を維持する
"""


def _cells(values: dict[int, float]) -> str:
    return " | ".join(f"{values[y]:,.0f}" for y in YEARS)


def financials(gain: float = 0, net_income: dict | None = None, operating: dict | None = None) -> str:
    ni = net_income or NET_INCOME
    heads = " | ".join(f"{y}年3月期" for y in YEARS)
    return FINANCIALS.format(
        heads=heads, seps="---|" * len(YEARS), sales=_cells({y: 10000 + 500 * i for i, y in enumerate(YEARS)}),
        operating=_cells(operating or OPERATING), net_income=_cells(ni),
        eps=" | ".join(f"{ni[y] / 10:.2f}" for y in YEARS),
        gain=_cells({**{y: 0 for y in YEARS}, 2026: gain}), loss=_cells({y: 0 for y in YEARS}),
        assets=_cells({y: 10000 for y in YEARS}), equity=_cells({y: 6000 for y in YEARS}),
        debt=_cells({y: 1000 for y in YEARS}), cash=_cells({y: 3000 for y in YEARS}),
        cfo=_cells({y: 900 for y in YEARS}), depreciation=_cells({y: 200 for y in YEARS}))


def history(per: tuple[float, float] = (20, 10), pbr: tuple[float, float] = (2.5, 1.5), years=YEARS) -> str:
    return "\n".join(f"| {y}年3月期 | {per[0]} | {per[1]} | — | {pbr[0]} | {pbr[1]} | — |" for y in years)


def valuation_data(price: float = 1000, forecast: str = "92.40", price_date: str = PRICE_DATE,
                   hist: str | None = None) -> str:
    return VALUATION.format(collected=COLLECTED, price=f"{price:,.0f}", price_date=price_date, forecast=forecast,
                            history=history() if hist is None else hist)


def _company(root: Path, fin: str | None = None, val: str | None = None, ebitda: bool = True,
             growth: dict | None = None) -> Path:
    company = root / "companies" / "7203_toyota"
    competitors = COMPETITORS.format(price_date=PRICE_DATE, ebitda=EBITDA_SECTION if ebitda else "")
    for sub, name, text in (("ir", f"{COLLECTED}_financials-historical.md", financials() if fin is None else fin),
                            ("ir", f"{COLLECTED}_valuation-data.md", valuation_data() if val is None else val),
                            ("ir", f"{COLLECTED}_mid-term-plan.md", CAPITAL),
                            ("market", f"{COLLECTED}_competitors.md", competitors)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    write_growth(root, growth)
    return company


def write_growth(root: Path, result: dict | None = None, date: str = COLLECTED) -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / "growth"
    directory.mkdir(parents=True, exist_ok=True)
    body = {"verdict": "普通", "verdict_reason": "安定成長", "valid_until": "2027-03-30",
            "step1": {"eps_cagr": 8.0}, "step3": {"rating": "信頼できる", "basis": "達成率 100%"}, **(result or {})}
    (directory / f"{date}_growth.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    (directory / f"{date}_growth.md").write_text("# 成長性\n", encoding="utf-8")


def write_result(root: Path, kind: str, verdict: str, date: str = COLLECTED) -> None:
    directory = root / "companies" / "7203_toyota" / "analysis" / kind
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_{kind}.json").write_text(json.dumps({"verdict": verdict, "verdict_reason": "r"}),
                                                   encoding="utf-8")
    (directory / f"{date}_{kind}.md").write_text("# x\n", encoding="utf-8")


def _fresh_growth(monkeypatch) -> None:
    monkeypatch.setattr(VA.GR, "evaluate", lambda company, today: {"result": "fresh", "reason": "", "latest": None})


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    shutil.copytree(REPO / ".ai" / "templates" / "valuation", tmp_path / ".ai" / "templates" / "valuation")
    (tmp_path / "market" / "report").mkdir(parents=True)
    _company(tmp_path)
    _fresh_growth(monkeypatch)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = VA.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def company_obj(root: Path) -> P.Company:
    return P.Company(root, root / "companies" / "7203_toyota")


def cands_of(root: Path, measures: str | None = None) -> dict:
    company = company_obj(root)
    return X.candidates(company, I.gather_valuation(company), DAY, measures)


def prepared(root: Path, capsys, *extra: str) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", DAY, *extra, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def fill(md: Path, measures: str = "なし: 中期経営計画に改善策の記載なし") -> None:
    def answer(m: re.Match) -> str:
        key = m.group(1)
        if key in ("changes", "gaps"):
            return "- 初回の分析"
        if key == "measures":
            return measures
        return f"背景 {key}（brief による）"
    md.write_text(FILL_ANY.sub(answer, md.read_text(encoding="utf-8")), encoding="utf-8")


# ---------- va_rules ----------

HIST = [(f"{y}-03", 100.0, 0.0) for y in YEARS]


@pytest.mark.parametrize("current, zone", [(33, R.LOW), (33.4, R.LOW), (34, R.FAIR), (66, R.FAIR), (67, R.HIGH),
                                           (-5, R.LOW), (120, R.HIGH)])
def test_range_zone_boundaries(current, zone):
    assert R.range_zone(current, HIST)["zone"] == zone


def test_range_zone_needs_three_years_and_uses_the_newest_five():
    assert R.range_zone(10, HIST[:2])["zone"] is None
    hist = [("2015-03", 1000.0, 0.0)] + HIST  # the old wide year is outside the 5 years
    assert R.range_zone(50, hist)["high"] == 100.0


@pytest.mark.parametrize("current, zone", [(8.0, R.LOW), (8.1, R.FAIR), (11.9, R.FAIR), (12.0, R.HIGH)])
def test_peer_zone_boundaries(current, zone):
    assert R.peer_zone(current, [9.0, 10.0, 11.0])["zone"] == zone


def test_peer_zone_needs_two_peers_and_explains_growth_gaps():
    assert R.peer_zone(5.0, [10.0])["zone"] is None
    cheap = R.peer_zone(5.0, [10.0, 10.0], own_growth=2.0, peer_growths=[7.0, 7.0])
    assert cheap["raw_zone"] == R.LOW and cheap["zone"] == R.FAIR and cheap["explained"]
    assert R.peer_zone(5.0, [10.0, 10.0], own_growth=2.1, peer_growths=[7.0, 7.0])["zone"] == R.LOW
    dear = R.peer_zone(15.0, [10.0, 10.0], own_growth=20.0, peer_growths=[10.0, 10.0])
    assert dear["zone"] == R.FAIR


@pytest.mark.parametrize("z1, z2, rating, check", [
    (R.LOW, R.LOW, R.LOW, False), (R.LOW, R.FAIR, R.LOW, False), (R.LOW, R.HIGH, R.FAIR, True),
    (R.FAIR, R.FAIR, R.FAIR, False), (R.FAIR, R.HIGH, R.HIGH, False), (R.HIGH, R.LOW, R.FAIR, True),
])
def test_combine_matrix(z1, z2, rating, check):
    got = R.combine({"zone": z1, "basis": "a"}, {"zone": z2, "basis": "b"})
    assert (got["rating"], got["check"]) == (rating, check)


def test_combine_single_axis_and_none():
    assert R.combine({"zone": None, "basis": "a"}, {"zone": R.HIGH, "basis": "b"})["single_axis"]
    assert R.combine({"zone": None, "basis": "a"}, {"zone": None, "basis": "b"})["rating"] == R.PENDING


@pytest.mark.parametrize("ratings, verdict", [
    ({"a": R.LOW, "b": R.FAIR}, R.LOW),  # +0.5
    ({"a": R.HIGH, "b": R.FAIR}, R.HIGH),  # -0.5
    ({"a": R.LOW, "b": R.FAIR, "c": R.FAIR}, R.FAIR),  # +0.33
    ({"a": R.LOW, "b": R.NA, "c": R.PENDING}, R.PENDING),  # one scored
])
def test_score(ratings, verdict):
    assert R.score(ratings)["verdict"] == verdict


# ---------- va_series ----------

def test_cells():
    assert V.number("526円（終値、前日比 +2.14%）") == 526.0 and V.number("$146.62") == 146.62
    assert V.number("—（開示なし）") is None and V.number("(4.28)") == -4.28
    assert V.money("336億351万円") == (33603510000.0, "円")
    assert V.money("279.5億ドル") == (27950000000.0, "ドル")
    assert V.date_in("2026年10月9日 終値") == "2026-10-09"


def test_series_reads_price_eps_history_and_peers(repo):
    company = company_obj(repo)
    base = V.base(company, I.gather_valuation(company))
    assert base["price"]["price"] == 1000 and base["price"]["date"] == PRICE_DATE
    assert base["price"]["shares"] == 10_000_000
    assert base["market_cap"]["value"] == pytest.approx(10000)
    assert base["per_share"]["bps"]["value"] == 600  # the newest BPS row, not the older one
    assert base["per_share"]["eps_actual"]["value"] == 84  # the quarterly row is skipped
    assert base["forecast_eps"]["value"] == pytest.approx(92.4)
    assert [h["per_low"] for h in base["history"]] == [10] * 5  # 「PER 安値」 is read as the low
    assert base["history"][0]["pbr_low"] == 1.5
    latest = base["years"]["rows"][-1]
    assert (latest["net_income"], latest["operating_income"], latest["depreciation"], latest["debt"],
            latest["cash"], latest["eps"]) == (840, 1400, 200, 1000, 3000, 84)
    peers = base["peers"]
    assert [p["name"] for p in peers["peers"]] == ["アルファ社（1111）", "ベータ社（2222）"]
    alpha = peers["peers"][0]
    assert alpha["cagr"] == pytest.approx(10.0) and alpha["roe"] == 12.0
    assert alpha["ev_ebitda_calc"] == pytest.approx(11000 / 1300)  # (100億 + 2,000 − 1,000) ÷ (1,000 + 300)
    assert peers["own"]["roe"] == 14.0 and peers["date"] == PRICE_DATE


def test_history_reads_the_yuho_period_end_table():
    body = ("| 年度 | PER 高 | PER 低 |\n|---|---|---|\n| 2025年3月期 | 20 | 10 |\n\n"
            "### 有価証券報告書記載の期末PER（株価収益率）\n\n| 2025年3月期 | 2026年3月期 |\n|---|---|\n| 17.0倍 | 13.5倍 |\n")
    found = I.Found(I.SPEC["history"], "ok", Path("x.md"), "4. 過去推移", body)
    rows = {h["year"]: h for h in V.history_data(found)}
    assert rows["2025-03"]["per_end"] == 17.0 and rows["2026-03"]["per_end"] == 13.5
    assert rows["2025-03"]["per_high"] == 20


# ---------- the indicators (a hand-made base) ----------

def _rows(net_income: dict | None = None, operating: dict | None = None, gain: float | None = None) -> list[dict]:
    ni, op = net_income or NET_INCOME, operating or OPERATING
    return [{"year": f"{y}-03", "net_income": ni[y],
             "extra_gain": None if gain is None else (gain if y == 2026 else 0),
             "extra_loss": None if gain is None else 0, "operating_income": op[y], "depreciation": 200.0,
             "debt": 1000.0, "cash": 3000.0, "equity": 6000.0, "eps": ni[y] / 10} for y in YEARS]


def _peer(name: str, per_f: float, pbr: float, ev: float | None = None, cagr: float = 10.0, roe: float = 13.0) -> dict:
    return {"name": name, "price": None, "market_cap": None, "per_actual": per_f + 1, "per_forecast": per_f,
            "pbr": pbr, "ev_ebitda": None, "cagr": cagr, "roe": roe, "debt": None, "cash": None, "ebitda_year": None,
            "ev_ebitda_calc": ev}


def _base(rows: list[dict] | None = None, price: float = 1000.0, forecast: float | None = 92.4, bps: float = 600.0,
          hist: list[dict] | None = None, peers: list[dict] | None = None) -> dict:
    rows = rows or _rows()
    hist = hist if hist is not None else [{"year": f"{y}-03", "per_high": 20.0, "per_low": 10.0, "pbr_high": 2.5,
                                           "pbr_low": 1.5, "per_end": None} for y in YEARS]
    return {"price": {"price": price, "date": PRICE_DATE, "currency": "円", "shares": 1e7, "shares_source": "s",
                      "market_cap": None, "source": "", "price_cell": ""},
            "per_share": {"eps_actual": None, "eps_forecast": None, "bps": {"value": bps, "label": "BPS"}},
            "reported": {"per_actual": None, "per_forecast": None, "pbr": None, "roe_forecast": None},
            "history": hist, "analyst": None, "years": {"rows": rows, "splits": [], "odd": [], "unit": "百万円"},
            "latest_year": rows[-1]["year"],
            "forecast_eps": {"value": forecast, "label": "f", "target": None} if forecast is not None else None,
            "market_cap": {"value": price * 1e7 / 1e6, "basis": "b"},
            "peers": {"peers": peers if peers is not None else [_peer("A", 11.0, 1.8, 8.5), _peer("B", 12.0, 2.0, 6.0)],
                      "own": {"cagr": 10.0, "roe": 14.0, "row": None}, "date": PRICE_DATE}}


@pytest.mark.parametrize("gain, adjusted", [(83, False), (84, True)])  # 10% of 840
def test_eps_adjusted_at_ten_percent_of_net_income(gain, adjusted):
    s1 = X.eps_step(_base(_rows(gain=gain)))
    assert s1["adjusted"] is adjusted
    if adjusted:
        assert s1["eps_used"] == pytest.approx(84 * (840 - 84 * 0.7) / 840)


@pytest.mark.parametrize("ni_2026, op_2026, na", [
    (-10, 1400, "赤字"), (840, -5, "営業赤字"), (390, 1400, "50%以上減った"), (391, 1400, None)])
def test_per_not_applicable(ni_2026, op_2026, na):
    rows = _rows({**NET_INCOME, 2026: ni_2026}, {**OPERATING, 2026: op_2026})
    per = X.per_step(_base(rows), None)
    assert (na in per["na"]) if na else per["na"] is None
    assert (per["rating"] == R.NA) is bool(na)


def test_per_discount_also_judges_the_actual_per():
    base = _base(forecast=200.0)  # forecast PER 5.0 and actual PER 11.9 are both 割安: the higher PER is taken
    assert X.per_step(base, None)["used"] == "予想PER"
    discounted = X.per_step(base, {"step3": {"rating": X.DISCOUNT}})
    assert discounted["used"] == "実績PER" and discounted["per_used"] == pytest.approx(1000 / 84)


@pytest.mark.parametrize("price, rating", [(1000, R.LOW), (1400, R.FAIR), (1800, R.HIGH)])
def test_pbr_follows_the_fair_pbr(price, rating):
    # 適正PBR = 92.4 / 600 (15.4%) × 平均PER 15 (the mid of 20 / 10) = 2.31; 1000 / 600 = 1.67 is -28%
    pbr = X.pbr_step(_base(price=price))
    assert pbr["fair"]["fair"] == pytest.approx(2.31)
    assert pbr["rating"] == rating


def test_pbr_value_trap_needs_improvement_measures():
    rows = [dict(r, net_income=r["net_income"] / 3, eps=r["eps"] / 3) for r in _rows()]  # ROE 4.7%
    base = _base(rows, price=300.0, forecast=30.0, bps=600.0,
                 hist=[{"year": f"{y}-03", "per_high": 40.0, "per_low": 20.0, "pbr_high": 1.2, "pbr_low": 0.6,
                        "per_end": None} for y in YEARS],
                 peers=[_peer("A", 20.0, 1.0), _peer("B", 22.0, 1.1)])
    assert X.pbr_step(base)["before_trap"] == R.LOW  # PBR 0.5 against a fair PBR of 1.5
    assert X.pbr_step(base, "なし")["rating"] == R.FAIR
    assert X.pbr_step(base, None)["rating"] == R.FAIR  # 不明 counts as なし
    assert X.pbr_step(base, "あり")["rating"] == R.LOW


@pytest.mark.parametrize("cagr, rating", [(10.0, R.FAIR), (5.42, R.FAIR), (5.41, R.HIGH), (5.0, R.HIGH),
                                          (4.99, R.NA)])
def test_peg_boundaries(cagr, rating):
    base = _base(forecast=92.4)  # forecast PER 10.82; the company plan is +10%, so the standard is the CAGR
    peg = X.peg_step(base, X.per_step(base, None), {"step1": {"eps_cagr": cagr}})
    assert peg["rating"] == rating, peg["sentence"]


def test_peg_safety_margin_and_cyclical_years():
    base = _base(forecast=100.8)  # plan +20%
    peg = X.peg_step(base, X.per_step(base, None), {"step1": {"eps_cagr": 20.0}})  # 9.92 ÷ 20 = 0.50; pessimistic 0.99
    assert peg["rating"] == R.LOW and peg["margin"]
    halved = _base(_rows({**NET_INCOME, 2024: 330}))
    assert X.peg_step(halved, X.per_step(halved, None), {"step1": {"eps_cagr": 20.0}})["rating"] == R.NA


def test_ev_ebitda_value_history_and_divergence():
    base = _base()
    ev = X.ev_step(base, X.per_step(base, None))
    assert ev["value"] == pytest.approx((10000 + 1000 - 3000) / 1600)
    first = ev["history"][0]  # 2022: (20 × 600 + 1,000 − 3,000) ÷ 1,200
    assert first["high"] == pytest.approx(10000 / 1200) and first["basis"] == "PER × 純利益"
    rows = [dict(r, operating_income=-300.0) for r in _rows()]
    assert X.ev_step(_base(rows), {"rating": R.NA})["rating"] == R.NA  # EBITDA -100
    div = X._divergence({"rating": R.HIGH}, {"rating": R.LOW, "net_cash": 2000.0, "ebitda": 1600.0},
                        {"depreciation": 200.0, "debt": 1000.0, "equity": 6000.0})
    assert div["reasons"] == ["現金が多い（ネットキャッシュがプラス）"]


def test_step3_final_check_raises_a_cheap_verdict():
    items = {k: {"rating": R.LOW} for k, _ in X.INDICATORS}
    assert X.step3(items, {})["verdict"] == R.LOW
    raised = X.step3(items, {"cash_flow": {"verdict": "懸念"}})
    assert raised["verdict"] == R.FAIR and raised["final_check"]["raised"]
    assert X.step3(items, {"swot": {"verdict": "No"}})["verdict"] == R.FAIR


# ---------- end to end ----------

def test_candidates_end_to_end(repo):
    cands = cands_of(repo)
    ratings = {name: cands[key]["rating"] for key, name in X.INDICATORS}
    assert ratings == {"PER": R.LOW, "PBR": R.LOW, "PEG": R.FAIR, "EV/EBITDA": R.LOW}
    assert cands["verdict"] == R.LOW and cands["step3"]["average"] == pytest.approx(0.75)
    assert cands["peg"]["cases"]["standard"] == pytest.approx(8.0)  # min(EPS CAGR 8.0, plan 10.0)
    assert any(p.startswith("PER:") for p in cands["flip_prices"])
    assert X.warnings(cands) == []


def test_old_price_requests_a_price_collection(tmp_path, monkeypatch, capsys):
    shutil.copytree(REPO / ".ai" / "templates" / "valuation", tmp_path / ".ai" / "templates" / "valuation")
    _company(tmp_path, val=valuation_data(price_date="2026-09-30"))
    _fresh_growth(monkeypatch)
    code, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["price_age"] == 12
    assert any(X.PRICE_ITEM in r["items"] for r in out["missing_inputs"])
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and "--skip-collect" in out["error"]
    md = prepared(tmp_path, capsys, "--skip-collect")
    assert "分析日の12日前" in md.with_name(f"{DAY}_brief.md").read_text(encoding="utf-8")


def test_missing_peer_ebitda_is_requested(tmp_path):
    _company(tmp_path, ebitda=False)
    company = company_obj(tmp_path)
    found = I.gather_valuation(company)
    requests = X.collect_requests(company, found, X.candidates(company, found, DAY))
    assert any(X.EBITDA_ITEM in r["items"] for r in requests)


def test_growth_is_required(repo, monkeypatch, capsys):
    monkeypatch.setattr(VA.GR, "evaluate", lambda company, today: {"result": "none", "reason": "", "latest": None})
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "growth"
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and "growth" in out["error"]


def test_prepare_fill_build(repo, capsys):
    md = prepared(repo, capsys)
    text = md.read_text(encoding="utf-8")
    keys = FILL_ANY.findall(text)
    assert "cheap-reason" in keys and "measures" not in keys and "special-bg" not in keys
    assert "該当なし（EPS を調整していない）" in text and "${" not in text
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["verdict"] == R.LOW and out["PER"].startswith(R.LOW)
    result = json.loads((repo / out["json"]).read_text(encoding="utf-8"))
    assert result["valid_until"] == "2026-10-19" and result["price"]["date"] == PRICE_DATE
    assert result["step3"]["average"] == pytest.approx(0.75)
    built = md.read_text(encoding="utf-8")
    assert "**割安**" in built and "STEP 3 割安（平均点：+0.75）" in built
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "fresh" and out["next"] == "report_existing"
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-20", capsys=capsys)
    assert out["result"] == "expired"


def test_build_rejects_new_numbers_and_approximations(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    text = md.read_text(encoding="utf-8").replace("背景 report-points（brief による）", "PER は約 9.87倍 まで下がりうる")
    md.write_text(text, encoding="utf-8")
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 1
    joined = " ".join(out["issues"])
    assert "9.87" in joined and "概数" in joined


def test_a_concern_in_step2_turns_cheap_into_fair(repo, capsys):
    write_result(repo, "cash-flow", "懸念")
    md = prepared(repo, capsys)
    fill(md)
    code, out = run(repo, "build", "--company", "7203", capsys=capsys)
    assert code == 0 and out["verdict"] == R.FAIR
    assert "キャッシュフローが懸念" in out["verdict_reason"]


def test_value_trap_answer_decides_the_pbr(tmp_path, monkeypatch, capsys):
    shutil.copytree(REPO / ".ai" / "templates" / "valuation", tmp_path / ".ai" / "templates" / "valuation")
    fin = financials(net_income={y: v / 3 for y, v in NET_INCOME.items()})  # ROE 4.7%
    val = valuation_data(price=300, forecast="30.00", hist=history(per=(40, 20), pbr=(1.2, 0.6)))
    _company(tmp_path, fin=fin, val=val)
    _fresh_growth(monkeypatch)
    md = prepared(tmp_path, capsys)
    assert "measures" in FILL_ANY.findall(md.read_text(encoding="utf-8"))
    fill(md, measures="ROE の改善策は書かれている")  # no あり/なし/不明 choice
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 1 and any("あり: " in i for i in out["issues"])
    text = md.read_text(encoding="utf-8").replace("ROE の改善策は書かれている", "なし: 中期経営計画に記載なし")
    md.write_text(text, encoding="utf-8")
    code, out = run(tmp_path, "build", "--company", "7203", capsys=capsys)
    assert code == 0, out
    assert out["PBR"].startswith(R.FAIR) and out["measures"] == "なし"


def test_new_price_triggers_a_reanalysis(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    assert run(repo, "build", "--company", "7203", capsys=capsys)[0] == 0
    newer = repo / "companies" / "7203_toyota" / "raw" / "ir" / f"{DAY}_valuation-data.md"
    newer.write_text(valuation_data(price=1100, price_date=DAY), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "triggered"


def test_a_new_upstream_result_triggers_a_reanalysis(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    assert run(repo, "build", "--company", "7203", capsys=capsys)[0] == 0
    write_result(repo, "safety", "懸念", date=DAY)  # built later the same day
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["result"] == "triggered" and "安全性" in out["reason"]


def test_review_fixes():
    assert V.date_in("2026-02-31 と 2026-03-01") == "2026-03-01"  # an impossible date is skipped
    cell = "147.15ドル（取引中の値）。前営業日の確定終値 146.62ドル（10-12）"
    assert V.close_price(cell) == 146.62 and V.close_price("526円（終値）") == 526
    rich = _base(_rows(), price=10.0)  # market cap 100 < cash 3,000 - debt 1,000: EV negative
    assert X.ev_step(rich, X.per_step(rich, None))["rating"] == R.NA
    base = _base(forecast=200.0)  # forecast PER 5.0, actual 11.9: the range axis uses the actual PER
    assert X.per_step(base, None)["rule"]["axis1"]["position"] == round((1000 / 84 - 10) / 10 * 100)
    one = X.peg_step(_base(forecast=None), X.per_step(_base(forecast=None), None), {"step1": {"eps_cagr": 8.0}})
    assert "候補が1つだけ" in one["sentence"]


def test_bps_comes_from_the_tanshin_first(repo):
    data = repo / "companies" / "7203_toyota" / "data"
    data.mkdir(parents=True, exist_ok=True)
    head = "doc_id,document,filing_date,fiscal_year_end,context,element,value,unit\n"
    rows = ("1,決算短信,2026年５月13日,2026-03-31,CurrentYearInstant_ConsolidatedMember_ResultMember,NetAssetsPerShare,"
            "590.0,円\n"
            "2,第１四半期決算短信,2026年８月12日,2027-03-31,CurrentAccumulatedQ1Instant_ConsolidatedMember_ResultMember,"
            "NetAssetsPerShare,610.0,円\n"
            "2,第１四半期決算短信,2026年８月12日,2027-03-31,CurrentAccumulatedQ1Instant_NonConsolidatedMember_ResultMember,"
            "NetAssetsPerShare,99.0,円\n")
    (data / "tdnet_facts.csv").write_text(head + rows, encoding="utf-8")
    bps = cands_of(repo)["base"]["per_share"]["bps"]
    assert bps["value"] == 610.0 and bps["source"].startswith("data/tdnet_facts.csv")


def test_peer_multiples_are_price_over_per_share_figures():
    body = ("| 会社 | 株価 | 時価総額 | PER（実績） | PER（予想） | PBR | EV/EBITDA | EPS（実績） | EPS（予想） | BPS |\n"
            "|---|---|---|---|---|---|---|---|---|---|\n"
            "| アルファ社 | 1,000円 | 100億円 | 15.0倍 | 12.0倍 | 2.0倍 | — | 80.00 | — | 400.0 |\n"
            "| ベータ社 | 500円 | 50億円 | 10.0倍 | 9.0倍 | 1.0倍 | — | — | — | — |\n")
    found = I.Found(I.SPEC["peer_valuation"], "ok", Path("x.md"), "6. PER・PBR", body)
    alpha, beta = V.peer_table(found)
    assert alpha["per_actual"] == pytest.approx(12.5) and alpha["per_actual_shown"] == 15.0
    assert alpha["per_forecast"] == 12.0 and alpha["pbr"] == pytest.approx(2.5)  # no forecast EPS: the shown value
    assert alpha["computed"] == ["per_actual", "pbr"]
    assert (beta["per_actual"], beta["pbr"], beta["computed"]) == (10.0, 1.0, [])


def test_an_uncertain_share_count_gives_the_upper_bound_ev(tmp_path, monkeypatch):
    val = valuation_data().replace(
        "| 発行済株式数（自己株式を除く） | 10,000,000株 | 短信 |",
        "| 発行済株式数（自己株式を含む） | 12,000,000株 | 短信 |\n| 自己株式数 | 2,000,000株（交付後の残数は未確認） | 短信 |\n"
        "| 期末後のコーポレートアクション | 株式交換（自己株式を交付） | status.md |")
    _company(tmp_path, val=val)
    cands = cands_of(tmp_path)
    sens = cands["ev"]["sensitivity"]
    assert cands["base"]["price"]["shares"] == 10_000_000 and sens["shares"] == 12_000_000
    assert sens["value"] == pytest.approx((12000 + 1000 - 3000) / 1600)
    assert "上限" in cands["ev"]["sentence"]
    joined = " ".join(X.warnings(cands))
    assert "株式数" in joined and "株式分割" not in joined


def test_write_guard_protects_the_valuation_files(repo, capsys):
    prepared(repo, capsys)
    base = "companies/7203_toyota/analysis/valuation"
    rel = f"{base}/{DAY}_valuation.md"
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_valuation.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None


def test_unfilled_skeleton_does_not_validate(repo, capsys):
    text = prepared(repo, capsys).read_text(encoding="utf-8")
    template = (repo / ".ai" / "templates" / "valuation" / "valuation.md").read_text(encoding="utf-8")
    assert any("FILL" in i for i in D.validate(text, template, cands_of(repo)))
