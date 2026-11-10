import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_positioning as P  # noqa: E402
import cr_technicals as T  # noqa: E402

JAPAN = """# 需給 — テスト

| 日付 | 信用買い残 | 信用売り残 | 信用倍率 | 出典 |
|---|---|---|---|---|
| 2026-11-06 | 1,500,000 | 250,000 | 6.00 | 株探 |
| 2026-10-09 | 1,000,000 | 250,000 | 4.00 | 株探 |
| 2026-10-16 | 1,100,000 | 250,000 | | 株探 |
| 2026-10-23 | 1,200,000 | 250,000 | 4.80 | 株探 |
| 2026-10-30 | 1,300,000 | 250,000 | 5.20 | 株探 |
| 日付不明 | 9 | 9 | 9 | — |
"""
US = """| 日付 | 空売り残高 | 浮動株比率 | 日数 |
|---|---|---|---|
| 2026-10-15 | 4,000,000 | 9.0% | 4.0 |
| 2026-10-31 | 5,000,000 | 12.5% | 6.2 |
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    (tmp_path / "raw" / "market").mkdir(parents=True, exist_ok=True)
    (tmp_path / "raw" / "market" / name).write_text(text, encoding="utf-8")
    return tmp_path


def test_parse_sorts_rows_and_fills_the_ratio():
    rows = P.parse(JAPAN)
    assert [r["date"] for r in rows] == ["2026-10-09", "2026-10-16", "2026-10-23", "2026-10-30", "2026-11-06"]
    assert rows[1]["ratio"] == 4.4  # 1,100,000 ÷ 250,000 when the cell is blank


def test_japan_summary_flags_a_high_ratio(tmp_path):
    s = P.summarize(_write(tmp_path, "2026-11-08_positioning.md", JAPAN))
    assert s["ok"] and s["date"] == "2026-11-06"
    assert "信用買い残 1,500,000株（4週前比 +50.0%）" in s["text"] and "信用倍率 6.00倍" in s["text"]
    assert any("5倍超" in n for n in s["notes"])


def test_us_summary_flags_heavy_short_interest(tmp_path):
    s = P.summarize(_write(tmp_path, "2026-11-08_positioning.md", US))
    assert "空売り残高 5,000,000株" in s["text"] and "浮動株に対する比率 12.5%" in s["text"]
    assert len(s["notes"]) == 2


def test_newest_file_wins_and_missing_material(tmp_path):
    _write(tmp_path, "2026-10-01_positioning.md", US)
    _write(tmp_path, "2026-11-08_positioning.md", JAPAN)
    assert "信用倍率" in P.summarize(tmp_path)["text"]
    assert not P.summarize(tmp_path / "none")["ok"]


def test_brief_lines_include_the_positioning():
    lines = T.brief_lines({"ok": False, "state": T.NO_DATA}, None, {"text": "需給（…）: 信用倍率 6.00倍", "notes": ["x"]})
    assert "- 需給（…）: 信用倍率 6.00倍" in lines and "  - 注目: x" in lines
