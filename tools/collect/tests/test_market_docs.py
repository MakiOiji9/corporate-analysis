import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "market")]

import excerpt as X  # noqa: E402
import render as R  # noqa: E402
import watch as W  # noqa: E402
from validate import validate_text  # noqa: E402


class _Resp:
    def __init__(self, text: str):
        self.content = text.encode("utf-8")


def _get(pages: dict):
    return lambda url, **_: _Resp(pages[url])


# ---------------------------------------------------------------- watch

def test_find_date_from_label_url_and_rfc822():
    assert W.find_date("所信表明演説 令和8年10月5日") == "2026-10-05"
    assert W.find_date("", "https://x/2026/0929getsurei/main.pdf") == "2026-09-29"
    assert W.find_date("https://x/fy2026/20251226taikou.pdf") == "2025-12-26"
    assert W.find_date("Wed, 7 Oct 2026 18:00:00 GMT") == "2026-10-07"
    assert W.find_date("no date") == ""


def test_date_pattern_two_digit_year():
    assert W.date_from_pattern(r"gor(?P<y>\d{2})(?P<m>\d{2})a", "/outlook/gor2607a.pdf") == "2026-07-01"


def test_list_candidates_html_filters_and_titles():
    html = ('<a href="/jp/105/statement/2026/1005shoshinhyomei.html">所信表明演説 令和8年10月5日</a>'
            '<a href="/jp/105/statement/2026/0926kaiken.html">会見 令和8年9月26日</a>')
    entry = {"key": "pm-speech", "layer": "A", "type": "html_links", "title": "演説",
             "url": "https://k/jp/{n}/statement/index.html",
             "link_pattern": r"/statement/\d{4}/\d{4}shoshinhyomei", "title_pattern": "所信表明"}
    cands = W.list_candidates(entry, _get({"https://k/jp/105/statement/index.html": html}), {"n": "105"})
    assert [(c.url, c.published) for c in cands] == [
        ("https://k/jp/105/statement/2026/1005shoshinhyomei.html", "2026-10-05")]


def test_list_candidates_sorts_oldest_first_pages():
    html = "".join(f'<a href="/beigebook2026{m:02d}-summary.htm">HTML</a>' for m in (1, 4, 7))
    entry = {"key": "bb", "type": "html_links", "title": "Beige", "url": "https://f/bb.htm",
             "link_pattern": r"beigebook\d{6}-summary", "date_pattern": r"beigebook(?P<y>\d{4})(?P<m>\d{2})",
             "use_entry_title": True}
    cands = W.list_candidates(entry, _get({"https://f/bb.htm": html}), {})
    assert [c.published for c in cands] == ["2026-07-01", "2026-04-01", "2026-01-01"]
    assert cands[0].title == "Beige（2026-07-01）"


def test_parse_rss_with_bom_and_cdata():
    xml = ("﻿<?xml version='1.0'?><rss><channel><item><title>FOMC statement</title>"
           "<link><![CDATA[https://fed/a.htm]]></link><pubDate><![CDATA[Wed, 16 Sep 2026 18:00:00 GMT]]></pubDate>"
           "</item></channel></rss>")
    assert W.parse_rss(xml) == [("https://fed/a.htm", "FOMC statement", "2026-09-16")]


def test_pick_new_stops_at_first_known_url():
    cands = [W.Candidate("k", "A", "summarize", t, u, "") for t, u in
             (("2027", "u2027"), ("2026", "u2026"), ("2025", "u2025"))]
    assert [c.url for c in W.pick_new(cands, {"u2026"})] == ["u2027"]
    assert [c.url for c in W.pick_new(cands, set())] == ["u2027", "u2026", "u2025"]


def test_follow_returns_none_without_matching_document():
    page = '<a href="/fy2027/gaisan.pdf">概算要求</a>'
    cand = W.Candidate("budget", "B", "summarize", "令和9年度予算", "https://m/fy2027/index.html", "")
    assert W.follow(cand, {"link_pattern": r"\.pdf$", "title_pattern": "ポイント"},
                    _get({"https://m/fy2027/index.html": page})) is None
    page2 = '<a href="/fy2026/point.pdf">予算のポイント</a>'
    cand2 = W.Candidate("budget", "B", "summarize", "令和8年度予算", "https://m/fy2026/index.html", "")
    hit = W.follow(cand2, {"link_pattern": r"\.pdf$", "title_pattern": "ポイント"},
                   _get({"https://m/fy2026/index.html": page2}))
    assert hit.url == "https://m/fy2026/point.pdf" and hit.page_url == "https://m/fy2026/index.html"


def test_follow_chain_goes_two_pages_deep():
    pages = {"https://m/fy2026/index.html": '<a href="/fy2026/seifuan2026/index.html">令和８年度予算政府案</a>',
             "https://m/fy2026/seifuan2026/index.html": '<a href="/fy2026/seifuan2026/01.pdf">予算のポイント</a>'}
    cand = W.Candidate("budget", "B", "summarize", "令和8年度予算", "https://m/fy2026/index.html", "")
    rules = [{"link_pattern": r"seifuan\d{4}/index\.html$", "title_pattern": "政府案"},
             {"link_pattern": r"\.pdf$", "title_pattern": "ポイント"}]
    hit = W.follow(cand, rules, _get(pages))
    assert hit.url == "https://m/fy2026/seifuan2026/01.pdf" and hit.page_url == "https://m/fy2026/index.html"


def test_resolve_vars_reports_errors_per_var():
    pages = {"https://k/": '<a href="/jp/105/statement/x">', "https://b/": "nothing"}
    values, errors = W.resolve_vars({"cab": {"url": "https://k/", "pattern": r"/jp/(\d+)/statement/"},
                                     "boj": {"url": "https://b/", "pattern": r"(state_\d{4})"}}, _get(pages))
    assert values == {"cab": "105"} and len(errors) == 1 and errors[0].startswith("boj")


# ---------------------------------------------------------------- excerpt

def test_excerpt_keeps_head_and_keyword_pages_within_limit():
    pages = {1: "表紙", 2: "目次", 3: "雑記" * 50, 4: "投資 投資 半導体", 5: "賃上げ"}
    text = X.build_excerpt(pages, ["投資", "賃上げ"], max_chars=1000)
    assert "=====PAGE 1=====" in text and "=====PAGE 4=====" in text and "=====PAGE 5=====" in text
    assert "=====PAGE 3=====" not in text


def test_excerpt_single_page_trims_to_keyword_paragraphs():
    body = "\n".join(["冒頭"] * 5 + ["関係ない段落" * 20] * 30 + ["投資を強化する"])
    text = X.build_excerpt({1: body}, ["投資"], max_chars=300)
    assert "投資を強化する" in text and len(text) < 600


# ---------------------------------------------------------------- render + validate

def _filled_policy_doc() -> str:
    skeleton = R.render_doc_skeleton("raw/policy-doc.md", title="骨太の方針2026", collected="2026-10-11",
                                     url="https://x", source_path="s.pdf", layer="A", published="2026-07-21",
                                     excerpt_path="s.excerpt.txt", previous="なし")
    replacements = {
        "summary": "成長投資を進める方針を示した。",
        "measures": "| 成長投資 | 官民で投資を拡大 | — （記載なし） | p.3 |",
        "sectors": "| 半導体 | 国内生産拠点の整備 | p.5 |",
        "changes": "— （前回版なし）",
        "pending": "なし",
    }
    lines = []
    for line in skeleton.splitlines():
        key = next((k for k in replacements if line.startswith(f"<!-- FILL:{k}")), None)
        lines.append(replacements[key] if key else line)
    return "\n".join(lines) + "\n"


def test_validate_skeleton_reports_fill_and_filled_doc_passes():
    template = R.template_path("raw/policy-doc.md").read_text(encoding="utf-8")
    skeleton = R.render_doc_skeleton("raw/policy-doc.md", title="T", collected="2026-10-11", url="u",
                                     source_path="s", layer="A", published="—", excerpt_path="e", previous="なし")
    assert any("FILL" in i for i in validate_text(skeleton, template))
    assert validate_text(_filled_policy_doc(), template) == []


def test_validate_detects_changed_heading_empty_cell_and_words():
    template = R.template_path("raw/policy-doc.md").read_text(encoding="utf-8")
    doc = _filled_policy_doc()
    assert validate_text(doc.replace("## 3. 文書に登場する産業・技術分野", "## 3. 関連銘柄"), template)
    assert any("空欄" in i for i in validate_text(doc.replace("| p.5 |", "|  |"), template))
    assert any("評価" in i for i in validate_text(doc.replace("成長投資を進める", "割安な株を買うべき"), template))


def test_render_indicators_table_passes_validation(tmp_path):
    from store import Summary

    entries = [{"id": "A", "name": "失業率", "group": "雇用", "unit": "%", "decimals": 1, "source": "総務省",
                "source_url": "https://d/"},
               {"id": "B", "name": "CPI", "group": "物価", "unit": "%", "source": "総務省"}]
    text = R.render_indicators("japan", entries, {"A": Summary("2026-08-01", 2.6, "2026-07-01", 2.5, "2025-08-01", 2.4),
                                                  "B": None}, {"B": "データなし"}, "2026-10-11",
                               tmp_path / "japan_series.csv")
    template = R.template_path("raw/series-table.md").read_text(encoding="utf-8")
    assert validate_text(text, template) == []
    assert "| 雇用 | 失業率 | 2026-08-01 | 2.6 | 2.5（2026-07-01） | 2.4（2025-08-01） | % | 総務省 |" in text
