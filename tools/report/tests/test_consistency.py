import json
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "collect" / "market"), str(REPO / "tools" / "collect")]

import consistency as K  # noqa: E402


def _ev(date: str, event: str, kind: str = "検索", market: str = "us") -> dict:
    return {"date": date, "market": market, "event": event, "detail": "", "kind": kind, "certainty": "検索要約"}


def test_renamed_deadline_with_a_new_date_is_flagged():
    prev = [_ev("2026-12-11", "暫定歳出法（CR）の期限")]
    now = [_ev("2026-12-04", "暫定予算（CR）の期限（H.R. 9770 案）")]
    moved = K.moved_events(now, prev, "2026-10-26")
    assert len(moved) == 1 and moved[0]["before"] == "2026-12-11" and moved[0]["after"] == "2026-12-04"


def test_recurring_similar_names_pair_with_their_own_row():
    prev = [_ev("2026-11-16", "2026年7-9月期 実質GDP 1次速報", market="japan"),
            _ev("2026-12-08", "2026年7-9月期 実質GDP 2次速報", market="japan")]
    now = [_ev("2026-11-16", "2026年7-9月期 実質GDP 1次速報", market="japan"),
           _ev("2026-12-08", "2026年7-9月期 実質GDP 2次速報", market="japan")]
    assert K.moved_events(now, prev, "2026-10-26") == []


def test_official_rows_and_past_events_are_not_compared():
    prev = [_ev("2026-11-10", "CPI（消費者物価指数）", kind="確定"), _ev("2026-10-20", "暫定予算の期限")]
    now = [_ev("2026-12-10", "CPI（消費者物価指数）", kind="確定"), _ev("2026-12-04", "暫定予算の期限")]
    assert K.moved_events(now, prev, "2026-10-26") == []


def test_a_month_becoming_an_exact_date_is_a_confirmation():
    prev = [_ev("2026-12 予定", "第2次補正予算案", market="japan")]
    now = [_ev("2026-12-11", "第2次補正予算案", market="japan")]
    assert K.moved_events(now, prev, "2026-10-26") == []


def test_unrelated_names_are_not_paired():
    prev = [_ev("2026-11-03", "中間選挙")]
    now = [_ev("2026-12-31", "EU の鉄鋼・アルミ派生品関税の引き下げ期限")]
    assert K.moved_events(now, prev, "2026-10-26") == []


def test_check_reads_the_newest_earlier_facts(tmp_path: Path):
    for week, date in (("2026-10-12", "2026-12-18"), ("2026-10-19", "2026-12-11")):
        (tmp_path / f"{week}_facts.json").write_text(
            json.dumps({"week": week, "events": [_ev(date, "暫定歳出法の期限")]}), encoding="utf-8")
    facts = {"week": "2026-10-26", "events": [_ev("2026-12-04", "暫定歳出法の期限")]}
    rows = K.check(facts, tmp_path)
    assert len(rows) == 1 and "2026-12-11 → 今週 2026-12-04" in rows[0]["detail"] and "2026-10-19" in rows[0]["detail"]
    assert K.check({"week": "2026-10-05", "events": []}, tmp_path) == []
