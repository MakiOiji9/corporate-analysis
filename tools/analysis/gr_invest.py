"""成長性 手順5: 成長投資（投資比率 × 投資効率）.

成長投資 = 維持投資（減価償却費で近似）を超えて、将来の売上・利益を増やすために使ったお金:
  設備投資の純増（有形・無形の取得 − 減価償却費） + 研究開発費 + 運転資本の増加（売上債権 + 棚卸資産 − 仕入債務）
  + 子会社の取得. Shareholder returns, financial investments and the capex within the depreciation are not counted.
  The amounts come from data/financials.csv (xbrl_financials.py / edgar.py); outflows are read by their size (EDINET
  stores them negative, us-gaap positive).

投資比率 (how much): growth investment ÷ sales over the newest RATIO_YEARS years, against the RATIO_YEARS before them
  (高い / 標準 / 低い, RATIO_BAND of the earlier ratio and at least RATIO_MIN_PT apart; 不明 without the earlier years).
  設備投資 ÷ 減価償却 below UNDERINVEST for the newest UNDERINVEST_YEARS years is 投資不足 (成長の前借り); it caps the
  verdict at 普通. A company whose capex is below ASSET_LIGHT_PCT of sales is 設備が少ない業態: the 投資不足 rule is
  not used.
投資効率 (did it pay): 増分 ROIC = ΔNOPAT ÷ Δ投下資本 within the accounting-consistent CAGR window of 手順1, with
  AVG_YEARS-year averages at both ends; the capital of the end is taken LAG_YEARS earlier (investment pays later) when
  the window is long enough (2 × AVG_YEARS + LAG_YEARS years), else without the lag (noted). Fewer than MIN_YEARS years
  is 不明. ROIC and 投下資本 are mt_returns' (the moat analysis' definition). 良好 >= the cost of capital / 普通 >= half
  of it / 問題あり below. A capital that barely grew (below SMALL_CAPITAL of the start) is 良好 when NOPAT grew, else 不明.
  人材集約型 (the parent's average salary × the consolidated employees >= PEOPLE_PCT of sales, Japan only) is judged
  by the people instead: 問題あり when the operating income per employee fell PEOPLE_FALL_YEARS years running while the
  headcount grew, 良好 when headcount and the operating income per employee both grew, else 普通.
  投資先行期: the growth investment of the newest SURGE_YEARS years at SURGE times the years before and a mid-term
  plan on file: a 問題あり efficiency is read as 不明（投資先行期）.
判定 (the matrix of the plan): 効率 良好 → 良好 (比率 低い: 普通); 効率 普通 → 普通; 効率 問題あり → 問題あり; 効率 不明
  → 不明. 投資不足 caps 良好 at 普通. 金融（sector_rules.FINANCIAL）は対象外.
"""
from __future__ import annotations

import statistics

import mt_returns as R
import sector_rules as SR
import sf_series as SS
from common import read_csv_rows
from ff_metrics import _months_apart

RATIO_YEARS = 5
RATIO_BAND = 0.2
RATIO_MIN_PT = 0.5
UNDERINVEST = 1.0
UNDERINVEST_YEARS = 3
ASSET_LIGHT_PCT = 3.0
MIN_YEARS = 6
AVG_YEARS = 3
LAG_YEARS = 2
SMALL_CAPITAL = 0.05
PEOPLE_PCT = 40.0
PEOPLE_FALL_YEARS = 3
SURGE = 1.5
SURGE_YEARS = 2
VERDICTS = ("良好", "普通", "問題あり", "不明", "対象外")
CSV_ITEMS = ("capex_tangible", "capex_intangible", "depreciation", "research_and_development", "receivables",
             "inventories", "trade_payables", "acquisition_of_subsidiaries", "summary.employees",
             "summary.average_salary")


# ---------- the yearly amounts ----------

def _float(text: str | None) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def csv_values(company) -> dict[str, dict[str, float]]:
    """{item: {year (YYYY-MM): value}} of the CSV_ITEMS in data/financials.csv."""
    out: dict[str, dict[str, float]] = {item: {} for item in CSV_ITEMS}
    for row in read_csv_rows(company.path / "data" / "financials.csv"):
        value = _float(row.get("value"))
        if row.get("item") in out and value is not None:
            out[row["item"]][row["period_end"][:7]] = value
    return out


def _size(value: float | None) -> float:
    return abs(value) if value is not None else 0.0


WORKING_CAPITAL = (("receivables", 1.0), ("inventories", 1.0), ("trade_payables", -1.0))


def _working_capital(values: dict, year: str | None, used: list[tuple[str, float]]) -> float | None:
    """売上債権 + 棚卸資産 − 仕入債務 of the items the company reports in the window (used); None when the year
    lacks one of them (a part missing in one year would read as a jump of the whole balance)."""
    if year is None or not used or any(year not in values[item] for item, _ in used):
        return None
    return sum(sign * values[item][year] for item, sign in used)


def yearly(values: dict, sales: dict[str, float], years: list[str]) -> list[dict]:
    """One row per year with capex and depreciation: the parts of the growth investment (百万)."""
    used = [(item, sign) for item, sign in WORKING_CAPITAL if any(y in values[item] for y in years)]
    rows = []
    for year in years:
        if year not in values["capex_tangible"] or year not in values["depreciation"]:
            continue
        capex = _size(values["capex_tangible"][year]) + _size(values["capex_intangible"].get(year))
        dep = values["depreciation"][year]
        # the year before within the window only: across a change of accounting standard the balances do not compare
        prior = next((y for y in years if _months_apart(y, year) == 12), None)
        wc, wc_prior = _working_capital(values, year, used), _working_capital(values, prior, used)
        rows.append({"year": year, "sales": sales.get(year), "capex": capex, "depreciation": dep,
                     "net_capex": capex - dep, "rnd": values["research_and_development"].get(year),
                     "working_capital": None if wc is None or wc_prior is None else wc - wc_prior,
                     "acquisition": _size(values["acquisition_of_subsidiaries"].get(year)),
                     "capex_to_dep": round(capex / dep, 2) if dep > 0 else None})
    return [dict(r, growth=r["net_capex"] + (r["rnd"] or 0.0) + (r["working_capital"] or 0.0) + r["acquisition"])
            for r in rows]


# ---------- 投資比率 ----------

def _share(rows: list[dict], key: str) -> float | None:
    counted = [r for r in rows if r["sales"]]
    sales = sum(r["sales"] for r in counted)
    return round(sum(r[key] or 0.0 for r in counted) / sales * 100, 1) if sales > 0 else None


def _comparable(recent: list[dict], earlier: list[dict]) -> tuple[float | None, float | None]:
    """The two windows' growth investment ÷ sales on the parts both have in every year (a part missing in one
    window, e.g. R&D only in the newer filings, would read as a change of the ratio)."""
    parts = ["net_capex", "acquisition"] + [k for k in ("rnd", "working_capital")
                                            if all(r[k] is not None for r in recent + earlier)]
    marked = [dict(r, comparable=sum(r[k] or 0.0 for k in parts)) for r in recent + earlier]
    return _share(marked[:len(recent)], "comparable"), _share(marked[len(recent):], "comparable")


def ratio(rows: list[dict]) -> dict:
    recent = rows[-RATIO_YEARS:]
    # the first year has no year before it for the working capital: leave it out of the earlier window
    earlier = [r for r in rows[-2 * RATIO_YEARS:-RATIO_YEARS] if not (r is rows[0] and r["working_capital"] is None)]
    now = _share(recent, "growth")
    level, before, now_same = "不明", None, None
    if len(earlier) >= 3:
        now_same, before = _comparable(recent, earlier)
        if now_same is not None and before is not None:
            band = max(RATIO_BAND * abs(before), RATIO_MIN_PT)
            level = "高い" if now_same - before >= band else "低い" if before - now_same >= band else "標準"
    capex_share = _share(recent, "capex")
    tail = [r["capex_to_dep"] for r in rows[-UNDERINVEST_YEARS:]]
    light = capex_share is not None and capex_share < ASSET_LIGHT_PCT
    under = (not light and len(tail) == UNDERINVEST_YEARS and all(t is not None and t < UNDERINVEST for t in tail))
    return {"recent": now, "earlier": before, "level": level, "years": len(recent),
            "recent_comparable": now_same,
            "span": f"{recent[0]['year']}〜{recent[-1]['year']}" if recent else "—",
            "earlier_span": f"{earlier[0]['year']}〜{earlier[-1]['year']}" if len(earlier) >= 3 else None,
            "capex_share": capex_share, "rnd_share": _share(recent, "rnd"),
            "capex_to_dep": tail[-1] if tail else None, "underinvest": under, "asset_light": light,
            "missing_rnd": any(r["rnd"] is None for r in recent),
            "missing_working_capital": any(r["working_capital"] is None for r in recent if r is not rows[0])}


def surge(rows: list[dict]) -> bool:
    recent, before = rows[-SURGE_YEARS:], rows[-SURGE_YEARS - 3:-SURGE_YEARS]
    if len(recent) < SURGE_YEARS or len(before) < 3:
        return False
    base = statistics.mean(r["growth"] for r in before)
    return base > 0 and statistics.mean(r["growth"] for r in recent) >= SURGE * base


# ---------- 投資効率 ----------

def incremental_roic(roic_rows: list[dict], tax: float, hurdle: float, first: str | None, last: str | None) -> dict:
    rows = [r for r in roic_rows if first and last and first <= r["year"] <= last]
    n = len(rows)
    base = {"rating": "不明", "value": None, "years": n, "lag": 0, "hurdle": hurdle}
    if n < MIN_YEARS:
        return {**base, "sentence": f"増分 ROIC は計算しない（会計基準をそろえた期間が {n} 年で {MIN_YEARS} 年未満）"}
    lag = LAG_YEARS if n >= 2 * AVG_YEARS + LAG_YEARS else 0
    nopat = [R._nopat(r["operating"], tax) for r in rows]
    capital = [r["invested"] for r in rows]
    start_nopat, end_nopat = statistics.mean(nopat[:AVG_YEARS]), statistics.mean(nopat[-AVG_YEARS:])
    start_cap, end_cap = statistics.mean(capital[:AVG_YEARS]), statistics.mean(capital[n - AVG_YEARS - lag:n - lag])
    d_nopat, d_cap = end_nopat - start_nopat, end_cap - start_cap
    span = f"{rows[0]['year']}〜{rows[-1]['year']}"
    lag_text = (f"投下資本は{lag}年前までの{AVG_YEARS}年平均（投資が利益になるまでの時間差）" if lag
                else "期間が短く時間差は取れない")
    out = {**base, "lag": lag, "span": span, "d_nopat": round(d_nopat), "d_capital": round(d_cap)}
    if d_cap <= SMALL_CAPITAL * start_cap:
        if d_nopat > 0:
            return {**out, "rating": "良好", "sentence": f"{span}: 投下資本をほとんど増やさずに税引後営業利益が "
                    f"{d_nopat:+,.0f} 増えた（{lag_text}）"}
        return {**out, "sentence": f"{span}: 投下資本がほとんど増えておらず、増分 ROIC に意味が無い（{lag_text}）"}
    value = round(d_nopat / d_cap * 100, 1)
    rating = "良好" if value >= hurdle else "普通" if value >= hurdle / 2 else "問題あり"
    return {**out, "rating": rating, "value": value,
            "sentence": f"{span}: 増分 ROIC {value:.1f}%（税引後営業利益の増加 {d_nopat:+,.0f} ÷ 投下資本の増加 "
                        f"{d_cap:+,.0f}、{AVG_YEARS}年平均どうし。{lag_text}）。資本コスト {hurdle:.0f}% に対して{rating}"}


def _cagr(values: list[float]) -> float | None:
    if len(values) < 2 or values[0] <= 0 or values[-1] <= 0:
        return None
    return round(((values[-1] / values[0]) ** (1 / (len(values) - 1)) - 1) * 100, 1)


def people(values: dict, sales: dict[str, float], operating: dict[str, float], years: list[str]) -> dict:
    """Headcount, operating income per employee and the parent's average salary over the newest RATIO_YEARS years."""
    staff = [(y, values["summary.employees"][y]) for y in years if y in values["summary.employees"]][-RATIO_YEARS:]
    per = [(y, operating[y] / n) for y, n in staff if y in operating and n > 0]
    salary = [(y, values["summary.average_salary"][y]) for y in years if y in values["summary.average_salary"]]
    last_year = staff[-1][0] if staff else None
    share = None
    if salary and last_year and sales.get(last_year):
        share = round(staff[-1][1] * salary[-1][1] / 1e6 / sales[last_year] * 100, 1)
    falls = 0
    for (_, a), (_, b) in zip(per, per[1:]):
        falls = falls + 1 if b < a else 0
    return {"employees": staff, "per_employee": [(y, round(v, 2)) for y, v in per], "salary": salary[-RATIO_YEARS:],
            "employees_cagr": _cagr([n for _, n in staff]), "per_employee_cagr": _cagr([v for _, v in per]),
            "falling_years": falls, "people_share": share, "intensive": share is not None and share >= PEOPLE_PCT}


def people_efficiency(p: dict) -> tuple[str, str]:
    grew = (p["employees_cagr"] or 0) > 0
    if p["falling_years"] >= PEOPLE_FALL_YEARS and grew:
        return "問題あり", (f"人員を増やした（従業員数 CAGR {p['employees_cagr']:+.1f}%）が、1人当たり営業利益が "
                         f"{p['falling_years']} 年続けて下がった")
    if p["per_employee_cagr"] is None:
        return "不明", "1人当たり営業利益の推移を計算できない"
    if grew and p["per_employee_cagr"] >= 0:
        return "良好", (f"人員（従業員数 CAGR {p['employees_cagr']:+.1f}%）と1人当たり営業利益（CAGR "
                      f"{p['per_employee_cagr']:+.1f}%）がともに伸びた")
    return "普通", (f"1人当たり営業利益の CAGR {p['per_employee_cagr']:+.1f}%、従業員数 CAGR "
                  f"{p['employees_cagr'] or 0:+.1f}%")


# ---------- 判定 ----------

def verdict(level: str, efficiency: str, underinvest: bool) -> str:
    if efficiency in ("不明", "問題あり", "普通"):
        return efficiency
    result = "普通" if level == "低い" else "良好"
    return "普通" if underinvest else result


def sentence(result: str, r: dict, efficiency: dict) -> str:
    level = {"高い": "以前より高い", "低い": "以前より低い", "標準": "以前並み", "不明": "以前と比べられない"}[r["level"]]
    share = f"{r['recent']:.1f}%" if r["recent"] is not None else "—"
    under = "。設備投資が減価償却費を下回る年が続く（投資不足）" if r["underinvest"] else ""
    return (f"成長投資は{result}: 売上に対する成長投資 {share}（{r['span']}、{level}）、"
            f"効率（{efficiency['basis']}）は{efficiency['rating']}{under}")


def _empty(result: str, text: str, **extra) -> dict:
    return {"verdict": result, "sentence": text, "rows": [], "ratio": None, "efficiency": None, "people": None,
            "notes": [], **extra}


def step5(company, s1: dict, growth_rows: list[dict], has_plan: bool) -> dict:
    """The growth investment of 手順5: {verdict, sentence, ratio, efficiency, people, rows, notes}."""
    excluded, info = SR.applies(company, {SR.FINANCIAL})
    if excluded:
        return _empty("対象外", SR.note(info, "成長投資（設備投資・運転資本）で成長を見ない（資産は貸出・運用のため）"))
    values = csv_values(company)
    sales = {r["year"]: r["sales"] for r in growth_rows if r["sales"]}
    operating = {r["year"]: r["operating_income"] for r in growth_rows if r["operating_income"] is not None}
    first, last = s1.get("first"), s1.get("last")
    years = [r["year"] for r in growth_rows if first and last and first <= r["year"] <= last]
    rows = yearly(values, sales, years)
    mkt = R.market(company)
    tax, hurdle = R.TAX[mkt], R.HURDLE[mkt]
    roic = incremental_roic(R.roic_rows(SS.self_series(company), tax, hurdle), tax, hurdle, first, last)
    staff = people(values, sales, operating, years)
    if not rows:
        return _empty("不明", "設備投資・減価償却費の時系列が無く、成長投資を計算できない",
                      efficiency={"rating": roic["rating"], "basis": "増分 ROIC", "sentence": roic["sentence"],
                                  "roic": roic}, people=staff)
    r = ratio(rows)
    notes = []
    # labour-intensive companies are asset-light; the parent's salary × the group's headcount overstates the people
    # cost of a holding company with heavy-asset subsidiaries, so a capex-heavy company stays on the ROIC
    if staff["intensive"] and r["asset_light"]:
        rating, why = people_efficiency(staff)
        efficiency = {"rating": rating, "basis": "人材", "sentence": why, "roic": roic}
        notes.append(f"人材集約型（従業員数 × 平均年間給与 ÷ 売上 {staff['people_share']:.1f}%）: 効率は人材の指標で見る"
                     "（平均年間給与は提出会社の値）")
    else:
        efficiency = {"rating": roic["rating"], "basis": "増分 ROIC", "sentence": roic["sentence"], "roic": roic}
    if efficiency["rating"] == "問題あり" and surge(rows) and has_plan:
        efficiency = {**efficiency, "rating": "不明",
                      "sentence": efficiency["sentence"] + "。直近の成長投資が過去の1.5倍以上で中期経営計画があるため"
                                                          "投資先行期とみなし、効率は次の見直しで確かめる"}
        notes.append("投資先行期: 効率の「問題あり」を不明として扱った")
    if r["asset_light"]:
        notes.append(f"設備投資が売上の {r['capex_share']:.1f}% で {ASSET_LIGHT_PCT:.0f}% 未満: 投資不足の規則は使わない")
    if r["underinvest"]:
        notes.append("減価償却費は無形資産・使用権資産（リース）の償却を含むことがあり、設備投資 ÷ 減価償却は低めに出うる")
    if r["missing_rnd"]:
        notes.append("研究開発費が取れない年がある（成長投資に 0 として数えた）")
    if r["missing_working_capital"]:
        notes.append("運転資本の増加を計算できない年がある（成長投資に 0 として数えた）")
    result = verdict(r["level"], efficiency["rating"], r["underinvest"])
    return {"verdict": result, "sentence": sentence(result, r, efficiency), "rows": rows, "ratio": r,
            "efficiency": efficiency, "people": staff, "notes": notes}
