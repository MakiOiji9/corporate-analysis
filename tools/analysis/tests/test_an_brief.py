import sys
from pathlib import Path

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ANALYSIS)]

import an_brief as AB  # noqa: E402

DAY = "2026-11-02"
LONG = "市場規模は 100億円、CAGR 5.0%。" * 20  # over MIN_CHARS
SHORT = "短い節"


class Company:
    def __init__(self, root: Path):
        self.root = root

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()


def brief(*sections: tuple[str, str], mark: bool = False) -> str:
    text = "# 材料\n\n## 1. 章\n\n" + "\n\n".join(f"### {h}\n\n{b}" for h, b in sections) + "\n"
    return text + ("\n<!-- skeleton-sha1: " + "0" * 40 + " -->\n" if mark else "")


def _setup(tmp_path: Path) -> tuple[Company, Path, Path]:
    analysis = tmp_path / "companies" / "1111_x" / "analysis"
    (analysis / "five-forces").mkdir(parents=True)
    (analysis / "three-c").mkdir(parents=True)
    (analysis / "five-forces" / f"{DAY}_brief.md").write_text(
        brief(("業界: 市場規模", LONG), ("短い", SHORT), ("違う", LONG + "x")), encoding="utf-8")
    return Company(tmp_path), analysis / "three-c", analysis / "five-forces" / f"{DAY}_brief.md"


def test_long_identical_sections_become_pointers_and_expand_back(tmp_path):
    company, own, _ = _setup(tmp_path)
    text = brief(("業界: 市場規模", LONG), ("短い", SHORT), ("違う", LONG), mark=True)
    out = AB.dedupe(text, company, own, DAY)
    pointer = f"（companies/1111_x/analysis/five-forces/{DAY}_brief.md の「### 業界: 市場規模」と同じ内容のため省略。"
    assert pointer in out and out.count(LONG) == 1  # only the different section keeps its body
    assert f"### 短い\n\n{SHORT}" in out and out.rstrip().endswith("-->")  # short sections and the mark stay
    assert AB.expand(out, tmp_path).count(LONG) == 2


def test_other_days_and_pointers_are_not_shared(tmp_path):
    company, own, other = _setup(tmp_path)
    text = brief(("業界: 市場規模", LONG))
    assert AB.dedupe(text, company, own, "2026-11-03") == text
    pointed = AB.dedupe(text, company, own, DAY)
    (own / f"{DAY}_brief.md").write_text(pointed, encoding="utf-8")
    other.unlink()  # the target is gone: a later brief must not point at a pointer, expand leaves it as it is
    moat = own.parent / "moat"
    moat.mkdir()
    assert AB.dedupe(text, company, moat, DAY) == text
    assert AB.expand(pointed, tmp_path) == pointed
    assert AB.read_brief(own / "none.md", tmp_path) == ""
