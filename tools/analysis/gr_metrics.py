"""CAGR and every judgement of 企業分析フレームワーク.md 2-2 (成長性).

  CAGR = (最終年の値 ÷ 初年の値)^(1 ÷ 年数) − 1, over the newest MAX_YEARS fiscal years with sales.
  手順1 (成長の水準, at least MIN_YEARS years of sales and EPS): 停滞・縮小: 売上か EPS の CAGR がマイナス /
    高成長: 売上 >= 5% かつ EPS >= 7% / 安定成長: それ以外でともにプラス. EPS is split-adjusted (gr_series);
    without enough EPS years the net income stands in and says so. A first year at a loss gives no CAGR.
  手順2 (減収・減益の年): years whose sales, operating income or EPS fell from the year before, with whether the
    level of the year before came back within RECOVERY_YEARS years. The writer classifies each year
    (一時 / 構造 / 不明) from the brief; build refuses 一時 for a year that never recovered.
  手順3 (会社計画の信頼性): 期初予想 vs 実績 per year (営業利益, else 経常利益, else 純利益). 90% 以上の年が
    過半で、直近2年が続けて未達でない → 信頼できる / それ以外 → 割り引いて扱う. Reported for STEP 3 only.
  手順4 (成長の質): (a) 営業利益 CAGR >= 売上 CAGR, (b) sales growth not from M&A (the acquired companies'
    annual sales taken out of the last year), (c) EPS growth not from buybacks (EPS CAGR − 純利益 CAGR <= 2pt).
    手順1 is judged again with the organic sales CAGR / the net income CAGR where (b) / (c) fail.
  手順5 (結論, in this order): 懸念: 手順1 (or the quality-adjusted 手順1) 停滞・縮小, or a 構造 year /
    判定保留: 手順1 lacks years / 普通: a quality problem / 判定保留: a 不明 year or a quality point that
    could not be checked / 良好: 高成長 or 安定成長 with none of the above.
"""
from __future__ import annotations

import json
import re

import an_common as A
import gr_inputs as I
import gr_series as S
from ff_metrics import _months_apart

MIN_YEARS, MAX_YEARS = 5, 10
HIGH_SALES, HIGH_EPS = 5.0, 7.0
BORDER_PT = 1.0  # a CAGR within this of a threshold is borderline
RECOVERY_YEARS = 2
PLAN_HIT = 90.0
PLAN_BORDER = 5.0  # an achievement within this of PLAN_HIT is borderline
BUYBACK_GAP_PT = 2.0
MA_GAP_PT = 1.0
MA_MATERIAL_SHARE = 0.01  # a CF outflow for subsidiaries below 1% of that year's sales is not looked into
PLAN_SANE = (20.0, 500.0)  # an achievement outside this band is a unit mismatch between the sources, not a result
MARKET_DEFAULT = 3.0  # 1-2 の「成長性 高」の下限（市場成長率が読めないとき）
MARKET_CAGR = re.compile(r"CAGR[^\d%。]{0,6}?(\d+(?:\.\d+)?)\s*[%％]")
DECLINE_METRICS = (("sales", "売上高"), ("operating_income", "営業利益"), ("eps", "EPS"))
PLAN_ORDER = (("operating_income", "営業利益"), ("ordinary_income", "経常利益"), ("net_income", "純利益"))
CLASSES = ("一時", "構造", "不明")
OWN_UNAVAILABLE = "成長性の財務時系列"  # collect-filings reports a short own history under this name
OWN_ITEM = f"財務時系列: 売上高・営業利益・当期純利益・EPS（{MIN_YEARS}年以上）"
DECLINE_ITEM = I.SPEC["decline"].label


# ---------- the yearly rows ----------

def yearly_rows(series: S.Series, eps: dict[str, float]) -> list[dict]:
    """The newest MAX_YEARS fiscal years with sales: sales, operating income, net income, adjusted EPS."""
    years = sorted(series["sales"])[-MAX_YEARS:]
    rows = []
    for year in years:
        def value(field: str) -> float | None:
            v = series[field].get(year)
            return v.value if v else None
        rows.append({"year": year, "sales": value("sales"), "operating_income": value("operating_income"),
                     "net_income": value("net_income"), "eps": eps.get(year),
                     "eps_reported": value("eps"), "acquisition": value("acquisition"),
                     "buyback": value("buyback"), "source": series["sales"][year].source,
                     "primary": series["sales"][year].primary})
    return rows


def _consecutive(rows: list[dict]) -> list[tuple[dict, dict]]:
    return [(p, c) for p, c in zip(rows, rows[1:]) if _months_apart(p["year"], c["year"]) == 12]


def yoy(rows: list[dict], key: str) -> dict[str, float | None]:
    out = {}
    for prev, cur in _consecutive(rows):
        a, b = prev[key], cur[key]
        out[cur["year"]] = (b / a - 1) * 100 if a is not None and b is not None and a > 0 else None
    return out


# ---------- CAGR ----------

def cagr(rows: list[dict], key: str) -> dict:
    """{value (%), first, last, years, sign}. No value when the first year is a loss (sign tells the direction
    when the last year turned to a loss)."""
    points = [r for r in rows if r[key] is not None]
    if len(points) < 2:
        return {"value": None, "sign": None, "points": len(points), "first": None, "last": None,
                "reason": "2年分の値が無い"}
    a, b = points[0], points[-1]
    span = _months_apart(a["year"], b["year"]) / 12
    base = {"points": len(points), "first": a["year"], "last": b["year"], "span": span}
    if a[key] <= 0 and b[key] > 0:
        return {**base, "value": None, "sign": "+", "reason": f"初年（{a['year']}）が赤字・ゼロで計算できない（最終年は黒字）"}
    if a[key] <= 0:
        return {**base, "value": None, "sign": None, "reason": f"初年（{a['year']}）・最終年（{b['year']}）とも赤字・ゼロ"}
    if b[key] <= 0:
        return {**base, "value": None, "sign": "-", "reason": f"最終年（{b['year']}）が赤字・ゼロ"}
    value = ((b[key] / a[key]) ** (1 / span) - 1) * 100
    return {**base, "value": value, "sign": "-" if value < 0 else "+", "reason": ""}


def fmt_cagr(c: dict) -> str:
    return f"{c['value']:.1f}%" if c.get("value") is not None else f"—（{c.get('reason') or '計算できない'}）"


def rate_growth(sales: dict, eps: dict) -> str | None:
    """高成長 / 安定成長 / 停滞・縮小, or None when a CAGR cannot be computed."""
    if "-" in (sales["sign"], eps["sign"]):
        return "停滞・縮小"
    if sales["value"] is None or eps["value"] is None:
        return None
    if sales["value"] >= HIGH_SALES and eps["value"] >= HIGH_EPS:
        return "高成長"
    return "安定成長"


# ---------- 手順1 ----------

def _window(rows: list[dict], keys: tuple[str, ...]) -> list[dict]:
    """The rows from the first to the last year where every key has a value (all CAGRs over one period)."""
    full = [i for i, r in enumerate(rows) if all(r[k] is not None for k in keys)]
    return rows[full[0]:full[-1] + 1] if full else []


def step1(rows: list[dict]) -> dict:
    with_eps = len(_window(rows, ("sales", "eps")))
    with_ni = len(_window(rows, ("sales", "net_income")))
    eps_key = "eps" if with_eps >= MIN_YEARS or with_eps >= with_ni else "net_income"
    window = _window(rows, ("sales", eps_key))
    sales, op, eps = cagr(window, "sales"), cagr(window, "operating_income"), cagr(window, eps_key)
    ni = cagr(window, "net_income")
    years = sum(r["sales"] is not None and r[eps_key] is not None for r in window)
    stand_in = "" if eps_key == "eps" else "（EPS が足りないため当期純利益で代用）"
    base = {"years": years, "sales": sales, "operating_income": op, "eps": eps, "net_income": ni,
            "eps_key": eps_key, "stand_in": stand_in, "window": [r["year"] for r in window],
            "first": window[0]["year"] if window else None, "last": window[-1]["year"] if window else None}
    cagrs = (f"売上 CAGR {fmt_cagr(sales)}、営業利益 CAGR {fmt_cagr(op)}、"
             f"{'EPS' if eps_key == 'eps' else '純利益'} CAGR {fmt_cagr(eps)}")
    if years < MIN_YEARS:
        return {**base, "rating": None, "basis": f"売上高と EPS が揃った年が {years} 年で {MIN_YEARS} 年に満たない",
                "sentence": f"{cagrs}（参考値）。{years}年分しかなく、{MIN_YEARS}年に満たず判定できない"}
    rating = rate_growth(sales, eps)
    if rating is None:
        why = "CAGR を計算できない（" + "、".join(c["reason"] for c in (sales, eps) if c["value"] is None) + "）"
        return {**base, "rating": None, "basis": why, "sentence": f"{cagrs}。{why}"}
    why = {"高成長": f"売上 CAGR {HIGH_SALES:.0f}% 以上かつ EPS CAGR {HIGH_EPS:.0f}% 以上",
           "停滞・縮小": "売上または EPS の CAGR がマイナス",
           "安定成長": "売上・EPS とも CAGR がプラス（高成長の基準には届かない）"}[rating] + stand_in
    span = f"{base['first']}〜{base['last']}"
    return {**base, "rating": rating, "basis": why, "sentence": f"{cagrs}（{span}）で{rating}"}


# ---------- 手順2 ----------

def _recovery(rows: list[dict], index: int, key: str, base: float) -> tuple[str, str | None]:
    """回復 / 遅れて回復 / 未回復 / 未確認, and the year the level came back."""
    cur = rows[index]
    later = rows[index + 1:]
    for r in later:
        if r[key] is not None and r[key] >= base:
            within = _months_apart(cur["year"], r["year"]) <= RECOVERY_YEARS * 12
            return ("回復" if within else "遅れて回復"), r["year"]
    observed = [r for r in later if r[key] is not None]
    if not observed or _months_apart(cur["year"], observed[-1]["year"]) < RECOVERY_YEARS * 12:
        return "未確認", None
    return "未回復", None


RECOVERY_ORDER = ("未回復", "未確認", "遅れて回復", "回復")


def decline_years(rows: list[dict]) -> list[dict]:
    """Years whose sales, operating income or EPS fell from the year before."""
    index = {r["year"]: i for i, r in enumerate(rows)}
    out = []
    for prev, cur in _consecutive(rows):
        metrics = []
        for key, name in DECLINE_METRICS:
            a, b = prev[key], cur[key]
            if a is None or b is None or b >= a:
                continue
            status, year = _recovery(rows, index[cur["year"]], key, a)
            change = (b / a - 1) * 100 if a > 0 else None
            metrics.append({"key": key, "name": name, "from": a, "to": b, "change": change,
                            "recovery": status, "recovered": year})
        if metrics:
            worst = min(metrics, key=lambda m: RECOVERY_ORDER.index(m["recovery"]))["recovery"]
            out.append({"year": cur["year"], "metrics": metrics, "recovery": worst})
    return out


# ---------- 手順3 ----------

def plan_rows(plan: dict[str, dict], series: S.Series, last_year: str | None) -> tuple[list[dict], list[dict]]:
    """期初予想 vs 実績 per year (the first metric of PLAN_ORDER with a positive forecast and an actual), and the
    rows dropped because the achievement is outside PLAN_SANE (the forecast and the actual in different units)."""
    out, dropped = [], []
    for year, rec in plan.items():
        if last_year is None or year > last_year:
            continue
        for metric, name in PLAN_ORDER:
            forecast = rec["forecast"].get(metric)
            actual = rec["actual"].get(metric) or series.get(metric, {}).get(year)
            if forecast is None or forecast.value <= 0 or actual is None:
                continue
            sales_f, sales_a = rec["forecast"].get("sales"), rec["actual"].get("sales") or series["sales"].get(year)
            sales_rate = (sales_a.value / sales_f.value * 100 if sales_f and sales_a and sales_f.value > 0 else None)
            row = {"year": year, "metric": name, "forecast": forecast.value, "actual": actual.value,
                   "rate": actual.value / forecast.value * 100, "sales_rate": sales_rate,
                   "source": forecast.source, "primary": forecast.primary and actual.primary}
            (out if PLAN_SANE[0] <= row["rate"] <= PLAN_SANE[1] else dropped).append(row)
            break
    return out[-MAX_YEARS:], dropped


def step3(rows: list[dict]) -> dict:
    if not rows:
        return {"rating": None, "rows": rows, "basis": "期初予想と実績の組が無い",
                "sentence": "会社計画の達成率は計算できない（期初予想と実績の組が無い）"}
    hits = [r for r in rows if r["rate"] >= PLAN_HIT]
    misses_recent = len(rows) >= 2 and all(r["rate"] < PLAN_HIT for r in rows[-2:])
    trusted = len(hits) * 2 > len(rows) and not misses_recent
    rating = "信頼できる" if trusted else "割り引いて扱う"
    avg = sum(r["rate"] for r in rows) / len(rows)
    why = (f"{len(rows)}年中 {len(hits)}年で達成率 {PLAN_HIT:.0f}% 以上"
           + ("、直近2年が続けて未達" if misses_recent else ""))
    return {"rating": rating, "rows": rows, "hits": len(hits), "average": avg, "basis": why,
            "sentence": f"計画達成率は平均{avg:.0f}%（{why}）で、計画は{rating}"}


# ---------- 手順4 ----------

def _check_margin(s1: dict) -> dict:
    sales, op = s1["sales"], s1["operating_income"]
    name = "営業利益の伸び ≥ 売上の伸び"
    if op["value"] is not None and sales["value"] is not None:
        ok = op["value"] >= sales["value"]
        detail = f"営業利益 CAGR {op['value']:.1f}% / 売上 CAGR {sales['value']:.1f}%"
        return {"name": name, "status": "問題なし" if ok else "問題あり", "detail": detail,
                "problem": "" if ok else "営業利益が売上ほど伸びていない（利益率が下がっている）"}
    if op["sign"] == "+" and op["value"] is None:
        return {"name": name, "status": "問題なし", "detail": "営業利益が赤字から黒字化（利益率は上昇）",
                "problem": ""}
    if op["value"] is None and op["first"] is not None and op["sign"] != "+":
        return {"name": name, "status": "問題あり", "detail": op["reason"], "problem": "直近の営業利益が赤字"}
    return {"name": name, "status": "不明", "detail": op.get("reason") or "営業利益の時系列が無い", "problem": ""}


def _window_years(s1: dict) -> tuple[str | None, str | None]:
    return s1["sales"]["first"], s1["sales"]["last"]


def _check_ma(s1: dict, rows: list[dict], ma: list[dict], ma_status: str) -> dict:
    name = "売上増が M&A 頼みでない"
    first, last = _window_years(s1)
    if first is None:
        return {"name": name, "status": "不明", "detail": "売上の時系列が無い", "problem": "", "organic": None}
    outflow = [r["year"] for r in rows if first < r["year"] <= last and r["acquisition"] and r["sales"]
               and abs(r["acquisition"]) >= r["sales"] * MA_MATERIAL_SHARE]
    deals = [d for d in ma if first < d["year"] <= last]
    if not outflow and not deals:
        if ma_status in ("ok", "unavailable"):
            note = "" if ma_status == "ok" else "（M&A の節は取得できず、CF の支出だけで確認）"
            return {"name": name, "status": "問題なし", "detail": f"期間内の M&A なし{note}", "problem": "",
                    "organic": None}
        return {"name": name, "status": "不明", "detail": "M&A・連結範囲の変更の材料が無い", "problem": "",
                "organic": None}
    years = sorted(set(outflow) | {d["year"] for d in deals})
    unknown = [d["target"] for d in deals if d["sales"] is None] + \
        [y for y in outflow if not any(d["year"] == y for d in deals)]
    if unknown:
        return {"name": name, "status": "不明", "problem": "", "organic": None,
                "detail": f"M&A あり（{'、'.join(years)}）。買収先の売上が分からない（{'、'.join(unknown)}）"}
    acquired = sum(d["sales"] for d in deals)
    last_sales = next(r["sales"] for r in rows if r["year"] == last)
    first_sales = next(r["sales"] for r in rows if r["year"] == first)
    organic_last = last_sales - acquired
    span = s1["sales"]["span"]
    organic = ((organic_last / first_sales) ** (1 / span) - 1) * 100 if organic_last > 0 and first_sales > 0 else None
    gap = s1["sales"]["value"] - organic if organic is not None and s1["sales"]["value"] is not None else None
    detail = (f"M&A あり（{'、'.join(years)}、買収先の売上 計{acquired:,.0f}百万）。除いた売上 CAGR "
              f"{'—' if organic is None else f'{organic:.1f}%'}")
    if gap is None or gap > MA_GAP_PT:
        return {"name": name, "status": "問題あり", "detail": detail, "organic": organic,
                "problem": "売上の伸びの一部が M&A による（除いた実質の CAGR で判断し直す）"}
    return {"name": name, "status": "問題なし", "detail": detail, "problem": "", "organic": organic}


def _check_buyback(s1: dict) -> dict:
    name = "EPS の伸びが自社株買い頼みでない"
    if s1["eps_key"] != "eps":
        return {"name": name, "status": "問題なし", "detail": "EPS が足りず純利益で代用（自社株買いの影響を含まない）",
                "problem": ""}
    eps, ni = s1["eps"], s1["net_income"]
    if eps["value"] is None or ni["value"] is None:
        return {"name": name, "status": "不明", "detail": eps.get("reason") or ni.get("reason") or "計算できない",
                "problem": ""}
    gap = eps["value"] - ni["value"]
    detail = f"EPS CAGR {eps['value']:.1f}% / 純利益 CAGR {ni['value']:.1f}%（差 {gap:+.1f}pt）"
    if gap > BUYBACK_GAP_PT:
        return {"name": name, "status": "問題あり", "detail": detail,
                "problem": "EPS の伸びの一部が自社株買い（株式数の減少）による（純利益の CAGR で判断し直す）"}
    return {"name": name, "status": "問題なし", "detail": detail, "problem": ""}


def step4(s1: dict, rows: list[dict], ma: list[dict], ma_status: str) -> dict:
    checks = [_check_margin(s1), _check_ma(s1, rows, ma, ma_status), _check_buyback(s1)]
    problems = [c["problem"] for c in checks if c["status"] == "問題あり"]
    unknown = [c["name"] for c in checks if c["status"] == "不明"]
    quality = "問題あり" if problems else "不明" if unknown else "高い"
    sales, eps = dict(s1["sales"]), dict(s1["eps"])
    adjusted_parts = []
    organic = checks[1]["organic"]
    if checks[1]["status"] == "問題あり" and organic is not None:
        sales.update(value=organic, sign="-" if organic < 0 else "+")
        adjusted_parts.append(f"M&A を除いた売上 CAGR {organic:.1f}%")
    if checks[2]["status"] == "問題あり":
        eps = dict(s1["net_income"])
        adjusted_parts.append(f"純利益 CAGR {fmt_cagr(eps)}")
    adjusted = None
    if adjusted_parts and s1["rating"] is not None:
        rating = rate_growth(sales, eps)
        adjusted = {"rating": rating, "basis": "、".join(adjusted_parts),
                    "sentence": f"{'、'.join(adjusted_parts)}で判断し直すと{rating or '判定できない'}"}
    sentence = {"高い": "3点とも問題なく、成長の質は高い",
                "問題あり": "成長の質に問題あり: " + "。".join(problems),
                "不明": "成長の質は確かめきれない（" + "・".join(unknown) + "）"}[quality]
    return {"checks": checks, "quality": quality, "problems": problems, "unknown": unknown,
            "adjusted": adjusted, "sentence": sentence}


# ---------- 手順5 ----------

def judge(s1: dict, declines: list[dict], s4: dict, classes: dict[str, str] | None) -> tuple[str, str]:
    """(良好/普通/懸念/判定保留, why). classes: year -> 一時 / 構造 / 不明 (None before the writer fills them:
    the candidate then assumes every year is 一時 and says so)."""
    adjusted = (s4["adjusted"] or {}).get("rating")
    if s1["rating"] == "停滞・縮小":
        return "懸念", f"手順1が停滞・縮小（{s1['basis']}）"
    if adjusted == "停滞・縮小":
        return "懸念", f"成長の質で補正すると停滞・縮小（{s4['adjusted']['basis']}）"
    years = [d["year"] for d in declines]
    filled = classes or {}
    structural = [y for y in years if filled.get(y) == "構造"]
    if structural:
        return "懸念", f"構造的な減収・減益の要因あり（{'、'.join(structural)}）"
    if s1["rating"] is None:
        return "判定保留", f"手順1を判定できない（{s1['basis']}）"
    if s4["problems"]:
        return "普通", f"手順1は{s1['rating']}だが、成長の質に問題あり（{'。'.join(s4['problems'])}）"
    unknown = [y for y in years if filled.get(y) == "不明"] if classes is not None else []
    if unknown or s4["unknown"]:
        parts = ([f"減収・減益の原因が不明の年（{'、'.join(unknown)}）"] if unknown else []) + \
                ([f"成長の質の確認ができない点（{'・'.join(s4['unknown'])}）"] if s4["unknown"] else [])
        return "判定保留", f"手順1は{s1['rating']}だが、{'、'.join(parts)}がある（材料不足。普通・懸念という意味ではない）"
    pending = "（減収・減益の年の分類が一時のときの候補）" if classes is None and years else ""
    return "良好", f"手順1が{s1['rating']}、構造的な減収減益要因なし、成長の質が高い{pending}"


def borderline(s1: dict, s3: dict, s4: dict) -> list[str]:
    out = []
    sales, eps = s1["sales"]["value"], s1["eps"]["value"]
    for name, value, limits in (("売上 CAGR", sales, (0.0, HIGH_SALES)), ("EPS CAGR", eps, (0.0, HIGH_EPS))):
        if value is None:
            continue
        for limit in limits:
            if abs(value - limit) <= BORDER_PT:
                out.append(f"手順1: {name} {value:.1f}% が基準 {limit:.0f}% に近い")
    margin = s4["checks"][0]
    op = s1["operating_income"]["value"]
    if margin["status"] != "不明" and op is not None and sales is not None and abs(op - sales) <= BORDER_PT:
        out.append(f"手順4: 営業利益 CAGR {op:.1f}% と売上 CAGR {sales:.1f}% の差が {BORDER_PT:.0f}pt 以内")
    ni = s1["net_income"]["value"]
    if s1["eps_key"] == "eps" and eps is not None and ni is not None \
            and abs((eps - ni) - BUYBACK_GAP_PT) <= BORDER_PT:
        out.append(f"手順4: EPS と純利益の CAGR の差 {eps - ni:+.1f}pt が基準 {BUYBACK_GAP_PT:.0f}pt に近い")
    near = [r["year"] for r in s3["rows"][-2:] if abs(r["rate"] - PLAN_HIT) <= PLAN_BORDER]
    if near:
        out.append(f"手順3: 直近の計画達成率が {PLAN_HIT:.0f}% に近い年（{'、'.join(near)}）")
    return out


# ---------- STEP 1 ----------

def market_growth(three_c: dict | None) -> tuple[float, str]:
    reason = ((three_c or {}).get("growth") or {}).get("reason") or ""
    m = MARKET_CAGR.search(reason)
    if m:
        return float(m.group(1)), "3C の市場成長率"
    return MARKET_DEFAULT, f"3C の理由に CAGR の数値が無いため「成長性 高」の下限 {MARKET_DEFAULT:.0f}%"


def consistency(s1: dict, three_c: dict | None) -> list[dict]:
    """企業分析フレームワーク.md「STEP 1 との整合性チェック」のうち 2-2 に関わる行."""
    rating = ((three_c or {}).get("growth") or {}).get("rating")
    sales = s1["sales"]["value"]
    step2 = f"売上 CAGR {fmt_cagr(s1['sales'])}"
    if not three_c:
        result, step1_text = "未実施（3C分析の結果なし）", "—"
    elif rating != "高":
        result, step1_text = f"対象外（市場の成長性 {rating or '—'}）", f"市場の成長性 {rating or '—'}"
    elif sales is None:
        result, step1_text = "判断できない（売上 CAGR を計算できない）", "市場の成長性 高"
    else:
        market, basis = market_growth(three_c)
        step1_text = f"市場の成長性 高（{basis} {market:.1f}%）"
        result = "整合" if sales >= market else "不整合（シェアを落としている可能性）"
    return [{"check": "市場成長性が高い ⇔ 売上成長", "step1": step1_text, "step2": step2, "result": result}]


# ---------- everything ----------

def candidates(company, found: dict) -> dict:
    series = S.self_series(company)
    eps, splits, odd = S.adjusted_eps(series)
    rows = yearly_rows(series, eps)
    s1 = step1(rows)
    declines = decline_years(rows)
    plans, dropped = plan_rows(S.plan_records(company, found["plan"]), series, s1["last"])
    s3 = step3(plans)
    ma = S.ma_rows(found["ma"])
    s4 = step4(s1, rows, ma, found["ma"].status)
    verdict, why = judge(s1, declines, s4, None)
    return {"series": series, "rows": rows, "splits": splits, "odd_share_jumps": odd, "plan_dropped": dropped,
            "step1": s1, "declines": declines, "step3": s3, "ma": ma, "step4": s4,
            "borderline": borderline(s1, s3, s4), "verdict": verdict, "why": why}


def collect_requests(company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, plus a short own history, and the company's explanation of the decline years."""
    unavailable = I.unavailable_items(company)
    extra: list[tuple[str, str]] = []
    if cands["step1"]["years"] < MIN_YEARS and not any(OWN_UNAVAILABLE in u for u in unavailable):
        extra.append(("collect-filings", OWN_ITEM))
    if cands["declines"] and found["decline"].status in ("missing", "blank"):
        years = "、".join(d["year"] for d in cands["declines"])
        extra.append(("collect-filings", f"{DECLINE_ITEM}（{years}）"))
    out = [dict(r, items=list(r["items"])) for r in I.collect_requests(found)]
    for agent, item in extra:
        hit = next((r for r in out if r["agent"] == agent), None)
        if hit is None:
            out.append({"agent": agent, "items": [item]})
        elif item not in hit["items"]:
            hit["items"] = hit["items"] + [item]
    return out


def series_digest(cands: dict) -> str:
    """Every number the result rests on: a new fiscal year or a corrected value re-opens the result."""
    def r2(v: float | None) -> float | None:
        return None if v is None else round(v, 2)
    rows = [[r["year"], r2(r["sales"]), r2(r["operating_income"]), r2(r["net_income"]), r2(r["eps"])]
            for r in cands["rows"]]
    plans = [[r["year"], r["metric"], r2(r["forecast"]), r2(r["actual"])] for r in cands["step3"]["rows"]]
    ma = [[d["year"], d["target"], r2(d["sales"])] for d in cands["ma"]]
    return A.digest(json.dumps([rows, plans, ma], ensure_ascii=False))


def warnings(cands: dict) -> list[str]:
    """Signs that the series were read wrongly or adjusted (shown in the brief and prepare's output)."""
    out = [f"EPS: {s['before']}→{s['after']} で 純利益÷EPS（株式数）が約{s['factor']:g}倍に変わった。株式分割・併合と"
           f"みなし、{s['before']} 以前の EPS を {s['factor']:g} で割って直近の基準にそろえた（分割の事実を brief で確かめる）"
           for s in cands["splits"]]
    out += [f"EPS: {o['before']}→{o['after']} で 純利益÷EPS（株式数）が約{o['ratio']:.3g}倍に変わった。分割としては大きすぎる"
            "ため調整していない（表の単位の読み違いの可能性。brief で確かめる）" for o in cands["odd_share_jumps"]]
    out += [f"会社計画 {r['year']}: 達成率 {r['rate']:.0f}% は予想と実績の単位の違いとみなし、手順3から除いた"
            f"（{PLAN_SANE[0]:.0f}〜{PLAN_SANE[1]:.0f}% の範囲外）" for r in cands["plan_dropped"]]
    if cands["step1"]["stand_in"]:
        out.append("EPS の年数が足りず、手順1は当期純利益の CAGR で代用した")
    secondary = [r["year"] for r in cands["rows"] if not r["primary"]]
    if secondary:
        out.append(f"売上高が二次情報（集計サイト）の年: {'、'.join(secondary)}")
    return out
