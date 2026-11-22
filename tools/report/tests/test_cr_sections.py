import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import cr_sections as S  # noqa: E402


def test_a_split_reads_as_share_counts_and_a_multiple():
    split = {"period_end": "2014-03-31", "from": 60264, "to": 6086800, "change_pct": 10000.2, "kind": "株式分割"}
    assert S.issuance_text(split) == "2014-03 株式分割（発行済株式数 60,264株 → 6,086,800株、約101倍）"
    split = {"period_end": "2026-03-31", "from": 6228800, "to": 63853000, "change_pct": 925.1, "kind": "株式分割"}
    assert S.issuance_text(split).endswith("約10.3倍）")
    offer = {"period_end": "2020-03-31", "from": 1000, "to": 1200, "change_pct": 20.0, "kind": "第三者割当"}
    assert S.issuance_text(offer) == "2020-03 第三者割当（発行済株式数 1,000株 → 1,200株、20.0% 増）"
    assert "%" in S.issuance_text({"period_end": "2020-03-31", "change_pct": 20.0, "kind": "不明"})
