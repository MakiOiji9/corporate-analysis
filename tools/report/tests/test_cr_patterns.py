import datetime as dt
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_patterns as P  # noqa: E402


def _rows(closes: list[float], start: dt.date = dt.date(2023, 1, 2)) -> list[dict]:
    return [{"date": (start + dt.timedelta(days=i)).isoformat(), "close": c, "high": c * 1.01, "low": c * 0.99,
             "volume": 100.0} for i, c in enumerate(closes)]


def _path(points: list[tuple[int, float]]) -> list[float]:
    out: list[float] = []
    for (a, pa), (b, pb) in zip(points, points[1:]):
        out += [pa + (pb - pa) * j / (b - a) for j in range(b - a)]
    return out + [points[-1][1]]


def _find(closes: list[float], key: str) -> dict | None:
    return next((p for p in P.detect(_rows(closes)) if p["key"] == key), None)


def test_zigzag_finds_turns_and_marks_the_last_provisional():
    piv = P.zigzag(_path([(0, 100), (20, 130), (40, 100), (60, 130)]), 0.1)
    assert [q["kind"] for q in piv] == ["L", "H", "L", "H"] and piv[-1]["provisional"]
    assert P.zigzag([100.0, 101.0, 100.0], 0.1) == []


def test_weekly_aggregates_iso_weeks():
    rows = _rows([10, 11, 12, 13, 14, 15, 16, 17, 18, 19])  # 2023-01-02 is a Monday
    w = P.weekly(rows)
    assert [r["close"] for r in w] == [16, 19] and w[0]["volume"] == 700.0
    assert w[0]["high"] == 16 * 1.01 and w[0]["low"] == 10 * 0.99 and w[0]["date"] == "2023-01-08"


def test_double_top_completes_with_neckline_target_and_invalidation():
    p = _find(_path([(0, 100), (40, 140), (70, 115), (100, 140), (125, 110), (140, 100)]), "double_top")
    assert p and p["status"] == "完成" and p["bias"] == "down"
    assert p["trigger"] == 115 and p["target"] == 90 and p["invalidation"] == 140
    assert "確定" not in p["sentence"] and "ダブルトップが完成" in p["sentence"]


def test_double_top_still_forming_above_the_neckline():
    p = _find(_path([(0, 100), (40, 140), (70, 115), (100, 140), (110, 130)]), "double_top")
    assert p and p["status"] == "形成中" and "まだ確定していない" in p["sentence"]


def test_double_top_fails_when_the_close_passes_the_top():
    p = _find(_path([(0, 100), (40, 140), (70, 115), (100, 139), (110, 128), (125, 146)]), "double_top")
    assert p and p["status"] == "失敗" and "失敗" in p["sentence"]


def test_inverse_head_and_shoulders_with_target():
    p = _find(_path([(0, 150), (30, 100), (50, 120), (80, 80), (110, 120), (140, 100), (160, 125)]), "hs_bottom")
    assert p and p["status"] == "完成" and p["bias"] == "up" and p["invalidation"] == 80
    assert p["target"] > p["trigger"] and p["lines"][0]["label"] == "ネックライン"


def test_cup_with_handle():
    p = _find(_path([(0, 80), (30, 100), (100, 70), (170, 99), (185, 92), (200, 101)]), "cup_handle")
    assert p and p["status"] == "完成" and p["trigger"] == 100 and p["invalidation"] == 92 and p["target"] == 130


def test_bull_flag_and_symmetric_triangle():
    flag = _find(_path([(0, 100), (10, 100), (25, 140), (40, 130), (55, 138), (70, 133)]), "flag_bull")
    assert flag and flag["status"] == "形成中" and flag["trigger"] == 140
    tri = _find(_path([(0, 100), (20, 140), (40, 105), (60, 132), (80, 110), (100, 127), (115, 115), (122, 122)]), "tri_sym")
    assert tri and tri["status"] in ("形成中", "完成") and tri["bias"] in ("up", "flat")


def test_flat_noise_has_no_pattern():
    assert P.detect(_rows([100 + (i % 3) * 0.1 for i in range(300)])) == []
    assert P.detect(_rows([100.0] * 10)) == []


def test_analyze_marks_stability_and_history_reference():
    closes = _path([(0, 100), (40, 140), (70, 115), (100, 140), (125, 110), (140, 100)])
    a = P.analyze(_rows(closes))
    assert a["patterns"] and a["stability"] in (P.STABLE, P.UNSTABLE) and all("stable" in p for p in a["patterns"])
    assert P.analyze(_rows([100.0] * 80))["stability"] == P.NONE
    # one finished double top, with the price falling on afterwards: the past case is a reference value
    h = P.history(_rows(closes + [100 - i * 0.2 for i in range(1, 60)]))
    assert h["double_top"]["n"] == 1 and h["double_top"]["ref"] and h["double_top"]["hit_rate"] == 1.0
