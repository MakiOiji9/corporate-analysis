"""The rule every valuation indicator shares (企業分析フレームワーク.md STEP 3「全指標共通：割安・割高の判定ルール」)
and the STEP 3 scoring.

  軸1 (過去レンジでの位置): (現在値 − 過去5年の最低値) ÷ (最高値 − 最低値); 33% 以下 割安圏 / 34〜66% 妥当圏 /
    67% 以上 割高圏 (the position is rounded to a whole percent; below the range counts as 割安圏, above as 割高圏).
    The range is the newest RANGE_YEARS years of yearly highs and lows; fewer than MIN_RANGE_YEARS -> 判定できない.
  軸2 (同業比較): the current value against the median of the peers (MIN_PEERS or more): 20% 以上低い 割安圏 /
    ±20% 以内 妥当圏 / 20% 以上高い 割高圏. 「成長率や利益率の差で説明できる」 is a proxy: a 割安圏 with the target's
    growth (or ROE) EXPLAIN_PT or more below the peers' median, or a 割高圏 with it EXPLAIN_PT or more above,
    goes back to 妥当圏.
  組み合わせ: the 3×3 table; with one axis only, that axis decides (片軸); with none -> 判定保留.
  STEP 3: 割安 +1 / 妥当 0 / 割高 −1 (評価対象外・判定保留 excluded); average >= +0.5 割安, <= −0.5 割高, else 妥当;
    fewer than MIN_SCORED indicators scored -> 判定保留.
"""
from __future__ import annotations

from statistics import median

LOW, FAIR, HIGH = "割安", "妥当", "割高"
NA, PENDING = "評価対象外", "判定保留"
ZONE = {LOW: "割安圏", FAIR: "妥当圏", HIGH: "割高圏"}
RANGE_YEARS, MIN_RANGE_YEARS = 5, 3
LOW_PCT, HIGH_PCT = 33, 67  # position (rounded %) <= 33 割安圏, >= 67 割高圏
PEER_BAND = 0.20
MIN_PEERS = 2
EXPLAIN_PT = 5.0
SCORE = {LOW: 1, FAIR: 0, HIGH: -1}
VERDICT_BAND = 0.5
MIN_SCORED = 2
BORDER_PCT = 5  # a position within 5pt of 33 / 67
BORDER_PEER = 0.05  # a peer difference within 5pt of ±20%
MATRIX = {(LOW, LOW): LOW, (LOW, FAIR): LOW, (LOW, HIGH): FAIR, (FAIR, LOW): LOW, (FAIR, FAIR): FAIR,
          (FAIR, HIGH): HIGH, (HIGH, LOW): FAIR, (HIGH, FAIR): HIGH, (HIGH, HIGH): HIGH}
CONFLICT = {(LOW, HIGH), (HIGH, LOW)}  # 妥当（要因を確認）
ORDER = (LOW, FAIR, HIGH)


def fmt(value: float | None, suffix: str = "倍", digits: int = 1) -> str:
    return "—" if value is None else f"{value:,.{digits}f}{suffix}"


# ---------- 軸1 ----------

def range_zone(current: float | None, history: list[tuple[str, float | None, float | None]]) -> dict:
    """history: (year, high, low) oldest first. {zone, position, low, high, years, basis}."""
    usable = [(y, h, lo) for y, h, lo in history if h is not None and lo is not None][-RANGE_YEARS:]
    out = {"zone": None, "position": None, "low": None, "high": None, "years": [y for y, _, _ in usable]}
    if current is None:
        return {**out, "basis": "現在値を計算できない"}
    if len(usable) < MIN_RANGE_YEARS:
        return {**out, "basis": f"過去レンジが{len(usable)}期分しかない（{MIN_RANGE_YEARS}期以上で判定）"}
    low, high = min(lo for _, _, lo in usable), max(h for _, h, _ in usable)
    if high <= low:
        return {**out, "low": low, "high": high, "basis": "過去レンジの最高値と最低値が同じ"}
    position = round((current - low) / (high - low) * 100)
    zone = LOW if position <= LOW_PCT else HIGH if position >= HIGH_PCT else FAIR
    span = f"{usable[0][0]}〜{usable[-1][0]} の {len(usable)} 期"
    return {**out, "zone": zone, "position": position, "low": low, "high": high,
            "basis": f"現在 {current:.1f}倍、{span}のレンジ {low:.1f}〜{high:.1f}倍で位置 {position}%（{ZONE[zone]}）"}


# ---------- 軸2 ----------

def _explained(raw: str, own: float | None, others: list[float], what: str) -> tuple[bool, str]:
    """Is a 割安圏 / 割高圏 explained by the growth (ROE) difference? (adjusted, note)."""
    if raw == FAIR or own is None or len(others) < MIN_PEERS:
        return False, ""
    gap = own - median(others)
    if raw == LOW and gap <= -EXPLAIN_PT:
        return True, f"{what}が同業の中央値より{-gap:.1f}pt 低く、低い倍率はその差で説明できるため妥当圏とする"
    if raw == HIGH and gap >= EXPLAIN_PT:
        return True, f"{what}が同業の中央値より{gap:.1f}pt 高く、高い倍率はその差で説明できるため妥当圏とする"
    return False, ""


def peer_zone(current: float | None, values: list[float], own_growth: float | None = None,
              peer_growths: tuple[float, ...] | list[float] = (), what: str = "売上高の3年CAGR") -> dict:
    """{zone, raw_zone, median, diff, count, explained, basis}."""
    values = [v for v in values if v is not None and v > 0]
    out = {"zone": None, "raw_zone": None, "median": None, "diff": None, "count": len(values), "explained": False}
    if current is None:
        return {**out, "basis": "現在値を計算できない"}
    if len(values) < MIN_PEERS:
        return {**out, "basis": f"比べられる同業が{len(values)}社（{MIN_PEERS}社以上で判定）"}
    mid = median(values)
    diff = round(current / mid - 1, 6)  # 8 ÷ 10 − 1 is −0.19999… in floating point: the boundary must hold
    raw = LOW if diff <= -PEER_BAND else HIGH if diff >= PEER_BAND else FAIR
    explained, note = _explained(raw, own_growth, [g for g in peer_growths if g is not None], what)
    zone = FAIR if explained else raw
    basis = f"同業 {len(values)} 社の中央値 {mid:.1f}倍に対して {diff * 100:+.0f}%（{ZONE[raw]}）" + (f"。{note}" if note else "")
    return {**out, "zone": zone, "raw_zone": raw, "median": mid, "diff": diff, "explained": explained, "basis": basis}


# ---------- 組み合わせ ----------

def combine(axis1: dict, axis2: dict) -> dict:
    """{rating, single_axis, check, basis}: the 3×3 table, or the one axis that could be judged."""
    z1, z2 = axis1["zone"], axis2["zone"]
    if z1 is None and z2 is None:
        return {"rating": PENDING, "single_axis": False, "check": False,
                "basis": f"過去レンジ（{axis1['basis']}）と同業比較（{axis2['basis']}）がどちらも判定できない"}
    if z1 is None or z2 is None:
        zone, which = (z2, "同業比較") if z1 is None else (z1, "過去レンジ")
        missing = axis1 if z1 is None else axis2
        return {"rating": zone, "single_axis": True, "check": False,
                "basis": f"{which}だけで判定（片軸。もう一方は{missing['basis']}）"}
    rating = MATRIX[(z1, z2)]
    check = (z1, z2) in CONFLICT
    note = "。軸が逆向きのため妥当（要因を確認）" if check else ""
    return {"rating": rating, "single_axis": False, "check": check,
            "basis": f"過去レンジ {ZONE[z1]} × 同業比較 {ZONE[z2]} → {rating}{note}"}


def common_rule(current: float | None, history: list[tuple[str, float | None, float | None]], peers: list[float],
                own_growth: float | None = None, peer_growths: tuple[float, ...] | list[float] = (),
                what: str = "売上高の3年CAGR") -> dict:
    axis1 = range_zone(current, history)
    axis2 = peer_zone(current, peers, own_growth, peer_growths, what)
    return {"axis1": axis1, "axis2": axis2, **combine(axis1, axis2)}


def borderline(name: str, rule: dict) -> list[str]:
    """Comparisons of the common rule close enough to a boundary to move one zone."""
    out = []
    pos = rule["axis1"]["position"]
    if pos is not None and any(abs(pos - b) <= BORDER_PCT for b in (LOW_PCT, HIGH_PCT)):
        out.append(f"{name}: 過去レンジでの位置 {pos}% が境界（{LOW_PCT}% / {HIGH_PCT}%）に近い")
    diff = rule["axis2"]["diff"]
    if diff is not None and abs(abs(diff) - PEER_BAND) <= BORDER_PEER:
        out.append(f"{name}: 同業の中央値との差 {diff * 100:+.0f}% が境界（±{PEER_BAND * 100:.0f}%）に近い")
    return out


def more_expensive(a: str, b: str) -> str:
    """The rating nearer to 割高 (the conservative one of two judgements)."""
    ranked = [r for r in (a, b) if r in ORDER]
    if not ranked:
        return a
    return max(ranked, key=ORDER.index)


# ---------- STEP 3 ----------

def score(ratings: dict[str, str]) -> dict:
    """{scores, average, verdict, basis} over the indicators' ratings (name -> rating)."""
    scored = {name: SCORE[r] for name, r in ratings.items() if r in SCORE}
    if len(scored) < MIN_SCORED:
        return {"scores": scored, "average": None, "verdict": PENDING,
                "basis": f"点数になった指標が{len(scored)}つ（{MIN_SCORED}つ以上で判定。材料不足・評価対象外が多い）"}
    average = sum(scored.values()) / len(scored)
    verdict = LOW if average >= VERDICT_BAND else HIGH if average <= -VERDICT_BAND else FAIR
    return {"scores": scored, "average": average, "verdict": verdict,
            "basis": f"{len(scored)} 指標の平均点 {average:+.2f}（+{VERDICT_BAND} 以上で割安、−{VERDICT_BAND} 以下で割高）"}
