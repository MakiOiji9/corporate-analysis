import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect"), str(REPO / "tools" / "guard")]

import company_report as CR  # noqa: E402
import cr_doc as D  # noqa: E402
import cr_status as S  # noqa: E402
import write_guard as WG  # noqa: E402

TODAY = "2026-10-31"
DIR = "3798_uls-group"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
STALE: dict = {"key": None}  # the analysis the fake evaluate() reports as not fresh

RESULTS = {
    "five-forces": {"attractiveness": "中", "total": 6, "industry": "IT コンサルティング",
                    "factors": [{"name": "新規参入の脅威", "rating": "強", "reason": "参入障壁が低い"}]},
    "three-c": {"verdict": "明確", "win_reason": "実績で選ばれる", "customer": {"conclusion": "大企業"}},
    "moat": {"verdict": "広い", "durability": "5年は崩れない", "effective_moats": ["スイッチングコスト"]},
    "swot": {"verdict": "Yes", "sentence": "強みで脅威に対抗できる",
             "top_strength": {"id": "S1", "fact": "継続取引", "impact": "大"},
             "top_threat": {"id": "T1", "fact": "生成AI", "impact": "大"}},
    "profitability": {"verdict": "良好", "step1": {"average": 15.3, "minimum": 12.9},
                      "step2": {"year": "2026-03", "self": 18.3, "avg": 16.3, "diff": 2.0},
                      "roe_rows": [{"year": "2025-03", "roe": 18.0}, {"year": "2026-03", "roe": 18.8}],
                      "handoff": {"report_points": "ROE は平均 15.3%"}},
    "growth": {"verdict": "良好", "step1": {"rating": "高成長", "sales_cagr": 15.1, "eps_cagr": 16.2},
               "step3": {"rating": "信頼できる", "average": 123.5},
               "progress": {"quarter": 1, "items": {"operating_income": {"progress": 26.5, "prior_progress": 29.3}}},
               "rows": [{"year": "2025-03", "sales": 14000, "operating_income": 2600, "net_income": 1600, "eps": 29},
                        {"year": "2026-03", "sales": 16600, "operating_income": 3046, "net_income": 2027, "eps": 36}]},
    "safety": {"verdict": "良好", "step1": {"items": [{"name": "自己資本比率", "value": 74.7, "peer_avg": 71.0,
                                                  "rating": "クリア", "target": "40%以上"}]}},
    "cash-flow": {"verdict": "良好", "step1": {"rating": "良好", "sentence": "営業CF はすべての年でプラス"},
                  "cf_rows": [{"year": "2026-03", "cfo": 1994, "fcf": 1463, "net_income": 2027, "ratio": 0.98}]},
    "valuation": {"verdict": "割安", "verdict_reason": "4指標の平均 +0.75",
                  "price": {"value": 541.0, "date": "2026-10-30", "currency": "円"},
                  "per": {"rating": "割安", "sentence": "予想PER 13.3倍",
                          "rule": {"axis1": {"low": 11.3, "high": 32.6, "position": 17}}},
                  "pbr": {"rating": "割安", "sentence": "PBR 2.56倍"}, "peg": {"rating": "妥当", "sentence": "PEG 1.08"},
                  "ev": {"rating": "割安", "sentence": "EV/EBITDA 6.9倍"}, "sheet": "PER 割安／STEP 3 割安",
                  "flip_prices": ["PER: 割高圏になる株価 1,035円 以上"]},
}

OUTLOOK = """# 地合い

## 1. 総合判断

| 市場 | 注意の度合い | 金融環境 | 景気 | 市場のストレス | 前回 | 判断の要約 |
|---|---|---|---|---|---|---|
| 日本 | 注意 | 中立 | 横ばい | 普通 | 注意 | 落ち着いている |

## 4. 展望

| 期間 | 市場 | 判断 | 基本シナリオ | 上振れ要因 | 下振れ要因 | 確認する指標・イベント |
|---|---|---|---|---|---|---|
| 短期 | 日本 | 注意 | 横ばい | 円安 | 円高 | 日銀会合 |
| 中期 | 日本 | 平常 | 回復 | 賃上げ | 景気後退 | 短観 |
| 長期 | 日本 | 平常 | 成長 | 改革 | 人口減 | GDP |
"""

STATUS = """# データ鮮度

## 1. データ鮮度

| 区分 | 最新データの時点 | 取得日 | raw ファイル | 次回更新トリガー |
|---|---|---|---|---|
| 四半期決算 | 1Q | 2026-10-11 | data/tdnet_facts.csv | 2027年3月期 中間決算の発表 |
"""


def _company(root: Path, verdicts: dict | None = None) -> Path:
    company = root / "companies" / DIR
    (company / "reports").mkdir(parents=True)
    (company / "overview.md").write_text("# ULSグループ（3798）\n", encoding="utf-8")
    (company / "status.md").write_text(STATUS, encoding="utf-8")
    for kind, result in RESULTS.items():
        directory = company / "analysis" / kind
        directory.mkdir(parents=True)
        body = {**result, **(verdicts or {}).get(kind, {}),
                "md": f"companies/{DIR}/analysis/{kind}/2026-10-20_{kind}.md"}
        (directory / f"2026-10-20_{kind}.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        (directory / f"2026-10-20_{kind}.md").write_text("# done\n", encoding="utf-8")
    day = dt.date(2025, 10, 1)
    lines = ["date,open,high,low,close,adj_close,volume,retrieved"]
    for i in range(400):
        close = 549 - (i % 50)  # a sawtooth that ends low in its 52-week range
        lines.append(f"{(day + dt.timedelta(days=i)).isoformat()},{close},{close + 5},{close - 5},{close},{close},"
                     f"100,{TODAY}")
    (company / "data").mkdir()
    (company / "data" / "prices.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return company


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REPO / ".ai" / "templates" / "company-report", tmp_path / ".ai" / "templates" / "company-report")
    (tmp_path / "market" / "report").mkdir(parents=True)
    (tmp_path / "market" / "report" / "2026-10-26_outlook.md").write_text(OUTLOOK, encoding="utf-8")
    STALE["key"] = None

    def step_state(step, company, today):
        found = S.latest(step, company)
        return {"key": step.key, "skill": step.skill, "label": step.label, "step": step.number,
                "result": "triggered" if step.key == STALE["key"] else "fresh", "reason": "",
                "date": found[0] if found else None, "verdict": found[1].get(step.verdict_key) if found else None}

    monkeypatch.setattr(S, "step_state", step_state)
    return tmp_path


def _run(root: Path, capsys, *argv: str) -> dict:
    CR.main(list(argv), root)
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _prepare(root: Path, capsys) -> dict:
    return _run(root, capsys, "prepare", "--company", "3798", "--date", TODAY, "--skip-prices")


FILLED = {
    "summary": "- 大企業向けの IT コンサルで、売上高は 16,600百万円\n- ROE 18.8% で財務も良好、株価は割安\n"
               "- 短期・中期・長期とも投資検討",
    "about": "大企業に IT コンサルティングを提供し、売上高は 16,600百万円。",
    "break": "- 営業利益率が2期連続で同業平均を下回る\n- ROE が2期連続で8%を下回る",
    "watch": "- 次の決算で進捗率を確かめる\n- 生成AI の影響を確かめる",
}


def _fill(text: str, horizons: dict) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in horizons:
            return f"{horizons[key]}。条件をすべて満たす。"
        return FILLED.get(key, "投資の理由は実績で選ばれること。")
    return FILL_ANY.sub(repl, text)


def test_check_reports_first_not_fresh_skill(repo, capsys):
    _company(repo)
    STALE["key"] = "moat"
    out = _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)
    assert out["ok"] and out["next"] == "moat"
    assert [s["skill"] for s in out["steps"]] == [s.skill for s in S.STEPS]
    gate = _prepare(repo, capsys)
    assert not gate["ok"] and "moat" in gate["error"]


def test_stale_outlook_asks_for_market_report(repo, capsys):
    _company(repo)
    out = _run(repo, capsys, "check", "--company", "3798", "--date", "2026-12-31")
    assert out["next"] == "market-report"


def test_prepare_fill_build_flow(repo, capsys):
    company = _company(repo)
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "prepare"
    out = _prepare(repo, capsys)
    assert out["ok"], out
    assert (out["step1"], out["step2"], out["step3"]) == ("A", "A", "割安")
    assert out["horizons"] == {"short": "投資検討", "mid": "投資検討", "long": "投資検討"}
    assert set(out["fill_keys"]) == {"summary", "about", "short", "mid", "long", "thesis", "break", "watch"}
    md = company / "reports" / f"{TODAY}_company-report.md"
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "write"
    blocked = _run(repo, capsys, "build", "--company", "3798")
    assert not blocked["ok"] and any("FILL" in i for i in blocked["issues"])
    md.write_text(_fill(md.read_text(encoding="utf-8"), out["horizons"]), encoding="utf-8")
    built = _run(repo, capsys, "build", "--company", "3798")
    assert built["ok"], built
    html = (company / "reports" / f"{TODAY}_company-report.html").read_text(encoding="utf-8")
    assert "<svg" in html and "投資検討" in html and "52週" in html and "用語集" in html and "ROE" in html
    assert "<dt>FCF</dt>" not in html  # the brief's writing rules do not put terms into the glossary
    result = json.loads((company / "reports" / f"{TODAY}_company-report.json").read_text(encoding="utf-8"))
    assert result["horizons"]["long"]["verdict"] == "投資検討" and result["price_range"]["source"] == "prices"
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "report_existing"
    again = _prepare(repo, capsys)
    assert not again["ok"] and "--redo" in again["error"]


def test_html_escapes_written_text(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    text = _fill(md.read_text(encoding="utf-8"), out["horizons"])
    md.write_text(text.replace("投資の理由は実績で選ばれること。", "<script>alert(1)</script>実績"), encoding="utf-8")
    assert _run(repo, capsys, "build", "--company", "3798")["ok"]
    html = (company / "reports" / f"{TODAY}_company-report.html").read_text(encoding="utf-8")
    assert "<script>alert(1)" not in html and "&lt;script&gt;alert(1)" in html


def test_build_rejects_changed_verdicts_and_forbidden_words(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    filled = _fill(md.read_text(encoding="utf-8"), out["horizons"])
    md.write_text(filled.replace("| 長期（3年以上） | 投資検討", "| 長期（3年以上） | 見送り"), encoding="utf-8")
    issues = _run(repo, capsys, "build", "--company", "3798")["issues"]
    assert any("結論の表" in i for i in issues)
    md.write_text(filled.replace("投資の理由は実績で選ばれること。", "今が買い時。おそらく上がる。"), encoding="utf-8")
    issues = _run(repo, capsys, "build", "--company", "3798")["issues"]
    assert any("推奨・推測" in i for i in issues)
    md.write_text(filled.replace("- 生成AI の影響を確かめる\n", ""), encoding="utf-8")
    issues = _run(repo, capsys, "build", "--company", "3798")["issues"]
    assert any("4.3" in i for i in issues)


def test_cash_flow_concern_passes_every_horizon(repo, capsys):
    _company(repo, {"cash-flow": {"verdict": "懸念"}})
    out = _prepare(repo, capsys)
    assert out["step2"] == "C"
    assert out["horizons"] == {"short": "見送り", "mid": "見送り", "long": "見送り"}


def test_pending_three_c_gives_provisional_verdicts(repo, capsys):
    _company(repo, {"three-c": {"verdict": "判定保留"}})
    out = _prepare(repo, capsys)
    assert out["step1"] == "B（暫定）"
    assert out["horizons"]["long"] == "判定保留（暫定: 投資検討）"


def test_kept_draft_follows_new_verdicts(repo, capsys):
    company = _company(repo)
    _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:about", "書いた。<!-- FILL:about"), encoding="utf-8")
    (company / "analysis" / "valuation" / "2026-10-20_valuation.json").write_text(
        json.dumps({**RESULTS["valuation"], "verdict": "割高"}, ensure_ascii=False), encoding="utf-8")
    out = _prepare(repo, capsys)
    text = md.read_text(encoding="utf-8")
    facts = json.loads((company / "reports" / f"{TODAY}_company-report_facts.json").read_text(encoding="utf-8"))
    assert out["kept"] and "書いた。" in text
    assert D.horizon_rows(facts) in text and "| 長期（3年以上） | ウォッチ |" in text


def test_write_guard_report_files(repo):
    company = _company(repo)
    rel = f"companies/{DIR}/reports/{TODAY}_company-report"
    for suffix in (".html", ".json", "_facts.json", "_brief.md"):
        assert "スクリプト" in WG.decide("Write", rel + suffix, repo, TODAY)
    assert "prepare" in WG.decide("Edit", rel + ".md", repo, TODAY)
    (company / "reports" / f"{TODAY}_company-report.md").write_text("x", encoding="utf-8")
    assert "上書き" in WG.decide("Write", rel + ".md", repo, TODAY)
    assert WG.decide("Edit", rel + ".md", repo, TODAY) is None
    old = f"companies/{DIR}/reports/2026-10-01_company-report"
    (repo / (old + ".md")).write_text("x", encoding="utf-8")
    (repo / (old + ".json")).write_text("{}", encoding="utf-8")
    assert "変更禁止" in WG.decide("Edit", old + ".md", repo, TODAY)
