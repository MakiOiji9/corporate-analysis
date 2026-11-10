"""Trading scenarios of the company report (参考): two or three prices at which buying could be considered, each with
its reason, stop, take-profit levels, downside / upside, the reward-to-risk ratio and what can go wrong there, plus
the levels a holder would watch.

Every price comes from the chart (cr_technicals' support and resistance lines, ATR) or from the valuation (the PER
range's cheap edge, the fair PBR): nothing is predicted. The entries are the current price, the nearest support and
the value prices below the market; prices within MERGE of each other are one entry with both reasons.
"""
from __future__ import annotations

MAX_ENTRIES = 3
MERGE = 0.03        # two candidate prices within 3% are one entry (both reasons shown)
BELOW = 0.99        # the next level below an entry is at least 1% under it
ABOVE = 1.01
NO_SUPPORT_ATR = 2  # without a line below, the stop is this many ATR under the entry
VALUE_LABELS = {"per_cheap": "PER が過去レンジの割安圏になる株価", "pbr_cheap": "適正PBR から2割安い株価"}
TAKE_LABELS = {"per_rich": "PER が過去レンジの割高圏になる株価", "pbr_rich": "適正PBR から2割高い株価"}
FAIR_LABEL = "適正PBR の株価"
LOW_52 = "52週安値"


def _role(line: dict, current: float) -> dict:
    """A past low above the price is now a ceiling, a past high below it a floor: the label says so."""
    label = line["label"]
    if label.startswith("直近の安値") and line["price"] > current:
        label = label.replace("直近の安値", "以前の安値", 1) + "（今は上値の抵抗になりやすい）"
    elif label.startswith("直近の高値") and line["price"] < current:
        label = label.replace("直近の高値", "以前の高値", 1) + "（今は下値の支えになりやすい）"
    return {**line, "label": label}


def _level(label: str, price: float) -> dict:
    return {"label": label, "price": round(price, 2)}


def _pct(a: float, b: float) -> float:
    return round((a / b - 1) * 100, 1)


def _candidates(t: dict, flips: dict) -> tuple[list[dict], str]:
    """[{label, price, basis, kind}] (current first) and a note on value prices already above the market."""
    current = t["current"]
    lines = t["levels"]["lines"]
    out = [{"label": "今の株価", "price": current, "basis": f"今の株価（{t.get('date') or '—'} 終値）", "kind": "now"}]
    supports = [x for x in lines if x["price"] < current * BELOW]
    if supports:
        s = max(supports, key=lambda x: x["price"])
        out.append({"label": s["label"], "price": s["price"], "basis": f"下の支持線（{s['label']}）", "kind": "support"})
    above = []
    for key, label in VALUE_LABELS.items():
        price = flips.get(key)
        if price is None:
            continue
        if price >= current:
            above.append(f"{label} {price:,.0f} より今の株価が安い（すでに割安圏）")
            continue
        out.append({"label": label, "price": price, "basis": f"{label}（バリュエーション）", "kind": "value"})
    return out, "。".join(above)


def _entries(t: dict, flips: dict) -> list[dict]:
    candidates, note = _candidates(t, flips)
    if note:
        candidates[0]["basis"] += "。" + note
    chosen: list[dict] = []
    for c in [candidates[0]] + sorted(candidates[1:], key=lambda c: -c["price"]):
        near = next((e for e in chosen if e["kind"] != "now" and abs(c["price"] / e["price"] - 1) <= MERGE), None)
        if near:  # one entry, both reasons; the lower price is the more cautious one
            chosen[chosen.index(near)] = {**near, "price": min(near["price"], c["price"]),
                                         "basis": f"{near['basis']} と {c['basis']}（{c['price']:,.0f}）が近い",
                                         "also": near.get("also", []) + [c["kind"]]}
        elif len(chosen) < MAX_ENTRIES:
            chosen.append(c)
    return chosen


def _stop(price: float, lines: list[dict], atr: float) -> dict:
    below = [x for x in lines if x["price"] < price * BELOW]
    if not below:
        return _level(f"買値の {NO_SUPPORT_ATR} ATR 下（下に支持線が無い）", price - NO_SUPPORT_ATR * atr)
    line = max(below, key=lambda x: x["price"])
    return _level(f"{line['label']}（{line['price']:,.0f}）の 1 ATR 下", line["price"] - atr)


def _distinct(levels: list[dict]) -> list[dict]:
    """Low to high, a level within MERGE of the one kept before it dropped (488 and 489 are one level)."""
    out: list[dict] = []
    for x in sorted(levels, key=lambda x: x["price"]):
        if not out or x["price"] > out[-1]["price"] * (1 + MERGE):
            out.append(x)
    return out


def _targets(price: float, lines: list[dict], flips: dict, atr: float) -> tuple[dict | None, dict | None]:
    """The first two distinct levels at least one ATR above the entry (a closer one is within a day's move)."""
    floor = max(price * ABOVE, price + atr)
    ups = [x for x in lines if x["price"] > floor]
    if flips.get("pbr_fair") and flips["pbr_fair"] > floor:
        ups.append({"label": FAIR_LABEL, "price": flips["pbr_fair"]})
    ups = _distinct(ups)
    first = ups[0] if ups else None
    second = ups[1] if len(ups) > 1 else None
    return (_level(first["label"], first["price"]) if first else None,
            _level(second["label"], second["price"]) if second else None)


def _risks(entry: dict, t: dict, context: dict, stop: dict) -> list[str]:
    out = []
    kinds = [entry["kind"], *entry.get("also", [])]
    if "now" in kinds:
        if "下降" in (t.get("state") or ""):
            out.append(f"株価は下降トレンドの途中で、損切りの目安（{stop['price']:,.0f}）まで下がる余地がある")
        elif "買われすぎ" in (t.get("state") or ""):
            out.append("短期に買われすぎで、反落しやすい位置")
        else:
            out.append(f"方向感が出ていない位置で、下の支持線を割ると損切りの目安（{stop['price']:,.0f}）まで下がりうる")
    if "support" in kinds:
        out.append(f"支持線（{entry['label']}）を終値で割り込むと、次の支持線まで下がりやすい")
    if "value" in kinds:
        out.append("割安圏の株価は予想EPS・BPS から計算している。業績予想の下方修正があると割安圏の株価そのものが下がる")
    if context.get("trend") == "下降トレンド":
        out.append("長期の株価も下降トレンド")
    if context.get("outlook") == "警戒":
        out.append(f"地合いが警戒（{context.get('week') or '—'} の週）で、市場全体の下げに巻き込まれやすい")
    if context.get("review"):
        out.append(f"次の決算（{context['review']}）で業績予想が変わると値動きが大きくなる")
    return out


def build(t: dict, flips: dict, context: dict) -> dict:
    """{ok, buys: [{label, price, basis, stop, target1, target2, down, up1, up2, rr, risks}], holder: {take, exit}}."""
    levels = (t or {}).get("levels") or {}
    if not (t or {}).get("ok") or not levels.get("atr") or not levels.get("lines"):
        return {"ok": False, "buys": [], "holder": {"take": [], "exit": []}}
    atr, current = levels["atr"], t["current"]
    lines = [_role(x, current) for x in levels["lines"]]
    t = {**t, "levels": {**levels, "lines": lines}}
    buys = []
    for e in _entries(t, flips or {}):
        stop = _stop(e["price"], lines, atr)
        first, second = _targets(e["price"], lines, flips or {}, atr)
        down = _pct(stop["price"], e["price"])
        up1 = _pct(first["price"], e["price"]) if first else None
        buys.append({"label": e["label"], "price": round(e["price"], 2), "basis": e["basis"], "stop": stop,
                     "target1": first, "target2": second, "down": down, "up1": up1,
                     "up2": _pct(second["price"], e["price"]) if second else None,
                     "rr": round(up1 / -down, 2) if up1 is not None and down < 0 else None,
                     "risks": _risks(e, t, context, stop)})
    floor = max(current * ABOVE, current + atr)
    take = [x for x in lines if x["price"] > floor]
    take += [{"label": label, "price": flips[key]} for key, label in TAKE_LABELS.items()
             if (flips or {}).get(key) and flips[key] > floor]
    take = _distinct(take)[:MAX_ENTRIES]
    exits = ([_level(f"損切りの目安（{levels['stop']['label']}）", levels["stop"]["price"])] if levels.get("stop") else [])
    low52 = next((x for x in lines if x["label"] == LOW_52), None)
    if low52 and all(abs(low52["price"] / x["price"] - 1) > MERGE for x in exits):
        exits.append(_level("52週安値を割る（1年の下値を更新）", low52["price"]))
    return {"ok": True, "buys": buys,
            "holder": {"take": [_level(x["label"], x["price"]) for x in take], "exit": exits}}
