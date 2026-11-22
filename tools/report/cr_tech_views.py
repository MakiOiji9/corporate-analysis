"""テクニカル分析の切り口ごとの見立て: トレンド・モメンタム・ボラティリティ・出来高・水準・パターン、そして総合。

Each aspect (切り口) stands on its own: state, evidence (each marked 順張り / 逆張り where it matters), outlook and
confidence. The overall view lists the aspects side by side, so a trend-following and a contrarian reading that cancel
each other stay visible, and builds three scenarios (強気・基本・弱気) with a trigger, a target and an invalidation price.
Nothing here feeds the 短期・中期 scores (cr_technicals does); the indicator functions are reused from there.

Moving averages: 25・75・200 days (daily), 13・26・52 weeks (weekly). Confidence 高/中/低 comes from how many pieces of
evidence there are and how well they agree, never from a feeling.
"""
from __future__ import annotations

import cr_patterns as P
import cr_technicals as T

MA = {P.DAILY: (25, 75, 200), P.WEEKLY: (13, 26, 52)}
SLOPE = {P.DAILY: 20, P.WEEKLY: 8}
CHART = {P.DAILY: 250, P.WEEKLY: 156}
YEAR = {P.DAILY: 250, P.WEEKLY: 52}
UNIT = {P.DAILY: "日", P.WEEKLY: "週"}  # one bar of the timeframe (ATR の値幅の単位)
RECENT = {P.DAILY: 60, P.WEEKLY: 26}      # the window of "recent high / low" and the OBV comparison
SHORT_VOL = {P.DAILY: 5, P.WEEKLY: 2}
STOCH = 14
FIBO = (0.382, 0.5, 0.618)
SQUEEZE, EXPAND = 20, 80                    # percentile of the band width
SAME = 0.015                                # levels within 1.5% of each other support each other
KEYS = ("trend", "momentum", "volatility", "volume", "levels", "pattern")
NAMES = {"trend": "トレンド", "momentum": "モメンタム（勢い）", "volatility": "ボラティリティ（値動きの大きさ）",
         "volume": "出来高", "levels": "水準（支持線・抵抗線）", "pattern": "チャートパターン"}
DIRECTIONAL = ("trend", "momentum", "volume", "pattern")
DIR_WORD = {P.UP: "上向き", P.DOWN: "下向き", P.FLAT: "中立", None: "判定できない"}
HIGH, MID, LOW = "高", "中", "低"
MIN_ROWS = 60


def _conf(votes: list[int]) -> str:
    nz = [v for v in votes if v]
    if len(nz) < 2:
        return LOW
    top = max(nz.count(1), nz.count(-1)) / len(nz)
    return HIGH if len(nz) >= 3 and top >= 0.8 else MID if top >= 0.6 else LOW


def _dir(total: int, need: int = 1) -> str:
    return P.UP if total >= need else P.DOWN if total <= -need else P.FLAT


def _aspect(key: str, state: str, direction: str | None, evidence: list[tuple[str, int, str]], outlook: str,
            confidence: str) -> dict:
    return {"key": key, "name": NAMES[key], "state": state, "direction": direction,
            "evidence": [{"text": t, "vote": v, "style": s} for t, v, s in evidence], "outlook": outlook,
            "confidence": confidence}


def _nodata(key: str, why: str) -> dict:
    return _aspect(key, f"判定できない（{why}）", None, [], "材料が足りないため見立てを出さない。", LOW)


# ---------------------------------------------------------------- trend
def _dow(piv: list[dict]) -> int:
    hs, ls = [q["price"] for q in piv if q["kind"] == "H"][-2:], [q["price"] for q in piv if q["kind"] == "L"][-2:]
    if len(hs) < 2 or len(ls) < 2:
        return 0
    return 1 if hs[1] > hs[0] and ls[1] > ls[0] else -1 if hs[1] < hs[0] and ls[1] < ls[0] else 0


def trend(rows: list[dict], tf: str, piv: list[dict]) -> dict:
    closes, dates = [r["close"] for r in rows], [r["date"] for r in rows]
    a, b, c = MA[tf]
    unit = "日" if tf == P.DAILY else "週"
    if len(rows) < c + SLOPE[tf]:
        return _nodata("trend", f"{c}{unit}線を出すだけの本数がない")
    mas = {n: T.sma(closes, n) for n in MA[tf]}
    close, (ma_a, ma_b, ma_c) = closes[-1], (mas[a][-1], mas[b][-1], mas[c][-1])
    slope = (ma_b / mas[b][-1 - SLOPE[tf]] - 1) * 100
    ev: list[tuple[str, int, str]] = []
    pos = sum(1 if close > m else -1 for m in (ma_a, ma_b, ma_c))
    ev.append((f"株価 {P.px(close)} は {a}{unit}線 {P.px(ma_a)}・{b}{unit}線 {P.px(ma_b)}・{c}{unit}線 {P.px(ma_c)} のうち"
               f"{sum(close > m for m in (ma_a, ma_b, ma_c))}本より上", 1 if pos >= 2 else -1 if pos <= -2 else 0, "順張り"))
    order = 1 if ma_a > ma_b > ma_c else -1 if ma_a < ma_b < ma_c else 0
    ev.append((f"{a}・{b}・{c}{unit}線は" + ("上から短い順に並ぶ（上昇の並び）" if order > 0 else
                                       "下から短い順に並ぶ（下降の並び）" if order < 0 else "並びがそろわない"), order, "順張り"))
    ev.append((f"{b}{unit}線の傾きは {SLOPE[tf]}{unit}前比 {slope:+.1f}%", 1 if slope > 1 else -1 if slope < -1 else 0, "順張り"))
    dow = _dow(piv)
    ev.append(("ダウ理論: " + ("高値・安値とも切り上がり（上昇トレンド）" if dow > 0 else
                          "高値・安値とも切り下がり（下降トレンド）" if dow < 0 else "高値・安値の向きがそろわない"), dow, "順張り"))
    cross = T.last_cross(T.sma(closes, a), T.sma(closes, b), dates, 60 if tf == P.DAILY else 26)
    if cross:
        ev.append((f"{a}{unit}線が{b}{unit}線を" + ("上抜けた（ゴールデンクロス）" if cross["kind"] == "golden" else
                                              "下抜けた（デッドクロス）") + f"（{cross['date']}）",
                   1 if cross["kind"] == "golden" else -1, "順張り"))
    votes = [v for _, v, _ in ev]
    d = _dir(sum(votes), 2)
    state = {P.UP: "上昇トレンド", P.DOWN: "下降トレンド", P.FLAT: "方向感のないもみ合い"}[d]
    outlook = {P.UP: f"上昇の流れが続きやすい形。{b}{unit}線 {P.px(ma_b)} を終値で割り込むと流れが変わりうる。",
               P.DOWN: f"下降の流れが続きやすい形。{b}{unit}線 {P.px(ma_b)} を終値で上回ると流れが変わりうる。",
               P.FLAT: f"向きが決まっていない。{a}{unit}線 {P.px(ma_a)} と {c}{unit}線 {P.px(ma_c)} のどちらに寄るかが焦点。"}[d]
    return _aspect("trend", state, d, ev, outlook, _conf(votes))


# ---------------------------------------------------------------- momentum
def _stochastic(rows: list[dict]) -> tuple[float, float] | None:
    if len(rows) < STOCH + 3:
        return None
    ks = []
    for i in range(len(rows) - 3, len(rows)):
        span = rows[i - STOCH + 1:i + 1]
        hi, lo = max(r["high"] for r in span), min(r["low"] for r in span)
        ks.append(50.0 if hi == lo else (rows[i]["close"] - lo) / (hi - lo) * 100)
    return ks[-1], sum(ks) / 3


def _divergence(closes: list[float], rsis: list, piv: list[dict]) -> int:
    """+1: price made a lower low but the RSI did not (bullish); −1: a higher high with a lower RSI (bearish)."""
    for kind, sign in (("H", -1), ("L", 1)):
        pts = [q for q in piv if q["kind"] == kind and rsis[q["i"]] is not None][-2:]
        if len(pts) == 2:
            a, b = pts
            if kind == "H" and b["price"] > a["price"] and rsis[b["i"]] < rsis[a["i"]] - 2:
                return -1
            if kind == "L" and b["price"] < a["price"] and rsis[b["i"]] > rsis[a["i"]] + 2:
                return 1
    return 0


def momentum(rows: list[dict], tf: str, piv: list[dict]) -> dict:
    closes = [r["close"] for r in rows]
    if len(rows) < 40:
        return _nodata("momentum", "40本に満たない")
    r = T.rsi(closes)[-1]
    line, signal, hist = T.macd(closes)
    ev: list[tuple[str, int, str]] = []
    if hist[-1] is not None and hist[-2] is not None:
        up = line[-1] > signal[-1]
        widening = abs(hist[-1]) > abs(hist[-2])
        ev.append((f"MACD は{'シグナルより上' if up else 'シグナルより下'}で、差は{'広がっている' if widening else '縮んでいる'}",
                   (1 if up else -1) * (1 if widening else 0), "順張り"))
    if r is not None:
        ev.append((f"RSI {r:.0f}" + ("（買われすぎ圏。逆張りでは下げを警戒）" if r >= T.RSI_HIGH else
                                    "（売られすぎ圏。逆張りでは反発を期待）" if r <= T.RSI_LOW else "（中立圏）"),
                   -1 if r >= T.RSI_HIGH else 1 if r <= T.RSI_LOW else 0, "逆張り"))
    st = _stochastic(rows)
    if st:
        k = st[0]
        ev.append((f"ストキャスティクス %K {k:.0f}・%D {st[1]:.0f}" + ("（買われすぎ圏）" if k >= 80 else "（売られすぎ圏）" if k <= 20 else "（中立圏）"),
                   -1 if k >= 80 else 1 if k <= 20 else 0, "逆張り"))
    div = _divergence(closes, T.rsi(closes), piv)
    if div:
        ev.append(("ダイバージェンス: " + ("株価が安値を切り下げたのに RSI は切り下げていない（下げの勢いが弱まっている）" if div > 0 else
                                     "株価が高値を切り上げたのに RSI は切り上げていない（上げの勢いが弱まっている）"), div, "逆張り"))
    follow = sum(v for _, v, s in ev if s == "順張り")
    contra = sum(v for _, v, s in ev if s == "逆張り")
    votes = [v for _, v, _ in ev]
    split = follow * contra < 0
    d = P.FLAT if split else _dir(follow + contra)
    parts = []
    if any(s == "順張り" and v for _, v, s in ev):
        parts.append("順張り系（MACD）は" + DIR_WORD[_dir(follow)])
    if any(s == "逆張り" and v for _, v, s in ev):
        parts.append("逆張り系（RSI・ストキャスティクス）は" + DIR_WORD[_dir(contra)])
    state = "、".join(parts) if parts else "目立った偏りはない"
    outlook = ("順張り系と逆張り系で向きが割れており、打ち消し合っている。勢いだけでは方向を決められない。" if split else
               {P.UP: "勢いは上向き。", P.DOWN: "勢いは下向き。", P.FLAT: "勢いに偏りはない。"}[d])
    ev_out = ev or [("勢いの指標が出せない", 0, "順張り")]
    return _aspect("momentum", state, d, ev_out, outlook, _conf(votes))


# ---------------------------------------------------------------- volatility
def volatility(rows: list[dict], tf: str) -> dict:
    closes = [r["close"] for r in rows]
    if len(rows) < T.BB_DAYS + 30:
        return _nodata("volatility", "本数が足りない")
    upper, lower = T.bollinger(closes)
    mid = T.sma(closes, T.BB_DAYS)
    widths = [(u - lo) / m for u, lo, m in zip(upper, lower, mid) if u is not None and m]
    hist = widths[-YEAR[tf]:]
    pct = sum(w <= widths[-1] for w in hist) / len(hist) * 100
    a = T.atr(rows)
    ev: list[tuple[str, int, str]] = [(f"ボリンジャーバンドの幅は直近 1 年の下位 {pct:.0f}% の位置", 0, "順張り")]
    if a:
        ev.append((f"ATR（1{UNIT[tf]}あたりの平均的な値幅）は {P.px(a)}、株価の {a / closes[-1] * 100:.1f}%", 0, "順張り"))
    if pct <= SQUEEZE:
        state, outlook = "収縮（スクイーズ）", "値動きが小さく縮んでいる。大きく動く前の静けさになりやすいが、向きは示さない。"
    elif pct >= EXPAND:
        state, outlook = "拡大", "値動きが大きく広がっている。荒れた相場で、損切り幅は広めに見る必要がある。"
    else:
        state, outlook = "通常", "値動きの大きさは平常。"
    return _aspect("volatility", state, P.FLAT, ev, outlook, MID if len(hist) >= 100 else LOW)


# ---------------------------------------------------------------- volume
def volume(rows: list[dict], tf: str) -> dict:
    vols = [r.get("volume") for r in rows]
    n = RECENT[tf]
    if len(rows) < n + 5 or any(v is None for v in vols[-n:]) or not sum(v or 0 for v in vols[-n:]):
        return _nodata("volume", "出来高のデータが足りない")
    k = SHORT_VOL[tf]
    ratio = (sum(vols[-k:]) / k) / (sum(vols[-n:]) / n)
    chg = rows[-1]["close"] / rows[-1 - k]["close"] - 1
    obv = [0.0]
    for p, r in zip(rows, rows[1:]):
        obv.append(obv[-1] + (r["volume"] or 0) * (1 if r["close"] > p["close"] else -1 if r["close"] < p["close"] else 0))
    ev: list[tuple[str, int, str]] = []
    word = "増えている" if ratio >= 1.2 else "減っている" if ratio <= 0.8 else "平常"
    vote = (1 if chg > 0 else -1) if ratio >= 1.2 and abs(chg) > 0.005 else 0
    ev.append((f"直近 {k}{'日' if tf == P.DAILY else '週'}の出来高は {n} 本平均の {ratio:.2f} 倍（{word}）"
               + ("で、値動きの向きに出来高が伴っている" if vote else ""), vote, "順張り"))
    obv_chg = obv[-1] - obv[-n]
    ev.append(("OBV（上げの日の出来高を足し、下げの日を引いた累計）は" + (f"過去 {n} 本で増加" if obv_chg > 0 else f"過去 {n} 本で減少"),
               1 if obv_chg > 0 else -1, "順張り"))
    window = rows[-n:]
    near_high = rows[-1]["close"] >= max(r["close"] for r in window) * 0.99
    near_low = rows[-1]["close"] <= min(r["close"] for r in window) * 1.01
    div = 0
    if near_high and obv[-1] < max(obv[-n:]) * 0.95 and max(obv[-n:]) > 0:
        div = -1
        ev.append(("株価は高値圏なのに OBV は高値を更新していない（上げに出来高が伴っていない）", -1, "逆張り"))
    elif near_low and obv[-1] > min(obv[-n:]) + abs(min(obv[-n:])) * 0.05 and obv[-1] > min(obv[-n:]):
        div = 1
        ev.append(("株価は安値圏なのに OBV は安値を更新していない（売りが続いていない）", 1, "逆張り"))
    votes = [v for _, v, _ in ev]
    d = _dir(sum(votes))
    state = {P.UP: "買いが優勢", P.DOWN: "売りが優勢", P.FLAT: "拮抗"}[d]
    outlook = {P.UP: "出来高は上げを支えている。", P.DOWN: "出来高は下げを裏づけている。", P.FLAT: "出来高からは向きを決められない。"}[d]
    return _aspect("volume", state, d, ev, outlook, _conf(votes))


# ---------------------------------------------------------------- levels
def _candidates(rows: list[dict], tf: str, piv: list[dict]) -> list[tuple[str, float]]:
    closes = [r["close"] for r in rows]
    n = RECENT[tf]
    out = [(f"直近 {n} 本の高値", max(r["high"] for r in rows[-n:])), (f"直近 {n} 本の安値", min(r["low"] for r in rows[-n:]))]
    y = rows[-YEAR[tf]:]
    out += [("52週高値", max(r["high"] for r in y)), ("52週安値", min(r["low"] for r in y))]
    unit = "日" if tf == P.DAILY else "週"
    for m in MA[tf][1:]:
        if len(closes) >= m:
            out.append((f"{m}{unit}線", T.sma(closes, m)[-1]))
    for q in [q for q in piv if not q.get("provisional")][-4:]:
        out.append(("直近の天井" if q["kind"] == "H" else "直近の底", q["price"]))
    if len(piv) >= 2:
        a, b = piv[-2], piv[-1]
        lo, hi = (a["price"], b["price"]) if a["kind"] == "L" else (b["price"], a["price"])
        for f in FIBO:
            price = hi - (hi - lo) * f if b["kind"] == "H" else lo + (hi - lo) * f
            out.append((f"フィボナッチ {f * 100:.1f}% 戻し", price))
    return out


def _cluster(items: list[tuple[str, float]], price: float, below: bool, count: int = 3) -> list[dict]:
    pool = sorted((v, k) for k, v in items if (v < price if below else v > price))
    if below:
        pool.reverse()
    levels: list[dict] = []
    for v, k in pool:
        if levels and abs(v - levels[-1]["price"]) / levels[-1]["price"] <= SAME:
            levels[-1]["labels"].append(k)
            continue
        levels.append({"price": round(v, 2), "labels": [k]})
    return levels[:count]


def levels(rows: list[dict], tf: str, piv: list[dict]) -> dict:
    if len(rows) < MIN_ROWS:
        return _nodata("levels", "本数が足りない")
    price = rows[-1]["close"]
    items = _candidates(rows, tf, piv)
    sup, res = _cluster(items, price, True), _cluster(items, price, False)
    ev: list[tuple[str, int, str]] = []
    for name, lst in (("支持線（下）", sup), ("抵抗線（上）", res)):
        for lv in lst[:2]:
            ev.append((f"{name} {P.px(lv['price'])}（{price and (lv['price'] / price - 1) * 100:+.1f}%）: " + "・".join(lv["labels"]), 0, "順張り"))
    near = sup[0] if sup else None
    conf = HIGH if near and len(near["labels"]) >= 3 else MID if near and len(near["labels"]) == 2 else LOW
    state = (f"支持線 {P.px(sup[0]['price'])}、抵抗線 {P.px(res[0]['price'])} の間" if sup and res else
             "上に目立った抵抗線がない（高値圏）" if sup else "下に目立った支持線がない（安値圏）")
    outlook = ("複数の根拠が重なる線ほど意識されやすい。" + (f"下は {P.px(sup[0]['price'])} 付近、上は {P.px(res[0]['price'])} 付近が目安。" if sup and res else ""))
    a = _aspect("levels", state, P.FLAT, ev, outlook, conf)
    a["supports"], a["resistances"] = sup, res
    return a


# ---------------------------------------------------------------- pattern
def pattern(pat: dict) -> dict:
    found = pat["patterns"]
    if not found:
        return _aspect("pattern", "確認できる形はない", P.FLAT, [("定義に当てはまる形は見つからない", 0, "順張り")],
                       "形がないことは、強気とも弱気とも言えない。", LOW)
    ev = [(f"{p['name']}（{p['status']}、{BIAS_WORD_LONG[p['bias']]}）", (1 if p["bias"] == P.UP else -1 if p["bias"] == P.DOWN else 0)
           if p["status"] == P.DONE else 0, "順張り") for p in found]
    main = next((p for p in found if p["status"] == P.DONE), found[0])
    d = main["bias"] if main["status"] == P.DONE else P.FLAT
    hist = main.get("history")
    score = bool(main.get("stable")) + bool(hist and not hist["ref"]) + (main["status"] == P.DONE)
    state = f"{main['name']}（{main['status']}）" + ("ほか" if len(found) > 1 else "")
    return _aspect("pattern", state, d, ev, main["sentence"], HIGH if score >= 3 else MID if score == 2 else LOW)


BIAS_WORD_LONG = {P.UP: "上昇につながる形", P.DOWN: "下落につながる形", P.FLAT: "どちらかに抜ける形"}


# ---------------------------------------------------------------- overall
def _share(count: int, n: int) -> str:
    if n < 3:
        return LOW
    r = count / n
    return HIGH if r >= 0.6 else MID if r >= 0.4 else LOW


def scenarios(aspects: dict, rows: list[dict], pat: dict) -> dict:
    price = rows[-1]["close"]
    lv = aspects["levels"]
    sup, res = lv.get("supports", []), lv.get("resistances", [])
    n = len([k for k in DIRECTIONAL if aspects[k]["direction"] is not None])
    cnt = {d: sum(aspects[k]["direction"] == d for k in DIRECTIONAL) for d in (P.UP, P.DOWN, P.FLAT)}
    up_pat = next((p for p in pat["patterns"] if p["bias"] == P.UP and p["status"] != P.FAILED), None)
    down_pat = next((p for p in pat["patterns"] if p["bias"] == P.DOWN and p["status"] != P.FAILED), None)
    a = T.atr(rows) or price * 0.03
    r1 = res[0]["price"] if res else round(max(r["high"] for r in rows[-RECENT[pat["timeframe"]]:]), 2)
    r2 = (up_pat["target"] if up_pat else res[1]["price"] if len(res) > 1 else round(r1 + 2 * a, 2))
    s1 = sup[0]["price"] if sup else round(min(r["low"] for r in rows[-RECENT[pat["timeframe"]]:]), 2)
    s2 = (down_pat["target"] if down_pat else sup[1]["price"] if len(sup) > 1 else round(s1 - 2 * a, 2))
    r2, s2 = (r2 if r2 > r1 else round(r1 + 2 * a, 2)), (s2 if s2 < s1 else round(s1 - 2 * a, 2))
    bull = {"name": "強気", "trigger": r1, "target": r2, "invalidation": s1, "confidence": _share(cnt[P.UP], n),
            "text": f"終値で {P.px(r1)} を上抜けると上昇に向かう形。目安は {P.px(r2)}。終値で {P.px(s1)} を割り込むと、この見方は崩れる。"}
    bear = {"name": "弱気", "trigger": s1, "target": s2, "invalidation": r1, "confidence": _share(cnt[P.DOWN], n),
            "text": f"終値で {P.px(s1)} を割り込むと下落に向かう形。目安は {P.px(s2)}。終値で {P.px(r1)} を上抜けると、この見方は崩れる。"}
    base = {"name": "基本（もみ合い）", "trigger": None, "target": None, "invalidation": None, "confidence": _share(cnt[P.FLAT], n),
            "text": f"{P.px(s1)} から {P.px(r1)} の範囲で推移し、どちらにも抜けない見方。"}
    order = sorted((bull, base, bear), key=lambda s: -{HIGH: 2, MID: 1, LOW: 0}[s["confidence"]])
    lead = order[0]["name"] if order[0]["confidence"] != LOW and (len(order) < 2 or order[0]["confidence"] != order[1]["confidence"]) else None
    return {"bull": bull, "base": base, "bear": bear, "leading": lead,
            "count": {"up": cnt[P.UP], "down": cnt[P.DOWN], "flat": cnt[P.FLAT], "judged": n}}


def overall(aspects: dict, rows: list[dict], pat: dict) -> dict:
    sc = scenarios(aspects, rows, pat)
    c = sc["count"]
    breakdown = [{"key": k, "name": aspects[k]["name"], "direction": aspects[k]["direction"], "state": aspects[k]["state"]}
                 for k in DIRECTIONAL]
    mixed = c["up"] > 0 and c["down"] > 0
    if c["judged"] < 3:
        head = "材料が足りず、総合の見立ては出さない。"
    elif mixed:
        head = (f"切り口ごとに向きが割れている（上向き {c['up']}・下向き {c['down']}・中立 {c['flat']}）。"
                "合算して「中立」に見えても、打ち消し合った結果なので、内訳を見て判断する。")
    elif c["up"] >= 2:
        head = f"{c['up']} つの切り口が上向きでそろい、逆向きはない。"
    elif c["down"] >= 2:
        head = f"{c['down']} つの切り口が下向きでそろい、逆向きはない。"
    else:
        head = "どの切り口も強い向きを示していない。"
    note = aspects["momentum"]["outlook"] if "割れて" in aspects["momentum"]["outlook"] else None
    return {"headline": head, "mixed": mixed, "breakdown": breakdown, "scenarios": sc, "momentum_note": note}


# ---------------------------------------------------------------- entry
def view(rows: list[dict], tf: str, pat: dict | None = None) -> dict:
    """One timeframe: aspects + overall + the series for the chart. pat is cr_patterns.analyze(rows, tf)."""
    pat = pat or P.analyze(rows, tf)
    out = {"timeframe": tf, "label": P.LABEL[tf], "ok": len(rows) >= MIN_ROWS, "date": rows[-1]["date"] if rows else None,
           "current": rows[-1]["close"] if rows else None, "patterns": pat}
    if not out["ok"]:
        out.update(aspects={}, overall=None, chart=None)
        return out
    piv = P.zigzag([r["close"] for r in rows], P.CONFIG[tf]["zig"] * 0.7)
    aspects = {"trend": trend(rows, tf, piv), "momentum": momentum(rows, tf, piv), "volatility": volatility(rows, tf),
               "volume": volume(rows, tf), "levels": levels(rows, tf, piv), "pattern": pattern(pat)}
    closes = [r["close"] for r in rows]
    start = max(0, len(rows) - CHART[tf])
    series = lambda vals: [[rows[i]["date"], round(vals[i], 2)] for i in range(start, len(rows)) if vals[i] is not None]  # noqa: E731
    out.update(aspects=aspects, overall=overall(aspects, rows, pat),
               chart={"close": series(closes), "mas": {f"{n}": series(T.sma(closes, n)) for n in MA[tf]},
                      "zigzag": [[rows[q["i"]]["date"], round(q["price"], 2)] for q in
                                 P.zigzag(closes, P.CONFIG[tf]["zig"]) if q["i"] >= start]})
    return out
