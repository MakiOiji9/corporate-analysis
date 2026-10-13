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

import sw_doc as D  # noqa: E402
import sw_metrics as X  # noqa: E402
import sw_paths as P  # noqa: E402
import swot as SW  # noqa: E402
import write_guard as G  # noqa: E402

DAY = "2026-10-12"
COLLECTED = "2026-10-01"
FF_DAY, TC_DAY, MOAT_DAY = "2026-10-03", "2026-10-04", "2026-10-05"
OUTLOOK_WEEK = "2026-10-05"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")
COMPANY_DIR = "7203_toyota"

YUHO = """# 有価証券報告書 抜粋 — テスト

## 2. 事業の内容・セグメント情報（p.5）

- 自動車事業の単一セグメント

## 3. 主要な販売先（売上高の10%以上）（p.22）

| 相手先 | 金額 | 比率 |
|---|---|---|
| A社 | 2,000 | 12.0% |

## 4. 事業等のリスク（要旨）（p.16）

- EV への移行
"""

FINANCIALS = """# 財務時系列 — テスト

## 1. 損益・貸借・CF（10年サマリー）

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2025/03 | 15,000百万円 | 2,800百万円 |
| 2026/03 | 16,600百万円 | 3,046百万円 |

## 4. 会社計画（期初予想）と実績

| 年度 | 売上高 | 営業利益 |
|---|---|---|
| 2027/03 | 20,200百万円 | 3,700百万円 |
"""

MTP = """# 中期経営計画 — テスト

## 1. 中期経営計画の有無・期間

- 2025〜2027年度の中期経営計画

## 3. 重点施策

- 採用を年120名に拡大
"""

INDUSTRY = """# 業界概要（自動車） — テスト

## 1. 市場規模と成長率

- 市場は年5%成長

## 8. 業界構造を変えうる要因（技術革新・規制変更・特許切れ）

- EV 化
"""

OUTLOOK = """# 地合い判断

## 1. 総合判断

| 市場 | 地合い判断 | 前回 | 判断の要約 |
|---|---|---|---|
| 日本 | 中立 | 中立 | 金利上昇 |
| 米国 | 慎重 | 中立 | 景気減速 |

## 3. 市場動向

### 3.5 財政・政策・政治

| 市場 | 見たもの | 情報源 | 結論 |
|---|---|---|---|
| 日本 | DX 予算 | 骨太の方針 | 追い風 |
| 米国 | 関税 | 大統領令 | 逆風 |

## 4. 展望

| 期間 | 市場 | 判断 | 基本シナリオ | 上振れ要因 | 下振れ要因 | 確認する指標・イベント |
|---|---|---|---|---|---|---|
| 短期 | 日本 | 中立 | 短期シナリオ | b | c | d |
| 中期 | 日本 | 中立 | 中期シナリオ | b | c | d |
| 長期 | 米国 | 中立 | 米国長期 | f | g | h |

## 5. リスク要因

| リスク | 市場 | 影響 | 兆候を確認する指標 | 根拠（情報源） |
|---|---|---|---|---|
| 円高 | 日本 | 大 | ドル円 | 日銀 |
| 原油高 | 日米 | 中 | WTI | EIA |
"""


def _company(root: Path, mtp: str = MTP, collected: str = COLLECTED) -> Path:
    company = root / "companies" / COMPANY_DIR
    for sub, name, text in (
            ("filings", f"{collected}_2026-03_yuho.md", YUHO),
            ("ir", f"{collected}_financials-historical.md", FINANCIALS),
            ("ir", f"{collected}_mid-term-plan.md", mtp),
            ("market", f"{collected}_industry-overview.md", INDUSTRY)):
        (company / "raw" / sub).mkdir(parents=True, exist_ok=True)
        (company / "raw" / sub / name).write_text(text, encoding="utf-8")
    (company / "overview.md").write_text("# トヨタ（7203）\n", encoding="utf-8")
    return company


def _result(root: Path, kind: str, date: str, result: dict) -> None:
    directory = root / "companies" / COMPANY_DIR / "analysis" / kind
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_{kind}.md").write_text(f"# {kind}\n\n完成\n", encoding="utf-8")
    (directory / f"{date}_{kind}.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


def _upstream(root: Path, moat_day: str = MOAT_DAY, strong: bool = True, effective=("スイッチングコスト",)) -> None:
    _result(root, "five-forces", FF_DAY, {
        "attractiveness": "中", "industry": "自動車", "valid_until": "2099-01-01",
        "factors": [{"key": "entry", "name": "新規参入の脅威", "rating": "強" if strong else "中", "reason": "参入が続く"},
                    {"key": "substitutes", "name": "代替品の脅威", "rating": "中", "reason": "公共交通"}]})
    _result(root, "three-c", TC_DAY, {"verdict": "明確", "verdict_reason": "理由", "win_reason": "品質で優れる",
                                      "valid_until": "2099-01-01", "inputs": [],
                                      "handoff": {"strengths": "品質", "weaknesses": "顧客の集中"}})
    _result(root, "moat", moat_day, {
        "verdict": "狭い", "verdict_reason": "該当が1つ", "valid_until": "2099-01-01", "inputs": [],
        "effective_moats": list(effective),
        "moats": [{"type": "スイッチングコスト", "rating": "該当", "basis": "継続率 93%"}],
        "risks": [{"factor": "EV 化", "timing": "5〜10年"}], "durability": "10年程度",
        "handoff": {"strengths": "スイッチングコスト", "threats": "EV 化"}})


def _outlook(root: Path, week: str = OUTLOOK_WEEK) -> None:
    (root / "market" / "report").mkdir(parents=True, exist_ok=True)
    (root / "market" / "report" / f"{week}_outlook.md").write_text(OUTLOOK, encoding="utf-8")


def _templates(root: Path) -> None:
    shutil.copytree(REPO / ".ai" / "templates" / "swot", root / ".ai" / "templates" / "swot")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _templates(tmp_path)
    _outlook(tmp_path)
    _company(tmp_path)
    _upstream(tmp_path)
    return tmp_path


def run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = SW.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


S_ROW = "| S1 | 1-3 スイッチングコスト | 継続率が高い | 継続率 93%（2026/03） | brief 1. | 一次 | 大 | 売上の大半に関わる |"
W_ROW = "| W1 | リスク 顧客の集中 | 上位1社の比率が高い | 12.0% | brief 1. | 一次 | 中 | 売上の12% |"
O_ROW = "| O1 | 業界 市場成長 | 市場が伸びる | 年5% | brief 4. | 二次 | 中 | 売上 +5% |"
T_ROW = "| T1 | 1-1 新規参入の脅威 | 参入が続く | 上場2件 | brief 0. | 二次 | 大 | 単価下落で利益の20%超 |"
ANSWERS = {
    "top-strength": "S1", "top-strength-reason": "影響が最も大きい", "top-threat": "T1",
    "top-threat-reason": "利益の20%超に効く", "answer": "条件付き", "answer-reason": "採用が進めば耐えられる",
    "measure": "採用を年120名に拡大（brief 2. 重点施策）",
    "sentence": "S1 により、T1 に対して条件付きで耐えられる。理由：採用計画が進めば単価を守れる",
    "step2-checks": "営業利益率", "summary": "強みで脅威に条件付きで耐える", "triggers": "採用が計画を下回れば No",
    "changes": "- 初回の分析", "gaps": "- なし",
}


def fill(md: Path, s: str = S_ROW, w: str = W_ROW, o: str = O_ROW, t: str = T_ROW, **answers: str) -> None:
    values = dict(ANSWERS, **{k.replace("_", "-"): v for k, v in answers.items()},
                  **{"s-rows": s, "w-rows": w, "o-rows": o, "t-rows": t})
    md.write_text(FILL_ANY.sub(lambda m: values[m.group(1)], md.read_text(encoding="utf-8")), encoding="utf-8")


def prepared(root: Path, capsys, date: str = DAY) -> Path:
    code, out = run(root, "prepare", "--company", "7203", "--date", date, capsys=capsys)
    assert code == 0, out
    return root / out["md"]


def build(root: Path, capsys, date: str | None = None) -> tuple[int, dict]:
    return run(root, "build", "--company", "7203", *(("--date", date) if date else ()), capsys=capsys)


# ---------- metrics ----------

def test_scale_reads_newest_actual_and_skips_plans(repo):
    s = X.scale(P.Company(repo, repo / "companies" / COMPANY_DIR))
    assert s["year"] == "2026-03" and s["yen"]
    rows = X.scale_rows(s)
    assert "| 売上高 | 2026-03 | 16,600百万円 | 3,320百万円 | 830百万円 |" in rows
    assert "| 営業利益 | 2026-03 | 3,046百万円 | 609百万円 | 152百万円 |" in rows


def test_scale_without_figures():
    assert "無い" in X.scale_rows(None) and "不明" in X.scale_note(None)


# ---------- check ----------

def test_check_goes_to_prepare(repo, capsys):
    code, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 0 and out["next"] == "prepare" and out["result"] == "none"
    assert out["moat"]["result"] == "fresh"


def test_check_runs_moat_first(repo, capsys):
    shutil.rmtree(repo / "companies" / COMPANY_DIR / "analysis" / "moat")
    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "moat" and out["moat"]["result"] == "none"


@pytest.mark.parametrize("week", [None, "2026-08-31"])
def test_check_runs_market_report_when_outlook_missing_or_stale(tmp_path, capsys, week):
    _company(tmp_path)
    _upstream(tmp_path)
    if week:
        _outlook(tmp_path, week)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "market_report" and out["outlook_stale"]


def test_check_requests_collect_for_mid_term_plan(tmp_path, capsys):
    _outlook(tmp_path)
    _company(tmp_path, mtp="# 中期経営計画\n\n## 2. 目標値\n\n- 売上 2兆円\n")
    _upstream(tmp_path)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect"
    assert out["missing_inputs"] == [{"agent": "collect-ir", "items": ["中計: 中期経営計画の有無・期間"]}]


def test_check_without_raw_needs_full_collect(tmp_path, capsys):
    (tmp_path / "companies" / COMPANY_DIR).mkdir(parents=True)
    _, out = run(tmp_path, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "collect" and out["needs_full_collect"]


def test_list_shows_swot_and_moat_state(repo, capsys):
    _, out = run(repo, "list", capsys=capsys)
    row = out["companies"][0]
    assert (row["dir"], row["swot"], row["moat"]) == (COMPANY_DIR, "none", "fresh")


# ---------- prepare ----------

def test_prepare_writes_required_items_scale_and_brief(repo, capsys):
    md = prepared(repo, capsys)
    text = md.read_text(encoding="utf-8")
    assert "| 脅威（T） | 1-1 新規参入の脅威 | 強: 参入が続く |" in text
    assert "| 強み（S） | 1-3 スイッチングコスト | 該当: 継続率 93% |" in text
    assert "| 売上高 | 2026-03 | 16,600百万円 |" in text
    assert "中（「強」の要因: 新規参入の脅威）" in text and "明確: 品質で優れる" in text
    brief = (md.parent / f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "新規参入の脅威: 強（「強」→ 脅威に必ず記載）" in brief
    assert "採用を年120名に拡大" in brief and "DX 予算" in brief and "中期シナリオ" in brief
    assert "関税" not in brief and "短期シナリオ" not in brief  # 米国 rows and the short term are left out


def test_prepare_refuses_until_market_report_unless_skipped(tmp_path, capsys):
    _templates(tmp_path)
    _company(tmp_path)
    _upstream(tmp_path)
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "market_report"
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, "--skip-market-report", capsys=capsys)
    assert code == 0 and out["skipped_market_report"]
    brief = (tmp_path / out["brief"]).read_text(encoding="utf-8")
    assert "完成済みの outlook.md が無い" in brief


def test_prepare_refuses_until_moat_is_fresh(repo, capsys):
    shutil.rmtree(repo / "companies" / COMPANY_DIR / "analysis" / "moat")
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and out["next"] == "moat" and "moat" in out["error"]


# ---------- cycle ----------

def test_full_cycle_then_fresh_triggered_and_expired(repo, capsys):
    md = prepared(repo, capsys)
    fill(md)
    code, out = build(repo, capsys)
    assert code == 0, out
    assert out["verdict"] == "条件付き" and out["top_strength"]["id"] == "S1" and out["top_threat"]["id"] == "T1"
    assert out["counts"] == {"S": 1, "W": 1, "O": 1, "T": 1}
    result = json.loads((md.parent / f"{DAY}_swot.json").read_text(encoding="utf-8"))
    assert result["valid_until"] == "2027-04-10" and result["upstream"]["moat"]["verdict"] == "狭い"
    assert result["quadrants"]["T"][0]["origin"] == "1-1 新規参入の脅威"
    assert "**条件付き**" in md.read_text(encoding="utf-8")

    _, out = run(repo, "check", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["next"] == "report_existing"
    _, out = run(repo, "check", "--company", "7203", "--date", "2027-04-11", capsys=capsys)
    assert out["result"] == "expired"

    _upstream(repo, moat_day="2026-10-20")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-21", capsys=capsys)
    assert out["result"] == "triggered" and out["newer_raw"][-1].endswith("2026-10-20_moat.json")


def test_changed_risk_section_triggers(repo, capsys):
    fill(prepared(repo, capsys))
    build(repo, capsys)
    path = repo / "companies" / COMPANY_DIR / "raw" / "filings" / "2026-10-15_2027-03_yuho.md"
    path.write_text(YUHO.replace("EV への移行", "EV への移行と半導体不足"), encoding="utf-8")
    _, out = run(repo, "check", "--company", "7203", "--date", "2026-10-16", capsys=capsys)
    assert out["result"] == "triggered" and out["newer_raw"] == [path.relative_to(repo).as_posix()]


@pytest.mark.parametrize("kwargs, verdict", [
    ({}, "条件付き"),
    ({"answer": "Yes", "measure": "—", "sentence": "S1 により、T1 に対して耐えられる。理由：継続率が高い"}, "Yes"),
    ({"s": S_ROW.replace("| 大 |", "| 中 |"), "top_strength": "なし", "answer": "No", "measure": "—",
      "sentence": "なし により、T1 に対して耐えられない。理由：大きな強みが無い"}, "No"),
    ({"t": T_ROW.replace("| 大 |", "| 小 |"), "top_threat": "なし", "answer": "Yes", "measure": "—",
      "sentence": "S1 により、なし に対して耐えられる。理由：中以上の脅威が無い"}, "Yes"),
    ({"t": T_ROW.replace("| 大 |", "| 不明 |"), "top_threat": "なし"}, "判定保留"),
])
def test_verdict(repo, capsys, kwargs, verdict):
    fill(prepared(repo, capsys), **kwargs)
    code, out = build(repo, capsys)
    assert code == 0, out
    assert out["verdict"] == verdict


def test_threat_falls_back_to_medium(repo, capsys):
    fill(prepared(repo, capsys), t=T_ROW.replace("| 大 |", "| 中 |"))
    code, out = build(repo, capsys)
    assert code == 0 and out["top_threat"]["impact"] == "中"


def test_none_row_in_a_quadrant(repo, capsys):
    fill(prepared(repo, capsys), o="| なし | — | 業界概要と地合いを確認したが該当なし | — | — | — | — | — |")
    code, out = build(repo, capsys)
    assert code == 0 and out["counts"]["O"] == 0


# ---------- validation ----------

@pytest.mark.parametrize("kwargs, message", [
    ({"t": T_ROW.replace("1-1 新規参入の脅威", "業界 参入")}, "必ず記載する項目が無い"),
    ({"s": S_ROW.replace("1-3 スイッチングコスト", "事業 継続率")}, "1-3 スイッチングコスト"),
    ({"s": S_ROW.replace("| S1 |", "| A1 |"), "top_strength": "A1"}, "番号は S1"),
    ({"w": W_ROW.replace("リスク 顧客の集中", "顧客の集中")}, "由来は"),
    ({"w": W_ROW.replace("| 中 |", "| 高 |")}, "影響度は"),
    ({"w": W_ROW.replace("| 一次 |", "| 確実 |")}, "根拠の確度は"),
    ({"top_threat": "T9"}, "表に無い番号"),
    ({"s": S_ROW + "\n" + S_ROW.replace("S1", "S2").replace("| 大 |", "| 中 |"), "top_strength": "S2"},
     "S2 は影響度「大」ではない"),
    ({"s": S_ROW.replace("| 大 |", "| 中 |"), "top_strength": "なし"}, "「No」にする"),
    ({"top_strength": "なし"}, "「なし」にしない"),
    ({"measure": "—"}, "必要な対策"),
    ({"sentence": "S1 により、T1 に対して耐えられる。理由：x"}, "結論の文は"),
    ({"answer_reason": "おそらく耐えられる"}, "おそらく"),
])
def test_validation(repo, capsys, kwargs, message):
    fill(prepared(repo, capsys), **kwargs)
    code, out = build(repo, capsys)
    assert code == 1 and any(message in issue for issue in out["issues"]), out


def test_required_rows_follow_the_upstream_results(tmp_path, capsys):
    _templates(tmp_path)
    _outlook(tmp_path)
    _company(tmp_path)
    _upstream(tmp_path, strong=False, effective=())
    md = prepared(tmp_path, capsys)
    assert "必ず記載する項目なし" in md.read_text(encoding="utf-8")
    fill(md, s=S_ROW.replace("1-3 スイッチングコスト", "1-2 KBF 品質"), t=T_ROW.replace("1-1 新規参入の脅威", "業界 参入"))
    code, out = build(tmp_path, capsys)
    assert code == 0, out


def test_flags(repo, capsys):
    fill(prepared(repo, capsys), w=W_ROW.replace("売上の12%", "迷った: 中と小").replace("| 一次 |", "| 参考 |"))
    _, out = build(repo, capsys)
    assert out["tie_breaks"] == ["W1"] and out["low_confidence"] == ["W1"] and out["unknown"] == []


def test_second_analysis_requires_change_reason(repo, capsys):
    fill(prepared(repo, capsys))
    build(repo, capsys)
    later = "2027-05-01"
    _outlook(repo, "2027-04-26")
    md2 = prepared(repo, capsys, date=later)
    assert "強み S1・脅威 T1（2026-10-12）" in md2.read_text(encoding="utf-8")
    fill(md2, answer="No", measure="—", sentence="S1 により、T1 に対して耐えられない。理由：採用が遅れた",
         answer_reason="採用が遅れて耐えられない", changes="- 判定を見直した")
    _, out = build(repo, capsys, date=later)
    assert any("前回から変更" in issue for issue in out["issues"])
    md2.write_text(md2.read_text(encoding="utf-8").replace("採用が遅れて耐えられない", "前回から変更: 採用が遅れた"),
                   encoding="utf-8")
    code, out = build(repo, capsys, date=later)
    assert code == 0 and out["previous"]["verdict"] == "条件付き" and out["verdict"] == "No"


def test_prepare_keeps_draft_unless_redo_and_refuses_same_day_redo(repo, capsys):
    md = prepared(repo, capsys)
    md.write_text(md.read_text(encoding="utf-8").replace("<!-- FILL:s-rows", S_ROW + "\n<!-- FILL:s-rows"),
                  encoding="utf-8")
    _, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert out["kept"] and S_ROW in md.read_text(encoding="utf-8")
    md.write_text(md.read_text(encoding="utf-8").replace(S_ROW + "\n", ""), encoding="utf-8")
    fill(md)
    build(repo, capsys)
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, "--redo", capsys=capsys)
    assert code == 1 and "build 済み" in out["error"]
    code, out = run(repo, "prepare", "--company", "7203", "--date", DAY, capsys=capsys)
    assert code == 1 and "有効" in out["error"]


# ---------- write guard ----------

def test_write_guard_protects_swot_files(repo, capsys):
    md = prepared(repo, capsys)
    rel = md.relative_to(repo).as_posix()
    base = rel.rsplit("/", 1)[0]
    assert G.decide("Edit", f"{base}/{DAY}_brief.md", repo, DAY)
    assert G.decide("Edit", f"{base}/{DAY}_swot.json", repo, DAY)
    assert G.decide("Write", rel, repo, DAY)
    assert G.decide("Edit", rel, repo, DAY) is None
    fill(md)
    build(repo, capsys)
    tomorrow = (dt.date.fromisoformat(DAY) + dt.timedelta(days=1)).isoformat()
    assert "完成済み分析（swot）" in G.decide("Edit", rel, repo, tomorrow)


# ---------- review follow-ups ----------

def test_brief_keeps_rows_for_both_markets_and_filters_us(repo, capsys):
    brief = (prepared(repo, capsys).parent / f"{DAY}_brief.md").read_text(encoding="utf-8")
    assert "原油高" in brief
    us = P.Company(repo, repo / "companies" / "AAPL_apple")
    from sw_brief import market_label, outlook_section
    lines = "\n".join(outlook_section(repo, {"path": f"market/report/{OUTLOOK_WEEK}_outlook.md", "age_days": 7},
                                      market_label(us)))
    assert market_label(us) == "米国" and "関税" in lines and "原油高" in lines and "DX 予算" not in lines


def test_loss_has_no_profit_yardstick():
    s = {"year": "2026-03", "sales": 1e10, "profit": -3e8, "source": "x", "yen": True}
    rows = X.scale_rows(s)
    assert "| 営業利益 | 2026-03 | -300百万円（赤字） | — | — |" in rows and "赤字" in X.scale_note(s)


def test_unknown_threat_is_not_read_as_no_threat(repo, capsys):
    t = T_ROW.replace("| 大 |", "| 不明 |") + "\n" + T_ROW.replace("T1", "T2").replace("1-1 新規参入の脅威", "業界 x") \
        .replace("| 大 |", "| 小 |")
    fill(prepared(repo, capsys), t=t, top_threat="なし")
    code, out = build(repo, capsys)
    assert code == 0 and out["verdict"] == "判定保留"
    assert "書き手の暫定の見方" in (repo / out["md"]).read_text(encoding="utf-8")


@pytest.mark.parametrize("kwargs, message", [
    ({"t": T_ROW.replace("| 大 |", "| 小 |"), "top_threat": "なし"}, "「Yes」にする"),
    ({"t": T_ROW.replace("1-1 新規参入の脅威", "1-1 新規参入")}, "必ず記載する項目が無い"),
    ({"w": W_ROW + "\n" + W_ROW}, "番号が重複"),
    ({"o": "| なし | — | 確認 | — | — | — | — | — |\n" + O_ROW}, "1行だけ"),
    ({"t": T_ROW.replace("| 大 |", "| 中 |"), "top_threat": "なし"}, "「なし」にしない"),
])
def test_more_validation(repo, capsys, kwargs, message):
    fill(prepared(repo, capsys), **kwargs)
    code, out = build(repo, capsys)
    assert code == 1 and any(message in issue for issue in out["issues"]), out


def test_required_row_with_note_matches(repo, capsys):
    fill(prepared(repo, capsys), t=T_ROW.replace("1-1 新規参入の脅威", "1-1 新規参入の脅威（強）"))
    code, out = build(repo, capsys)
    assert code == 0, out


def test_skeleton_shows_previous_answer(repo, capsys):
    fill(prepared(repo, capsys))
    build(repo, capsys)
    _outlook(repo, "2027-04-26")
    text = prepared(repo, capsys, date="2027-05-01").read_text(encoding="utf-8")
    assert "条件付き（結論 条件付き。2026-10-12）" in text


def test_prepare_skip_collect_succeeds(tmp_path, capsys):
    _templates(tmp_path)
    _outlook(tmp_path)
    _company(tmp_path, mtp="# 中期経営計画\n\n## 2. 目標値\n\n- 売上 2兆円\n")
    _upstream(tmp_path)
    code, out = run(tmp_path, "prepare", "--company", "7203", "--date", DAY, "--skip-collect", capsys=capsys)
    assert code == 0 and out["skipped_collect"] == [{"agent": "collect-ir", "items": ["中計: 中期経営計画の有無・期間"]}]


def test_required_items_unit():
    ff = ("2026-10-01", {"factors": [{"name": "業界内の競争", "rating": "強", "reason": "r"}]})
    moat = ("2026-10-02", {"effective_moats": ["ブランド"], "moats": [{"type": "ブランド", "basis": "b"}]})
    items = D.required_items(ff, moat)
    assert [(i["quadrant"], i["tag"], i["name"]) for i in items] == [("T", "1-1", "業界内の競争"), ("S", "1-3", "ブランド")]
