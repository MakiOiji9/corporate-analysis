"""Chart patterns found from the closes: zigzag pivots, geometric detectors, sensitivity check, past outcomes.

Deterministic and pure Python. A pattern is a dict:
  key, name, timeframe, bias (up/down/flat), status (形成中/完成/失敗), pivots, lines, trigger, target, invalidation,
  alt (the other side of a box or symmetric triangle), sentence, start_i, end_i, stable, history.

The shapes (each has a mirror for tops and bottoms):
  reversal      double top/bottom, triple top/bottom, head and shoulders (and inverse)
  continuation  triangles (rising / falling / symmetric), box, flag, wedge (rising / falling)
  other         cup with handle

Status: 形成中 = the shape stands but the line has not been broken; 完成 = the close broke the line recently;
        失敗 = the close went past the invalidation price. A finished move (target reached) or a stale break is dropped.
The detection is about the shape of the closes, not a forecast; a pattern forming is not yet confirmed.
"""
from __future__ import annotations

import datetime as dt
from statistics import median

VERSION = 1
DAILY, WEEKLY = "daily", "weekly"
LABEL = {DAILY: "日足", WEEKLY: "週足"}
CONFIG = {
    DAILY: dict(zig=0.07, recent=90, break_recent=40, min_gap=8, depth=0.06, pole=0.15, pole_bars=30, cup_min=60,
                cup_depth=(0.12, 0.5), stride=3, after=(20, 60), window=700, min_rows=60, unit="日"),
    WEEKLY: dict(zig=0.12, recent=40, break_recent=16, min_gap=3, depth=0.08, pole=0.25, pole_bars=12, cup_min=15,
                 cup_depth=(0.12, 0.5), stride=1, after=(4, 12), window=400, min_rows=30, unit="週"),
}
TOL = dict(top=0.03, triple=0.04, shoulder=0.08, head=0.03, neck=0.05, flat=0.03, rim=0.06)
SENSITIVITY = (0.8, 1.25)
MIN_SAMPLES = 5  # fewer past cases than this are shown as a reference value
MAX_SHOWN = 4
STABLE, UNSTABLE, NONE = "安定", "感度により変わる", "パターンなし"
UP, DOWN, FLAT = "up", "down", "flat"
FORMING, DONE, FAILED = "形成中", "完成", "失敗"
BIAS_WORD = {UP: "上昇", DOWN: "下落", FLAT: "どちらか"}


def px(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 100 else f"{v:,.2f}"


# ---------------------------------------------------------------- series
def weekly(rows: list[dict]) -> list[dict]:
    """Daily rows → weekly rows (ISO week): last close, highest high, lowest low, summed volume, last date."""
    out: list[dict] = []
    last_key = None
    for r in rows:
        y, w, _ = dt.date.fromisoformat(r["date"]).isocalendar()
        if (y, w) != last_key:
            out.append({"date": r["date"], "close": r["close"], "high": r["high"], "low": r["low"],
                        "volume": r.get("volume") or 0.0})
            last_key = (y, w)
        else:
            o = out[-1]
            o.update(date=r["date"], close=r["close"], high=max(o["high"], r["high"]), low=min(o["low"], r["low"]),
                     volume=(o["volume"] or 0.0) + (r.get("volume") or 0.0))
    return out


def zigzag(values: list[float], pct: float) -> list[dict]:
    """Turning points: a high or low is confirmed once the price has moved pct the other way. The last one is provisional."""
    n = len(values)
    if n < 3 or pct <= 0:
        return []
    piv: list[dict] = []
    hi = lo = 0
    d = 0
    for i in range(1, n):
        v = values[i]
        if d == 0:
            if v > values[hi]:
                hi = i
            if v < values[lo]:
                lo = i
            if lo < i and v >= values[lo] * (1 + pct):
                piv.append({"i": lo, "price": values[lo], "kind": "L"})
                d, hi = 1, i
            elif hi < i and v <= values[hi] * (1 - pct):
                piv.append({"i": hi, "price": values[hi], "kind": "H"})
                d, lo = -1, i
        elif d == 1:
            if v > values[hi]:
                hi = i
            elif v <= values[hi] * (1 - pct):
                piv.append({"i": hi, "price": values[hi], "kind": "H"})
                d, lo = -1, i
        else:
            if v < values[lo]:
                lo = i
            elif v >= values[lo] * (1 + pct):
                piv.append({"i": lo, "price": values[lo], "kind": "L"})
                d, hi = 1, i
    if d == 1:
        piv.append({"i": hi, "price": values[hi], "kind": "H", "provisional": True})
    elif d == -1:
        piv.append({"i": lo, "price": values[lo], "kind": "L", "provisional": True})
    return piv


def _fit(points: list[dict]) -> tuple[float, float]:
    """Least-squares line through pivots: (slope per bar, value at index 0)."""
    n = len(points)
    mx = sum(q["i"] for q in points) / n
    my = sum(q["price"] for q in points) / n
    den = sum((q["i"] - mx) ** 2 for q in points)
    slope = sum((q["i"] - mx) * (q["price"] - my) for q in points) / den if den else 0.0
    return slope, my - slope * mx


# ---------------------------------------------------------------- building blocks
def _status(sgn: int, closes: list[float], scan_from: int, neck_at, inval: float, target: float, cfg: dict) -> str | None:
    """sgn +1: a top (the line is broken downward); −1: a bottom. None: finished or stale."""
    n = len(closes)
    if sgn * closes[-1] > sgn * inval:
        return FAILED
    brk = next((j for j in range(scan_from, n) if sgn * closes[j] < sgn * neck_at(j)), None)
    if brk is None:
        return FORMING
    after = closes[brk:]
    if sgn * (min(after) if sgn > 0 else max(after)) <= sgn * target:
        return None
    return DONE if n - 1 - brk <= cfg["break_recent"] else None


def _sentence(name: str, status: str, bias: str, line_label: str, trigger: float, target: float,
              inval: float | None, alt: dict | None = None) -> str:
    down = bias == DOWN
    if alt:  # box / symmetric triangle: either side
        base = (f"{name}の形。上は {px(trigger)} を終値で上抜けると上方向、下は {px(alt['trigger'])} を終値で割り込むと"
                f"下方向に確認（目標はそれぞれ {px(target)}・{px(alt['target'])}）。どちらに抜けるかは決まっていない。")
        return base if status == FORMING else f"{name}が完成。{base}"
    cross, back = ("割り込む", "上回る") if down else ("上抜ける", "下回る")
    if status == FAILED:
        return f"{name}は失敗。終値が {px(inval)} を{back}ため、このかたちは当てはまらなくなった。"
    if status == DONE:
        head = f"{name}が完成。{line_label} {px(trigger)} を終値で{cross}形になっており、"
    else:
        head = f"{name}になりうる形（まだ確定していない）。{line_label} {px(trigger)} を終値で{cross}と確認され、"
    tail = f"目標は {px(target)}。" if target is not None else ""
    tail += f"終値が {px(inval)} を{back}と失敗。" if inval is not None else ""
    return head + tail


def _mk(rows: list[dict], tf: str, key: str, name: str, bias: str, status: str, pts: list[dict], lines: list[dict],
        trigger: float, target: float, inval: float | None, line_label: str, alt: dict | None = None) -> dict:
    return {"key": key, "name": name, "timeframe": tf, "bias": bias, "status": status,
            "pivots": [{"date": rows[q["i"]]["date"], "i": q["i"], "price": round(q["price"], 2)} for q in pts],
            "lines": lines, "trigger": round(trigger, 2), "target": round(target, 2),
            "invalidation": None if inval is None else round(inval, 2),
            "alt": None if not alt else {k: round(v, 2) for k, v in alt.items()},
            "sentence": _sentence(name, status, bias, line_label, trigger, target, inval, alt),
            "start_i": pts[0]["i"], "end_i": pts[-1]["i"]}


def _line(rows: list[dict], label: str, a: tuple[int, float], b: tuple[int, float]) -> dict:
    return {"label": label, "points": [{"date": rows[a[0]]["date"], "price": round(a[1], 2)},
                                        {"date": rows[b[0]]["date"], "price": round(b[1], 2)}]}


def _kinds(sgn: int, size: int) -> list[str]:
    pk, tr = ("H", "L") if sgn > 0 else ("L", "H")
    return [pk if j % 2 == 0 else tr for j in range(size)]


# ---------------------------------------------------------------- detectors
def _tops(p, rows, closes, cfg, tf, sgn) -> list[dict]:
    """Double and triple tops (sgn +1) or bottoms (−1)."""
    out, n = [], len(closes)
    word = "トップ" if sgn > 0 else "ボトム"
    bias = DOWN if sgn > 0 else UP
    for size, key, name, tol in ((3, "double", "ダブル", TOL["top"]), (5, "triple", "トリプル", TOL["triple"])):
        for k in range(len(p) - size + 1):
            seg = p[k:k + size]
            if [q["kind"] for q in seg] != _kinds(sgn, size) or seg[-1]["i"] < n - 1 - cfg["recent"]:
                continue
            if any(b["i"] - a["i"] < cfg["min_gap"] for a, b in zip(seg, seg[1:])):
                continue
            tops, necks = [q["price"] for q in seg[0::2]], [q["price"] for q in seg[1::2]]
            if (max(tops) - min(tops)) / max(tops) > tol:
                continue
            if len(necks) > 1 and (max(necks) - min(necks)) / max(necks) > TOL["shoulder"]:
                continue
            neck = min(necks) if sgn > 0 else max(necks)
            avg = sum(tops) / len(tops)
            height = abs(avg - neck)
            if height / avg < cfg["depth"]:
                continue
            extreme = max(tops) if sgn > 0 else min(tops)
            target = neck - sgn * height
            status = _status(sgn, closes, seg[-1]["i"], lambda j, v=neck: v, extreme, target, cfg)
            if status is None:
                continue
            out.append(_mk(rows, tf, f"{key}_{'top' if sgn > 0 else 'bottom'}", f"{name}{word}", bias, status, seg,
                           [_line(rows, "ネックライン", (seg[1]["i"], neck), (n - 1, neck))], neck, target, extreme,
                           "ネックライン"))
    return out


def _head_shoulders(p, rows, closes, cfg, tf, sgn) -> list[dict]:
    out, n = [], len(closes)
    for k in range(len(p) - 4):
        seg = p[k:k + 5]
        if [q["kind"] for q in seg] != _kinds(sgn, 5) or seg[-1]["i"] < n - 1 - cfg["recent"]:
            continue
        if any(b["i"] - a["i"] < cfg["min_gap"] for a, b in zip(seg, seg[1:])):
            continue
        s1, t1, head, t2, s2 = seg
        if any(sgn * (head["price"] - s["price"]) / s["price"] < TOL["head"] for s in (s1, s2)):
            continue
        if abs(s1["price"] - s2["price"]) / max(s1["price"], s2["price"]) > TOL["shoulder"]:
            continue
        if abs(t1["price"] - t2["price"]) / max(t1["price"], t2["price"]) > TOL["shoulder"]:
            continue
        slope = (t2["price"] - t1["price"]) / (t2["i"] - t1["i"])

        def neck_at(j, t=t1, s=slope):
            return t["price"] + s * (j - t["i"])

        height = abs(head["price"] - neck_at(head["i"]))
        if height / head["price"] < cfg["depth"]:
            continue
        target = neck_at(s2["i"]) - sgn * height
        status = _status(sgn, closes, s2["i"], neck_at, head["price"], target, cfg)
        if status is None:
            continue
        top = sgn > 0
        out.append(_mk(rows, tf, "hs_top" if top else "hs_bottom",
                       "ヘッドアンドショルダー（三尊天井）" if top else "逆ヘッドアンドショルダー（逆三尊）",
                       DOWN if top else UP, status, seg,
                       [_line(rows, "ネックライン", (t1["i"], t1["price"]), (n - 1, neck_at(n - 1)))],
                       neck_at(n - 1), target, head["price"], "ネックライン"))
    return out


def _converging(p, rows, closes, cfg, tf) -> list[dict]:
    """Box, triangles and wedges from the last pivots' upper and lower lines."""
    n = len(closes)
    conf = [q for q in p if not q.get("provisional")]
    for size in (6, 5, 4):
        seg = conf[-size:]
        if len(seg) < 4 or seg[-1]["i"] < n - 1 - cfg["recent"] or seg[-1]["i"] - seg[0]["i"] < 3 * cfg["min_gap"]:
            continue
        hs, ls = [q for q in seg if q["kind"] == "H"], [q for q in seg if q["kind"] == "L"]
        if len(hs) < 2 or len(ls) < 2:
            continue
        (sh, bh), (sl, bl) = _fit(hs), _fit(ls)
        i0, span = seg[0]["i"], seg[-1]["i"] - seg[0]["i"]
        mean = sum(q["price"] for q in seg) / len(seg)

        def upper(j, s=sh, b=bh):
            return b + s * j

        def lower(j, s=sl, b=bl):
            return b + s * j
        w0, w1 = upper(i0) - lower(i0), upper(n - 1) - lower(n - 1)
        if w0 <= 0 or w1 <= 0:
            continue
        kind = lambda s: UP if s * span / mean > TOL["flat"] else DOWN if s * span / mean < -TOL["flat"] else FLAT  # noqa: E731
        hk, lk = kind(sh), kind(sl)
        ratio = w1 / w0
        found = None
        if hk == FLAT and lk == FLAT and 0.8 <= ratio <= 1.25 and w0 / mean >= cfg["depth"]:
            found = ("box", "ボックス（もみ合い）", FLAT)
        elif ratio <= 0.85:
            found = {(FLAT, UP): ("tri_asc", "上昇トライアングル", UP), (DOWN, FLAT): ("tri_desc", "下降トライアングル", DOWN),
                     (DOWN, UP): ("tri_sym", "対称トライアングル", FLAT), (UP, UP): ("wedge_rising", "上昇ウェッジ", DOWN),
                     (DOWN, DOWN): ("wedge_falling", "下降ウェッジ", UP)}.get((hk, lk))
        if not found:
            continue
        key, name, bias = found
        up_t, lo_t = upper(n - 1), lower(n - 1)
        brk = next(((j, UP if closes[j] > upper(j) else DOWN) for j in range(seg[-1]["i"], n)
                    if closes[j] > upper(j) or closes[j] < lower(j)), None)
        lines = [_line(rows, "上の線", (i0, upper(i0)), (n - 1, up_t)), _line(rows, "下の線", (i0, lower(i0)), (n - 1, lo_t))]
        if brk is None:
            status, direction = FORMING, bias
        else:
            j, direction = brk
            if n - 1 - j > cfg["break_recent"]:
                continue
            status = FAILED if bias not in (FLAT, direction) else DONE
        if status == FAILED:
            direction = bias
        if direction == FLAT:
            pat = _mk(rows, tf, key, name, FLAT, status, seg, lines, up_t, up_t + w0, None, "上の線",
                      alt={"trigger": lo_t, "target": lo_t - w0})
        elif direction == UP:
            pat = _mk(rows, tf, key, name, UP, status, seg, lines, up_t, up_t + w0, lo_t, "上の線")
        else:
            pat = _mk(rows, tf, key, name, DOWN, status, seg, lines, lo_t, lo_t - w0, up_t, "下の線")
        return [pat]
    return []


def _flags(p, rows, closes, cfg, tf, sgn) -> list[dict]:
    """A sharp move (the pole) then a shallow drift against it (the flag). sgn +1: after a rise; −1: after a fall."""
    n = len(closes)
    conf = [q for q in p if not q.get("provisional")]
    for a, b in zip(conf, conf[1:]):
        if [a["kind"], b["kind"]] != (["L", "H"] if sgn > 0 else ["H", "L"]):
            continue
        pole = sgn * (b["price"] - a["price"])
        if pole / a["price"] < cfg["pole"] or b["i"] - a["i"] > cfg["pole_bars"]:
            continue
        if b["i"] < n - 1 - cfg["recent"] or n - 1 - b["i"] < cfg["min_gap"]:
            continue
        after = closes[b["i"] + 1:]
        brk = next((j for j in range(b["i"] + 1, n) if sgn * closes[j] > sgn * b["price"]), None)
        drift = [c for c in after if sgn * c <= sgn * b["price"]]
        worst = min(drift) if sgn > 0 else max(drift)
        if sgn * (b["price"] - worst) > 0.5 * pole:
            continue
        inval = b["price"] - sgn * 0.5 * pole
        if brk is not None and n - 1 - brk > cfg["break_recent"]:
            continue
        if brk is not None and sgn * (max(after) if sgn > 0 else min(after)) >= sgn * (b["price"] + sgn * pole):
            continue
        status = FORMING if brk is None else DONE
        name = "ブルフラッグ" if sgn > 0 else "ベアフラッグ"
        return [_mk(rows, tf, "flag_bull" if sgn > 0 else "flag_bear", name, UP if sgn > 0 else DOWN, status,
                    [a, b], [_line(rows, "旗の上端" if sgn > 0 else "旗の下端", (b["i"], b["price"]), (n - 1, b["price"]))],
                    b["price"], b["price"] + sgn * pole, inval, "旗の" + ("上端" if sgn > 0 else "下端"))]
    return []


def _cups(p, rows, closes, cfg, tf) -> list[dict]:
    n = len(closes)
    out = []
    for k in range(len(p) - 2):
        a, b, c = p[k:k + 3]
        if [a["kind"], b["kind"], c["kind"]] != ["H", "L", "H"] or c["i"] < n - 1 - cfg["recent"]:
            continue
        rim = max(a["price"], c["price"])
        depth = (rim - b["price"]) / rim
        if c["i"] - a["i"] < cfg["cup_min"] or not cfg["cup_depth"][0] <= depth <= cfg["cup_depth"][1]:
            continue
        if abs(a["price"] - c["price"]) / rim > TOL["rim"] or not 0.5 <= (c["i"] - b["i"]) / (b["i"] - a["i"]) <= 2.0:
            continue
        after = closes[c["i"] + 1:]
        handle = min(after) if after else None
        if handle is not None and (c["price"] - handle) > 0.5 * (rim - b["price"]):
            continue
        has_handle = handle is not None and n - 1 - c["i"] >= cfg["min_gap"]
        inval = handle if has_handle else b["price"]
        target = rim + (rim - b["price"])
        if closes[-1] < inval:
            status = FAILED
        else:
            brk = next((j for j in range(c["i"] + 1, n) if closes[j] > rim), None)
            if brk is None:
                status = FORMING
            elif max(closes[brk:]) >= target or n - 1 - brk > cfg["break_recent"]:
                continue
            else:
                status = DONE
        out.append(_mk(rows, tf, "cup_handle", "カップウィズハンドル" if has_handle else "カップ", UP, status, [a, b, c],
                       [_line(rows, "リム（取っ手の上端）", (a["i"], rim), (n - 1, rim))], rim, target, inval, "リム"))
    return out


def _dedupe(found: list[dict]) -> list[dict]:
    """A double inside a triple/head-and-shoulders is dropped; one per key, the latest; at most MAX_SHOWN."""
    big = [{q["i"] for q in f["pivots"]} for f in found if f["key"].startswith(("triple", "hs_"))]
    keep: dict[str, dict] = {}
    for f in found:
        if f["key"].startswith("double") and any({q["i"] for q in f["pivots"]} <= b for b in big):
            continue
        if f["key"] not in keep or f["end_i"] > keep[f["key"]]["end_i"]:
            keep[f["key"]] = f
    return sorted(keep.values(), key=lambda f: -f["end_i"])[:MAX_SHOWN]


def detect(rows: list[dict], tf: str = DAILY, scale: float = 1.0) -> list[dict]:
    cfg = CONFIG[tf]
    if len(rows) < cfg["min_rows"]:
        return []
    closes = [r["close"] for r in rows]
    piv = zigzag(closes, cfg["zig"] * scale)
    found: list[dict] = []
    for sgn in (1, -1):
        found += _tops(piv, rows, closes, cfg, tf, sgn) + _head_shoulders(piv, rows, closes, cfg, tf, sgn)
        found += _flags(piv, rows, closes, cfg, tf, sgn)
    found += _converging(piv, rows, closes, cfg, tf) + _cups(piv, rows, closes, cfg, tf)
    return _dedupe(found)


# ---------------------------------------------------------------- past outcomes
def history(rows: list[dict], tf: str = DAILY) -> dict[str, dict]:
    """Past 完成 patterns of this stock: how often the price moved the pattern's way afterwards.

    A pattern's first sighting as 完成 is its confirmation; later bars give the return after the short and long horizon.
    """
    cfg = CONFIG[tf]
    n = len(rows)
    seen: dict[tuple, tuple[dict, int]] = {}
    for k in range(cfg["min_rows"], n + 1, cfg["stride"]):
        for p in detect(rows[max(0, k - cfg["window"]):k], tf):
            if p["status"] == DONE:
                seen.setdefault((p["key"], p["pivots"][0]["date"]), (p, k))
    short, long_ = cfg["after"]
    per: dict[str, dict] = {}
    for p, k in seen.values():
        if k - 1 + short > n - 1 or p["bias"] == FLAT:
            continue
        entry = rows[k - 1]["close"]
        ret = rows[k - 1 + short]["close"] / entry - 1
        window = rows[k:k + long_]
        reached = (max(r["high"] for r in window) >= p["target"] if p["bias"] == UP
                   else min(r["low"] for r in window) <= p["target"]) if window else False
        s = per.setdefault(p["key"], {"name": p["name"], "returns": [], "hits": 0, "reached": 0})
        s["returns"].append(ret)
        s["hits"] += (ret > 0) if p["bias"] == UP else (ret < 0)
        s["reached"] += reached
    out = {}
    for key, s in per.items():
        m = len(s["returns"])
        out[key] = {"name": s["name"], "n": m, "hit_rate": round(s["hits"] / m, 2),
                    "median_return": round(median(s["returns"]), 4), "target_rate": round(s["reached"] / m, 2),
                    "ref": m < MIN_SAMPLES, "after": short, "unit": cfg["unit"]}
    return out


# ---------------------------------------------------------------- entry
def analyze(rows: list[dict], tf: str = DAILY) -> dict:
    """{timeframe, patterns, stability, history}. A pattern is stable when it still appears with the zigzag threshold ×0.8 and ×1.25."""
    found = detect(rows, tf)
    others = [{p["key"] for p in detect(rows, tf, s)} for s in SENSITIVITY]
    hist = history(rows, tf) if found or len(rows) >= CONFIG[tf]["min_rows"] else {}
    for p in found:
        p["stable"] = all(p["key"] in o for o in others)
        p["history"] = hist.get(p["key"])
    label = NONE if not found else STABLE if all(p["stable"] for p in found) else UNSTABLE
    return {"timeframe": tf, "label": LABEL[tf], "patterns": found, "stability": label, "history": hist}
