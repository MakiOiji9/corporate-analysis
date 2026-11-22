import datetime as dt
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import cr_ch_tech as CT  # noqa: E402
import cr_plain as PL  # noqa: E402
import cr_tech_cache as TC  # noqa: E402


def _rows(closes: list[float]) -> list[dict]:
    day = dt.date(2023, 1, 2)
    return [{"date": (day + dt.timedelta(days=i)).isoformat(), "close": c, "high": c * 1.01, "low": c * 0.99,
             "volume": 100.0 + i % 7} for i, c in enumerate(closes)]


def _facts() -> dict:
    up = [100 + i * 0.05 for i in range(300)] + [115 - i * 0.4 for i in range(60)] + [91 + i * 0.5 for i in range(40)]
    return {"technical_analysis": TC.analyze(_rows(up))}


def test_chapter_has_fixed_disclaimer_both_timeframes_and_no_internal_words():
    html = CT.chapter(_facts(), "08")
    assert "確実でもない" in html and "まだ確定していない" in html and "保証しない" in html
    assert "日足" in html and "週足" in html and "分析日時" in html and "<svg" in html
    assert "tech-daily" in html and "tech-weekly" in html and PL.leaks(html) == []


def test_chapter_without_prices_still_shows_the_disclaimer():
    html = CT.chapter({"technical_analysis": {"ok": False}}, "08")
    assert "確実でもない" in html and "出せない" in html
    assert "確実でもない" in CT.chapter({}, "08")
