"""Candidate ratings for the four viewpoints and the overall judgement (-> facts["scores"]).

Each viewpoint adds small signals scored -1 / 0 / +1 by fixed thresholds (constants below; the
skill document shows the same table). Total <= -2 is 逆風, >= +2 is 追い風, otherwise 中立.
Hysteresis: a viewpoint that was 逆風 (追い風) last week keeps it until the total reaches 0.
A signal whose input is missing scores 0 and is listed as missing, never guessed.
The writer adopts the candidates or overrides one with a reason; build re-applies combine().
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, replace

import store
from derived import Points, last, shifted, value_before

HEAD, NEUTRAL, TAIL = "追い風", "中立", "逆風"
RATINGS = (HEAD, NEUTRAL, TAIL)
THRESHOLD = 2
VIEWPOINTS = (("1", "① 株価・需給"), ("2", "② 金利・金融政策"), ("3", "③ マクロ"),
              ("4", "④ バリュエーション・センチメント"))
INDEX = {"japan": "JP_NIKKEI225", "us": "US_SP500"}
POLICY = {"japan": "JP_CALL", "us": "US_FFR_UPPER"}
TEN_YEAR = {"japan": "JP_JGB10Y", "us": "US_10Y"}
CORE_INFLATION = {"japan": ("JP_CPI_CORECORE_YOY", "CPI 生鮮食品・エネルギーを除く"),
                  "us": ("US_CORE_PCE_YOY", "コアPCE")}
UNEMPLOYMENT = {"japan": "JP_UNEMP", "us": "US_UNRATE"}

# ① equity and flows
FROM_HIGH_BAD, FROM_HIGH_GOOD = -10.0, -3.0      # % below the 1-year high
MONTH_BAD, MONTH_GOOD = -5.0, 5.0                # 1-month change, %
STREAK_WEEKS = 3                                 # weekly closes in a row
MA_BAND = 2.0                                    # % around the 200-day average
COT_WEEKS, COT_CHANGE = 4, 0.10                  # CFTC net vs 4 weeks before, share of |net|
# ② rates and policy
POLICY_DAYS, POLICY_STEP = 90, 0.10              # policy-rate change over 3 months, %pt
TEN_YEAR_MOVE = 0.30                             # 10-year yield over 1 month, %pt
REAL_TIGHT, REAL_EASY = 1.0, 0.0                 # real policy rate, %
# ③ macro
INFLATION_BAND, INFLATION_HIGH, INFLATION_LOW = (1.5, 2.5), 3.0, 0.5
UNEMP_UP, UNEMP_DOWN, UNEMP_POINTS = 0.3, -0.2, 3
NFP_WEAK, NFP_STRONG, NFP_POINTS = 50.0, 150.0, 3   # thousand, 3-month average
CI_POINTS = 3
RETAIL_GOOD, RETAIL_BAD = 3.0, 0.0
INDPRO_GOOD, INDPRO_BAD = 1.0, 0.0
# ④ valuation and sentiment
PER_GAP = 1.0                                    # forward P/E vs its 10-year average, times
YIELD_GAP_LOW, YIELD_GAP_HIGH = 1.0, 3.0         # earnings yield - 10-year yield, %pt
HY_MONTH_UP, HY_MONTH_DOWN, HY_PCTL_HIGH, HY_PCTL_LOW = 0.50, -0.30, 80.0, 20.0
IG_MONTH_UP, IG_MONTH_DOWN, IG_DAYS = 0.20, -0.10, 30   # investment-grade spread over 1 month, %pt
VIX_HIGH, VIX_LOW = 25.0, 15.0
OIL_YOY_HIGH, OIL_YOY_LOW = 30.0, -30.0           # WTI year-on-year, % (③ for both markets)
EPS = 1e-9                                       # float tolerance at the thresholds
HALF_WEIGHT_DAYS = 45   # a monthly figure whose month ended this long before the report week counts half
DIVERGENCE_NOTE = "株と信用のずれ（HY スプレッドが逆風の信号なので ① を追い風から中立に下げた）"


@dataclass(frozen=True)
class Signal:
    name: str
    value: str        # what was seen, as shown in the brief
    rule: str         # the thresholds
    score: int
    available: bool = True
    date: str | None = None   # the data point's date, for signals built on monthly / quarterly figures
    weight: float = 1.0       # 0.5 when that point is HALF_WEIGHT_DAYS old (score_market sets it)

    @property
    def points(self) -> float:
        return self.score * self.weight


def total_text(total: float) -> str:
    """'+2' / '−1.5' / '+0' as shown in the brief, outlook 8. and the slides."""
    if abs(total) < EPS:
        return "+0"
    text = f"{total:+.0f}" if float(total).is_integer() else f"{total:+.1f}"
    return text.replace("-", "−")


def missing(name: str, rule: str) -> Signal:
    return Signal(name, "—（未取得または時点が古い）", rule, 0, available=False)


def three_way(value: float, bad: bool, good: bool) -> int:
    return -1 if bad else (1 if good else 0)


def fmt(value: float, decimals: int = 1, unit: str = "") -> str:
    return f"{value:+.{decimals}f}{unit}".replace("-", "−")


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


# ---------------------------------------------------------------- ① equity and flows

def equity_signals(market: str, data: Inputs) -> list[Signal]:
    k = data.kpis.get(INDEX[market], {})
    out = []
    rule = f"≤ {FROM_HIGH_BAD:g}% で −1、≥ {FROM_HIGH_GOOD:g}% で +1"
    fh = k.get("from_high")
    out.append(Signal("1年高値比", fmt(fh, 1, "%"), rule,
                      three_way(fh, fh <= FROM_HIGH_BAD + EPS, fh >= FROM_HIGH_GOOD - EPS))
               if fh is not None else missing("1年高値比", rule))
    month = (k.get("changes") or {}).get("1m")
    rule = f"≤ {MONTH_BAD:g}% で −1、≥ +{MONTH_GOOD:g}% で +1"
    if month:
        d = month["delta"]
        out.append(Signal("1か月の騰落率", fmt(d, 1, "%"), rule, three_way(d, d <= MONTH_BAD + EPS, d >= MONTH_GOOD - EPS)))
    else:
        out.append(missing("1か月の騰落率", rule))
    run = k.get("streak", 0)
    rule = f"{STREAK_WEEKS}週以上の連続低下で −1、連続上昇で +1"
    seen = f"{abs(run)}週連続{'上昇' if run > 0 else '低下'}" if run else "なし"
    out.append(Signal("週末値の連続", seen, rule, three_way(run, run <= -STREAK_WEEKS, run >= STREAK_WEEKS))
               if k.get("value") is not None else missing("週末値の連続", rule))
    gap = data.derived_value(f"{INDEX[market]}_MA200")
    rule = f"< −{MA_BAND:g}% で −1、> +{MA_BAND:g}% で +1"
    out.append(Signal("200日移動平均からの乖離", fmt(gap, 1, "%"), rule, three_way(gap, gap < -MA_BAND, gap > MA_BAND))
               if gap is not None else missing("200日移動平均からの乖離", rule))
    out.append(foreign_flow_signal(data) if market == "japan" else cot_signal(data))
    return out


def foreign_flow_signal(data: Inputs) -> Signal:
    rule = "直近2週とも売り越しで −1、買い越しで +1"
    pts = data.series.get("JP_FLOW_FOREIGN", [])
    if len(pts) < 2:
        return missing("海外投資家の売買差引", rule)
    a, b = pts[-2][1], pts[-1][1]
    seen = f"{a:,.0f} → {b:,.0f} 億円".replace("-", "−") + f"（{pts[-1][0]} 週）"
    return Signal("海外投資家の売買差引", seen, rule, three_way(b, a < 0 and b < 0, a > 0 and b > 0))


def cot_signal(data: Inputs) -> Signal:
    rule = f"ネットが{COT_WEEKS}週前より |ネット|の{COT_CHANGE:.0%}以上減れば −1、増えれば +1"
    pts = data.series.get("US_COT_ES_NET", [])
    if len(pts) <= COT_WEEKS:
        return missing("CFTC 非商業部門ネット", rule)
    before, now = pts[-1 - COT_WEEKS][1], pts[-1][1]
    step = abs(before) * COT_CHANGE
    seen = f"{before:,.0f} → {now:,.0f} 枚（{COT_WEEKS}週）".replace("-", "−")
    return Signal("CFTC 非商業部門ネット", seen, rule, three_way(now, now < before - step, now > before + step))


# ---------------------------------------------------------------- ② rates and policy

def rate_signals(market: str, data: Inputs) -> list[Signal]:
    out = []
    pts = data.series.get(POLICY[market], [])
    rule = f"{POLICY_DAYS}日で +{POLICY_STEP:g} を超える引き上げで −1、引き下げで +1"
    now = last(pts)
    before = value_before(pts, shifted(now[0], POLICY_DAYS)) if now else None
    if now and before:
        delta = now[1] - before[1]
        out.append(Signal("政策金利の3か月の変化", f"{before[1]:.2f} → {now[1]:.2f}%", rule,
                          three_way(delta, delta > POLICY_STEP, delta < -POLICY_STEP)))
    else:
        out.append(missing("政策金利の3か月の変化", rule))
    month = (data.kpis.get(TEN_YEAR[market], {}).get("changes") or {}).get("1m")
    rule = f"1か月で +{TEN_YEAR_MOVE:g} 以上で −1、−{TEN_YEAR_MOVE:g} 以下で +1"
    if month:
        d = month["delta"]
        out.append(Signal("10年債利回りの1か月の変化", fmt(d, 2), rule,
                          three_way(d, d >= TEN_YEAR_MOVE - EPS, d <= -TEN_YEAR_MOVE + EPS)))
    else:
        out.append(missing("10年債利回りの1か月の変化", rule))
    real = data.derived_value("JP_REAL_POLICY" if market == "japan" else "US_REAL_POLICY")
    real = round(real, 2) if real is not None else None
    rule = f"> {REAL_TIGHT:g}% で −1（引き締め的）、< {REAL_EASY:g}% で +1（緩和的）"
    out.append(Signal("実質政策金利", fmt(real, 2, "%"), rule, three_way(real, real > REAL_TIGHT, real < REAL_EASY))
               if real is not None else missing("実質政策金利", rule))
    return out


# ---------------------------------------------------------------- ③ macro

def change_over(points: Points, steps: int) -> tuple[float, float] | None:
    if len(points) <= steps:
        return None
    return points[-1 - steps][1], points[-1][1]


def inflation_signal(market: str, data: Inputs) -> Signal:
    sid, label = CORE_INFLATION[market]
    lo, hi = INFLATION_BAND
    name = f"基調インフレ（{label}）"
    rule = f"{lo:g}〜{hi:g}% で +1、≥ {INFLATION_HIGH:g}% または < {INFLATION_LOW:g}% で −1"
    p = last(data.series.get(sid, []))
    if not p:
        return missing(name, rule)
    v = round(p[1], 1)  # the brief shows one decimal; judge the number the reader sees
    return Signal(name, f"{v:.1f}%（{p[0][:7]}）", rule,
                  three_way(v, v >= INFLATION_HIGH or v < INFLATION_LOW, lo <= v <= hi), date=p[0])


def unemployment_signal(market: str, data: Inputs) -> Signal:
    rule = f"{UNEMP_POINTS}か月で +{UNEMP_UP:g} 以上で −1、{UNEMP_DOWN:g} 以下で +1"
    pts = data.series.get(UNEMPLOYMENT[market], [])
    pair = change_over(pts, UNEMP_POINTS)
    if not pair:
        return missing("失業率の3か月の変化", rule)
    delta = pair[1] - pair[0]
    return Signal("失業率の3か月の変化", f"{pair[0]:.1f} → {pair[1]:.1f}%（{pts[-1][0][:7]}）", rule,
                  three_way(delta, delta >= UNEMP_UP - EPS, delta <= UNEMP_DOWN + EPS), date=pts[-1][0])


def level_signal(name: str, sid: str, data: Inputs, bad: float, good: float, unit: str) -> Signal:
    rule = f"< {bad:g}{unit} で −1、> {good:g}{unit} で +1"
    p = last(data.series.get(sid, []))
    if not p:
        return missing(name, rule)
    v = round(p[1], 1)  # judge the number the reader sees
    return Signal(name, f"{v:.1f}{unit}（{p[0][:7]}）", rule, three_way(v, v < bad, v > good), date=p[0])


def payroll_signal(data: Inputs) -> Signal:
    rule = f"{NFP_POINTS}か月平均 < {NFP_WEAK:g}千人で −1、> {NFP_STRONG:g}千人で +1"
    pts = data.series.get("US_NFP_CHANGE", [])
    if len(pts) < NFP_POINTS:
        return missing("雇用者数前月差の3か月平均", rule)
    avg = round(sum(v for _, v in pts[-NFP_POINTS:]) / NFP_POINTS)
    return Signal("雇用者数前月差の3か月平均", f"{avg:.0f}千人（{pts[-1][0][:7]}まで）", rule,
                  three_way(avg, avg < NFP_WEAK, avg > NFP_STRONG), date=pts[-1][0])


def ci_signal(sid: str, name: str, data: Inputs) -> Signal:
    rule = f"{CI_POINTS}か月で低下なら −1、上昇なら +1"
    pts = data.series.get(sid, [])
    pair = change_over(pts, CI_POINTS)
    if not pair:
        return missing(f"{name}の3か月の変化", rule)
    delta = pair[1] - pair[0]
    return Signal(f"{name}の3か月の変化", f"{pair[0]:.1f} → {pair[1]:.1f}（{pts[-1][0][:7]}）", rule,
                  three_way(delta, delta < 0, delta > 0), date=pts[-1][0])


def oil_signal(data: Inputs) -> Signal:
    """WTI against a year earlier: a large rise feeds inflation in both markets."""
    name = "原油（WTI）の前年比"
    rule = f"≥ +{OIL_YOY_HIGH:g}% で −1（物価の上振れ要因）、≤ {OIL_YOY_LOW:g}% で +1"
    pts = data.series.get("US_WTI", [])
    now = last(pts)
    before = value_before(pts, store._shift(now[0], years=-1)) if now else None
    if not now or not before or before[1] <= 0 or before[0] < store._shift(now[0], years=-1, days=-10):
        return missing(name, rule)
    yoy = round((now[1] / before[1] - 1) * 100, 1)
    return Signal(name, f"{fmt(yoy, 1, '%')}（{now[1]:.2f}ドル、{now[0]}）", rule,
                  three_way(yoy, yoy >= OIL_YOY_HIGH, yoy <= OIL_YOY_LOW))


def macro_signals(market: str, data: Inputs) -> list[Signal]:
    out = [inflation_signal(market, data), unemployment_signal(market, data)]
    if market == "us":
        return out + [payroll_signal(data),
                      level_signal("小売売上高（前年比）", "US_RETAIL_YOY", data, RETAIL_BAD, RETAIL_GOOD, "%"),
                      level_signal("鉱工業生産（前年比）", "US_INDPRO_YOY", data, INDPRO_BAD, INDPRO_GOOD, "%"),
                      oil_signal(data)]
    return out + [ci_signal("JP_CI_COINCIDENT", "景気動向指数 一致", data),
                  ci_signal("JP_CI_LEADING", "景気動向指数 先行", data), oil_signal(data)]


# ---------------------------------------------------------------- ④ valuation and sentiment

def valuation_signals(market: str, data: Inputs) -> list[Signal]:
    out = []
    if market == "us":
        gap = data.derived_value("US_PER_VS_10Y_AVG")
        rule = f"10年平均より +{PER_GAP:g}倍以上で −1、−{PER_GAP:g}倍以下で +1"
        out.append(Signal("予想PER − 10年平均", fmt(gap, 1, "倍"), rule,
                          three_way(gap, gap >= PER_GAP - EPS, gap <= -PER_GAP + EPS))
                   if gap is not None else missing("予想PER − 10年平均", rule))
    yg = data.derived_value("JP_YIELD_GAP" if market == "japan" else "US_YIELD_GAP")
    rule = f"< {YIELD_GAP_LOW:g} で −1（株式の上乗せが薄い）、> {YIELD_GAP_HIGH:g} で +1"
    out.append(Signal("益利回り − 10年債利回り", fmt(yg, 2), rule, three_way(yg, yg < YIELD_GAP_LOW, yg > YIELD_GAP_HIGH))
               if yg is not None else missing("益利回り − 10年債利回り（予想PER が無いか古い）", rule))
    if market == "us":
        out += [hy_signal(data), ig_signal(data)]
    vix = data.kpis.get("US_VIX", {}).get("value")
    rule = f"≥ {VIX_HIGH:g} で −1、≤ {VIX_LOW:g} で +1（日米共通のリスク指標）"
    out.append(Signal("VIX", f"{vix:.1f}", rule, three_way(vix, vix >= VIX_HIGH, vix <= VIX_LOW))
               if vix is not None else missing("VIX", rule))
    return out


def hy_signal(data: Inputs) -> Signal:
    rule = (f"1か月で +{HY_MONTH_UP:g} 以上または5年での位置 ≥ {HY_PCTL_HIGH:g}% で −1、"
            f"1か月で {HY_MONTH_DOWN:g} 以下かつ位置 ≤ {HY_PCTL_LOW:g}% で +1")
    month = (data.kpis.get("US_HY_OAS", {}).get("changes") or {}).get("1m")
    if not month:
        return missing("HY スプレッド", rule)
    pctl = data.derived_value("US_HY_OAS_PCTL")
    delta = month["delta"]
    wide = delta >= HY_MONTH_UP - EPS or (pctl is not None and pctl >= HY_PCTL_HIGH)
    tight = delta <= HY_MONTH_DOWN + EPS and pctl is not None and pctl <= HY_PCTL_LOW
    seen = f"1か月 {fmt(delta, 2)}" + (f"、5年での位置 {pctl:.0f}%" if pctl is not None else "")
    return Signal("HY スプレッド", seen, rule, three_way(delta, wide, tight))


def ig_signal(data: Inputs) -> Signal:
    rule = f"1か月で +{IG_MONTH_UP:g} 以上で −1、{IG_MONTH_DOWN:g} 以下で +1"
    pts = data.series.get("US_IG_OAS", [])
    now = last(pts)
    before = value_before(pts, shifted(now[0], IG_DAYS)) if now else None
    if not now or not before:
        return missing("投資適格社債スプレッド", rule)
    delta = now[1] - before[1]
    return Signal("投資適格社債スプレッド", f"{now[1]:.2f}（1か月 {fmt(delta, 2)}）", rule,
                  three_way(delta, delta >= IG_MONTH_UP - EPS, delta <= IG_MONTH_DOWN + EPS))


# ---------------------------------------------------------------- ratings and the overall judgement

SIGNALS = {"1": equity_signals, "2": rate_signals, "3": macro_signals, "4": valuation_signals}


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


def rate(total: float, previous: str | None) -> tuple[str, bool]:
    """(rating, hysteresis applied). Entering needs ±THRESHOLD; leaving needs the total back at 0."""
    raw = TAIL if total <= -THRESHOLD else (HEAD if total >= THRESHOLD else NEUTRAL)
    if raw == NEUTRAL and previous == TAIL and total < 0:
        return TAIL, True
    if raw == NEUTRAL and previous == HEAD and total > 0:
        return HEAD, True
    return raw, False


def combine(ratings: dict[str, str]) -> str:
    """Overall judgement from the four viewpoint ratings (keys "1".."4"); every case is covered."""
    tails = sum(1 for r in ratings.values() if r == TAIL)
    heads = sum(1 for r in ratings.values() if r == HEAD)
    if ratings.get("1") == TAIL and tails - 1 >= 2:
        return "弱気"
    if tails == 0 and heads >= 2:
        return "強気"
    if tails > heads:
        return "慎重"
    return "中立"


def adjust_divergence(market: str, viewpoints: list[dict]) -> None:
    """US only: ① 追い風 while the HY spread signal is −1 is a warning, not a tailwind (→ 中立).
    Japan has no credit-spread series, so it is left as is."""
    if market != "us":
        return
    equity = viewpoints[0]
    hy = next((s for s in viewpoints[3]["signals"] if s["name"] == "HY スプレッド"), None)
    if equity["rating"] == HEAD and hy and hy["score"] == -1:
        # the adjusted 中立 is what next week's hysteresis starts from; a held 追い風 is dropped on purpose
        equity["rating"], equity["adjusted"], equity["held"] = NEUTRAL, DIVERGENCE_NOTE, False


def score_market(market: str, data: Inputs, previous: dict[str, str] | None) -> dict:
    viewpoints = []
    for key, name in VIEWPOINTS:
        signals = weighted(SIGNALS[key](market, data), data.asof)
        total = round(sum(s.points for s in signals), 2)
        before = (previous or {}).get(key)
        rating, held = rate(total, before)
        viewpoints.append({"key": key, "name": name, "total": total, "rating": rating, "held": held,
                           "previous": before, "adjusted": "",
                           "signals": [{**asdict(s), "points": s.points} for s in signals],
                           "missing": [s.name for s in signals if not s.available]})
    adjust_divergence(market, viewpoints)
    return {"viewpoints": viewpoints, "candidate": combine({v["key"]: v["rating"] for v in viewpoints})}


def build_scores(data: Inputs, previous: dict[str, dict[str, str]] | None) -> dict[str, dict]:
    """previous: {market: {"1": rating, ...}} adopted last week (judgment.json), or None."""
    return {m: score_market(m, data, (previous or {}).get(m)) for m in ("japan", "us")}
