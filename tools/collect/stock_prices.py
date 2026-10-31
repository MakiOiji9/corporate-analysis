"""Daily share prices of a company (split-adjusted) for the company report's price ranges.

Usage:
  stock_prices.py --company 3798 [--years 10]

Source: the Yahoo Finance chart API (unofficial, no key; the same endpoint collect-market-info uses for sector
ETFs, tools/collect/market/series.py). Prices are split-adjusted by the source; adj_close is also adjusted for
dividends. A Japanese ticker (4 characters, digits first) is fetched as {code}.T, a US ticker as it is.
Writes companies/{ticker}_{name}/data/prices.csv (date,open,high,low,close,adj_close,volume,retrieved): the
rows fetched today replace the stored ones from the oldest fetched date on; when a split happened after the
stored rows were retrieved, the stored rows are dropped (they are on the old basis). The bar of a session that is
still open is not stored (its close is a live price). stdout is one JSON line. Exit 1 on failure.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "market")]

from common import REPO_ROOT, http_get, read_csv_rows, utf8_stdout, write_csv_atomic  # noqa: E402
from series import YAHOO_CHART, ProviderError, epoch  # noqa: E402

FIELDS = ["date", "open", "high", "low", "close", "adj_close", "volume", "retrieved"]
JAPAN_TICKER = re.compile(r"^\d{3}[0-9A-Z]$")  # same as tools/analysis/sf_series.JAPAN_TICKER
DEFAULT_YEARS = 10
DAYS_PER_YEAR = 366


def symbol_for(ticker: str) -> str:
    ticker = ticker.upper()
    return f"{ticker}.T" if JAPAN_TICKER.match(ticker) else ticker


def _number(value: object) -> str:
    if value is None:
        return ""
    number = float(value)
    return f"{number:.0f}" if number.is_integer() else f"{number:.4f}".rstrip("0").rstrip(".")


def _at(values: list | None, i: int) -> object:
    return values[i] if values and i < len(values) else None


def _day(ts: int, offset: int) -> str:
    return dt.datetime.fromtimestamp(int(ts) + offset, tz=dt.timezone.utc).date().isoformat()


def _live_day(meta: dict, now: int | None) -> str | None:
    """The trading day still in session at `now` (its bar's close is a live price, not a closing price)."""
    regular = (meta.get("currentTradingPeriod") or {}).get("regular") or {}
    start, end = regular.get("start"), regular.get("end")
    if now is None or start is None or end is None or not start <= now < end:
        return None
    return _day(start, int(meta.get("gmtoffset") or 0))


def parse_chart(payload: dict, retrieved: str, now: int | None = None) -> tuple[list[dict], dict]:
    """(rows oldest first, meta) from a chart API response; bars without a close and the bar of a session still
    open at `now` (epoch seconds) are dropped."""
    chart = payload.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise ProviderError(f"Yahoo chart API: {(chart.get('error') or {}).get('description', 'no result')}")
    result = chart["result"][0]
    meta = result.get("meta") or {}
    offset = int(meta.get("gmtoffset") or 0)
    indicators = result.get("indicators") or {}
    quote = (indicators.get("quote") or [{}])[0]
    adj = (indicators.get("adjclose") or [{}])[0].get("adjclose")
    rows: dict[str, dict] = {}
    for i, ts in enumerate(result.get("timestamp") or []):
        close = _at(quote.get("close"), i)
        if close is None:
            continue
        day = _day(ts, offset)  # a later bar of the same day wins
        rows[day] = {"date": day, "open": _number(_at(quote.get("open"), i)),
                     "high": _number(_at(quote.get("high"), i) or close),
                     "low": _number(_at(quote.get("low"), i) or close), "close": _number(close),
                     "adj_close": _number(_at(adj, i)), "volume": _number(_at(quote.get("volume"), i)),
                     "retrieved": retrieved}
    rows.pop(_live_day(meta, now) or "", None)
    splits = sorted(((result.get("events") or {}).get("splits") or {}).values(), key=lambda s: s.get("date", 0))
    info = {"currency": meta.get("currency"), "exchange": meta.get("exchangeName"),
            "splits": [{"date": _day(s["date"], offset), "ratio": s.get("splitRatio")} for s in splits
                       if s.get("date")]}
    return [rows[d] for d in sorted(rows)], info


def merge(stored: list[dict], fetched: list[dict], splits: list[dict] | None = None) -> list[dict]:
    """Stored rows before the first fetched date, then the fetched rows (the fresh fetch wins). A split after the
    stored rows were retrieved re-bases the prices, so the stored rows are then dropped instead of mixed in."""
    if not fetched:
        return stored
    oldest = min((r.get("retrieved") or "" for r in stored), default="")
    if any(s["date"] >= oldest for s in splits or []):
        return fetched
    first = fetched[0]["date"]
    return [r for r in stored if r["date"] < first] + fetched


def fetch(symbol: str, start: str, today: str, get=http_get, now: int | None = None) -> tuple[list[dict], dict]:
    resp = get(YAHOO_CHART.format(symbol=symbol),
               params={"period1": epoch(start), "period2": epoch(today) + 86400, "interval": "1d",
                       "events": "div,splits"})
    return parse_chart(resp.json(), today, now)


def company_dir(root: Path, arg: str) -> Path | None:
    key = arg.strip().replace("\\", "/").rstrip("/").split("/")[-1].lower()
    dirs = sorted(p for p in (root / "companies").glob("*_*") if p.is_dir())
    for rule in (lambda d: d.name.lower() == key, lambda d: d.name.lower().split("_", 1)[0] == key):
        hits = [d for d in dirs if rule(d)]
        if len(hits) == 1:
            return hits[0]
    return None


def run(root: Path, company_arg: str, years: int, today: str, get=http_get) -> dict:
    company = company_dir(root, company_arg)
    if company is None:
        return {"ok": False, "error": f"companies/ に「{company_arg}」の企業が無い"}
    path = company / "data" / "prices.csv"
    rel = path.relative_to(root).as_posix()
    symbol = symbol_for(company.name.split("_", 1)[0])
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=DAYS_PER_YEAR * years)).isoformat()
    try:
        fetched, info = fetch(symbol, start, today, get, int(time.time()))
    except (ProviderError, OSError, ValueError, RuntimeError) as exc:  # requests errors subclass OSError
        return {"ok": False, "symbol": symbol, "path": rel, "error": f"株価を取得できなかった: {exc}"}
    if not fetched:
        return {"ok": False, "symbol": symbol, "path": rel, "error": "株価の行が無い（銘柄コード・上場区分を確認）"}
    rows = merge(read_csv_rows(path), fetched, info["splits"])
    path.parent.mkdir(parents=True, exist_ok=True)
    write_csv_atomic(path, FIELDS, rows)
    return {"ok": True, "symbol": symbol, "path": rel, "rows": len(rows), "first": rows[0]["date"],
            "last": rows[-1]["date"], "last_close": rows[-1]["close"], **info}


def main(argv: list[str] | None = None, root: Path = REPO_ROOT, get=http_get) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="銘柄コード・企業ディレクトリ名")
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS, help="取得する年数（既定 10）")
    parser.add_argument("--date", help="YYYY-MM-DD（今日の代わり。テスト用）")
    args = parser.parse_args(argv)
    result = run(root, args.company, max(1, args.years), args.date or dt.date.today().isoformat(), get)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
