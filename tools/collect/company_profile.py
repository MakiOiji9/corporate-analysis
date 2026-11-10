"""The company's industry (業種) for the analyses' sector rules: companies/{ticker}_{name}/data/profile.json.

Usage:
  company_profile.py --company 3798_uls-group

Japan: the EDINET code list (EdinetcodeDlInfo.csv, no API key; 提出者業種 = the 33 業種 of the TSE). US: the SEC
submissions JSON (SIC code and description; needs SEC_USER_AGENT). The analyses read profile.json through
tools/analysis/sector_rules.py; without it they fall back to the 主力事業 text. stdout is one JSON line.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import CACHE_DIR, atomic_write_text, company_dir, http_get, utf8_stdout  # noqa: E402

CODELIST_URL = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
CACHE_DAYS = 7
JAPAN_TICKER = re.compile(r"^\d{3}[0-9A-Z]$")


def parse_codelist(text: str, ticker: str) -> dict | None:
    """The row of a listed filer whose 証券コード (5 characters) starts with the 4-character ticker."""
    lines = text.splitlines()[1:]  # the first line is the download note
    for row in csv.DictReader(lines):
        code = (row.get("証券コード") or "").strip()
        if code and code[:4].upper() == ticker.upper():
            return {"edinet_code": row.get("ＥＤＩＮＥＴコード"), "name": row.get("提出者名"),
                    "sector_name": row.get("提出者業種"), "fiscal_year_end": row.get("決算日"),
                    "sector_source": "EDINET コードリスト（提出者業種）"}
    return None


def parse_submissions(data: dict) -> dict:
    sic = str(data.get("sic") or "").strip()
    return {"cik": data.get("cik"), "name": data.get("name"), "sic": int(sic) if sic.isdigit() else None,
            "sector_name": data.get("sicDescription"), "fiscal_year_end": data.get("fiscalYearEnd"),
            "sector_source": "SEC submissions（SIC）"}


def _codelist_text() -> str:
    cache = CACHE_DIR / "edinet" / "EdinetcodeDlInfo.csv"
    fresh = cache.exists() and (dt.datetime.now().timestamp() - cache.stat().st_mtime) < CACHE_DAYS * 86400
    if not fresh:
        with zipfile.ZipFile(io.BytesIO(http_get(CODELIST_URL).content)) as zf:
            atomic_write_text(cache, zf.read(zf.namelist()[0]).decode("cp932"))
    return cache.read_text(encoding="utf-8")


def lookup(ticker: str) -> dict | None:
    if JAPAN_TICKER.match(ticker.upper()):
        found = parse_codelist(_codelist_text(), ticker)
        return {**found, "market": "japan"} if found else None
    from edgar import lookup_cik  # US only: needs SEC_USER_AGENT
    return {**parse_submissions(http_get(SUBMISSIONS_URL.format(cik=lookup_cik(ticker))).json()), "market": "us"}


def run(company_arg: str, today: str) -> dict:
    company = company_dir(company_arg)
    ticker = company.name.split("_", 1)[0]
    try:
        found = lookup(ticker)
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile, SystemExit) as exc:
        return {"ok": False, "error": f"業種を取得できなかった: {exc}"}
    if not found:
        return {"ok": False, "error": f"EDINET コードリストに証券コード {ticker} の上場会社が無い"}
    profile = {"ticker": ticker, **found, "retrieved": today}
    path = company / "data" / "profile.json"
    atomic_write_text(path, json.dumps(profile, ensure_ascii=False, indent=1) + "\n")
    return {"ok": True, "path": str(path), **profile}


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", required=True)
    args = ap.parse_args(argv)
    result = run(args.company, dt.date.today().isoformat())
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
