import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT), str(REPORT.parent / "analysis"), str(REPORT.parent / "collect" / "market"),
                str(REPORT.parent / "collect")]

import cr_extras as X  # noqa: E402
import cr_plain as P  # noqa: E402
import cr_sections as CS  # noqa: E402


def test_step_number_becomes_what_the_step_checks():
    assert P.plain("手順1が良好、営業利益率が同業平均以上", "profitability") == "「ROE の水準と安定性」が良好、営業利益率が同業平均以上"
    assert "「利益の質」（営業CF対純利益比率 0.77倍（5年平均））が懸念" == P.plain(
        "手順3（営業CF対純利益比率 0.77倍（5年平均））が懸念", "cash_flow")


def test_step_with_a_short_name_keeps_only_the_name():
    assert P.plain("PBR 2.02倍: 手順2（適正PBR）で判定", "valuation") == "PBR 2.02倍: 適正PBRで判定"


def test_step_named_by_its_analysis():
    assert P.plain("営業CF がマイナス（キャッシュフロー手順1が懸念）") == "営業CF がマイナス（キャッシュフローの「営業CF の安定性」が懸念）"


def test_unknown_analysis_still_hides_the_step_number():
    assert "手順" not in P.plain("手順4で確認した")


def test_file_paths_become_document_names():
    assert P.plain("地合い market/report/2026-10-26_outlook.md（短期の行）") == "地合い 地合いレポート（2026-10-26 の週）（短期の見通し）"
    assert P.plain("比べられない（2026-11-01_competitors.md「8. 顧客・人員の KPI」、2026-10-11_2026-03_yuho.md「6.」）") \
        == "比べられない（競合の資料、有価証券報告書）"
    assert P.plain("出典: data/tdnet_facts.csv（決算短信）") == "出典: 決算短信"
    assert P.plain("材料なし（raw/market/*_positioning.md が無い）") == "材料なし（信用残・空売りの資料が無い）"


def test_collection_agents_and_status_file_disappear():
    assert P.plain("顧客調査（collect-peers-valuation）") == "顧客調査"
    assert P.plain("比率も不明（collect-ir: 決算説明資料の製品別売上）") == "比率も不明（決算説明資料の製品別売上）"
    assert P.plain("取れていない（status.md）（必須）") == "取れていない（必須）"
    assert P.plain("評価軸による（status.md の未取得項目）") == "評価軸による（未取得の項目）"


def test_writer_notes_read_plainly():
    assert P.plain("数値は brief に無い。迷った: 中とした") == "数値は収集した資料に無い。判断が分かれた点: 中とした"
    assert P.plain("比べる材料が無いため ？ を △ とみなし") == "比べる材料が無いため同程度とみなし"


def test_plain_tree_returns_a_new_object():
    original = {"reason": "手順1が良好", "rows": ["brief に無い", 3], "n": None}
    out = P.plain_tree(original, "profitability")
    assert out == {"reason": "「ROE の水準と安定性」が良好", "rows": ["収集した資料に無い", 3], "n": None}
    assert original["reason"] == "手順1が良好"


def test_leaks_reads_only_visible_text():
    clean = '<a href="../analysis/moat/2026-11-10_moat.md">分析の本文</a><p>良好</p>'
    assert P.leaks(clean) == []
    dirty = "<p>手順2で判定（raw/ir/x.md）</p>"
    assert [x.split(":")[0] for x in P.leaks(dirty)] == ["手順N", "パス"]
    assert [x.split(":")[0] for x in P.leaks("<p>（2026-11-01_competitors.md）</p>")] == ["ファイル名"]


def test_leaks_catches_the_source_investors_name():
    assert P.leaks("<p>清原流の見方</p>")


def test_leaks_ignores_ordinary_business_text():
    text = ("<p>製造手順の見直し。metadata/ の整理、draw/ 機能。briefing を実施。"
            "出典 https://example.com/ir/report.md と https://x.jp/a.csv</p>")
    assert P.leaks(text) == []


def test_leaks_reads_tooltips_and_lists_every_hit():
    page = '<span data-tip="手順1の説明">x</span><p>手順2 と 手順3</p>'
    assert len(P.leaks(page)) == 3


def test_step_name_starting_with_a_digit_survives():
    assert P.plain("手順2が中", "five_forces") == "「5つの要因の評価」が中"
    assert P.plain("「3年連続増益」の記載") == "「3年連続増益」の記載"


def test_plain_is_idempotent():
    for key, text in (("cash_flow", "手順3（営業CF）が懸念（data/tdnet_facts.csv）"),
                      (None, "地合い market/report/2026-10-26_outlook.md（短期の行）")):
        once = P.plain(text, key)
        assert P.plain(once, key) == once


def test_brief_only_as_a_word():
    assert P.plain("briefing は brief に無い") == "briefing は収集した資料に無い"


def test_plain_tree_keeps_name_fields():
    out = P.plain_tree({"name": "A社（brief）", "sentence": "brief に無い"})
    assert out == {"name": "A社（brief）", "sentence": "収集した資料に無い"}


def test_dividend_falls_back_to_the_annual_report_summary(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "financials.csv").write_text(
        "doc_id,period_end,item,value,unit,element,context\n"
        "A,2025-02-28,summary.dps,60,円,e,c\nA,2025-02-28,summary.payout_ratio,50.0,%,e,c\n"
        "B,2026-02-28,summary.dps,70,円,e,c\nB,2026-02-28,summary.payout_ratio,55.0,%,e,c\n", encoding="utf-8")
    d = X.dividends(tmp_path, 3500.0, 20.0)
    assert (d["actual"], d["actual_fy"], d["payout_actual"]) == (70.0, "2026-02", 55.0)
    assert d["forecast"] is None and d["yield_basis"] == "実績" and d["yield"] == 2.0
    assert d["source"] == "有価証券報告書の主要な経営指標"


def test_dividend_without_any_material(tmp_path):
    assert X.dividends(tmp_path, 1000.0, 10.0)["source"] is None


def test_competitor_names_drop_the_collectors_notes():
    assert CS.short_name("ファナック（3月期。2022年3月期以降は IFRS を EDINET で確認）") == "ファナック"
    assert CS.short_name("三菱電機（全社）") == "三菱電機（全社）"


def test_equal_by_missing_material_says_so():
    detail = {"competitor": "同等", "kbf_table": [{"kbf": "品質", "self": "？", "peers": {}}]}
    assert "同程度とみなした" in CS._competitor_conclusion(detail)
    assert CS._competitor_conclusion({**detail, "kbf_table": [{"self": "○"}]}) == "同等"


def test_card_says_when_a_knockout_overrode_the_score():
    import cr_render as R
    h = {"score": 0.04, "verdict": "見送り", "knockout": ["STEP 1 が C（勝てる理由がなし、または SWOT が No）"]}
    line = R._knockout_line(h)
    assert "点数だけならウォッチだが" in line and "のため見送り" in line
    assert R._knockout_line({**h, "knockout": []}) == ""
    assert R._knockout_line({**h, "score": -0.5}) == ""  # the score alone already says 見送り


# ---------------------------------------------------------------- material freshness (cr_materials)

def test_materials_route_market_before_company_collection(tmp_path):
    import cr_materials as MT
    company = tmp_path / "c"
    (company / "raw" / "news").mkdir(parents=True)
    (company / "raw" / "news" / "2026-11-01_press-releases.md").write_text(
        "| 日付 | 見出し |\n|---|---|\n| 2026-10-30 | a |\n| 2026-07-01 | b |\n", encoding="utf-8")
    rows = MT.evaluate(company, {"week": "2026-10-26"}, "2026-11-11")
    by = {m["key"]: m for m in rows}
    assert by["news"]["stale"] and by["news"]["why"] == "10日前（上限 7日）"
    assert by["consensus"]["why"] == "無い" and by["prices"]["date"] is None
    assert by["market"]["stale"]
    assert MT.next_for(rows) == "market-report"
    fresh_market = [m if m["key"] != "market" else {**m, "stale": False} for m in rows]
    assert MT.next_for(fresh_market) == "collect-company-info"
    assert MT.collect_request(rows) == {"mode": "update", "agents": ["collect-ir", "collect-peers-valuation"],
                                        "items": [by["news"]["item"], by["consensus"]["item"],
                                                  by["management"]["item"]]}
    assert not by["governance"]["stale"]  # "c" is not a Japanese ticker: no annual report to collect


def test_stale_prices_alone_do_not_need_collection():
    import cr_materials as MT
    rows = [{"key": "prices", "stale": True, "by": MT.PREPARE}]
    assert MT.next_for(rows) is None and MT.collect_request(rows) is None


def test_governance_block_shows_the_owner_and_the_targets():
    facts = {"governance": {"as_of": "2026-03-31", "filed": "2026-06-17",
                            "owner": {"ratio": 50.6, "is_owner": True,
                                      "members": [{"name": "漆原　茂", "ratio": 45.4, "why": "役員本人"}]},
                            "president": {"name": "横山　芳成", "title": "代表取締役社長", "age": 52},
                            "issuances": [{"period_end": "2026-03-31", "kind": "株式分割", "change_pct": 925.1}],
                            "offering_within_5y": False},
             "management": {"file": "2026-11-01", "rows": [{"year": "2026-03", "kind": "期初予想", "item": "営業利益",
                                                           "target": "3,000", "actual": "3,046", "rate": 101.5,
                                                           "source": "s"}],
                            "messages": [], "average": {"期初予想": 101.5}}}
    html = CS.governance_block(facts)
    assert "オーナー企業（創業者・親族の保有が 20% 以上）" in html and "横山" in html and "52歳" in html
    assert "株式分割" in html and "101.5%" in html
    assert "集めていない" in CS.governance_block({})
