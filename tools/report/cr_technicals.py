"""テクニカル分析: daily prices -> trend, momentum, position, volume, reference price levels and a state word.

Pure functions on cr_prices.load() rows ({date, high, low, close, volume} oldest first). Every threshold is a
constant here, and the score replaces the report's old 株価の位置・勢い factor (cr_factors.price_factor):
  trend     13週(65)・26週(130)・52週(260) moving averages: close > 13週 > 26週 > 52週 with the 26週 line rising
            over TREND_SLOPE_DAYS +1, the reverse order with it falling −1, otherwise 0
  momentum  RSI(14, Wilder) ≤ 30 +1 (売られすぎ), ≥ 70 −1 (買われすぎ), plus half a point in the direction of the
            MACD(12, 26, 9) histogram when it is widening; clipped to ±1
  position  52週レンジの位置 ≤ 33% +1 / ≥ 67% −1, averaged with the gap to the 26週 line (beyond ±15% −1)
  score     the average of the three (a part without enough days is left out)
Volume (20日/60日 average ratio) and the Bollinger band (20, ±2σ) are shown, not scored.

The reference levels (押し目・利益確定・損切りの目安) are prices taken from the chart (moving averages, swing
highs/lows, the band, ATR): conditions to watch, not forecasts or advice. The state word comes from a fixed table.
"""
from __future__ import annotations

import datetime as dt
import math
import re

MA_SHORT, MA_MID, MA_LONG = 65, 130, 260  # 13週・26週・52週 in trading days
MA_LABELS = {MA_SHORT: "13週線", MA_MID: "26週線", MA_LONG: "52週線"}
TREND_SLOPE_DAYS = 20
CROSS_LOOKBACK = 60
RSI_DAYS, RSI_LOW, RSI_HIGH = 14, 30.0, 70.0
PULLBACK_RSI = 45.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 9
MACD_CROSS_LOOKBACK = 20
MACD_WEIGHT = 0.5
BB_DAYS, BB_WIDTH = 20, 2.0
ATR_DAYS = 14
VOLUME_SHORT, VOLUME_LONG = 20, 60
VOLUME_HIGH, VOLUME_LOW = 1.5, 0.67
YEAR_DAYS = 365
LOW_ZONE, TOP_ZONE = 33.0, 67.0
MA_GAP_LIMIT = 15.0
SWING_LOOKBACK, SWING_SIDE = 120, 5
LEVELS_SHOWN = 2
SAME_LEVEL = 0.001  # levels within 0.1% of each other are one level
CHART_DAYS = 250

UP_TREND, DOWN_TREND, RANGE = "上昇トレンド", "下降トレンド", "もみ合い"
NO_DATA = "判定不能（株価の日数が足りない）"
LOW_52 = "52週安値"
TABLE_LABELS = ("状態", "押し目の目安（下の支持線）", "利益確定の目安（上の抵抗線）", "損切りの目安", "シグナル")
ROW = re.compile(r"^\| (" + "|".join(TABLE_LABELS) + r") \|.*$", re.M)
# a forecast of the price reaching a level (「2,000円まで上がる。」), not a condition (「2,000円まで下がったら」);
# outlook.FORBIDDEN covers the advice words
FORECAST = re.compile(r"\d[\d,.]*\s*(?:円|ドル)\s*(?:まで|に|を)\s*(?:上がる|下がる|戻る|上昇する|下落する|到達する)"
                      r"(?:見込み|だろう|と予想|と予測|。|$)", re.M)


# ---------------------------------------------------------------- indicators (lists aligned with the rows)

def sma(values: list[float], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    total = 0.0
    for i, v in enumerate(values):
        total += v
        if i >= n:
            total -= values[i - n]
        if i >= n - 1:
            out[i] = total / n
    return out


def ema(values: list[float], n: int) -> list[float | None]:
    """Exponential moving average seeded with the simple average of the first n values."""
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    k = 2 / (n + 1)
    prev = sum(values[:n]) / n
    out[n - 1] = prev
    for i in range(n, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(closes: list[float], n: int = RSI_DAYS) -> list[float | None]:
    """Wilder's RSI (smoothed average gain / loss)."""
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= n:
        return out
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gain = sum(max(c, 0) for c in changes[:n]) / n
    loss = sum(max(-c, 0) for c in changes[:n]) / n

    def value(g: float, lo: float) -> float:
        return 100.0 if lo == 0 else 100 - 100 / (1 + g / lo)

    out[n] = value(gain, loss)
    for i in range(n + 1, len(closes)):
        c = changes[i - 1]
        gain = (gain * (n - 1) + max(c, 0)) / n
        loss = (loss * (n - 1) + max(-c, 0)) / n
        out[i] = value(gain, loss)
    return out


def macd(closes: list[float]) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """(MACD line, signal line, histogram)."""
    fast, slow = ema(closes, MACD_FAST), ema(closes, MACD_SLOW)
    line = [f - s if f is not None and s is not None else None for f, s in zip(fast, slow)]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    signal: list[float | None] = [None] * start + ema([v for v in line[start:] if v is not None], MACD_SIGNAL)
    hist = [m - s if m is not None and s is not None else None for m, s in zip(line, signal)]
    return line, signal, hist


def bollinger(closes: list[float], n: int = BB_DAYS, width: float = BB_WIDTH) -> tuple[list, list]:
    """(upper, lower) with the population standard deviation."""
    mid = sma(closes, n)
    upper: list[float | None] = [None] * len(closes)
    lower: list[float | None] = [None] * len(closes)
    for i in range(n - 1, len(closes)):
        window = closes[i - n + 1:i + 1]
        sd = math.sqrt(sum((c - mid[i]) ** 2 for c in window) / n)
        upper[i], lower[i] = mid[i] + width * sd, mid[i] - width * sd
    return upper, lower


def atr(rows: list[dict], n: int = ATR_DAYS) -> float | None:
    """Wilder's average true range at the last row."""
    if len(rows) <= n:
        return None
    trs = [max(r["high"] - r["low"], abs(r["high"] - p["close"]), abs(r["low"] - p["close"]))
           for p, r in zip(rows, rows[1:])]
    value = sum(trs[:n]) / n
    for tr in trs[n:]:
        value = (value * (n - 1) + tr) / n
    return value


def swings(rows: list[dict], lookback: int = SWING_LOOKBACK, side: int = SWING_SIDE) -> tuple[list, list]:
    """Swing highs and lows of the last `lookback` rows: a bar whose high (low) is the extreme of `side` bars on
    each side. Returns ([(date, high)], [(date, low)]) oldest first."""
    start = max(side, len(rows) - lookback)
    highs, lows = [], []
    for i in range(start, len(rows) - side):
        span = rows[i - side:i + side + 1]
        if rows[i]["high"] == max(r["high"] for r in span):
            highs.append((rows[i]["date"], rows[i]["high"]))
        if rows[i]["low"] == min(r["low"] for r in span):
            lows.append((rows[i]["date"], rows[i]["low"]))
    return highs, lows


def last_cross(fast: list[float | None], slow: list[float | None], dates: list[str], lookback: int) -> dict | None:
    """The newest crossing of fast over (golden) or under (dead) slow within the last `lookback` rows."""
    for i in range(len(fast) - 1, max(len(fast) - lookback, 1) - 1, -1):
        a0, b0, a1, b1 = fast[i - 1], slow[i - 1], fast[i], slow[i]
        if None in (a0, b0, a1, b1):
            return None
        if a0 <= b0 and a1 > b1:
            return {"kind": "golden", "date": dates[i]}
        if a0 >= b0 and a1 < b1:
            return {"kind": "dead", "date": dates[i]}
    return None


# ---------------------------------------------------------------- parts

def _pct(a: float, b: float | None) -> float | None:
    return round((a / b - 1) * 100, 1) if b else None


def _round(v: float | None, d: int = 2) -> float | None:
    return round(v, d) if v is not None else None


def trend_part(closes: list[float], mas: dict[int, list], dates: list[str]) -> dict:
    s, m, lg = (mas[n][-1] for n in (MA_SHORT, MA_MID, MA_LONG))
    cross = last_cross(mas[MA_SHORT], mas[MA_MID], dates, CROSS_LOOKBACK)
    if None in (s, m, lg) or len(closes) < MA_LONG + TREND_SLOPE_DAYS:
        return {"score": None, "order": None, "slope": None, "cross": cross, "value": "トレンド 不明（1年分の株価が無い）"}
    slope = _pct(m, mas[MA_MID][-1 - TREND_SLOPE_DAYS])
    close = closes[-1]
    if close > s > m > lg and slope > 0:
        score, order = 1.0, "上昇の並び（株価 > 13週線 > 26週線 > 52週線）"
    elif close < s < m < lg and slope < 0:
        score, order = -1.0, "下降の並び（株価 < 13週線 < 26週線 < 52週線）"
    else:
        score, order = 0.0, "移動平均の並びがそろわない"
    return {"score": score, "order": order, "slope": slope, "cross": cross,
            "value": f"{order}、26週線の傾き {slope:+.1f}%（{TREND_SLOPE_DAYS}営業日前比）"}


def momentum_part(closes: list[float], dates: list[str]) -> dict:
    r = rsi(closes)[-1]
    if r is None:
        return {"score": None, "rsi": None, "rsi_word": None, "macd": None, "value": "勢い 不明（株価の日数が足りない）"}
    line, signal, hist = macd(closes)
    h0, h1 = hist[-2] if len(hist) > 1 else None, hist[-1]
    macd_dir = 0.0
    if h0 is not None and h1 is not None:
        macd_dir = 1.0 if h1 > 0 and h1 > h0 else -1.0 if h1 < 0 and h1 < h0 else 0.0
    rsi_score = 1.0 if r <= RSI_LOW else -1.0 if r >= RSI_HIGH else 0.0
    rsi_word = "売られすぎ" if r <= RSI_LOW else "買われすぎ" if r >= RSI_HIGH else "中立"
    macd_word = ("上向きに拡大" if macd_dir > 0 else "下向きに拡大" if macd_dir < 0
                 else "方向感なし" if h1 is not None else "不明")
    return {"score": max(-1.0, min(1.0, rsi_score + MACD_WEIGHT * macd_dir)), "rsi": round(r, 1),
            "rsi_word": rsi_word,
            "macd": {"line": _round(line[-1]), "signal": _round(signal[-1]), "hist": _round(h1), "word": macd_word,
                     "cross": last_cross(line, signal, dates, MACD_CROSS_LOOKBACK)},
            "value": f"RSI {r:.0f}（{rsi_word}）、MACD のヒストグラム {macd_word}"}


def year_range(rows: list[dict]) -> tuple[float, float]:
    """(high, low) of the last 365 days."""
    start = (dt.date.fromisoformat(rows[-1]["date"]) - dt.timedelta(days=YEAR_DAYS)).isoformat()
    span = [r for r in rows if r["date"] > start]
    return max(r["high"] for r in span), min(r["low"] for r in span)


def position_part(rows: list[dict], ma_mid: float | None) -> dict:
    hi, lo = year_range(rows)
    close = rows[-1]["close"]
    pos = 50.0 if hi == lo else max(0.0, min(100.0, (close - lo) / (hi - lo) * 100))
    gap = _pct(close, ma_mid)
    parts = [1.0 if pos <= LOW_ZONE else -1.0 if pos >= TOP_ZONE else 0.0]
    if gap is not None:
        parts.append(-1.0 if abs(gap) > MA_GAP_LIMIT else 0.0)
    value = f"52週レンジの位置 {pos:.0f}%" + (f"、26週線との差 {gap:+.1f}%" if gap is not None else "")
    return {"score": sum(parts) / len(parts), "position": round(pos, 1), "gap": gap, "value": value}


def volume_part(rows: list[dict]) -> dict:
    vols = [r.get("volume") for r in rows[-VOLUME_LONG:]]
    if len(vols) < VOLUME_LONG or any(v is None for v in vols) or not sum(vols):
        return {"ratio": None, "word": "不明", "value": "出来高 不明"}
    ratio = (sum(vols[-VOLUME_SHORT:]) / VOLUME_SHORT) / (sum(vols) / VOLUME_LONG)
    word = "増加" if ratio >= VOLUME_HIGH else "減少" if ratio <= VOLUME_LOW else "平常"
    return {"ratio": round(ratio, 2), "word": word,
            "value": f"出来高 {ratio:.2f}倍（{VOLUME_SHORT}日平均÷{VOLUME_LONG}日平均、{word}）"}


# ---------------------------------------------------------------- levels and state

def _level(label: str, price: float, current: float) -> dict:
    return {"label": label, "price": round(price, 2), "gap": _pct(price, current)}


def _nearest(items: list[tuple[str, float]], current: float, below: bool) -> list[dict]:
    out: list[dict] = []
    for label, price in sorted(items, key=lambda x: x[1], reverse=below):
        if all(abs(price / o["price"] - 1) > SAME_LEVEL for o in out):
            out.append(_level(label, price, current))
    return out[:LEVELS_SHOWN]


def levels(rows: list[dict], mas: dict[int, list], upper: float | None, atr_value: float | None) -> dict:
    """Supports below and resistances above the close (nearest first) and a stop level."""
    current = rows[-1]["close"]
    highs, lows = swings(rows)
    hi52, lo52 = year_range(rows)
    below = [(MA_LABELS[n], mas[n][-1]) for n in (MA_MID, MA_LONG) if mas[n][-1] is not None]
    below += [(f"直近の安値（{d}）", p) for d, p in lows] + [(LOW_52, lo52)]
    above = [(f"直近の高値（{d}）", p) for d, p in highs] + [("52週高値", hi52)]
    if upper is not None:
        above.append(("ボリンジャーバンド +2σ", upper))
    supports = _nearest([x for x in below if x[1] < current], current, below=True)
    resistances = _nearest([x for x in above if x[1] > current], current, below=False)
    stop = None
    if supports and atr_value:
        # 1 ATR under the nearest support, but not under the 52-week low unless that low is the support itself
        support = supports[0]
        price, label = support["price"] - atr_value, f"{support['label']}の 1 ATR 下"
        if support["label"] != LOW_52 and price < lo52:
            price, label = lo52, LOW_52
        stop = {**_level(label, price, current),
                "basis": f"最も近い支持線から1日の平均的な値幅（ATR {atr_value:,.0f}）だけ下。"
                         "52週安値が支持線でなければ、52週安値より下にはしない"}
    elif atr_value:
        stop = {**_level("株価の 2 ATR 下", current - 2 * atr_value, current), "basis": "下に支持線が無いため"}
    # every line, low to high: the trading scenarios look for the next one below / above any entry price
    lines = [{"label": label, "price": round(price, 2)} for label, price in sorted(below + above, key=lambda x: x[1])]
    return {"supports": supports, "resistances": resistances, "stop": stop, "atr": _round(atr_value),
            "lines": lines}


def state(trend: dict, momentum: dict, close: float, ma_short: float | None) -> str:
    t, r = trend.get("score"), momentum.get("rsi")
    if t is None or r is None:
        return NO_DATA
    if t > 0:
        if r >= RSI_HIGH:
            return f"{UP_TREND}・買われすぎ"
        if r <= PULLBACK_RSI or (ma_short is not None and close < ma_short):
            return f"{UP_TREND}中の押し目"
        return UP_TREND
    if t < 0:
        if r <= RSI_LOW:
            return f"{DOWN_TREND}・売られすぎ"
        if ma_short is not None and close > ma_short:
            return f"{DOWN_TREND}中の戻り"
        return DOWN_TREND
    if r >= RSI_HIGH:
        return f"{RANGE}・買われすぎ"
    if r <= RSI_LOW:
        return f"{RANGE}・売られすぎ"
    return f"{RANGE}（方向感なし）"


def signals(trend: dict, momentum: dict, close: float, band: tuple, volume: dict) -> list[str]:
    out = []
    cross = trend.get("cross")
    if cross:
        word = "ゴールデンクロス（13週線が26週線を上抜け）" if cross["kind"] == "golden" else \
            "デッドクロス（13週線が26週線を下抜け）"
        out.append(f"{word} {cross['date']}")
    mc = (momentum.get("macd") or {}).get("cross")
    if mc:
        out.append(f"MACD がシグナル線を{'上抜け' if mc['kind'] == 'golden' else '下抜け'} {mc['date']}")
    if momentum.get("rsi_word") in ("売られすぎ", "買われすぎ"):
        out.append(f"RSI {momentum['rsi']:.0f}（{momentum['rsi_word']}）")
    upper, lower = band
    if upper is not None and close > upper:
        out.append("株価がボリンジャーバンド +2σ の上（短期の過熱）")
    if lower is not None and close < lower:
        out.append("株価がボリンジャーバンド −2σ の下（短期の売られすぎ）")
    if volume.get("word") in ("増加", "減少"):
        out.append(volume["value"])
    return out


# ---------------------------------------------------------------- evaluate

def _series(dates: list[str], values: list) -> list[list]:
    return [[d, round(v, 2)] for d, v in zip(dates, values) if v is not None]


def _chart(dates: list[str], closes: list[float], mas: dict, upper: list, lower: list, hist: list) -> dict:
    """The last CHART_DAYS rows of each line the report draws."""
    tail = slice(-CHART_DAYS, None)
    d = dates[tail]
    return {"close": _series(d, closes[tail]), "ma_short": _series(d, mas[MA_SHORT][tail]),
            "ma_mid": _series(d, mas[MA_MID][tail]), "bb_upper": _series(d, upper[tail]),
            "bb_lower": _series(d, lower[tail]), "rsi": _series(d, rsi(closes)[tail]),
            "macd_hist": _series(d, hist[tail])}


def evaluate(rows: list[dict]) -> dict:
    """Everything the report shows about the chart; ok is False when there are no rows."""
    if not rows:
        return {"ok": False, "state": NO_DATA, "score": None}
    closes = [r["close"] for r in rows]
    dates = [r["date"] for r in rows]
    mas = {n: sma(closes, n) for n in (MA_SHORT, MA_MID, MA_LONG)}
    upper, lower = bollinger(closes)
    trend = trend_part(closes, mas, dates)
    momentum = momentum_part(closes, dates)
    position = position_part(rows, mas[MA_MID][-1])
    volume = volume_part(rows)
    parts = [p["score"] for p in (trend, momentum, position) if p["score"] is not None]
    close = closes[-1]
    band = None
    if upper[-1] is not None and upper[-1] != lower[-1]:
        band = {"upper": round(upper[-1], 2), "lower": round(lower[-1], 2),
                "percent_b": round((close - lower[-1]) / (upper[-1] - lower[-1]) * 100, 1)}
    return {
        "ok": True, "date": dates[-1], "current": close,
        "score": round(sum(parts) / len(parts), 3) if parts else None,
        "state": state(trend, momentum, close, mas[MA_SHORT][-1]),
        "trend": trend, "momentum": momentum, "position": position, "volume": volume, "band": band,
        "averages": {MA_LABELS[n]: _round(mas[n][-1]) for n in mas},
        "levels": levels(rows, mas, upper[-1], atr(rows)),
        "signals": signals(trend, momentum, close, (upper[-1], lower[-1]), volume),
        "chart": _chart(dates, closes, mas, upper, lower, macd(closes)[2]),
    }


def value_text(t: dict) -> str:
    """The horizon factor's value: the state word and the three scored parts."""
    if not t.get("ok"):
        return "不明（株価の時系列が無い）"
    return f"{t['state']}。" + "、".join(t[k]["value"] for k in ("trend", "momentum", "position"))


REASON = (f"トレンド（移動平均の並びと26週線の傾き ±1）・勢い（RSI {RSI_LOW:.0f} 以下 +1・{RSI_HIGH:.0f} 以上 −1、"
          f"MACD の向きで ±{MACD_WEIGHT}）・位置（52週レンジ {LOW_ZONE:.0f}% 以下 +1・{TOP_ZONE:.0f}% 以上 −1、"
          f"26週線との差 ±{MA_GAP_LIMIT:.0f}% 超 −1）の平均")


# ---------------------------------------------------------------- md (6章) and build checks

def _levels_text(items: list[dict]) -> str:
    return "、".join(f"{x['label']} {x['price']:,.0f}（{x['gap']:+.1f}%）" for x in items) or "—"


def table_rows(t: dict) -> str:
    """The md's 6章 table rows (script-owned, like the conclusion table)."""
    if not t.get("ok"):
        return "\n".join(f"| {label} | {NO_DATA if label == '状態' else '—'} |" for label in TABLE_LABELS)
    lv, stop = t["levels"], t["levels"].get("stop")
    score = f"（テクニカル点数 {t['score']:+.2f}）" if t["score"] is not None else ""
    cells = (f"{t['state']}{score}", _levels_text(lv["supports"]), _levels_text(lv["resistances"]),
             f"{stop['label']} {stop['price']:,.0f}（{stop['gap']:+.1f}%）" if stop else "—",
             "、".join(t["signals"]) or "なし")
    return "\n".join(f"| {label} | {cell.replace('|', '／')} |" for label, cell in zip(TABLE_LABELS, cells))


def alignment(t: dict, long_verdict: str | None) -> str | None:
    """A sentence when the chart and the long-term verdict point different ways (the writer must mention it)."""
    if not t.get("ok") or t["state"] == NO_DATA:
        return None
    up = t["state"].startswith(UP_TREND)
    down = t["state"].startswith(DOWN_TREND)
    if up and long_verdict == "見送り":
        return "チャートは上向きだが、長期の判定は見送り。テクニカルの目安は値動きの参考で、事業・財務の判定は変えない"
    if down and long_verdict == "投資検討":
        return "長期の判定は投資検討だが、チャートは下向き。事業・財務の判定とは別に、値動きは弱い"
    return None


def positioning_lines(positioning: dict | None) -> list[str]:
    """The 需給 sentence (cr_positioning.summarize) and its notes, for the brief."""
    if not positioning:
        return []
    return [f"- {positioning['text']}"] + [f"  - 注目: {n}" for n in positioning.get("notes") or []]


def brief_lines(t: dict, long_verdict: str | None, positioning: dict | None = None) -> list[str]:
    lines = ["## 4.1 テクニカル（md 6章の材料。状態・点数・水準はスクリプトが決めた。変えない）", ""]
    if not t.get("ok") or t["state"] == NO_DATA:
        return lines + [f"- {NO_DATA}。6.1 は「テクニカルの目安は出せない（株価の日数が足りない）」と1文で書く"] \
            + positioning_lines(positioning) + [""]
    lv, band, vol = t["levels"], t.get("band") or {}, t["volume"]
    stop = lv.get("stop")
    lines += [f"- 状態: **{t['state']}**（テクニカル点数 {t['score']:+.2f}。短期・中期の「株価のテクニカル」の点数）",
              f"- トレンド: {t['trend']['value']}", f"- 勢い: {t['momentum']['value']}",
              f"- 位置: {t['position']['value']}",
              "- 移動平均: " + "、".join(f"{k} {v:,.0f}" for k, v in t["averages"].items() if v is not None),
              "- ボリンジャーバンド（20日、±2σ）: " + (f"上 {band['upper']:,.0f}・下 {band['lower']:,.0f}、%b {band['percent_b']:.0f}%"
                                                  if band else "—"),
              f"- {vol['value']}",
              f"- シグナル: {'、'.join(t['signals']) or 'なし'}", *positioning_lines(positioning), "",
              "### 参考水準（条件の目安。予想ではない）", "",
              f"- 押し目の目安（下の支持線。近い順）: {_levels_text(lv['supports'])}",
              f"- 利益確定の目安（上の抵抗線。近い順）: {_levels_text(lv['resistances'])}",
              (f"- 損切りの目安: {stop['label']} {stop['price']:,.0f}（{stop['gap']:+.1f}%）。{stop['basis']}" if stop
               else "- 損切りの目安: —")]
    note = alignment(t, long_verdict)
    if note:
        lines += ["", f"- **長期の判定との関係（6.1 で必ず触れる）**: {note}"]
    lines += ["", "- 6.1 の書き方: 「今の状態は〈状態〉。」で書き始め、決め手の指標を値と一緒に1つ以上。目安の水準は"
              "「〜を下回ったら」「〜に近づいたら」の条件形で書く（「〜円まで上がる」のような到達の予想、推奨の語は書かない）", ""]
    return lines


def state_head(t: dict) -> str:
    """The part of the state word the 6.1 text must contain (「上昇トレンド中の押し目」 -> 「上昇トレンド」)."""
    return re.split(r"[・（中]", t["state"])[0]


def validate(text: str, table_text: str, t: dict) -> list[str]:
    issues = []
    got = [line.strip() for line in table_text.splitlines() if ROW.match(line.strip())]
    if got != table_rows(t).splitlines():
        issues.append("6章のテクニカルの表がスクリプトの値と違う（表は変更しない。元に戻す）")
    if t.get("ok") and t["state"] != NO_DATA and text.strip() and state_head(t) not in text:
        issues.append(f"6.1 に今の状態（{t['state']}）が無い（状態から書き始める）")
    found = FORECAST.search(text)
    if found:
        issues.append(f"6.1: 株価の到達を予想する書き方をしない（「{found.group(0)}」）。「〜を下回ったら」の条件形で書く")
    return issues
