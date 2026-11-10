import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import ff_metrics as FF  # noqa: E402
import share_tables as ST  # noqa: E402

BODY = """上位企業のシェア（2025年、矢野経済研究所）

| 会社 | シェア | 年度 | 出典 |
|---|---|---|---|
| B社 | 20.0% | 2025 | 矢野経済 |
| 対象社 | 25.5% | 2025 | 矢野経済 |
| C社 | 15.0% | 2025 | 矢野経済 |
| D社 | 5.0% | 2025 | 矢野経済 |

### 自社シェアの推移

| 年度 | シェア | 出典 |
|---|---|---|
| 2025年 | 25.5% | 矢野経済 |
| 2022年 | 22.0% | 矢野経済 |
| 2023年 | 23.0% | 矢野経済 |
"""


def _found(body: str, status: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(status=status, body=body)


def test_concentration_sums_the_top_three():
    c = ST.concentration(_found(BODY))
    assert c["cr3"] == 60.5 and c["rating"] == "弱" and not c["fixed"]
    assert ST.concentration(_found("| 会社 | シェア |\n|---|---|\n| A | 10% |\n"))["rating"] is None
    assert ST.concentration(_found("", "missing"))["rating"] is None


@pytest.mark.parametrize("values, trend", [
    ([22.0, 23.0, 25.5], "拡大"), ([22.0, 22.1, 22.3], "安定"), ([22.0, 21.8, 21.2], "横ばい〜微減"),
    ([22.0, 21.0, 19.5], "低下"), ([22.0, 23.0], "不明"),
])
def test_share_trend(values, trend):
    rows = "\n".join(f"| {2022 + i} | {v}% |" for i, v in enumerate(values))
    body = f"### 自社シェアの推移\n\n| 年度 | シェア |\n|---|---|\n{rows}\n"
    assert ST.share_trend(_found(body))["trend"] == trend


def test_share_trend_sorts_the_years():
    t = ST.share_trend(_found(BODY))
    assert [y for y, _ in t["series"]] == ["2022", "2023", "2025"] and t["delta"] == 3.5


def test_supplier_uses_the_three_year_change():
    margins = {"2021-03": 40.0, "2022-03": 35.0, "2023-03": 40.0, "2024-03": 39.0}  # one bad year, then back
    assert FF.three_year_drop(margins) == (1.0, "2021-03", "2024-03")
    assert FF.three_year_drop({"2023-03": 40.0, "2024-03": 39.0}) is None
