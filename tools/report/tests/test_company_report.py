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
import cr_legends as L  # noqa: E402
import cr_status as S  # noqa: E402
import cr_technicals as T  # noqa: E402
import mdparse as M  # noqa: E402
import write_guard as WG  # noqa: E402

TODAY = "2026-10-31"
DIR = "3798_uls-group"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
STALE: dict = {"key": None, "result": "triggered"}  # the analysis the fake evaluate() reports as not fresh

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
                  "peers": [{"name": "アルファ社", "per_actual": 10.0, "per_forecast": 9.0, "pbr": 1.2,
                             "ev_ebitda_calc": 5.0, "cagr": 8.0, "roe": 12.0}],
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
    _materials(company, TODAY)
    return company


NEWS = """# プレスリリース

## 1. 適時開示・プレスリリース
| 日付 | 見出し | 要旨 | URL |
|---|---|---|---|
| 2026-10-28 | 第1四半期決算短信 | 増収 | https://example.com/a |
| 2026-07-20 | 新サービス | 見出しのみ | https://example.com/b |
"""


def _materials(company: Path, day: str) -> None:
    """The collected material the report checks for freshness (cr_materials), dated `day`."""
    for sub, name, text in (("news", f"{day}_press-releases.md", NEWS),
                            ("ir", f"{day}_valuation-data.md", "# 株価指標\n")):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")


@pytest.fixture
def repo(tmp_path, monkeypatch):
    shutil.copytree(REPO / ".ai" / "templates" / "company-report", tmp_path / ".ai" / "templates" / "company-report")
    (tmp_path / "market" / "report").mkdir(parents=True)
    (tmp_path / "market" / "report" / "2026-10-26_outlook.md").write_text(OUTLOOK, encoding="utf-8")
    STALE.update(key=None, result="triggered")

    def step_state(step, company, today):
        found = S.latest(step, company)
        return {"key": step.key, "skill": step.skill, "label": step.label, "step": step.number,
                "result": STALE["result"] if step.key == STALE["key"] else "fresh", "reason": "新しい raw がある",
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
    "break": "- 【悪化】営業利益率が2期連続で同業平均を下回る\n- 【悪化】ROE が2期連続で8%を下回る",
    "watch": "- 次の決算で進捗率を確かめる\n- 生成AI の影響を確かめる",
}


FACTOR_WORDS = "地合い・株価のテクニカル・直近の決算の進捗・株価の割安さ・成長性・収益性・キャッシュフロー・安全性・業界の魅力度・" \
               "勝てる理由・強みの持続性・強みで脅威に対抗できるか"


def _legend_verdicts(text: str) -> dict:
    """{key: 評価} from the md's 5章 table (the script's rows)."""
    keys = {name: key for key, name in L.NAMES.items()}
    return {keys[m.group(1)]: M.split_row(m.group(0))[1] for m in L.ROW.finditer(text)}


def _fill(text: str, horizons: dict) -> str:
    legends = _legend_verdicts(text)

    def repl(m: re.Match) -> str:
        key = m.group(1)
        if key in horizons:
            return f"{horizons[key]}。{FACTOR_WORDS}を確かめた。"
        if key in legends:
            return f"{L.SHORT[key]}{L.PHRASE}: {legends[key]}。項目の値で決めた。"
        if key == "technical":
            state = re.search(r"^\| 状態 \| (.+?)（", text, re.M)
            return f"今の状態は{state.group(1) if state else T.NO_DATA}。RSI と移動平均で決まった。"
        if key == "phase":  # the skeleton's instruction carries the script's verdict
            return f"株価の局面: {re.search(r'「株価の局面: (.+?)。」', m.group(0)).group(1)}。52週の位置で決まった。"
        if key == "winds":
            return f"{re.search(r'の結論（(.+?)）', m.group(0)).group(1)}。地合いレポートから。"
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


def test_use_existing_skips_triggered_analyses(repo, capsys):
    company = _company(repo)
    STALE["key"] = "moat"
    out = _run(repo, capsys, "check", "--company", "3798", "--date", TODAY, "--use-existing")
    assert out["next"] == "prepare"
    gate = _prepare(repo, capsys)
    assert not gate["ok"] and "--use-existing" in gate["error"]
    prepared = _run(repo, capsys, "prepare", "--company", "3798", "--date", TODAY, "--skip-prices", "--use-existing")
    assert prepared["ok"] and prepared["used_existing"] == ["moat（2026-10-20）"]
    md = company / "reports" / f"{TODAY}_company-report.md"
    md.write_text(_fill(md.read_text(encoding="utf-8"), prepared["horizons"]), encoding="utf-8")
    assert _run(repo, capsys, "build", "--company", "3798")["ok"]
    html = (company / "reports" / f"{TODAY}_company-report.html").read_text(encoding="utf-8")
    assert 'class="notice"' in html and "作り直していない分析" in html


def test_use_existing_still_runs_expired(repo, capsys):
    _company(repo)
    STALE["key"] = "moat"
    STALE["result"] = "expired"
    out = _run(repo, capsys, "check", "--company", "3798", "--date", TODAY, "--use-existing")
    assert out["next"] == "moat"


def test_stale_outlook_asks_for_market_report(repo, capsys):
    _company(repo)
    out = _run(repo, capsys, "check", "--company", "3798", "--date", "2026-12-31")
    assert out["next"] == "market-report"


def test_stale_news_asks_collect_company_info_with_the_agent_and_items(repo, capsys):
    company = _company(repo)
    for p in (company / "raw" / "news").iterdir():
        p.unlink()
    _materials(company, "2026-10-01")  # news and the valuation data are a month old
    out = _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)
    assert out["next"] == "collect-company-info"
    assert out["collect"]["mode"] == "update" and out["collect"]["agents"] == ["collect-ir"]
    news = next(m for m in out["materials"] if m["key"] == "news")
    assert news["stale"] and news["date"] == "2026-10-01"
    # one collection did not bring it: go on with the old material (the report marks it)
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY, "--use-stale")["next"] == "prepare"


def test_news_table_shorter_than_three_months_is_stale(repo, capsys):
    company = _company(repo)
    short = NEWS.replace("2026-07-20", "2026-10-20")
    (company / "raw" / "news" / f"{TODAY}_press-releases.md").write_text(short, encoding="utf-8")
    out = _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)
    news = next(m for m in out["materials"] if m["key"] == "news")
    assert out["next"] == "collect-company-info" and "3か月" in news["why"]


def test_prepare_fill_build_flow(repo, capsys):
    company = _company(repo)
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "prepare"
    out = _prepare(repo, capsys)
    assert out["ok"], out
    assert (out["step1"], out["step2"], out["step3"]) == ("A", "A", "割安")
    assert out["horizons"] == {"short": "投資検討", "mid": "投資検討", "long": "投資検討"}
    # 4.2 comes from the brief's candidates; 4.3 stays with the writer when there are too few gaps for 2 lines
    # 6.4 is written by the script when there is no market report sector (the fixture has no profile)
    assert set(out["fill_keys"]) == {"summary", "about", "short", "mid", "long", "thesis", "watch",
                                     "buffett", "soros", "rogers", "technical", "moves", "phase"}
    assert out["technical"]["state"] and out["technical"]["score"] is not None
    assert set(out["legends"]) == set(L.KEYS)
    assert all(v in (L.PREFER, L.HOLD, L.AVOID) for v in out["legends"].values())
    md = company / "reports" / f"{TODAY}_company-report.md"
    assert "### 4.2 判断が崩れる条件\n\n- 【悪化】" in md.read_text(encoding="utf-8")  # 投資検討: 悪化 first
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "write"
    blocked = _run(repo, capsys, "build", "--company", "3798")
    assert not blocked["ok"] and any("FILL" in i for i in blocked["issues"])
    md.write_text(_fill(md.read_text(encoding="utf-8"), out["horizons"]), encoding="utf-8")
    built = _run(repo, capsys, "build", "--company", "3798")
    assert built["ok"], built
    html = (company / "reports" / f"{TODAY}_company-report.html").read_text(encoding="utf-8")
    assert "<svg" in html and "投資検討" in html and "52週" in html and "用語集" in html and "ROE" in html
    assert "<dt>FCF</dt>" in html  # FCF is in the report now (the investors' view, B6), so it is in the glossary
    assert 'id="legends"' in html and "ウォーレン・バフェット" in html
    assert 'id="technical"' in html and "押し目の目安" in html and 'class="hl sup"' in html and "<dt>RSI</dt>" in html
    assert "## 4.1 テクニカル" in (company / "reports" / f"{TODAY}_company-report_brief.md").read_text(encoding="utf-8")
    assert "## 投資の神の視点" in (company / "reports" / f"{TODAY}_company-report_brief.md").read_text(encoding="utf-8")
    result = json.loads((company / "reports" / f"{TODAY}_company-report.json").read_text(encoding="utf-8"))
    assert result["horizons"]["long"]["verdict"] == "投資検討" and result["price_range"]["source"] == "prices"
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "report_existing"
    again = _prepare(repo, capsys)
    assert not again["ok"] and "--redo" in again["error"]
    redone = _run(repo, capsys, "prepare", "--company", "3798", "--date", TODAY, "--skip-prices", "--redo")
    assert redone["ok"] and redone["superseded"].endswith(f"reports/_superseded/{TODAY}-1")
    moved = repo / redone["superseded"]
    assert (moved / f"{TODAY}_company-report.html").exists() and (moved / f"{TODAY}_company-report.json").exists()
    assert "FILL:" in md.read_text(encoding="utf-8")  # a fresh skeleton, the built report kept in _superseded
    assert _run(repo, capsys, "check", "--company", "3798", "--date", TODAY)["next"] == "write"


PEER_MARGINS = {"profitability": {"step2": {"year": "2026-03", "self": 18.3, "avg": 16.3, "diff": 2.0,
                                            "rows": [{"peers": [{"name": "アルファ社", "margin": 14.0}]}]}}}


def test_brief_shows_nearest_boundary_recent_material_median_and_directions(repo, capsys):
    company = _company(repo, PEER_MARGINS)
    out = _prepare(repo, capsys)
    brief = (company / "reports" / f"{TODAY}_company-report_brief.md").read_text(encoding="utf-8")
    assert "まであと" in brief.split("## 3.")[1].split("## 4.")[0]  # every horizon names its nearest boundary
    assert "## 直近の材料" in brief and "52週高値から" in brief and "S1" in brief  # SWOT strengths and the drop
    assert "同業平均 16.3%（中央値 14.0%）" in brief
    assert "### 5.1 判定が上がる条件" in brief and "### 5.2 判定が下がる条件" in brief
    assert "（材料不足のため保守的に判定）（材料不足のため保守的に判定）" not in brief
    assert out["ok"]


def test_build_requires_the_direction_word_on_each_break_line(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    filled = _fill(md.read_text(encoding="utf-8"), out["horizons"])
    md.write_text(filled.replace("【悪化】営業利益率", "営業利益率"), encoding="utf-8")
    issues = _run(repo, capsys, "build", "--company", "3798")["issues"]
    assert any("4.2" in i and "【改善】" in i for i in issues)


def test_conservative_note_is_not_doubled():
    import cr_factors as CF
    a = {"verdict": "懸念", "reason": "不明の年を構造とみなした（材料不足のため保守的に判定）", "conservative": ["x"],
         "step": "2-2", "label": "成長性"}
    assert CF.analysis_factor(a)["reason"].count("保守的に判定") == 1
    assert "保守的" in CF.analysis_factor({**a, "reason": "理由"})["reason"]


def test_conservative_note_does_not_claim_the_verdict_came_from_missing_material():
    import cr_factors as CF
    a = {"verdict": "懸念", "reason": "手順1が停滞・縮小", "conservative": ["M&A が分からない"],
         "step": "2-2", "label": "成長性"}
    reason = CF.analysis_factor(a)["reason"]
    assert "材料不足のため保守的に判定" not in reason
    assert "一部の項目は材料不足のため保守的に扱った" in reason


def test_valuation_factor_counts_only_the_scored_indicators():
    import cr_factors as CF
    v = {"verdict": "妥当", "date": "2026-11-01", "detail": {"average": 0.0, "scored": 3, "sheet": "s"}}
    assert CF.valuation_factor(v)["value"] == "妥当（3指標の平均点 +0.00）"
    old = {**v, "detail": {"average": 0.0, "sheet": "s"}}
    assert CF.valuation_factor(old)["value"] == "妥当（指標の平均点 +0.00）"


def test_html_shows_3c_swot_peers_dividends_and_tooltips(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    md.write_text(_fill(md.read_text(encoding="utf-8"), out["horizons"]), encoding="utf-8")
    assert _run(repo, capsys, "build", "--company", "3798")["ok"]
    html = (company / "reports" / f"{TODAY}_company-report.html").read_text(encoding="utf-8")
    assert "期間ごとの良い点・悪い点" in html and 'class="gauge"' in html
    assert 'class="swot"' in html and "SWOT分析" in html
    assert "同業比較" in html and "株主還元" in html and "成長の見通し" in html
    assert "同業の平均" in html and "同業の中央値" in html and "最も近い境目" in html
    assert 'class="term"' in html
    assert not re.search(r'data-tip="[^"]*<span', html)  # a tooltip never lands inside an attribute
    assert '<svg' in html and not re.search(r"<svg[^>]*>[^<]*<span class=\"term\"", html)


def test_kbf_table_uses_short_peer_headers_with_a_legend():
    import cr_sections as CS
    detail = {"kbf": ["実績"], "kbf_table": [{"kbf": "実績", "self": "？", "basis": "根拠",
                                               "peers": {"ライズ・コンサルティング・グループ（9168）": "○", "ベイカレント（6532）": "？"}}]}
    out = CS.three_c_block(detail, {"verdict": "あいまい", "reason": "理由"})
    assert '<th class="nw">競合A</th>' in out and '<th class="nw">競合B</th>' in out
    assert "競合A: ライズ・コンサルティング・グループ（9168）" in out
    assert "<th class=\"nw\">ライズ" not in out  # long names stay out of the headers so the basis column keeps its width


def test_annotate_wraps_first_term_per_section_only():
    import cr_sections as CS
    html = ('<section id="a"><p>ROE が高い。ROE は上昇。</p><svg><text>ROE</text></svg></section>'
            '<section id="b"><p>ROE と PER</p><dt>PER</dt></section>')
    out = CS.annotate(html)
    assert out.count('data-tip=') == 3  # ROE in a, ROE and PER in b (the glossary's own dt is skipped)
    assert "<text>ROE</text>" in out


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


def test_build_warns_on_long_text_without_failing(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    filled = _fill(md.read_text(encoding="utf-8"), out["horizons"])
    md.write_text(filled.replace(FILLED["about"], FILLED["about"] * 20), encoding="utf-8")
    built = _run(repo, capsys, "build", "--company", "3798")
    assert built["ok"], built
    assert any(w.startswith("2.") and "字" in w for w in built["warnings"])


def test_one_cash_flow_concern_is_weighed_not_a_knockout(repo, capsys):
    _company(repo, {"cash-flow": {"verdict": "懸念",
                                  "step3": {"rating": "懸念", "sentence": "営業CF対純利益比率 0.77倍"}}})
    out = _prepare(repo, capsys)
    assert out["step2"] == "A"  # 良好3・懸念1 = +0.5
    assert out["horizons"] == {"short": "投資検討", "mid": "投資検討", "long": "投資検討"}


def test_serious_red_flag_passes_every_horizon(repo, capsys):
    _company(repo, {"cash-flow": {"verdict": "懸念", "step1": {"rating": "懸念", "sentence": "営業CF がマイナス"}}})
    out = _prepare(repo, capsys)
    assert out["step2"] == "C"
    assert out["horizons"] == {"short": "見送り", "mid": "見送り", "long": "見送り"}


def test_horizons_weigh_differently(repo, capsys):
    _company(repo, {"moat": {"verdict": "なし"}, "three-c": {"verdict": "あいまい"},
                    "five-forces": {"attractiveness": "低"}, "profitability": {"verdict": "普通"},
                    "growth": {"verdict": "普通"}})
    out = _prepare(repo, capsys)
    assert out["horizons"]["short"] == "投資検討" and out["horizons"]["long"] != "投資検討"


def test_pending_three_c_keeps_step1_provisional_but_scores_the_horizons(repo, capsys):
    _company(repo, {"three-c": {"verdict": "判定保留"}})
    out = _prepare(repo, capsys)
    assert out["step1"] == "B（暫定）"
    assert out["horizons"]["long"] == "投資検討"  # the pending 3C counts as 0 in the long-horizon score


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
    assert D.horizon_rows(facts) in text and facts["step3"]["verdict"] == "割高"


def test_build_checks_the_legend_section(repo, capsys):
    company = _company(repo)
    out = _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    filled = _fill(md.read_text(encoding="utf-8"), out["horizons"])
    verdict = out["legends"]["buffett"]
    other = next(v for v in (L.PREFER, L.HOLD, L.AVOID) if v != verdict)
    # the writer may not change the script's table, drop the phrase, or claim the investor would trade
    broken = filled.replace(f"| ウォーレン・バフェット（長期） | {verdict} |", f"| ウォーレン・バフェット（長期） | {other} |")
    broken = broken.replace(f"バフェット{L.PHRASE}: {verdict}。", "バフェットなら買う。")
    md.write_text(broken, encoding="utf-8")
    issues = _run(repo, capsys, "build", "--company", "3798")["issues"]
    assert any("投資の神の表" in i for i in issues)
    assert any("で書き始める" in i for i in issues) and any("売買" in i for i in issues)


def test_kept_draft_refreshes_the_legend_rows(repo, capsys):
    company = _company(repo)
    _prepare(repo, capsys)
    md = company / "reports" / f"{TODAY}_company-report.md"
    text = md.read_text(encoding="utf-8")
    md.write_text(L.ROW.sub("| ウォーレン・バフェット（長期） | 古い評価 | 古い理由 |", text, count=1), encoding="utf-8")
    again = _prepare(repo, capsys)
    assert again["kept"] and "古い評価" not in md.read_text(encoding="utf-8")


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
