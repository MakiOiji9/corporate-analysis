import json
import sys
from pathlib import Path

import pytest

COLLECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(COLLECT), str(COLLECT / "market")]

import stock_prices as SP  # noqa: E402
from series import ProviderError  # noqa: E402

JST = 32400
DAY = 86400
T0 = 1761523200  # 2025-10-27 00:00 UTC; bars are stamped at 00:00 UTC (09:00 JST)


def _payload(closes: list, splits: dict | None = None) -> dict:
    n = len(closes)
    return {"chart": {"error": None, "result": [{
        "meta": {"currency": "JPY", "exchangeName": "JPX", "gmtoffset": JST},
        "timestamp": [T0 + i * DAY for i in range(n)],
        "events": {"splits": splits or {}},
        "indicators": {"quote": [{"open": closes, "high": [c and c + 1 for c in closes],
                                  "low": [c and c - 1 for c in closes], "close": closes,
                                  "volume": [1000] * n}],
                       "adjclose": [{"adjclose": closes}]}}]}}


class _Resp:
    def __init__(self, payload: dict):
        self.payload = payload

    def json(self) -> dict:
        return self.payload


@pytest.mark.parametrize("ticker, symbol", [("3798", "3798.T"), ("130a", "130A.T"), ("CBRS", "CBRS"),
                                            ("aapl", "AAPL")])
def test_symbol_for(ticker, symbol):
    assert SP.symbol_for(ticker) == symbol


def test_parse_chart_drops_missing_closes_and_reads_splits():
    rows, info = SP.parse_chart(_payload([100.5, None, 102], {"x": {"date": T0, "splitRatio": "10:1"}}), "2025-11-01")
    assert [r["date"] for r in rows] == ["2025-10-27", "2025-10-29"]
    assert rows[0] == {"date": "2025-10-27", "open": "100.5", "high": "101.5", "low": "99.5", "close": "100.5",
                       "adj_close": "100.5", "volume": "1000", "retrieved": "2025-11-01"}
    assert info == {"currency": "JPY", "exchange": "JPX", "splits": [{"date": "2025-10-27", "ratio": "10:1"}]}


def test_parse_chart_raises_on_error():
    with pytest.raises(ProviderError):
        SP.parse_chart({"chart": {"error": {"description": "No data found"}, "result": None}}, "2025-11-01")


def test_parse_chart_drops_the_open_session_and_null_splits():
    payload = _payload([100, 101, 102])
    result = payload["chart"]["result"][0]
    result["events"] = {"splits": None}
    result["meta"]["currentTradingPeriod"] = {"regular": {"start": T0 + 2 * DAY, "end": T0 + 2 * DAY + 21600}}
    rows, info = SP.parse_chart(payload, "2025-10-29", now=T0 + 2 * DAY + 3600)
    assert [r["date"] for r in rows] == ["2025-10-27", "2025-10-28"] and info["splits"] == []
    rows, _ = SP.parse_chart(payload, "2025-10-29", now=T0 + 2 * DAY + 30000)  # after the close
    assert rows[-1]["date"] == "2025-10-29"


def test_merge_drops_stored_rows_after_a_split():
    stored = [{"date": "2020-01-06", "close": "1000", "retrieved": "2025-01-10"}]
    fetched = [{"date": "2021-01-04", "close": "100"}]
    assert SP.merge(stored, fetched, [{"date": "2025-09-29", "ratio": "10:1"}]) == fetched
    assert SP.merge(stored, fetched, [{"date": "2019-09-29", "ratio": "10:1"}]) == stored + fetched


def test_merge_keeps_older_rows_and_prefers_fetch():
    stored = [{"date": "2025-10-01", "close": "90"}, {"date": "2025-10-27", "close": "1000"}]
    fetched = [{"date": "2025-10-27", "close": "100"}]
    assert SP.merge(stored, fetched) == [{"date": "2025-10-01", "close": "90"}, {"date": "2025-10-27", "close": "100"}]
    assert SP.merge(stored, []) == stored


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "companies" / "3798_uls-group").mkdir(parents=True)
    return tmp_path


def test_run_writes_prices_csv(tmp_path, capsys):
    root = _repo(tmp_path)
    calls = []

    def get(url, params=None):
        calls.append((url, params))
        return _Resp(_payload([100, 101, 102]))

    assert SP.main(["--company", "3798", "--date", "2025-11-01"], root, get) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] and out["rows"] == 3 and out["last_close"] == "102" and out["symbol"] == "3798.T"
    assert "3798.T" in calls[0][0] and calls[0][1]["interval"] == "1d"
    text = (root / "companies/3798_uls-group/data/prices.csv").read_text(encoding="utf-8")
    assert text.splitlines()[0] == ",".join(SP.FIELDS)


def test_run_reports_fetch_failure(tmp_path, capsys):
    root = _repo(tmp_path)

    def get(url, params=None):
        raise OSError("timeout")

    assert SP.main(["--company", "3798", "--date", "2025-11-01"], root, get) == 1
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert not out["ok"] and "timeout" in out["error"]
    assert not (root / "companies/3798_uls-group/data/prices.csv").exists()


def test_run_unknown_company(tmp_path):
    assert SP.run(_repo(tmp_path), "9999", 10, "2025-11-01")["ok"] is False
