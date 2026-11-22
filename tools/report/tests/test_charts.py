import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import charts as C  # noqa: E402

MONTHS = [f"2026-{m:02d}-01" for m in range(1, 13)]


def _series(cls: str | None = None, markers: bool = False) -> dict:
    s = {"label": "線", "points": [[d, 100 + i] for i, d in enumerate(MONTHS)]}
    if cls:
        s["cls"] = cls
    if markers:
        s["markers"] = True
    return s


def test_markers_draw_a_visible_dot_per_point_only_when_asked():
    plain = C.line_chart([_series()], "t")
    marked = C.line_chart([_series(), _series("zig", markers=True)], "t")
    assert 'class="pt' not in plain
    assert marked.count('class="pt zig"') == len(MONTHS)


def test_narrow_chart_shows_fewer_date_labels():
    def dates(svg: str) -> int:
        return len(re.findall(r'class="tick"[^>]*>\d{4}-\d{2}<', svg))
    assert dates(C.line_chart([_series()], "t")) == 5
    assert dates(C.line_chart([_series()], "t", width=380)) == 3


def test_reference_line_labels_are_drawn_over_the_data_lines():
    svg = C.line_chart([_series()], "t", hlines=[{"label": "目標", "value": 105, "cls": "ref"}])
    assert svg.index('class="ln s0"') < svg.index('class="hl-l ref"')
    assert svg.index('class="hl ref"') < svg.index('class="ln s0"')
