import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import charts as C  # noqa: E402
import facts as F  # noqa: E402
import market_report as MR  # noqa: E402
import outlook as O  # noqa: E402
from state import Paths, check, outlook_state, parse_week, previous_outlook  # noqa: E402

SESSION = "2026-10-12_weekly"
FILL_ANY = re.compile(r"<!--\s*FILL:([\w-]+)[^>]*-->")

LATEST = f"""# 地合い情報の最新版 — {SESSION}

## 1. 最新セッションのファイル

| 種類 | ファイル |
|---|---|
| 指標（日本） | market/sessions/{SESSION}/raw/indicators-japan.md |
| 日程・市場指標（日本） | market/sessions/{SESSION}/raw/calendar-japan.md |
| 収集ステータス（日本） | market/sessions/{SESSION}/status.md |
| 指標（米国） | market/sessions/{SESSION}/raw/indicators-us.md |
| 日程・市場指標（米国） | market/sessions/{SESSION}/raw/calendar-us.md |
| 収集ステータス（米国） | market/sessions/{SESSION}/status.md |

## 2. 監視項目ごとの最新の文書

| 市場 | 層 | 監視項目 | 公表日 | 文書 | 要旨ファイル |
|---|---|---|---|---|---|
| 日本 | C | boj-statement | 2026-09-18 | 日銀 公表文 | market/policy/japan/raw/2026-10-11_boj-statement.md |
| 米国 | A | presidential-actions | 2026-10-08 | Executive Order <b>X</b> | market/policy/us/raw/missing.md |
| 日本 | A | honebuto | 2025-07-21 | 骨太の方針 | market/policy/japan/raw/2026-10-11_honebuto.md |
"""

CALENDAR_US = """# 政治・政策イベント — 米国

## 1. 確定日程（公式サイトからスクリプトが取得）

| 日付 | イベント | 内容 | 出典 | 確度 |
|---|---|---|---|---|
| 2026-10-14 | CPI（消費者物価指数） | 公表予定日 | https://fred.stlouisfed.org/ | 一次 |
| 2026-10-28 | FOMC | 会合 10-27〜10-28 | https://www.federalreserve.gov/ | 一次 |
| 2027-03-01 | 遠い予定 | 範囲外 | https://example.com | 一次 |

## 2. 今後の主要日程（web 検索）

| 日付 | イベント | 内容 | 出典 | 確度 |
|---|---|---|---|---|
| 2026-12 予定 | 歳出法案の審議 | レームダック会期 | https://example.com | 検索要約 |

## 3. 直近1か月の政治・政策の動き

| 日付 | 出来事 | 内容 | 出典 | 確度 |
|---|---|---|---|---|
| —（検索上限内で未確認） | 関税措置の発表 | 直近1か月の新規発表は確認できず | — | 検索要約 |
| 2026-09-02 | 暫定予算法の署名 | 12-11 まで | https://example.com | 検索要約 |

## 4. スクリプトで取得できない市場指標

| 指標 | 値 | 時点 | 出典 | 確度 |
|---|---|---|---|---|
| S&P500 予想PER（12か月先） | 19.0 | 2026-10-02 版 | https://example.com | 一次 |
| S&P500 予想EPS（来期） | —（PDF が読み取れず未確認） | — | — | 検索要約 |
| AAII センチメント | Bullish 32.7%（前週 30.1%） | 2026-09-23 週 | https://example.com | 検索要約 |

## 5. 未確認・保留事項

- なし
"""

INDICATORS_US = """# マクロ指標・市場需給 — 米国

## 1. 指標一覧

| 区分 | 指標 | 時点 | 値 | 前回（時点） | 1年前（時点） | 単位 | 出典 |
|---|---|---|---|---|---|---|---|
| 株価 | S&P500 | — | — | —（—） | —（—） | ポイント | x |

## 2. 取得できなかった系列

| 指標 | 理由 |
|---|---|
| S&P500 | FRED_API_KEY 未設定 |
"""

INDICATORS_NONE = """# マクロ指標・市場需給 — 日本

## 2. 取得できなかった系列

| 指標 | 理由 |
|---|---|
| なし | — |
"""

STATUS = """# 収集ステータス

## 7. 要確認事項

| ファイル | 内容 |
|---|---|
| market/sessions/x/raw/calendar-us.md | AAII の直近週は未確認 |
"""

DOC = """# 日銀 公表文

## 1. 要旨

政策金利を1.25%程度とした（p.1）。

## 2. 決定事項

| 項目 | 決定内容 | 前回からの変更 | 記載箇所 |
|---|---|---|---|
| 政策金利 | 1.25% | 変更あり | p.1 |

## 4. リスク要因として挙げられた事項

- 中東情勢（p.4）

## 5. 前回からの表現の変化

— （前回版なし）
"""

OLD_DOC = """# 骨太の方針

## 1. 要旨

責任ある積極財政を掲げた（p.6）。

## 2. 主要な施策・方針

| 分野 | 記述の要点 | 数値目標・予算・期限 | 記載箇所 |
|---|---|---|---|
| 財政 | 投資枠の創設 | — | p.30 |
"""


def _monthly(sid: str, base: float, step: float) -> list[str]:
    rows = []
    for m in range(1, 23):
        y, mo = 2025 + (m - 1) // 12, (m - 1) % 12 + 1
        rows.append(f"{sid},{y}-{mo:02d}-01,{base + m * step:.1f},2026-10-12")
    return rows


def _japan_rows() -> list[str]:
    rows = []
    start = dt.date(2025, 1, 1)
    for i in range(660):  # daily 2025-01-01 .. 2026-10-22
        d = (start + dt.timedelta(days=i)).isoformat()
        rows.append(f"JP_USDJPY,{d},{140 + i * 0.02:.4f},2026-10-12")
        rows.append(f"JP_JGB10Y,{d},{1.0 + i * 0.002:.4f},2026-10-12")
    return rows + _monthly("JP_CPI_YOY", 2.0, 0.0)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    shutil.copytree(REPO / "tools" / "collect" / "market" / "catalog", tmp_path / "tools/collect/market/catalog")
    shutil.copytree(REPO / ".ai" / "templates" / "market-report", tmp_path / ".ai/templates/market-report")
    market = tmp_path / "market"
    (market / "data").mkdir(parents=True)
    header = "series_id,date,value,retrieved\n"
    (market / "data" / "japan_series.csv").write_text(header + "\n".join(_japan_rows()) + "\n", encoding="utf-8")
    (market / "data" / "us_series.csv").write_text(header + "\n".join(_monthly("US_CPI_YOY", 300, 1)) + "\n",
                                                   encoding="utf-8")
    session = market / "sessions" / SESSION
    (session / "raw").mkdir(parents=True)
    (session / "raw" / "calendar-us.md").write_text(CALENDAR_US, encoding="utf-8")
    (session / "raw" / "calendar-japan.md").write_text("# 日本\n", encoding="utf-8")
    (session / "raw" / "indicators-us.md").write_text(INDICATORS_US, encoding="utf-8")
    (session / "raw" / "indicators-japan.md").write_text(INDICATORS_NONE, encoding="utf-8")
    (session / "status.md").write_text(STATUS, encoding="utf-8")
    (market / "policy" / "japan" / "raw").mkdir(parents=True)
    (market / "policy" / "japan" / "raw" / "2026-10-11_boj-statement.md").write_text(DOC, encoding="utf-8")
    (market / "policy" / "japan" / "raw" / "2026-10-11_honebuto.md").write_text(OLD_DOC, encoding="utf-8")
    (market / "LATEST.md").write_text(LATEST, encoding="utf-8")
    return tmp_path


def _fill(text: str, judgment: str = "中立") -> str:
    """Fill every FILL; the fixture's candidates are all 中立, so the judgement must be 中立 to build."""
    def value(m: re.Match) -> str:
        key = m.group(1)
        if key.startswith("judgment-") or key.endswith("-judgment"):
            return judgment
        if key.startswith("reason-"):
            return "—"
        if key.startswith("change-"):
            return "変更なし"
        if key == "key-messages":
            return "- 米10年債利回りが上昇（brief.md 1.）\n- ドル円は158円台\n- **FOMC** が 10-28"
        if key == "risks":
            return ("| 物価の再加速 | 米国 | 大 | CPI | brief.md 3. |\n| 金利上昇 | 日本 | 中 | 10年債 | brief.md 2. |\n"
                    "| 関税 | 日米 | 小 | 輸出 | brief.md 6. |")
        if key == "limits":
            return "- 判断に影響する欠損なし"
        return "記述 <script>alert(1)</script>"
    return FILL_ANY.sub(value, text)


def _run(repo: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = MR.main(list(argv), root=repo)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _facts(repo: Path) -> dict:
    return F.build_facts(Paths(repo), "2026-10-12", SESSION, "2026-10-12")


# ---------------------------------------------------------------- week & freshness

def test_week_is_the_monday():
    assert parse_week("2026-10-18") == "2026-10-12"
    assert parse_week("2026-10-12") == "2026-10-12"
    assert parse_week(None, today=dt.date(2026, 10, 14)) == "2026-10-12"


def test_check_freshness_and_running(repo):
    paths = Paths(repo)
    assert check(paths, "2026-10-12")["fresh"] is True
    stale = check(paths, "2026-10-19")
    assert stale["fresh"] is False and "より前" in stale["reason"]
    (repo / "market" / "sessions" / SESSION / ".running").write_text("{}", encoding="utf-8")
    assert check(paths, "2026-10-12")["running"] == [SESSION]


def test_check_without_latest(tmp_path):
    status = check(Paths(tmp_path), "2026-10-12")
    assert status["latest_session"] is None and status["fresh"] is False


# ---------------------------------------------------------------- facts

def test_kpi_changes_and_spark(repo):
    kpis = {k["id"]: k for k in _facts(repo)["kpis"]}
    usdjpy = kpis["JP_USDJPY"]
    assert usdjpy["date"] == "2026-10-22"
    assert usdjpy["changes"]["1w"]["delta"] == pytest.approx((153.18 / 153.04 - 1) * 100, rel=1e-6)
    assert usdjpy["changes"]["1y"]["base_date"] == "2025-10-22"
    assert kpis["JP_JGB10Y"]["changes"]["1m"]["delta"] == pytest.approx(0.06, abs=1e-6)  # difference for yields
    assert 50 <= len(usdjpy["spark"]) <= 54
    assert kpis["JP_NIKKEI225"]["value"] is None and kpis["JP_NIKKEI225"]["changes"] == {}


def test_charts_apply_transform_and_weekly_sampling(repo):
    charts = {c["id"]: c for c in _facts(repo)["charts"]}
    cpi = charts["us_prices"]["series"][0]["points"]
    assert cpi[0][0] == "2026-01-01"  # yoy needs a year of history
    assert cpi[0][1] == pytest.approx((313 / 301 - 1) * 100, rel=1e-4)
    usdjpy = charts["usdjpy"]["series"][0]["points"]
    assert len({dt.date.fromisoformat(d).isocalendar()[:2] for d, _ in usdjpy}) == len(usdjpy)


def test_calendar_window_docs_and_gaps(repo):
    facts = _facts(repo)
    assert [e["event"] for e in facts["events"]] == ["CPI（消費者物価指数）", "FOMC", "歳出法案の審議"]
    assert facts["politics"][0]["event"] == "暫定予算法の署名"
    assert facts["extras"][0]["value"] == "19.0"
    assert facts["series_failed"] == [{"market": "us", "name": "S&P500", "reason": "FRED_API_KEY 未設定"}]
    assert [r["content"] for r in facts["review_items"]] == ["AAII の直近週は未確認"]  # shared status read once
    assert [d["watch"] for d in facts["docs"]] == ["boj-statement", "presidential-actions", "honebuto"]


def test_unconfirmed_calendar_rows_leave_the_lists(repo):
    facts = _facts(repo)
    assert [p["event"] for p in facts["politics"]] == ["暫定予算法の署名"]
    assert [u["event"] for u in facts["unconfirmed"]] == ["関税措置の発表"]
    eps, aaii = facts["extras"][1], facts["extras"][2]
    assert (eps["value"], eps["note"]) == ("—", "PDF が読み取れず未確認")
    assert (aaii["value"], aaii["note"]) == ("Bullish 32.7%", "前週 30.1%")
    assert facts["extras"][0]["note"] == ""


def test_calendar_drivers_and_consensus_are_read_by_title():
    new = CALENDAR_US.replace("## 5. 未確認・保留事項", "## 5. 値動きの主な材料（報道）\n\n"
                              "| 日付 | 市場の動き | 報道された材料 | 出典 | 確度 |\n|---|---|---|---|---|\n"
                              "| 2026-10-23 | S&P500 が週間0.5%下落 | 金利先高観（報道） | https://example.com | 二次 |\n\n"
                              "## 6. 主要統計の市場予想と会合の織り込み\n\n"
                              "| イベント | 日付 | 市場予想 | 前回 | 出典 | 確度 |\n|---|---|---|---|---|---|\n"
                              "| CPI | 2026-11-10 | 前年比 3.6% | 3.7% | https://example.com | 二次 |\n\n"
                              "## 7. 未確認・保留事項")
    cal = F.parse_calendar(new, "us")
    assert cal["drivers"][0]["報道された材料"] == "金利先高観（報道）" and cal["drivers"][0]["market"] == "us"
    assert cal["consensus"][0]["市場予想"] == "前年比 3.6%"
    old = F.parse_calendar(CALENDAR_US, "us")  # a session collected before the sections existed
    assert old["drivers"] == [] and old["consensus"] == [] and len(old["events"]) == 4


def test_stale_indicators_are_flagged():
    catalogs = {"A": {"market": "us", "name": "月次", "frequency": "monthly"},
                "B": {"market": "us", "name": "月次（遅い）", "frequency": "monthly", "max_age_days": 60},
                "C": {"market": "us", "name": "日次", "frequency": "daily"}}
    series = {"A": [("2026-06-01", 1.0), ("2026-07-01", 2.0)], "B": [("2026-07-01", 1.0), ("2026-08-01", 2.0)],
              "C": [("2026-09-01", 1.0), ("2026-09-25", 2.0)], "D": [("2026-05-01", 1.0), ("2026-06-01", 2.0)]}
    catalogs["D"] = {"market": "us", "name": "月次（欠落）", "frequency": "monthly"}
    rows = {r["id"]: r for r in F.build_indicators(catalogs, series, "2026-10-12")["us"]}
    assert rows["A"]["stale"] is False            # 103 days: July data before the August release is normal
    assert rows["D"]["stale"] is True             # 133 days: a release is missing
    assert rows["B"]["stale"] is True             # catalog override
    assert rows["C"]["stale"] is True             # 17 days for a daily series


def test_streak_counts_the_last_run():
    assert F.streak([("a", 1), ("b", 2), ("c", 3), ("d", 2), ("e", 1)]) == -2
    assert F.streak([("a", 1), ("b", 2), ("c", 3)]) == 2
    assert F.streak([("a", 1), ("b", 1)]) == 0
    assert F.streak([("a", 1)]) == 0


def test_kpi_distance_from_high_and_streak(repo):
    kpis = {k["id"]: k for k in _facts(repo)["kpis"]}
    usdjpy = kpis["JP_USDJPY"]
    assert usdjpy["from_high"] == pytest.approx(0.0)        # rising series: the latest is the high
    assert usdjpy["streak"] == len(usdjpy["spark"]) - 1
    assert kpis["JP_NIKKEI225"]["from_high"] is None and kpis["JP_NIKKEI225"]["streak"] == 0


def test_brief_is_lean_and_lists_gaps(repo, capsys):
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "前回版なし" not in brief
    assert "責任ある積極財政を掲げた" in brief and "投資枠の創設" not in brief   # old doc: summary only
    assert "1年高値比" in brief and "連続" in brief
    assert "関税措置の発表" in brief.split("## 9.")[1]
    outlook = (repo / out["outlook"]).read_text(encoding="utf-8")
    assert "関税措置の発表" in outlook and "S&P500 予想EPS（来期）" in outlook


def test_event_span():
    assert F.event_span("2026-10-14") == ("2026-10-14", "2026-10-14", True)
    assert F.event_span("2026-12 予定") == ("2026-12-01", "2026-12-31", False)
    assert F.event_span("未定") is None


# ---------------------------------------------------------------- charts

def test_nice_ticks_cover_range():
    ticks = C.nice_ticks(0.47, 4.25)
    assert ticks[0] <= 0.47 and ticks[-1] >= 4.25 and len(ticks) <= 7


def test_line_chart_escapes_and_handles_empty():
    svg = C.line_chart([{"label": "<b>x</b>", "points": [["2026-01-01", 1.0], ["2026-02-01", 2.0]]}], "t")
    assert '<path class="ln s0"' in svg and "&lt;b&gt;x&lt;/b&gt;" in svg
    assert C.line_chart([{"label": "x", "points": []}], "t") == C.EMPTY


def test_bar_chart_signs():
    svg = C.bar_chart([["2026-01-01", 10], ["2026-01-08", -5]], "t")
    assert 'class="bar pos"' in svg and 'class="bar neg"' in svg


def test_fmt_uses_minus_sign():
    assert C.fmt(-1.234, 2, signed=True) == "−1.23"
    assert C.fmt(None) == "—"


# ---------------------------------------------------------------- prepare / build

def test_prepare_refuses_stale_material(repo, capsys):
    code, out = _run(repo, "prepare", "--week", "2026-10-19", capsys=capsys)
    assert code == 1 and "collect-market-info" in out["error"]
    code, out = _run(repo, "prepare", "--week", "2026-10-19", "--allow-stale", capsys=capsys)
    assert code == 0 and out["stale"] is True


def test_prepare_refuses_while_collecting(repo, capsys):
    (repo / "market" / "sessions" / SESSION / ".running").write_text("{}", encoding="utf-8")
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and "実行中" in out["error"]


def test_prepare_writes_skeleton_and_keeps_draft(repo, capsys):
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    assert code == 0 and out["fill"] > 50 and not out["outlook_kept"]
    outlook = repo / out["outlook"]
    text = outlook.read_text(encoding="utf-8")
    assert "| 2026-10-14 | 米国 | CPI（消費者物価指数） | <!-- FILL:event-1 --> |" in text
    assert "FRED_API_KEY 未設定" in text
    brief = (repo / out["brief"]).read_text(encoding="utf-8")
    assert "政策金利を1.25%程度とした" in brief and "（要旨ファイルが無い）" in brief
    outlook.write_text(text.replace("<!-- FILL:judgment-japan -->", "中立"), encoding="utf-8")
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    assert out["outlook_kept"] is True and "| 日本 | 中立 |" in outlook.read_text(encoding="utf-8")


def test_build_reports_issues_then_renders(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and any("FILL" in i for i in out["issues"])
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    outlook.write_text(_fill(outlook.read_text(encoding="utf-8")), encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 0, out
    assert out["judgments"] == {"japan": "中立", "us": "中立"} and out["overrides"] == []
    html = (repo / out["html"]).read_text(encoding="utf-8")
    assert '<span class="badge j-neutral">中立</span>' in html
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "Executive Order &lt;b&gt;X&lt;/b&gt;" in html
    assert "<strong>FOMC</strong>" in html
    assert html.count('<section class="slide') == 14 and 'id="s-scores"' in html
    judgment = json.loads((repo / out["judgment"]).read_text(encoding="utf-8"))
    assert judgment["viewpoints"]["japan"]["1"]["adopted"] == "中立"
    assert "${" not in html
    assert "関税措置の発表" not in html.split('id="s-fiscal"')[1].split("</section>")[0]
    assert "PDF が読み取れず未確認" in html
    assert outlook_state(outlook) == "done"


def test_build_warns_on_long_cells(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    text = _fill(outlook.read_text(encoding="utf-8"))
    long_text = "あ" * 200
    text = text.replace("記述 <script>alert(1)</script>", long_text, 1)  # first FILL = 日本の判断の要約
    outlook.write_text(text, encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 0
    assert any("判断の要約" in w and "200" in w for w in out["warnings"])


def test_calendar_slide_groups_dated_text_and_joins_points():
    import slides as SL
    facts = {"events": [{"date": "2026-10-14 まで", "market": "us", "event": "A|B", "detail": "d",
                         "kind": "検索", "certainty": "二次"}]}
    parsed = {"events": [{"date": "2026-10-14 まで", "market": "米国", "event": "A／B", "point": "注目"}]}
    html = SL.calendar(facts, parsed)
    assert "10/12 の週" in html and "日付未確定" not in html
    assert '<div class="pt">注目</div>' in html


def test_invalid_week_returns_json_error(repo, capsys):
    code, out = _run(repo, "check", "--week", "2026-13-01", capsys=capsys)
    assert code == 1 and "YYYY-MM-DD" in out["error"]


def test_build_warns_when_draft_predates_facts(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    outlook.write_text(_fill(outlook.read_text(encoding="utf-8")).replace(SESSION, "2026-10-05_weekly"),
                       encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 0 and out["warnings"]


def test_build_without_prepare(repo, capsys):
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and "prepare" in out["error"]


def test_previous_outlook_feeds_next_week(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    outlook.write_text(_fill(outlook.read_text(encoding="utf-8")), encoding="utf-8")
    assert previous_outlook(Paths(repo), "2026-10-19") == outlook
    code, out = _run(repo, "prepare", "--week", "2026-10-19", "--allow-stale", capsys=capsys)
    assert out["previous"]["japan"] == "中立"
    assert "前回（2026-10-12）" in (repo / "market" / "report" / "2026-10-19_outlook.md").read_text(encoding="utf-8")


def test_finished_outlook_needs_redo(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    outlook.write_text(_fill(outlook.read_text(encoding="utf-8")), encoding="utf-8")
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and "--redo" in out["error"]
    code, out = _run(repo, "prepare", "--week", "2026-10-12", "--redo", capsys=capsys)
    assert code == 0 and out["fill"] > 50


# ---------------------------------------------------------------- outlook validation

def _filled(repo: Path, capsys) -> tuple[str, str]:
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    text = _fill((repo / "market" / "report" / "2026-10-12_outlook.md").read_text(encoding="utf-8"))
    template = (repo / ".ai" / "templates" / "market-report" / "outlook.md").read_text(encoding="utf-8")
    return text, template


def test_validate_accepts_filled_outlook(repo, capsys):
    text, template = _filled(repo, capsys)
    assert O.validate(text, template) == []


def test_validate_rejects_bad_judgment_and_words(repo, capsys):
    text, template = _filled(repo, capsys)
    bad = text.replace("| 日本 | 中立 |", "| 日本 | やや強気 |", 1).replace("記述 <script>", "おそらく上昇 <script>", 1)
    bad = bad.replace("| 関税 | 日米 | 小 |", "| 関税 | 日米 | 極大 |")
    issues = O.validate(bad, template)
    assert any("総合判断（日本）" in i for i in issues)
    assert any("おそらく" in i for i in issues)
    assert any("大/中/小" in i for i in issues)


def test_validate_flags_price_targets_and_message_count(repo, capsys):
    text, template = _filled(repo, capsys)
    bad = (text.replace("記述 <script>", "日経平均は50,000円に到達する見込み <script>", 1)
           .replace("- **FOMC** が 10-28", ""))
    issues = O.validate(bad, template)
    assert any("水準の予想" in i for i in issues)
    assert any("キーメッセージ" in i for i in issues)


def _prepared_and_filled(repo: Path, capsys, week: str = "2026-10-12", *flags: str) -> Path:
    _run(repo, "prepare", "--week", week, *flags, capsys=capsys)
    outlook = repo / "market" / "report" / f"{week}_outlook.md"
    outlook.write_text(_fill(outlook.read_text(encoding="utf-8")), encoding="utf-8")
    return outlook


RATES_ROW_JP = "| 日本 | ② 金利・金融政策 | 中立（合計 +0） | 中立 | — |"


def test_build_requires_a_reason_and_a_consistent_judgment_for_overrides(repo, capsys):
    outlook = _prepared_and_filled(repo, capsys)
    text = outlook.read_text(encoding="utf-8")
    assert RATES_ROW_JP in text
    outlook.write_text(text.replace(RATES_ROW_JP, "| 日本 | ② 金利・金融政策 | 中立（合計 +0） | 逆風 | — |"),
                       encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and any("② 金利・金融政策" in i and "理由" in i for i in out["issues"])
    reason = "日銀公表文 2026-09-18 が引き続き利上げとする"
    text = text.replace(RATES_ROW_JP, f"| 日本 | ② 金利・金融政策 | 中立（合計 +0） | 逆風 | {reason} |")
    outlook.write_text(text, encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and any("「慎重」と同じにする" in i for i in out["issues"])
    text = text.replace("| 日本 | 中立 |", "| 日本 | 慎重 |", 1).replace("| 短期 | 日本 | 中立 |", "| 短期 | 日本 | 慎重 |")
    outlook.write_text(text, encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 0, out
    assert out["overrides"] == ["日本 ② 金利・金融政策: 中立 → 逆風"]


def test_build_checks_short_term_and_handoff(repo, capsys):
    outlook = _prepared_and_filled(repo, capsys)
    text = outlook.read_text(encoding="utf-8")
    outlook.write_text(text.replace("| 短期 | 米国 | 中立 |", "| 短期 | 米国 | 慎重 |"), encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and any("短期・米国" in i for i in out["issues"])
    outlook.write_text(text.replace("| 日米 | ドル円", "| 日米 | 円相場"), encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-12", capsys=capsys)
    assert code == 1 and any("10. 企業分析への引き継ぎ" in i for i in out["issues"])


def test_kept_draft_from_older_numbers_is_reported(repo, capsys):
    _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    outlook = repo / "market" / "report" / "2026-10-12_outlook.md"
    text = outlook.read_text(encoding="utf-8")
    outlook.write_text(text.replace("| 日米 | ドル円", "| 日米 | 円相場"), encoding="utf-8")  # as if the numbers moved
    code, out = _run(repo, "prepare", "--week", "2026-10-12", capsys=capsys)
    assert code == 0 and out["outlook_kept"] and any("--redo" in w for w in out["warnings"])


def test_stale_series_are_not_scored(repo):
    facts = _facts(repo)  # the fixture's JP_CPI_YOY ends 2026-10 (fresh); age it by moving the week far ahead
    later = F.build_facts(Paths(repo), "2027-06-07", SESSION, "2027-06-07")
    assert any(r["stale"] for r in later["indicators"]["japan"] if r["id"] == "JP_JGB10Y")
    sig = next(s for v in later["scores"]["japan"]["viewpoints"] for s in v["signals"]
               if s["name"] == "10年債利回りの1か月の変化")
    assert not sig["available"]
    assert facts["scores"]["japan"]["viewpoints"][1]["signals"][1]["available"]


def test_period_changes_need_a_reason_next_week(repo, capsys):
    _prepared_and_filled(repo, capsys)
    assert _run(repo, "build", "--week", "2026-10-12", capsys=capsys)[0] == 0
    outlook = _prepared_and_filled(repo, capsys, "2026-10-19", "--allow-stale")
    text = outlook.read_text(encoding="utf-8")
    assert "| 中期 | 日本 | 中立 | 変更なし |" in text
    assert (repo / "market" / "report" / "2026-10-19_brief.md").read_text(encoding="utf-8").count("前週 中立") >= 1
    outlook.write_text(text.replace("| 中期 | 日本 | 中立 |", "| 中期 | 日本 | 慎重 |", 1), encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-19", capsys=capsys)
    assert code == 1 and any("9. 中期・日本" in i for i in out["issues"])
    outlook.write_text(text, encoding="utf-8")
    code, out = _run(repo, "build", "--week", "2026-10-19", capsys=capsys)
    assert code == 0, out
    html = (repo / out["html"]).read_text(encoding="utf-8")
    assert html.count('<td class="rt r-neutral">中立</td>') >= 16  # two weeks × four viewpoints × two markets


def test_validate_rejects_changed_headings(repo, capsys):
    text, template = _filled(repo, capsys)
    issues = O.validate(text.replace("## 5. リスク要因", "## 5. リスク"), template)
    assert any("テンプレートと違う" in i for i in issues)
