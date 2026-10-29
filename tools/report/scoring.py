"""Candidate ratings for the three axes and the attention level (-> facts["scores"]).

The market is described, not forecast. Three axes, each a sum of small signals scored -1 / 0 / +1
by fixed thresholds (constants below; the skill document shows the same table). On every axis +1
points to the side that needs attention:

  金融環境 (money)    +1 = tightening pressure  -> 引き締め / 中立 / 緩和
  景気     (economy)  +1 = slowing              -> 減速 / 横ばい / 拡大
  市場のストレス (stress) +1 = more stress     -> 高い / 普通 / 低い

Total >= +2 gives the first label, <= -2 the last, otherwise the middle one. Hysteresis: an axis that
was at an end label last week keeps it until its total is back at 0. A monthly signal whose month
ended more than HALF_WEIGHT_DAYS before the report week counts half. A missing input scores 0.
The attention level (平常 / 注意 / 警戒) follows from the axes by attention(). Price momentum, flows
and valuation are reported as reference only (short-term reversals make them poor axis signals).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, replace

import store
from derived import Points, last, shifted, value_before

AXES = (("money", "金融環境", ("引き締め", "中立", "緩和")),
        ("economy", "景気", ("減速", "横ばい", "拡大")),
        ("stress", "市場のストレス", ("高い", "普通", "低い")))
AXIS_NAME = {key: name for key, name, _ in AXES}
AXIS_LABELS = {key: labels for key, _, labels in AXES}
CALM, WATCH, ALERT = "平常", "注意", "警戒"
ATTENTION_WORDS = (CALM, WATCH, ALERT)
THRESHOLD = 2
INDEX = {"japan": "JP_NIKKEI225", "us": "US_SP500"}
POLICY = {"japan": "JP_CALL", "us": "US_FFR_UPPER"}
TEN_YEAR = {"japan": "JP_JGB10Y", "us": "US_10Y"}
CORE_INFLATION = {"japan": ("JP_CPI_CORECORE_YOY", "CPI 生鮮食品・エネルギーを除く"),
                  "us": ("US_CORE_PCE_YOY", "コアPCE")}
UNEMPLOYMENT = {"japan": "JP_UNEMP", "us": "US_UNRATE"}

# 金融環境 (+1 = tightening pressure)
POLICY_DAYS, POLICY_STEP = 90, 0.10              # policy-rate change over 3 months, %pt
TEN_YEAR_MOVE = 0.30                             # 10-year yield over 1 month, %pt
REAL_TIGHT, REAL_EASY = 1.0, 0.0                 # real policy rate, %
REAL10_TIGHT, REAL10_EASY = 2.0, 0.5             # US 10-year TIPS yield, %
INFLATION_HIGH, INFLATION_LOW = 3.0, 1.5         # core inflation, % y/y
OIL_YOY_HIGH, OIL_YOY_LOW = 30.0, -30.0          # WTI year-on-year, %
# 景気 (+1 = slowing)
UNEMP_UP, UNEMP_DOWN, UNEMP_POINTS = 0.3, -0.2, 3
NFP_WEAK, NFP_STRONG, NFP_POINTS = 50.0, 150.0, 3   # thousand, 3-month average
CI_POINTS = 3
RETAIL_WEAK, RETAIL_STRONG = 0.0, 3.0
INDPRO_WEAK, INDPRO_STRONG = 0.0, 1.0
# 市場のストレス (+1 = more stress)
HY_MONTH_UP, HY_MONTH_DOWN, HY_PCTL_HIGH, HY_PCTL_LOW = 0.50, -0.30, 80.0, 20.0
IG_MONTH_UP, IG_MONTH_DOWN, IG_DAYS = 0.20, -0.10, 30
VIX_HIGH, VIX_LOW = 25.0, 15.0
RV_HIGH = {"japan": 28.0, "us": 25.0}            # 20-day realised volatility, % a year
RV_LOW = {"japan": 14.0, "us": 12.0}
DRAWDOWN_HIGH, DRAWDOWN_LOW = -10.0, -3.0        # % below the 1-year high
# reference only
MA_BAND = 2.0
EPS = 1e-9
HALF_WEIGHT_DAYS = 45   # a monthly figure whose month ended this long before the report week counts half


@dataclass(frozen=True)
class Signal:
    name: str
    value: str        # what was seen, as shown in the brief
    rule: str         # the thresholds (+1 = the side that needs attention)
    score: int
    available: bool = True
    date: str | None = None   # the data point's date, for signals built on monthly figures
    weight: float = 1.0       # 0.5 when that month ended HALF_WEIGHT_DAYS before (score_market sets it)

    @property
    def points(self) -> float:
        return self.score * self.weight


def missing(name: str, rule: str) -> Signal:
    return Signal(name, "—（未取得または時点が古い）", rule, 0, available=False)


def three_way(up: bool, down: bool) -> int:
    """+1 toward the attention side, -1 away from it."""
    return 1 if up else (-1 if down else 0)


def fmt(value: float, decimals: int = 1, unit: str = "") -> str:
    return f"{value:+.{decimals}f}{unit}".replace("-", "−")


def total_text(total: float) -> str:
    """'+2' / '−1.5' / '+0' as shown in the brief, outlook 8. and the slides."""
    if abs(total) < EPS:
        return "+0"
    text = f"{total:+.0f}" if float(total).is_integer() else f"{total:+.1f}"
    return text.replace("-", "−")


@dataclass(frozen=True)
class Inputs:
    """What the signals read: KPI tiles and derived items by id, transformed series by id.
    The caller leaves out stale series and KPIs, so every signal treats them as missing."""
    kpis: dict[str, dict]
    derived: dict[str, dict]
    series: dict[str, Points]
    asof: str | None = None   # the report week's Monday (or the backtest date) for the half weight

    def derived_value(self, did: str) -> float | None:
        d = self.derived.get(did)
        return None if not d or d["value"] is None or d.get("stale") else d["value"]


def change_over(points: Points, steps: int) -> tuple[float, float] | None:
    if len(points) <= steps:
        return None
    return points[-1 - steps][1], points[-1][1]


def month_change(points: Points, days: int) -> tuple[tuple[str, float], tuple[str, float]] | None:
    now = last(points)
    before = value_before(points, shifted(now[0], days)) if now else None
    return (before, now) if now and before else None


# ---------------------------------------------------------------- 金融環境

def policy_signal(market: str, data: Inputs) -> Signal:
    name = "政策金利の3か月の変化"
    rule = f"{POLICY_DAYS}日で +{POLICY_STEP:g} を超える引き上げで +1、引き下げで −1"
    pair = month_change(data.series.get(POLICY[market], []), POLICY_DAYS)
    if not pair:
        return missing(name, rule)
    (_, a), (_, b) = pair
    return Signal(name, f"{a:.2f} → {b:.2f}%", rule, three_way(b - a > POLICY_STEP, b - a < -POLICY_STEP))


def ten_year_signal(market: str, data: Inputs) -> Signal:
    name = "10年債利回りの1か月の変化"
    rule = f"1か月で +{TEN_YEAR_MOVE:g} 以上で +1、−{TEN_YEAR_MOVE:g} 以下で −1"
    month = (data.kpis.get(TEN_YEAR[market], {}).get("changes") or {}).get("1m")
    if not month:
        return missing(name, rule)
    d = month["delta"]
    return Signal(name, fmt(d, 2), rule, three_way(d >= TEN_YEAR_MOVE - EPS, d <= -TEN_YEAR_MOVE + EPS))


def real_policy_signal(market: str, data: Inputs) -> Signal:
    name = "実質政策金利"
    rule = f"> {REAL_TIGHT:g}% で +1（引き締め的）、< {REAL_EASY:g}% で −1（緩和的）"
    real = data.derived_value("JP_REAL_POLICY" if market == "japan" else "US_REAL_POLICY")
    if real is None:
        return missing(name, rule)
    real = round(real, 2)
    return Signal(name, fmt(real, 2, "%"), rule, three_way(real > REAL_TIGHT, real < REAL_EASY))


def real10_signal(data: Inputs) -> Signal:
    name = "実質10年金利（TIPS）"
    rule = f"> {REAL10_TIGHT:g}% で +1、< {REAL10_EASY:g}% で −1"
    p = last(data.series.get("US_REAL10Y", []))
    if not p:
        return missing(name, rule)
    v = round(p[1], 2)
    return Signal(name, f"{v:.2f}%（{p[0]}）", rule, three_way(v > REAL10_TIGHT, v < REAL10_EASY))


def inflation_signal(market: str, data: Inputs) -> Signal:
    sid, label = CORE_INFLATION[market]
    name = f"基調インフレ（{label}）"
    rule = f"≥ {INFLATION_HIGH:g}% で +1（引き締め圧力）、< {INFLATION_LOW:g}% で −1"
    p = last(data.series.get(sid, []))
    if not p:
        return missing(name, rule)
    v = round(p[1], 1)  # the brief shows one decimal; judge the number the reader sees
    return Signal(name, f"{v:.1f}%（{p[0][:7]}）", rule, three_way(v >= INFLATION_HIGH, v < INFLATION_LOW),
                  date=p[0])


def oil_signal(data: Inputs) -> Signal:
    """WTI against a year earlier: a large rise adds to inflation pressure in both markets."""
    name = "原油（WTI）の前年比"
    rule = f"≥ +{OIL_YOY_HIGH:g}% で +1（物価の上振れ圧力）、≤ {OIL_YOY_LOW:g}% で −1"
    pts = data.series.get("US_WTI", [])
    now = last(pts)
    before = value_before(pts, store._shift(now[0], years=-1)) if now else None
    if not now or not before or before[1] <= 0 or before[0] < store._shift(now[0], years=-1, days=-10):
        return missing(name, rule)
    yoy = round((now[1] / before[1] - 1) * 100, 1)
    return Signal(name, f"{fmt(yoy, 1, '%')}（{now[1]:.2f}ドル、{now[0]}）", rule,
                  three_way(yoy >= OIL_YOY_HIGH, yoy <= OIL_YOY_LOW))


def money_signals(market: str, data: Inputs) -> list[Signal]:
    out = [policy_signal(market, data), ten_year_signal(market, data), real_policy_signal(market, data),
           inflation_signal(market, data), oil_signal(data)]
    return out + [real10_signal(data)] if market == "us" else out


# ---------------------------------------------------------------- 景気

def unemployment_signal(market: str, data: Inputs) -> Signal:
    name = "失業率の3か月の変化"
    rule = f"{UNEMP_POINTS}か月で +{UNEMP_UP:g} 以上で +1、{UNEMP_DOWN:g} 以下で −1"
    pts = data.series.get(UNEMPLOYMENT[market], [])
    pair = change_over(pts, UNEMP_POINTS)
    if not pair:
        return missing(name, rule)
    delta = pair[1] - pair[0]
    return Signal(name, f"{pair[0]:.1f} → {pair[1]:.1f}%（{pts[-1][0][:7]}）", rule,
                  three_way(delta >= UNEMP_UP - EPS, delta <= UNEMP_DOWN + EPS), date=pts[-1][0])


def three_month_signal(sid: str, name: str, data: Inputs) -> Signal:
    rule = f"{CI_POINTS}か月で低下なら +1、上昇なら −1"
    pts = data.series.get(sid, [])
    pair = change_over(pts, CI_POINTS)
    if not pair:
        return missing(f"{name}の3か月の変化", rule)
    delta = pair[1] - pair[0]
    return Signal(f"{name}の3か月の変化", f"{pair[0]:.1f} → {pair[1]:.1f}（{pts[-1][0][:7]}）", rule,
                  three_way(delta < 0, delta > 0), date=pts[-1][0])


def level_signal(name: str, sid: str, data: Inputs, weak: float, strong: float, unit: str) -> Signal:
    rule = f"< {weak:g}{unit} で +1、> {strong:g}{unit} で −1"
    p = last(data.series.get(sid, []))
    if not p:
        return missing(name, rule)
    v = round(p[1], 1)  # judge the number the reader sees
    return Signal(name, f"{v:.1f}{unit}（{p[0][:7]}）", rule, three_way(v < weak, v > strong), date=p[0])


def payroll_signal(data: Inputs) -> Signal:
    name = "雇用者数前月差の3か月平均"
    rule = f"{NFP_POINTS}か月平均 < {NFP_WEAK:g}千人で +1、> {NFP_STRONG:g}千人で −1"
    pts = data.series.get("US_NFP_CHANGE", [])
    if len(pts) < NFP_POINTS:
        return missing(name, rule)
    avg = round(sum(v for _, v in pts[-NFP_POINTS:]) / NFP_POINTS)
    return Signal(name, f"{avg:.0f}千人（{pts[-1][0][:7]}まで）", rule, three_way(avg < NFP_WEAK, avg > NFP_STRONG),
                  date=pts[-1][0])


def economy_signals(market: str, data: Inputs) -> list[Signal]:
    out = [unemployment_signal(market, data)]
    if market == "us":
        return out + [payroll_signal(data),
                      level_signal("小売売上高（前年比）", "US_RETAIL_YOY", data, RETAIL_WEAK, RETAIL_STRONG, "%"),
                      level_signal("鉱工業生産（前年比）", "US_INDPRO_YOY", data, INDPRO_WEAK, INDPRO_STRONG, "%")]
    return out + [three_month_signal("JP_CI_COINCIDENT", "景気動向指数 一致", data),
                  three_month_signal("JP_CI_LEADING", "景気動向指数 先行", data),
                  three_month_signal("JP_IIP", "鉱工業生産", data)]


# ---------------------------------------------------------------- 市場のストレス

def hy_signal(data: Inputs) -> Signal:
    name = "HY スプレッド（米国。日米共通の信用指標）"
    rule = (f"1か月で +{HY_MONTH_UP:g} 以上または5年での位置 ≥ {HY_PCTL_HIGH:g}% で +1、"
            f"1か月で {HY_MONTH_DOWN:g} 以下かつ位置 ≤ {HY_PCTL_LOW:g}% で −1")
    month = (data.kpis.get("US_HY_OAS", {}).get("changes") or {}).get("1m")
    if not month:
        return missing(name, rule)
    pctl = data.derived_value("US_HY_OAS_PCTL")
    delta = month["delta"]
    wide = delta >= HY_MONTH_UP - EPS or (pctl is not None and pctl >= HY_PCTL_HIGH)
    tight = delta <= HY_MONTH_DOWN + EPS and pctl is not None and pctl <= HY_PCTL_LOW
    seen = f"1か月 {fmt(delta, 2)}" + (f"、5年での位置 {pctl:.0f}%" if pctl is not None else "")
    return Signal(name, seen, rule, three_way(wide, tight))


def ig_signal(data: Inputs) -> Signal:
    name = "投資適格社債スプレッド"
    rule = f"1か月で +{IG_MONTH_UP:g} 以上で +1、{IG_MONTH_DOWN:g} 以下で −1"
    pair = month_change(data.series.get("US_IG_OAS", []), IG_DAYS)
    if not pair:
        return missing(name, rule)
    (_, a), (_, b) = pair
    delta = b - a
    return Signal(name, f"{b:.2f}（1か月 {fmt(delta, 2)}）", rule,
                  three_way(delta >= IG_MONTH_UP - EPS, delta <= IG_MONTH_DOWN + EPS))


def vix_signal(data: Inputs) -> Signal:
    name = "VIX"
    rule = f"≥ {VIX_HIGH:g} で +1、≤ {VIX_LOW:g} で −1（日米共通のリスク指標）"
    vix = data.kpis.get("US_VIX", {}).get("value")
    if vix is None:
        return missing(name, rule)
    return Signal(name, f"{vix:.1f}", rule, three_way(vix >= VIX_HIGH, vix <= VIX_LOW))


def rv_signal(market: str, data: Inputs) -> Signal:
    name = "指数の値動きの大きさ（20日の実現変動率）"
    hi, lo = RV_HIGH[market], RV_LOW[market]
    rule = f"> {hi:g}% で +1、< {lo:g}% で −1（年率）"
    rv = data.derived_value(f"{INDEX[market]}_RV20")
    if rv is None:
        return missing(name, rule)
    rv = round(rv, 1)
    return Signal(name, f"{rv:.1f}%", rule, three_way(rv > hi, rv < lo))


def drawdown_signal(market: str, data: Inputs) -> Signal:
    name = "1年高値からの下落"
    rule = f"≤ {DRAWDOWN_HIGH:g}% で +1、≥ {DRAWDOWN_LOW:g}% で −1"
    fh = data.kpis.get(INDEX[market], {}).get("from_high")
    if fh is None:
        return missing(name, rule)
    return Signal(name, fmt(fh, 1, "%"), rule, three_way(fh <= DRAWDOWN_HIGH + EPS, fh >= DRAWDOWN_LOW - EPS))


def stress_signals(market: str, data: Inputs) -> list[Signal]:
    out = [hy_signal(data)]
    if market == "us":
        out.append(ig_signal(data))
    return out + [vix_signal(data), rv_signal(market, data), drawdown_signal(market, data)]


# ---------------------------------------------------------------- reference (not scored)

def reference(market: str, data: Inputs) -> list[dict]:
    """Price momentum, flows and valuation: shown with the axes, never added to them."""
    k = data.kpis.get(INDEX[market], {})
    changes = k.get("changes") or {}
    out = []

    def add(name: str, value: str | None) -> None:
        out.append({"name": name, "value": value or "—（未取得）"})

    month, year = changes.get("1m"), changes.get("1y")
    add("1か月の騰落率", fmt(month["delta"], 1, "%") if month else None)
    add("12か月の騰落率", fmt(year["delta"], 1, "%") if year else None)
    gap = data.derived_value(f"{INDEX[market]}_MA200")
    trend = None
    if gap is not None:
        trend = f"{fmt(gap, 1, '%')}（{'上昇基調' if gap > MA_BAND else '下落基調' if gap < -MA_BAND else '横ばい'}）"
    add("200日移動平均からの乖離", trend)
    run = k.get("streak", 0)
    add("週末値の連続", (f"{abs(run)}週連続{'上昇' if run > 0 else '低下'}" if run else "なし")
        if k.get("value") is not None else None)
    if market == "japan":
        pts = data.series.get("JP_FLOW_FOREIGN", [])
        add("海外投資家の売買差引", f"{pts[-1][1]:,.0f} 億円".replace("-", "−") + f"（{pts[-1][0]} 週）" if pts else None)
    else:
        pts = data.series.get("US_COT_ES_NET", [])
        add("CFTC 非商業部門ネット", f"{pts[-1][1]:,.0f} 枚".replace("-", "−") + f"（{pts[-1][0]}）" if pts else None)
        per = data.derived_value("US_PER_VS_10Y_AVG")
        add("予想PER − 10年平均", fmt(per, 1, "倍") if per is not None else None)
    yg = data.derived_value("JP_YIELD_GAP" if market == "japan" else "US_YIELD_GAP")
    add("益利回り − 10年債利回り", fmt(yg, 2, "%ポイント") if yg is not None else None)
    return out


# ---------------------------------------------------------------- ratings and the attention level

SIGNALS = {"money": money_signals, "economy": economy_signals, "stress": stress_signals}


def weighted(signals: list[Signal], asof: str | None) -> list[Signal]:
    """Half weight for a monthly signal whose month ended more than HALF_WEIGHT_DAYS before asof.
    The age runs from the month end (the stored date is the 1st), so a figure for September counts
    in full through mid-November, while an August figure read in late October counts half."""
    if not asof:
        return signals
    return [replace(s, weight=0.5) if s.date and age_days(month_end(s.date), asof) > HALF_WEIGHT_DAYS else s
            for s in signals]


def month_end(date: str) -> str:
    d = dt.date.fromisoformat(date)
    nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return (nxt - dt.timedelta(days=1)).isoformat()


def age_days(date: str, asof: str) -> int:
    return (dt.date.fromisoformat(asof) - dt.date.fromisoformat(date)).days


def rate(total: float, previous: str | None, labels: tuple[str, str, str]) -> tuple[str, bool]:
    """(label, hysteresis applied). labels = (attention side, middle, other side).
    Entering an end label needs ±THRESHOLD; leaving it needs the total back at 0."""
    up, middle, down = labels
    raw = up if total >= THRESHOLD else (down if total <= -THRESHOLD else middle)
    if raw == middle and previous == up and total > 0:
        return up, True
    if raw == middle and previous == down and total < 0:
        return down, True
    return raw, False


def attention(ratings: dict[str, str]) -> str:
    """平常 / 注意 / 警戒 from the three axis labels; every combination is covered."""
    tight = ratings.get("money") == AXIS_LABELS["money"][0]
    slowing = ratings.get("economy") == AXIS_LABELS["economy"][0]
    stressed = ratings.get("stress") == AXIS_LABELS["stress"][0]
    if stressed or (tight and slowing):
        return ALERT
    if tight or slowing:
        return WATCH
    return CALM


def score_market(market: str, data: Inputs, previous: dict[str, str] | None) -> dict:
    axes = []
    for key, name, labels in AXES:
        signals = weighted(SIGNALS[key](market, data), data.asof)
        total = round(sum(s.points for s in signals), 2)
        before = (previous or {}).get(key)
        rating, held = rate(total, before, labels)
        axes.append({"key": key, "name": name, "total": total, "rating": rating, "held": held, "previous": before,
                     "signals": [{**asdict(s), "points": s.points} for s in signals],
                     "missing": [s.name for s in signals if not s.available]})
    return {"axes": axes, "candidate": attention({a["key"]: a["rating"] for a in axes}),
            "reference": reference(market, data)}


def build_scores(data: Inputs, previous: dict[str, dict[str, str]] | None) -> dict[str, dict]:
    """previous: {market: {"money": label, ...}} adopted last week (judgment.json), or None."""
    return {m: score_market(m, data, (previous or {}).get(m)) for m in ("japan", "us")}
