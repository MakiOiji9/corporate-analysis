"""EDINET API v2 client: list a company's filings and download them into sources/.

Requires EDINET_API_KEY (env or .env). Without it, exits with code 3 so the
caller falls back to the PDF route (fetch.py + pdf_text.py + find_pages.py).

Usage:
  edinet.py list  --code 3798 --from 2026-06-01 --to 2026-06-30
  edinet.py list  --code 3798 --fy-end-month 3 --years 10      # scans each year's filing month
  edinet.py fetch --doc-id S100YCBQ --company <dir> [--kind csv|pdf|xbrl] [--period 2026-03]

The document list API is per-day, so daily results are cached in .cache/edinet/
(past dates only). 'csv' (XBRL->CSV zip) is what xbrl_financials.py reads.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import (  # noqa: E402
    CACHE_DIR, atomic_write_text, company_dir, http_get, load_env, store_document, utf8_stdout,
)

API = "https://api.edinet-fsa.go.jp/api/v2"
DOC_TYPES = {"120": "有価証券報告書", "130": "訂正有価証券報告書", "140": "四半期報告書",
             "150": "訂正四半期報告書", "160": "半期報告書", "170": "訂正半期報告書",
             "180": "臨時報告書"}
KIND_PARAM = {"xbrl": "1", "pdf": "2", "csv": "5"}
KIND_EXT = {"xbrl": ".zip", "pdf": ".pdf", "csv": "_csv.zip"}
REQUEST_INTERVAL_SEC = 0.3
MISSING_KEY_EXIT = 3
FILING_LAG_MONTHS = 3  # 有報 is due within 3 months after fiscal year end


def api_key() -> str:
    load_env()
    key = os.environ.get("EDINET_API_KEY", "")
    if not key:
        print("EDINET_API_KEY not set -> use the PDF route (fetch.py / pdf_text.py / find_pages.py)")
        sys.exit(MISSING_KEY_EXIT)
    return key


def daily_list(day: dt.date, key: str) -> list[dict]:
    cache = CACHE_DIR / "edinet" / f"{day.isoformat()}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    resp = http_get(f"{API}/documents.json",
                    params={"date": day.isoformat(), "type": "2", "Subscription-Key": key})
    results = resp.json().get("results") or []
    if day < dt.date.today():
        atomic_write_text(cache, json.dumps(results, ensure_ascii=False))
    time.sleep(REQUEST_INTERVAL_SEC)
    return results


def scan_windows(fy_end_month: int, years: int) -> list[tuple[dt.date, dt.date]]:
    """One window per year: the whole month in which the 有報 is due."""
    today = dt.date.today()
    windows = []
    for back in range(years + 1):
        year = today.year - back
        month = fy_end_month + FILING_LAG_MONTHS
        year, month = (year + 1, month - 12) if month > 12 else (year, month)
        start = dt.date(year, month, 1)
        end = (dt.date(year + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1))
        if start <= today:
            windows.append((start, min(end, today)))
    return windows


def list_filings(code: str, windows: list[tuple[dt.date, dt.date]]) -> list[dict]:
    key = api_key()
    sec_code = code + "0" if len(code) == 4 else code
    found = []
    for start, end in windows:
        day = start
        while day <= end:
            found += [d for d in daily_list(day, key) if d.get("secCode") == sec_code]
            day += dt.timedelta(days=1)
    return sorted(found, key=lambda d: d.get("submitDateTime") or "")


def cmd_list(args: argparse.Namespace) -> None:
    if args.fy_end_month:
        windows = scan_windows(args.fy_end_month, args.years)
    else:
        windows = [(dt.date.fromisoformat(args.date_from), dt.date.fromisoformat(args.date_to))]
    api_key()  # fail fast before printing anything
    print("| docID | 種別 | 期間 | 提出日時 | 書類名 | csv |\n|---|---|---|---|---|---|")
    for d in list_filings(args.code, windows):
        kind = DOC_TYPES.get(d.get("docTypeCode", ""), d.get("docTypeCode", ""))
        print(f"| {d['docID']} | {kind} | {d.get('periodStart')}〜{d.get('periodEnd')} | "
              f"{d.get('submitDateTime')} | {d.get('docDescription')} | {d.get('csvFlag')} |")


def cmd_fetch(args: argparse.Namespace) -> None:
    key = api_key()
    company = company_dir(args.company)
    url = f"{API}/documents/{args.doc_id}"
    resp = http_get(url, params={"type": KIND_PARAM[args.kind], "Subscription-Key": key})
    if "application/json" in resp.headers.get("Content-Type", ""):
        raise SystemExit(f"EDINET error: {resp.text[:300]}")
    path, is_new = store_document(company, resp.content, args.doc_id + KIND_EXT[args.kind], {
        "doc_type": f"edinet-{args.kind}", "period": args.period, "doc_id": args.doc_id,
        "url": f"{url}?type={KIND_PARAM[args.kind]}", "note": "EDINET API v2",
    })
    print(f"{'SAVED' if is_new else 'DUPLICATE'} {path}")
    if path.suffix == ".zip":
        out_dir = path.with_suffix("")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out_dir)
        print(f"EXTRACTED {out_dir}")


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_list = sub.add_parser("list")
    p_list.add_argument("--code", required=True)
    p_list.add_argument("--from", dest="date_from")
    p_list.add_argument("--to", dest="date_to")
    p_list.add_argument("--fy-end-month", type=int)
    p_list.add_argument("--years", type=int, default=10)
    p_fetch = sub.add_parser("fetch")
    p_fetch.add_argument("--doc-id", required=True)
    p_fetch.add_argument("--company", required=True)
    p_fetch.add_argument("--kind", choices=list(KIND_PARAM), default="csv")
    p_fetch.add_argument("--period", default="")
    args = ap.parse_args()
    if args.cmd == "list" and not (args.fy_end_month or (args.date_from and args.date_to)):
        ap.error("list needs --from/--to or --fy-end-month")
    cmd_list(args) if args.cmd == "list" else cmd_fetch(args)


if __name__ == "__main__":
    main()
