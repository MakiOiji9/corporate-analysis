"""Inline SVG charts for the report (no external library, so the HTML stays one offline file).

Colours are not set here: every mark carries a class (s0, s1, s2, pos, neg, grid ...) that the
report stylesheet maps to theme tokens, so light/dark and print all follow the CSS.
"""
from __future__ import annotations

import datetime as dt
import math
from html import escape

EMPTY = '<div class="chart-empty">データ未取得</div>'
LABEL_GAP = 13  # px between end-of-line labels
HIT_POINTS = 130  # hover dots only up to this many points per series


def fmt(value: float | None, decimals: int = 1, signed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{value:+,.{decimals}f}" if signed else f"{value:,.{decimals}f}"
    return text.replace("-", "−")


def nice_ticks(lo: float, hi: float, count: int = 5) -> list[float]:
    if hi == lo:
        hi, lo = hi + 1, lo - 1
    raw = (hi - lo) / max(count - 1, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    ticks, v = [], math.floor(lo / step) * step
    while v <= hi + step * 1e-9:
        ticks.append(round(v, 10))
        v += step
    if ticks[-1] < hi:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def tick_decimals(ticks: list[float]) -> int:
    step = abs(ticks[1] - ticks[0]) if len(ticks) > 1 else 1
    return 0 if step >= 1 else (1 if step >= 0.1 else 2)


def _ordinal(date: str) -> int:
    return dt.date.fromisoformat(date).toordinal()


def _frame(width: int, height: int, title: str, body: list[str]) -> str:
    return (f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
            + "".join(body) + "</svg>")


def _y_axis(ticks: list[float], y, left: float, right: float) -> list[str]:
    d = tick_decimals(ticks)
    out = []
    for t in ticks:
        yy = y(t)
        cls = "grid zero" if t == 0 else "grid"
        out.append(f'<line class="{cls}" x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}"/>')
        out.append(f'<text class="tick" x="{left - 6}" y="{yy + 4:.1f}" text-anchor="end">{fmt(t, d)}</text>')
    return out


def _x_axis(positions: list[tuple[str, float]], bottom: float, count: int = 5) -> list[str]:
    """positions: (date, x) in drawing order; up to `count` evenly spaced labels."""
    if not positions:
        return []
    n = len(positions)
    picks = sorted({round(i * (n - 1) / (count - 1)) for i in range(count)}) if n > 1 else [0]
    span_days = _ordinal(positions[-1][0]) - _ordinal(positions[0][0])
    out = []
    for k, i in enumerate(picks):
        d, xx = positions[i]
        label = d[:7] if span_days > 200 else d[5:]
        anchor = "start" if k == 0 else ("end" if k == len(picks) - 1 else "middle")
        out.append(f'<text class="tick" x="{xx:.1f}" y="{bottom + 18}" text-anchor="{anchor}">{label}</text>')
    return out


def _spread_labels(items: list[tuple[float, str]], top: float, bottom: float) -> list[tuple[float, str]]:
    """Push end labels apart vertically so lines ending close together stay readable."""
    placed: list[tuple[float, str]] = []
    for y, html in sorted(items):
        y = max(y, top + 4)
        if placed and y - placed[-1][0] < LABEL_GAP:
            y = placed[-1][0] + LABEL_GAP
        placed.append((min(y, bottom), html))
    return placed


def _hlines(hlines: list[dict], y, left: float, right: float, decimals: int) -> list[str]:
    """Horizontal reference lines ({label, value, cls}) with their labels at the left end, pushed apart vertically
    so lines close together keep readable labels."""
    out, labels = [], []
    for h in hlines:
        yy = y(h["value"])
        cls = escape(h.get("cls") or "")
        out.append(f'<line class="hl {cls}" x1="{left}" x2="{right}" y1="{yy:.1f}" y2="{yy:.1f}">'
                   f'<title>{escape(h["label"])}: {fmt(h["value"], decimals)}</title></line>')
        labels.append((yy - 4, f'class="hl-l {cls}">{escape(h["label"])} {fmt(h["value"], decimals)}'))
    top = min((yy for yy, _ in labels), default=0) - LABEL_GAP * len(labels)
    for yy, html in _spread_labels(labels, top, float("inf")):
        out.append(f'<text x="{left + 4}" y="{yy:.1f}" {html}</text>')
    return out


def line_chart(series: list[dict], title: str, decimals: int = 1, width: int = 720, height: int = 300,
               hlines: list[dict] | None = None) -> str:
    """series: [{"label", "points": [[date, value], ...], "cls"?}]; the mark class is cls or s{i} (series index).
    hlines: horizontal reference lines [{label, value, cls}] drawn across the chart and kept inside the scale.
    Hover dots are drawn only for series of up to HIT_POINTS points (a daily series would make the file heavy)."""
    drawn = [(i, s) for i, s in enumerate(series) if s.get("points")]
    if not drawn:
        return EMPTY
    hlines = hlines or []
    left, right, top, bottom = 52, width - 78, 14, height - 30
    values = [p[1] for _, s in drawn for p in s["points"]] + [h["value"] for h in hlines]
    dates = sorted({p[0] for _, s in drawn for p in s["points"]})
    ticks = nice_ticks(min(values), max(values))
    x0, x1 = _ordinal(dates[0]), _ordinal(dates[-1])

    def x(d: str) -> float:
        return left + (right - left) * ((_ordinal(d) - x0) / (x1 - x0) if x1 > x0 else 0.5)

    def y(v: float) -> float:
        return bottom - (bottom - top) * (v - ticks[0]) / (ticks[-1] - ticks[0])

    body = _y_axis(ticks, y, left, right) + _x_axis([(d, x(d)) for d in dates], bottom)
    body += _hlines(hlines, y, left, right, decimals)
    labels = []
    for i, s in drawn:
        pts = s["points"]
        cls = escape(s.get("cls") or f"s{i}")
        path = "M" + " L".join(f"{x(d):.1f},{y(v):.1f}" for d, v in pts)
        body.append(f'<path class="ln {cls}" d="{path}"><title>{escape(s["label"])}</title></path>')
        if len(pts) <= HIT_POINTS:
            body += [f'<circle class="hit" cx="{x(d):.1f}" cy="{y(v):.1f}" r="5">'
                     f'<title>{escape(s["label"])} {escape(d)}: {fmt(v, decimals)}</title></circle>' for d, v in pts]
        if s.get("cls"):  # a styled helper line (a band): no end label
            continue
        d_last, v_last = pts[-1]
        body.append(f'<circle class="dot {cls}" cx="{x(d_last):.1f}" cy="{y(v_last):.1f}" r="3.5"/>')
        labels.append((y(v_last), f'class="end {cls}">{fmt(v_last, decimals)}'))
    for yy, html in _spread_labels(labels, top, bottom):
        body.append(f'<text x="{right + 8}" y="{yy + 4:.1f}" {html}</text>')
    return _frame(width, height, title, body)


def bar_chart(points: list, title: str, decimals: int = 0, width: int = 720, height: int = 260) -> str:
    """One series of signed bars (pos / neg classes) around a zero line."""
    if not points:
        return EMPTY
    left, right, top, bottom = 64, width - 16, 14, height - 30
    values = [p[1] for p in points]
    ticks = nice_ticks(min(min(values), 0), max(max(values), 0))
    slot = (right - left) / len(points)
    bar_w = max(slot * 0.7, 1.5)

    def y(v: float) -> float:
        return bottom - (bottom - top) * (v - ticks[0]) / (ticks[-1] - ticks[0])

    centers = [(d, left + slot * (i + 0.5)) for i, (d, _) in enumerate(points)]
    body = _y_axis(ticks, y, left, right) + _x_axis(centers, bottom)
    zero = y(0)
    for (d, v), (_, cx) in zip(points, centers):
        top_y, h = (y(v), zero - y(v)) if v >= 0 else (zero, y(v) - zero)
        cls = "bar pos" if v >= 0 else "bar neg"
        body.append(f'<rect class="{cls}" x="{cx - bar_w / 2:.1f}" y="{top_y:.1f}" width="{bar_w:.1f}" '
                    f'height="{max(h, 0.5):.1f}" rx="1"><title>{escape(d)}: {fmt(v, decimals)}</title></rect>')
    return _frame(width, height, title, body)


def range_chart(rows: list[dict], current: float | None, title: str, width: int = 720, row_h: int = 40) -> str:
    """Horizontal ranges (a football field): rows [{label, low, high, mid?, note?, alt?}], one band per row, with an
    optional middle tick and a vertical line at the current price. Bands carry class rng (rng alt for rows
    flagged alt), the line class now."""
    rows = [r for r in rows if r.get("low") is not None and r.get("high") is not None]
    if not rows:
        return EMPTY
    left, right, top = 176, width - 24, 26
    bottom = top + row_h * len(rows)
    values = [v for r in rows for v in (r["low"], r["high"])] + ([current] if current else [])
    lo, hi = min(values), max(values)
    pad = (hi - lo) * 0.06 or abs(hi) * 0.1 or 1

    def x(v: float) -> float:
        return left + (right - left) * (v - (lo - pad)) / ((hi + pad) - (lo - pad))

    body = []
    for i, r in enumerate(rows):
        yy = top + row_h * i
        mid_y = yy + row_h / 2 + 4
        cls = "rng alt" if r.get("alt") else "rng"
        x0, x1 = x(min(r["low"], r["high"])), x(max(r["low"], r["high"]))
        note = f' {r["note"]}' if r.get("note") else ""
        body.append(f'<text class="rlabel" x="{left - 10}" y="{mid_y:.1f}" text-anchor="end">{escape(r["label"])}</text>')
        body.append(f'<rect class="{cls}" x="{x0:.1f}" y="{yy + 9:.1f}" width="{max(x1 - x0, 2):.1f}" '
                    f'height="{row_h - 18}" rx="3"><title>{escape(r["label"])}: {fmt(r["low"], 0)}〜'
                    f'{fmt(r["high"], 0)}{escape(note)}</title></rect>')
        if r.get("mid") is not None:
            xm = x(r["mid"])
            body.append(f'<line class="mid" x1="{xm:.1f}" x2="{xm:.1f}" y1="{yy + 6:.1f}" y2="{yy + row_h - 6:.1f}"/>')
        # the end values sit outside the band, or just inside it when the band reaches the chart's edge
        lo_x, lo_anchor = (x0 - 4, "end") if x0 - left > 44 else (x0 + 4, "start")
        hi_x, hi_anchor = (x1 + 4, "start") if right - x1 > 44 else (x1 - 4, "end")
        body.append(f'<text class="tick" x="{lo_x:.1f}" y="{mid_y:.1f}" text-anchor="{lo_anchor}">{fmt(r["low"], 0)}</text>')
        if x1 - x0 > 90 or hi_anchor == "start":  # inside both ends only when the band is wide enough
            body.append(f'<text class="tick" x="{hi_x:.1f}" y="{mid_y:.1f}" text-anchor="{hi_anchor}">'
                        f'{fmt(r["high"], 0)}</text>')
    if current:
        xc = x(current)
        body.append(f'<line class="now" x1="{xc:.1f}" x2="{xc:.1f}" y1="{top - 6}" y2="{bottom + 4}"/>')
        body.append(f'<text class="now-l" x="{xc:.1f}" y="{top - 10}" text-anchor="middle">今 {fmt(current, 0)}</text>')
    return _frame(width, bottom + 12, title, body)


def sparkline(points: list, width: int = 160, height: int = 44) -> str:
    if len(points) < 2:
        return '<svg class="spark" viewBox="0 0 1 1" aria-hidden="true"></svg>'
    values = [p[1] for p in points]
    lo, hi = min(values), max(values)
    span = hi - lo or 1

    def xy(i: int, v: float) -> tuple[float, float]:
        return 2 + (width - 6) * i / (len(values) - 1), height - 3 - (height - 6) * (v - lo) / span

    path = "M" + " L".join("{:.1f},{:.1f}".format(*xy(i, v)) for i, v in enumerate(values))
    lx, ly = xy(len(values) - 1, values[-1])
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" aria-hidden="true" preserveAspectRatio="none">'
            f'<path d="{path}"/><circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.6"/></svg>')
