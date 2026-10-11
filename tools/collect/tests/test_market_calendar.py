import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "market")]

import calendar_fixed as CF  # noqa: E402

FOMC_HTML = """
<h4><a>2026 FOMC Meetings</a></h4>
<div class="fomc-meeting__month col-xs-5"><strong>September</strong></div>
<div class="fomc-meeting__date col-xs-4">15-16*</div>
<div class="fomc-meeting__month col-xs-5"><strong>October</strong></div>
<div class="fomc-meeting__date col-xs-4">27-28</div>
<div class="fomc-meeting__month col-xs-5"><strong>April/May</strong></div>
<div class="fomc-meeting__date col-xs-4">30-1</div>
<div class="fomc-meeting__month col-xs-5"><strong>November</strong></div>
<div class="fomc-meeting__date col-xs-4">5 (unscheduled)</div>
<h4><a>2025 FOMC Meetings</a></h4>
<div class="fomc-meeting__month col-xs-5"><strong>December</strong></div>
<div class="fomc-meeting__date col-xs-4">9-10*</div>
"""

BOJ_HTML = """<table><caption>2026年 金融政策決定会合 開催日</caption>
<tr><td>9月17日（木）・18日（金）</td><td>9月18日（金）</td></tr>
<tr><td>10月29日（木）・30日（金）</td><td>10月30日（金）</td></tr>
<tr><td>4月30日（木）・5月1日（金）</td></tr></table>"""


def test_parse_fomc_rows_with_sep_and_two_month_meetings():
    rows = CF.parse_fomc(FOMC_HTML, "u")
    by_date = {r[0]: r for r in rows}
    assert set(by_date) == {"2026-09-16", "2026-10-28", "2026-05-01", "2025-12-10"}
    assert "SEP" in by_date["2026-09-16"][2] and "SEP" not in by_date["2026-10-28"][2]
    assert by_date["2026-05-01"][2].startswith("会合 04-30〜05-01")


def test_parse_boj_mpm_marks_outlook_meetings():
    rows = CF.parse_boj_mpm(BOJ_HTML, "u")
    assert [r[0] for r in rows] == ["2026-09-18", "2026-10-30", "2026-05-01"]
    assert "展望レポート" in rows[1][2] and "展望レポート" not in rows[0][2]


def test_parsers_accept_abbreviated_months_and_spaces():
    html = ('<h4>2027 FOMC Meetings</h4><div class="fomc-meeting__month"><strong>Jan/Feb</strong></div>'
            '<div class="fomc-meeting__date">31-1</div>')
    assert CF.parse_fomc(html, "u")[0][0] == "2027-02-01"
    boj = "2026年 金融政策決定会合 <td>12月17日（木）・ <br>18日（金）</td>"
    assert CF.parse_boj_mpm(boj, "u")[0][0] == "2026-12-18"


def test_fetch_fixed_reports_empty_parse_and_hides_api_key(monkeypatch):
    class Resp:
        content = b"<html>layout changed</html>"

    def get(url, params=None, **_):
        if "fred" in url:
            raise RuntimeError("404 for url: https://api.stlouisfed.org/fred/release/dates?api_key=SECRET&x=1")
        return Resp()

    monkeypatch.setenv("FRED_API_KEY", "SECRET")
    rows, errors = CF.fetch_fixed([{"type": "fomc", "url": "f"}, {"type": "fred_release", "release_id": 10,
                                                                 "name": "CPI"}], "2026-10-11", "2027-01-09", get)
    assert rows == [] and len(errors) == 2
    assert "SECRET" not in " ".join(errors) and "読み取れない" in errors[0]


def test_fetch_fixed_filters_window_and_reports_errors(monkeypatch):
    class Resp:
        def __init__(self, text: str = "", payload: dict | None = None):
            self.content, self._payload = text.encode("utf-8"), payload

        def json(self):
            return self._payload

    def get(url, params=None, **_):
        if "fred" in url:
            return Resp(payload={"release_dates": [{"date": "2026-10-14"}, {"date": "2027-03-01"}]})
        return Resp(FOMC_HTML)

    monkeypatch.setenv("FRED_API_KEY", "x")
    sources = [{"type": "fomc", "url": "f"}, {"type": "fred_release", "release_id": 10, "name": "CPI"},
               {"type": "nope"}]
    rows, errors = CF.fetch_fixed(sources, "2026-10-11", "2027-01-09", get)
    assert [(r[0], r[1]) for r in rows] == [("2026-10-14", "CPI"), ("2026-10-28", "FOMC")]
    assert len(errors) == 1 and "nope" in errors[0]
