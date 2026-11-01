import json
import sys
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ANALYSIS)]

import an_fill as F  # noqa: E402

MD = """# 分析

| 項目 | 内容 |
|---|---|
| 背景 | <!-- FILL:bg 背景を1文 --> |
| 要点 | <!-- FILL:points 要点を2文 --> |

## 7. 前回からの変更点

<!-- FILL:changes 箇条書き（- で始める） -->
"""


def test_fill_spec_lists_keys_hints_and_cells():
    spec = F.fill_spec(MD)
    assert [s["key"] for s in spec] == ["bg", "points", "changes"]
    assert spec[0] == {"key": "bg", "hint": "背景を1文", "cell": True} and spec[2]["cell"] is False


def test_prefill_keeps_none_and_blank_for_the_writer():
    text = F.prefill(MD, {"points": None, "bg": "  ", "changes": "- なし"})
    assert F.fill_keys(text) == ["bg", "points"] and "## 7. 前回からの変更点\n\n- なし" in text


def test_cell_text_is_one_line_without_pipes_and_blocks_keep_lines():
    text, used, issues = F.apply_fills(MD, {"bg": "a | b\nc", "changes": "- 1\n- 2"})
    assert issues == [] and used == ["bg", "changes"]
    assert "| 背景 | a ｜ b c |" in text and "- 1\n- 2" in text


def test_apply_fills_refuses_unknown_and_empty_keys_without_writing():
    text, used, issues = F.apply_fills(MD, {"bg": "", "nope": "x"})
    assert text == MD and used == []
    assert issues == ["nope: md に無い FILL のキー（prepare の fill_keys を使う）", "bg: 本文が文字列でない、または空"]
    assert F.apply_fills(MD, ["bg"])[2] == ["JSON は {\"FILL のキー\": \"本文\"} のオブジェクトにする"]


def test_fill_at_build_waits_until_only_its_keys_remain():
    def compute(_: str) -> dict:
        return {"changes": "- 初回の分析"}
    assert F.fill_at_build(MD, ("changes",), compute) == MD  # bg and points are still the writer's
    done = F.substitute(MD, {"bg": "x", "points": "y"})[0]
    assert F.fill_keys(F.fill_at_build(done, ("changes",), compute)) == []


def test_changes_bullets():
    assert F.changes_bullets(None, [("a", 1, 2)]) == "- 初回の分析"
    prev = ("2026-01-01", {})
    assert F.changes_bullets(prev, [("a", 1.0, 1.04), ("b", None, "")]) == "- なし"
    assert F.changes_bullets(prev, [("ROE", 9.0, 10.26)]) == "- ROE: 9.0 → 10.3（前回 2026-01-01）"


def test_run_fill_and_prepare_fields(tmp_path):
    md = tmp_path / "2026-11-01_x.md"
    md.write_text(MD, encoding="utf-8")
    fills = F.default_fills_path(md)
    assert fills.name == "2026-11-01_fills.json"
    assert F.run_fill(md, fills, None)["error"].endswith("が無い")
    fills.write_text(json.dumps({"bg": "背景"}, ensure_ascii=False), encoding="utf-8")

    def write(path: Path, text: str) -> None:
        path.write_text(text, encoding="utf-8")
    assert F.run_fill(md, fills, write) == {"ok": True, "filled": ["bg"], "remaining": ["points", "changes"]}

    class Company:
        @staticmethod
        def rel(path: Path) -> str:
            return path.name
    out = F.prepare_fields(Company, md, build_keys=("changes",))
    assert out["fill_keys"] == ["points"] and out["filled_at_build"] == ["changes"] and out["fill"] == 1
