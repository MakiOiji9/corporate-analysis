import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_judge as J  # noqa: E402

GOOD4 = {"収益性": "良好", "成長性": "良好", "安全性": "良好", "キャッシュフロー": "良好"}


def _s(grade: str, pending: bool = False) -> dict:
    return {"grade": grade, "pending": pending}


# ---------------------------------------------------------------- STEP 1

@pytest.mark.parametrize("attr, win, moat, swot, grade, pending", [
    ("中", "明確", "広い", "Yes", "A", False),
    ("高", "明確", "広い", "Yes", "A", False),
    ("低", "明確", "広い", "Yes", "B", False),
    ("中", "あいまい", "広い", "Yes", "B", False),
    ("中", "明確", "狭い", "Yes", "B", False),
    ("中", "明確", "広い", "条件付き", "B", False),
    ("高", "なし", "広い", "Yes", "C", False),
    ("高", "明確", "広い", "No", "C", False),
    ("中", "判定保留", "なし", "条件付き", "B", True),   # 3798: 勝てる理由が保留なら確定しない
    ("中", "判定保留", "広い", "No", "C", False),        # C は保留があっても C
    ("中", "明確", "広い", None, "B", True),
])
def test_step1_rules(attr, win, moat, swot, grade, pending):
    result = J.step1(attr, win, moat, swot)
    assert (result["grade"], result["pending"]) == (grade, pending)
    assert len(result["rows"]) == 4


def test_step1_lists_failed_a_conditions():
    result = J.step1("中", "あいまい", "狭い", "Yes")
    assert result["failed"] == ["勝てる理由が明確", "モートが広い"]


# ---------------------------------------------------------------- STEP 2

@pytest.mark.parametrize("items, mismatch, grade, pending", [
    (GOOD4, [], "A", False),
    ({**GOOD4, "成長性": "普通"}, [], "A", False),
    ({**GOOD4, "成長性": "普通"}, ["食い違い"], "B", False),
    ({**GOOD4, "成長性": "普通", "安全性": "普通"}, [], "B", False),
    ({**GOOD4, "成長性": "懸念"}, [], "B", False),
    ({**GOOD4, "成長性": "懸念", "安全性": "懸念"}, [], "C", False),
    ({**GOOD4, "キャッシュフロー": "懸念"}, [], "C", False),     # CF 懸念だけで C
    ({**GOOD4, "安全性": "判定保留"}, [], "B", True),
    ({**GOOD4, "安全性": None, "キャッシュフロー": "懸念"}, [], "C", False),
])
def test_step2_rules(items, mismatch, grade, pending):
    result = J.step2(items, mismatch)
    assert (result["grade"], result["pending"]) == (grade, pending)


@pytest.mark.parametrize("moat, win, prof, diff, count", [
    ("広い", "明確", "良好", 2.0, 0),
    ("広い", "明確", "良好", -0.5, 1),
    ("広い", "明確", "懸念", 2.0, 2),
    ("狭い", "あいまい", "懸念", -3.0, 0),
    ("狭い", "明確", "懸念", None, 1),
])
def test_mismatches(moat, win, prof, diff, count):
    assert len(J.mismatches(moat, win, prof, diff)) == count


# ---------------------------------------------------------------- long term (decision matrix)

@pytest.mark.parametrize("g1, g2, s3, verdict", [
    ("A", "A", "割安", "投資検討"), ("A", "A", "妥当", "投資検討"), ("A", "A", "割高", "ウォッチ"),
    ("A", "B", "割安", "投資検討"), ("B", "A", "妥当", "ウォッチ"), ("B", "B", "割高", "見送り"),
    ("C", "A", "割安", "見送り"), ("A", "C", "妥当", "見送り"), ("C", "C", "割高", "見送り"),
])
def test_long_term_matrix(g1, g2, s3, verdict):
    result = J.long_term(_s(g1), _s(g2), s3)
    assert result["verdict"] == verdict and result["provisional"] is None


def test_long_term_notes_split_buying():
    assert J.long_term(_s("A"), _s("A"), "妥当")["note"] == "分割購入など"


def test_long_term_pending_step1_gives_provisional():
    result = J.long_term(_s("B", pending=True), _s("A"), "割安")
    assert result["verdict"] == "判定保留" and result["provisional"] == "投資検討"


def test_long_term_c_wins_over_pending():
    result = J.long_term(_s("B", pending=True), _s("C"), "割安")
    assert result["verdict"] == "見送り" and result["provisional"] is None


@pytest.mark.parametrize("g, expected", [("A", "ウォッチ"), ("B", "ウォッチ")])
def test_long_term_pending_valuation_caps_at_watch(g, expected):
    result = J.long_term(_s(g), _s("A"), "判定保留")
    assert result["verdict"] == "判定保留" and result["provisional"] == expected


# ---------------------------------------------------------------- mid term

def _long(verdict: str, provisional: str | None = None) -> dict:
    return {"verdict": verdict, "provisional": provisional, "rows": [], "why": "", "note": ""}


def _progress(rate: float, prior: float | None, quarter: int = 1) -> dict:
    return {"quarter": quarter, "items": {"operating_income": {"progress": rate, "prior_progress": prior}}}


def test_mid_term_keeps_long_when_all_checks_pass():
    result = J.mid_term(_long("投資検討"), _progress(26.5, 29.3), "注意", "信頼できる", "妥当")
    assert result["verdict"] == "投資検討"


@pytest.mark.parametrize("progress, outlook, plan, s3", [
    (_progress(20.0, 29.3), "注意", "信頼できる", "妥当"),     # 前年同期の 90% 未満
    (_progress(20.0, None), "注意", "信頼できる", "妥当"),     # 標準ペース 25% の 90% 未満
    (None, "注意", "信頼できる", "妥当"),                      # 不明は良い方に読まない
    (_progress(30.0, 29.3), "警戒", "信頼できる", "妥当"),
    (_progress(30.0, 29.3), "平常", "信頼できない", "割高"),
])
def test_mid_term_steps_down_once(progress, outlook, plan, s3):
    assert J.mid_term(_long("投資検討"), progress, outlook, plan, s3)["verdict"] == "ウォッチ"


def test_mid_term_plan_row_is_unknown_without_valuation():
    result = J.mid_term(_long("投資検討"), _progress(30, 29), "平常", "信頼できない", "判定保留")
    assert result["rows"][3]["ok"] is None and result["verdict"] == "ウォッチ"


def test_short_term_position_rounds_half_up():
    assert J.short_term(_long("投資検討"), "注意", 66.5, 0.0)["verdict"] == "ウォッチ"


def test_mid_term_steps_down_only_one_level():
    assert J.mid_term(_long("投資検討"), None, "警戒", "信頼できない", "割高")["verdict"] == "ウォッチ"


def test_mid_term_progress_boundary():
    pace = 29.3 * J.PROGRESS_RATIO
    assert J.mid_term(_long("投資検討"), _progress(pace, 29.3), "注意", "信頼できる", "割安")["verdict"] == "投資検討"


def test_mid_term_never_above_long():
    assert J.mid_term(_long("見送り"), _progress(40, 20), "平常", "信頼できる", "割安")["verdict"] == "見送り"
    assert J.mid_term(_long("ウォッチ"), _progress(40, 20), "平常", "信頼できる", "割安")["verdict"] == "ウォッチ"


def test_mid_term_carries_provisional():
    result = J.mid_term(_long("判定保留", "投資検討"), _progress(30, 29), "平常", "信頼できる", "割安")
    assert result["verdict"] == "判定保留" and result["provisional"] == "投資検討"


# ---------------------------------------------------------------- short term

@pytest.mark.parametrize("long, outlook, pos, gap, verdict", [
    ("投資検討", "注意", 40.0, 5.0, "投資検討"),
    ("投資検討", "注意", 66.4, 5.0, "投資検討"),   # 66% は上位1/3ではない
    ("投資検討", "注意", 66.6, 5.0, "ウォッチ"),   # 67% は上位1/3
    ("投資検討", "注意", 40.0, 15.0, "投資検討"),
    ("投資検討", "注意", 40.0, 15.1, "ウォッチ"),
    ("投資検討", "警戒", 40.0, 5.0, "ウォッチ"),
    ("投資検討", "警戒", 80.0, 5.0, "見送り"),
    ("ウォッチ", "警戒", 80.0, 5.0, "見送り"),
    ("ウォッチ", "平常", 10.0, 0.0, "ウォッチ"),   # 長期を超えない
    ("見送り", "平常", 10.0, 0.0, "見送り"),
    ("投資検討", "平常", None, None, "ウォッチ"),   # 株価が不明なら投資検討にしない
])
def test_short_term_rules(long, outlook, pos, gap, verdict):
    result = J.short_term(_long(long), outlook, pos, gap)
    assert result["verdict"] == verdict
    assert result["note"]


def test_short_term_rows_mark_unknown():
    rows = J.short_term(_long("投資検討"), None, None, None)["rows"]
    assert [r["ok"] for r in rows[1:]] == [None, None, None]
    assert all(r["value"] == "—" for r in rows[1:])
