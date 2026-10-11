"""Scheduled dates that official sites publish in a fixed format (no web search needed).

A catalog "calendar.fixed_sources" entry:
  {"type": "fomc", "url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"}
  {"type": "boj_mpm", "url": "https://www.boj.or.jp/mopo/mpmsche_minu/index.htm"}
  {"type": "fred_release", "release_id": 10, "name": "CPI（消費者物価指数）"}   # FRED_API_KEY

fetch_fixed returns calendar rows [date, event, content, source, 確度] within the window,
sorted by date, and one error string per source that failed. Search-calendar then only
looks for what is not covered here.
"""
from __future__ import annotations

import os
import re
from html import unescape

FRED_RELEASE_DATES = "https://api.stlouisfed.org/fred/release/dates"
FRED_RELEASE_PAGE = "https://fred.stlouisfed.org/release?rid={rid}"
MONTHS = {m[:3]: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August",
                                          "September", "October", "November", "December"), 1)}  # 'Apr' or 'April'
FOMC_YEAR = re.compile(r"(\d{4}) FOMC Meetings")
FOMC_ROW = re.compile(r"fomc-meeting__month[^>]*>(?:\s*<[^>]+>)*\s*([A-Za-z/]+)"
                      r".*?fomc-meeting__date[^>]*>(?:\s*<[^>]+>)*\s*([^<]+)", re.S)
FOMC_DAYS = re.compile(r"(\d{1,2})(?:\s*-\s*(\d{1,2}))?\s*(\*)?")
TAG = re.compile(r"<[^>]+>")
CHARSET = re.compile(rb"charset\s*=\s*[\"']?([\w-]+)", re.I)
BOJ_TOKEN = re.compile(r"(?P<year>20\d{2})年\s*金融政策決定会合"
                       r"|(?P<m1>\d{1,2})月\s*(?P<d1>\d{1,2})日\s*（[^）]）\s*・\s*(?:(?P<m2>\d{1,2})月\s*)?"
                       r"(?P<d2>\d{1,2})日\s*（[^）]）")
BOJ_OUTLOOK_MONTHS = (1, 4, 7, 10)
API_KEY = re.compile(r"api_key=[^&\s]+")
PRIMARY = "一次"


def _iso(year: int, month: int, day: int) -> str:
    return f"{year}-{month:02d}-{day:02d}"


def _decode(content: bytes) -> str:
    m = CHARSET.search(content[:4000])
    try:
        return content.decode(m.group(1).decode() if m else "utf-8", errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


def parse_fomc(html: str, url: str) -> list[list[str]]:
    rows = []
    heads = list(FOMC_YEAR.finditer(html))
    for i, head in enumerate(heads):
        year = int(head.group(1))
        section = html[head.end():heads[i + 1].start() if i + 1 < len(heads) else len(html)]
        for month_text, date_text in FOMC_ROW.findall(section):
            text = unescape(date_text).strip()
            days = FOMC_DAYS.match(text)
            months = [MONTHS.get(m.strip()[:3]) for m in month_text.split("/")]
            if not days or None in months or re.search(r"unscheduled|notation", text, re.I):
                continue
            first, last = int(days.group(1)), int(days.group(2) or days.group(1))
            start, end = _iso(year, months[0], first), _iso(year, months[-1], last)
            content = f"会合 {start[5:]}〜{end[5:]}。最終日に声明公表・議長会見"
            if days.group(3):
                content += "。SEP（経済見通し）公表"
            rows.append([end, "FOMC", content, url, PRIMARY])
    return rows


def parse_boj_mpm(html: str, url: str) -> list[list[str]]:
    text = re.sub(r"\s+", " ", unescape(TAG.sub(" ", html)))
    rows, year = [], None
    for m in BOJ_TOKEN.finditer(text):
        if m.group("year"):
            year = int(m.group("year"))
            continue
        if year is None:
            continue
        m1, d1, d2 = int(m.group("m1")), int(m.group("d1")), int(m.group("d2"))
        m2 = int(m.group("m2") or m1)
        start, end = _iso(year, m1, d1), _iso(year, m2, d2)
        content = f"会合 {start[5:]}〜{end[5:]}。最終日に公表文・総裁会見"
        if m2 in BOJ_OUTLOOK_MONTHS:
            content += "。展望レポート公表"
        rows.append([end, "日銀 金融政策決定会合", content, url, PRIMARY])
    return rows


def parse_fred_release(payload: dict, name: str, release_id: int) -> list[list[str]]:
    page = FRED_RELEASE_PAGE.format(rid=release_id)
    return [[d["date"], name, "公表予定日（FRED のリリース日程）", page, PRIMARY]
            for d in payload.get("release_dates", []) if d.get("date")]


def _fetch_one(source: dict, window_from: str, get) -> list[list[str]]:
    kind = source["type"]
    if kind == "fomc":
        return parse_fomc(_decode(get(source["url"]).content), source["url"])
    if kind == "boj_mpm":
        return parse_boj_mpm(_decode(get(source["url"]).content), source["url"])
    if kind == "fred_release":
        key = os.environ.get("FRED_API_KEY", "")
        if not key:
            raise ValueError("FRED_API_KEY 未設定")
        payload = get(FRED_RELEASE_DATES, params={
            "release_id": str(source["release_id"]), "api_key": key, "file_type": "json",
            "realtime_start": window_from, "include_release_dates_with_no_data": "true",
            "sort_order": "asc"}).json()
        return parse_fred_release(payload, source["name"], source["release_id"])
    raise ValueError(f"unknown fixed source type {kind}")


def fetch_fixed(sources: list[dict], window_from: str, window_to: str, get) -> tuple[list[list[str]], list[str]]:
    rows, errors = [], []
    for source in sources:
        try:
            found = _fetch_one(source, window_from, get)
            if not found:  # a page whose layout changed parses to nothing instead of raising
                raise ValueError("日程を1件も読み取れない（ページの形式が変わった可能性）")
        except Exception as exc:  # noqa: BLE001 - one failing site must not stop the others
            message = API_KEY.sub("api_key=***", str(exc))[:100]
            errors.append(f"{source.get('name') or source['type']}: {type(exc).__name__}: {message}")
            continue
        rows += [r for r in found if window_from <= r[0] <= window_to]
    unique = {tuple(r) for r in rows}
    return sorted((list(r) for r in unique), key=lambda r: (r[0], r[1])), errors
