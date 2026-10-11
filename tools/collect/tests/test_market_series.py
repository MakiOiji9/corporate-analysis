import io
import sys
from pathlib import Path

import pytest

sys.path[:0] = [str(Path(__file__).resolve().parents[1]), str(Path(__file__).resolve().parents[1] / "market")]

import series as S  # noqa: E402
import store  # noqa: E402


def test_parse_boj_daily_skips_nulls():
    payload = {"STATUS": 200, "RESULTSET": [{"FREQUENCY": "DAILY", "VALUES": {
        "SURVEY_DATES": [20260901, 20260902, 20260905], "VALUES": [159.77, None, 155.65]}}]}
    obs = S.parse_boj(payload, "JP_USDJPY")
    assert [(o.date, o.value) for o in obs] == [("2026-09-01", 159.77), ("2026-09-05", 155.65)]


def test_boj_quarterly_and_monthly_dates():
    assert S.boj_date(202603, "QUARTERLY") == "2026-07-01"
    assert S.boj_date(202609, "MONTHLY") == "2026-09-01"


def test_parse_boj_error_status_raises():
    with pytest.raises(S.ProviderError):
        S.parse_boj({"STATUS": 400, "MESSAGE": "bad code"}, "X")


def test_parse_dashboard_filters_cycle_and_seasonal():
    def value(time, cycle, seasonal, v):
        return {"VALUE": {"@time": time, "@cycle": cycle, "@isSeasonal": seasonal,
                          "@regionCode": "00000", "$": v}}
    payload = {"GET_STATS": {"RESULT": {"status": "0"}, "STATISTICAL_DATA": {"DATA_INF": {"DATA_OBJ": [
        value("20260700", "1", "2", "2.5"), value("20260800", "1", "2", "2.6"),
        value("20260800", "1", "1", "2.4"), value("20261Q00", "2", "2", "2.5"), value("2025CY00", "3", "1", "2.5"),
    ]}}}}
    obs = S.parse_dashboard(payload, "JP_UNEMP", cycle="1", seasonal="2")
    assert [(o.date, o.value) for o in obs] == [("2026-07-01", 2.5), ("2026-08-01", 2.6)]
    assert S.dashboard_date("20263Q00") == "2026-07-01"


def test_parse_mof_jgb_converts_wareki_and_skips_dash():
    text = "国債金利情報,,\n基準日,1年,10年\nR8.10.1,1.668,3.092\nR8.10.2,1.65,-\nH31.4.26,-0.1,-0.04\n"
    obs = S.parse_mof_jgb(text, "JP_JGB10Y", "10年")
    assert [(o.date, o.value) for o in obs] == [("2026-10-01", 3.092), ("2019-04-26", -0.04)]


def test_parse_mof_jgb_missing_tenor_raises():
    with pytest.raises(S.ProviderError):
        S.parse_mof_jgb("基準日,1年\nR8.10.1,1.6\n", "X", "10年")


def test_parse_fred_skips_missing_dot():
    obs = S.parse_fred({"observations": [{"date": "2026-09-01", "value": "4.1"},
                                         {"date": "2026-09-02", "value": "."}]}, "US_10Y")
    assert [(o.date, o.value) for o in obs] == [("2026-09-01", 4.1)]
    with pytest.raises(S.ProviderError):
        S.parse_fred({"error_message": "Bad Request. The value for variable api_key is not registered."}, "X")


def test_parse_cftc_net_is_long_minus_short_sorted():
    rows = [{"report_date_as_yyyy_mm_dd": "2026-10-06T00:00:00.000",
             "noncomm_positions_long_all": "212009", "noncomm_positions_short_all": "366079"},
            {"report_date_as_yyyy_mm_dd": "2026-09-29T00:00:00.000",
             "noncomm_positions_long_all": "200000", "noncomm_positions_short_all": "100000"}]
    obs = S.parse_cftc(rows, "US_COT")
    assert [(o.date, o.value) for o in obs] == [("2026-09-29", 100000.0), ("2026-10-06", -154070.0)]


def test_jpx_weekly_links_newest_first():
    html = ('<a href="/x/stock_1_w_20260914_20260918.xlsx">a</a>'
            '<a href="/y/stock_1_w_20260928_20261002.xlsx">b</a>'
            '<a href="/z/stock_val_1_260902.xls">monthly</a>')
    links = S.jpx_weekly_links(html, 5)
    assert links == [("https://www.jpx.co.jp/y/stock_1_w_20260928_20261002.xlsx", "2026-10-02"),
                     ("https://www.jpx.co.jp/x/stock_1_w_20260914_20260918.xlsx", "2026-09-18")]


def _jpx_workbook() -> bytes:
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["投資部門別 株式売買状況"])
    ws.append([None, None, None, "自己計 Proprietary", None, None, None, "委託計 Brokerage"])
    ws.append([None, None, None, None, None, None, None, "海外投資家 Foreigners", None, None, None, "個人 Individuals"])
    ws.append(["年月週", "市場", "単位", "売", "買", "差引 Balance", "合計", "売", "買", "差引 Balance", "合計",
               "売", "買", "差引 Balance", "合計"])
    ws.append(["2026095", "二市場\nTokyo & Nagoya", "株数", 1, 1, 0, 2, 1, 1, 0, 2, 1, 1, 0, 2])
    ws.append([None, "金額 Value", None, 10, 20, 1_000_000, 30, 10, 20, -100_400_000, 30, 10, 20, 52_000_000, 30])
    ws.merge_cells(start_row=2, start_column=4, end_row=2, end_column=7)
    ws.merge_cells(start_row=3, start_column=8, end_row=3, end_column=11)
    ws.merge_cells(start_row=3, start_column=12, end_row=3, end_column=15)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_jpx_flows_reads_net_value_in_oku_yen():
    obs = S.parse_jpx_flows(_jpx_workbook(), "2026-10-02", {"海外投資家": "F", "個人": "I"})
    assert sorted((o.series_id, o.date, o.value) for o in obs) == [
        ("F", "2026-10-02", -1004.0), ("I", "2026-10-02", 520.0)]


def test_upsert_series_is_idempotent_and_summarize(tmp_path):
    csv_path = tmp_path / "japan_series.csv"
    monthly = [S.Obs("CPI", f"{y}-{m:02d}-01", 100 + (y - 2025) * 12 + m) for y in (2025, 2026) for m in range(1, 13)]
    store.upsert_series(csv_path, monthly)
    store.upsert_series(csv_path, monthly[-2:])
    points = store.load_points(csv_path)
    assert len(points["CPI"]) == 24
    level = store.summarize(points["CPI"], "level", "monthly")
    assert (level.latest_date, level.latest, level.prev, level.year_date) == ("2026-12-01", 124.0, 123.0, "2025-12-01")
    yoy = store.summarize(points["CPI"], "yoy_pct", "monthly")
    assert yoy.latest == pytest.approx((124 / 112 - 1) * 100)
    assert yoy.year is None  # no data two years back
    diff = store.summarize(points["CPI"], "diff", "monthly")
    assert diff.latest == 1.0


def test_summarize_daily_compares_with_one_month_earlier():
    points = [("2026-08-31", 1.0), ("2026-09-10", 2.0), ("2026-10-09", 3.0)]
    s = store.summarize(points, "level", "daily")
    assert (s.latest_date, s.prev_date, s.prev) == ("2026-10-09", "2026-08-31", 1.0)
    assert s.year_date == "—"
