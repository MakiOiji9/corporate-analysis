"""投資の質 (investment): every number and every judgement; the writer only classifies (themes, plans, trends).

Inputs
  data/financials.csv     capex, depreciation, R&D, acquisitions, impairment, goodwill, PP&E, construction in progress,
                          net assets, operating CF, investment securities (xbrl_financials.py / edgar.py)
  data/investments.json   the segment capex / revenue / profit (yuho_investments.py; Japanese filers only)
  the growth analysis's candidates (gr_metrics.candidates): the accounting-consistent window, the yearly sales and
                          operating income, and 手順5 (gr_invest.step5: the growth investment ratio against the past
                          and the peers, and the incremental ROIC). Those moved here from the growth verdict.

Yearly table and change points (CHANGE_RULES): capex ÷ sales against the 3 years before (SURGE_X / DROP_X), the
segment mix of capex (MIX_PT), R&D ÷ sales (RND_PT), acquisitions (MA_PCT of sales or a business combination note),
capex ÷ depreciation crossing 1 (攻め ↔ 守り), and a theme first named that year (from the writer's themes at build).

Axes (5.3 of docs/proposals/investment-analysis.md)
  ① 投資効率      gr_invest's efficiency (incremental ROIC, or the people for a labour-intensive company) with
                  (c) PP&E turnover and the segment that took the most capex (its revenue and margin)
  ② 中計との整合  the writer's class of the mid-term plan row and of each planned facility's outcome (plan_axis)
  ③ 潮流との整合  the writer's class of each theme against the industry's structural changes and policy (trend_axis)
  ④ 競合比較      gr_invest's ratio level against the past and the peers' median (高い / 同等 / 低い / 不明)
  ⑤ 失敗の履歴    (a) impairment, (b) goodwill
  ⑥ 資金と規律    (d) construction in progress, (e) capex ÷ depreciation, (f) funding beyond operating CF,
                  (g) continuity of the themes, (h) investment securities (a proxy of 政策保有株)
Verdict (final): 懸念 when ①, ⑤ or ⑥ has 問題あり; 良好 when ① 良好, ② 整合/一部, ③ 合う/一部 and no 問題あり
(④ 低い caps 良好 at 普通); 判定保留 when ① is 不明 and half or more of ②〜④ are 不明; else 普通.
"""
from __future__ import annotations

import json
import statistics

import gr_invest as V
import sector_rules as SR
from common import read_csv_rows

VERDICTS = ("良好", "普通", "懸念", "判定保留")
OK, WATCH, BAD = "問題なし", "注意", "問題あり"
SEVERITY = {OK: 0, WATCH: 1, BAD: 2, "不明": -1}
PLAN_CLASSES = ("整合", "一部", "乖離", "不明")
PLAN_OUTCOMES = ("予定どおり", "延期", "中止・縮小", "金額の膨張", "不明")
TREND_CLASSES = ("合う", "一部", "逆行", "不明")
WINDOW = 5            # years for (a) and (f)
BASE_YEARS = 3        # the years before a year that a change is measured against
SURGE_X, DROP_X = 1.5, 0.5
MIX_PT = 10.0
RND_PT = 1.0
MA_PCT = 5.0
IMPAIR_WATCH, IMPAIR_BAD, GOODWILL_IMPAIRS = 5.0, 10.0, 2
GOODWILL_WATCH, GOODWILL_BAD = 30.0, 50.0
TURNOVER_WATCH, TURNOVER_BAD = 3, 5
CIP_X, CIP_YEARS = 2.0, 3
UNDER_X, UNDER_YEARS = 0.8, 3
FUND_WATCH, FUND_BAD = 30.0, 50.0
THEME_KEEP, THEME_LOW_YEARS = 50.0, 2
SECURITIES_WATCH, SECURITIES_BAD = 10.0, 20.0
EXTRA_ITEMS = {"impairment_loss": ("impairment_loss",), "ppe": ("property_plant_and_equipment",),
               "cip": ("construction_in_progress",), "goodwill": ("goodwill",),
               "net_assets": ("net_assets", "summary.net_assets"), "cfo": ("cfo", "summary.cfo"),
               "securities": ("investment_securities",)}
# segment names in investments.json that are totals or adjustments, not a business
NOT_SEGMENT = ("ReportableSegments", "TotalOfReportableSegmentsAndOthers", "ReconcilingItems",
               "UnallocatedAmountsAndElimination")
OTHER_SEGMENT = ("OperatingSegmentsNotIncludedInReportableSegmentsAndOtherRevenueGeneratingBusinessActivities",
                 "OtherReportableSegments", "Other")


# ---------- materials ----------

def _float(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def extra_values(company) -> dict[str, dict[str, float]]:
    """{key: {YYYY-MM: value}} of EXTRA_ITEMS (the first item of each key that a year has)."""
    raw: dict[str, dict[str, float]] = {}
    for row in read_csv_rows(company.path / "data" / "financials.csv"):
        value = _float(row.get("value"))
        if value is not None:
            raw.setdefault(row.get("item", ""), {})[row["period_end"][:7]] = value
    out = {}
    for key, items in EXTRA_ITEMS.items():
        merged: dict[str, float] = {}
        for item in reversed(items):  # the first item wins
            merged.update(raw.get(item, {}))
        out[key] = merged
    return out


def load_investments(company) -> dict | None:
    path = company.path / "data" / "investments.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def segment_label(name: str) -> str:
    return "その他" if name in OTHER_SEGMENT else name


def segment_capex(invest: dict | None) -> dict[str, dict[str, float]]:
    """{YYYY-MM: {segment: capex}} of the business segments (totals and adjustments left out)."""
    out: dict[str, dict[str, float]] = {}
    for s in (invest or {}).get("segments", []):
        value = _float(s.get("value"))
        if s.get("metric") != "capex" or value is None or s.get("segment") in NOT_SEGMENT:
            continue
        year = s["period_end"][:7]
        label = segment_label(s["segment"])
        out.setdefault(year, {})[label] = out.get(year, {}).get(label, 0.0) + value
    return out


def segment_series(invest: dict | None, metric: str) -> dict[str, dict[str, float]]:
    """{segment: {YYYY-MM: value}} of a segment metric (revenue / profit)."""
    out: dict[str, dict[str, float]] = {}
    for s in (invest or {}).get("segments", []):
        value = _float(s.get("value"))
        if s.get("metric") == metric and value is not None and s.get("segment") not in NOT_SEGMENT:
            label = segment_label(s["segment"])
            out.setdefault(label, {})[s["period_end"][:7]] = value
    return out


def combination_years(invest: dict | None) -> list[str]:
    """Years whose business combination note says something (not 'no material matter')."""
    out = []
    for y in (invest or {}).get("years", []):
        block = (y.get("texts") or {}).get("business_combinations") or {}
        text = block.get("text", "")
        element = block.get("element", "")
        if text and "NATextBlock" not in element and "記載すべき重要な事項はありません" not in text \
                and "該当事項はありません" not in text:
            out.append(y["period_end"][:7])
    return out


# ---------- yearly table ----------

def _pct(part: float | None, whole: float | None) -> float | None:
    return round(part / whole * 100, 1) if part is not None and whole else None


def table(growth_rows: list[dict], extra: dict, seg: dict) -> list[dict]:
    """One row per year of gr_invest's rows (capex and depreciation known), with the shares and the segment mix."""
    rows = []
    for r in growth_rows:
        y = r["year"]
        mix_total = sum(seg.get(y, {}).values())
        rows.append({**r, "capex_share": _pct(r["capex"], r["sales"]), "rnd_share": _pct(r["rnd"], r["sales"]),
                     "acquisition_share": _pct(r["acquisition"], r["sales"]),
                     "impairment": abs(extra["impairment_loss"][y]) if y in extra["impairment_loss"] else None,
                     "goodwill": extra["goodwill"].get(y), "ppe": extra["ppe"].get(y), "cip": extra["cip"].get(y),
                     "net_assets": extra["net_assets"].get(y), "cfo": extra["cfo"].get(y),
                     "securities": extra["securities"].get(y),
                     "mix": {k: round(v / mix_total * 100, 1) for k, v in seg.get(y, {}).items()} if mix_total else {}})
    return rows


# ---------- change points ----------

def _base(rows: list[dict], i: int, key: str) -> float | None:
    values = [r[key] for r in rows[max(0, i - BASE_YEARS):i] if r[key] is not None]
    return statistics.mean(values) if len(values) == BASE_YEARS else None


def change_points(rows: list[dict], ma_note_years: list[str] = ()) -> list[dict]:
    """[{year, kind, text}] in year order."""
    out = []
    for i, r in enumerate(rows):
        y = r["year"]
        base = _base(rows, i, "capex_share")
        if base and r["capex_share"] is not None:
            if r["capex_share"] >= SURGE_X * base:
                out.append({"year": y, "kind": "投資の急増", "text": f"設備投資 ÷ 売上 {r['capex_share']:.1f}%（前3年平均 "
                            f"{base:.1f}% の {r['capex_share'] / base:.1f}倍）"})
            elif r["capex_share"] <= DROP_X * base:
                out.append({"year": y, "kind": "投資の急減", "text": f"設備投資 ÷ 売上 {r['capex_share']:.1f}%（前3年平均 "
                            f"{base:.1f}% の {r['capex_share'] / base:.1f}倍）"})
        if i and r["mix"] and rows[i - 1]["mix"]:
            moved = [(k, r["mix"].get(k, 0.0) - rows[i - 1]["mix"].get(k, 0.0))
                     for k in sorted(set(r["mix"]) | set(rows[i - 1]["mix"]))]
            big = [(k, d) for k, d in moved if abs(d) >= MIX_PT]
            if big:
                out.append({"year": y, "kind": "配分の変化", "text": "セグメント別の設備投資の構成比: " + "、".join(
                    f"{k} {d:+.1f}pt" for k, d in big)})
        rbase = _base(rows, i, "rnd_share")
        if rbase is not None and r["rnd_share"] is not None and abs(r["rnd_share"] - rbase) >= RND_PT:
            out.append({"year": y, "kind": "研究開発の変化", "text": f"研究開発費 ÷ 売上 {r['rnd_share']:.1f}%（前3年平均 "
                        f"{rbase:.1f}% から {r['rnd_share'] - rbase:+.1f}pt）"})
        share = r["acquisition_share"]
        if (share is not None and share >= MA_PCT) or y in ma_note_years:
            amount = f"子会社の取得 {r['acquisition']:,.0f}（売上の {share:.1f}%）" if share else "子会社の取得の支出なし"
            note = "、企業結合の注記あり" if y in ma_note_years else ""
            out.append({"year": y, "kind": "M&A", "text": amount + note})
        if i and r["capex_to_dep"] is not None and rows[i - 1]["capex_to_dep"] is not None:
            a, b = rows[i - 1]["capex_to_dep"], r["capex_to_dep"]
            if (a < 1.0) != (b < 1.0):
                phase = "守り → 攻め" if b >= 1.0 else "攻め → 守り"
                out.append({"year": y, "kind": "局面の切り替わり", "text": f"設備投資 ÷ 減価償却費 {a:.2f} → {b:.2f}（{phase}）"})
    return out


def theme_points(year_themes: dict[str, list[str]]) -> list[dict]:
    """A theme named for the first time in a year (the first year of the table has nothing to compare with)."""
    out, seen = [], set()
    for i, year in enumerate(sorted(year_themes)):
        themes = year_themes[year]
        new = [t for t in themes if t not in seen]
        if i and new:
            out.append({"year": year, "kind": "新しい投資テーマ", "text": "、".join(new)})
        seen.update(themes)
    return out


# ---------- (a)〜(h) ----------

def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


GOODWILL_HIT_SHARE = 0.5      # the impairment covers at least half of the year's fall of goodwill
GOODWILL_HIT_EQUITY = 0.5     # and is at least 0.5% of net assets (FX moves and J-GAAP amortisation are not hits)


def _goodwill_hit(prev: dict, cur: dict, equity: float) -> bool:
    """A year counted as a goodwill impairment (the statements carry no separate goodwill impairment line): goodwill
    fell, and the year's impairment loss covers most of the fall and is material."""
    if not (cur["impairment"] and prev["goodwill"] and cur["goodwill"] is not None):
        return False
    fall = prev["goodwill"] - cur["goodwill"]
    return (fall > 0 and cur["impairment"] >= GOODWILL_HIT_SHARE * fall
            and cur["impairment"] >= GOODWILL_HIT_EQUITY / 100 * equity)


def impairment(rows: list[dict]) -> dict:
    recent = rows[-WINDOW:]
    known = [r for r in recent if r["impairment"] is not None]
    equity = next((r["net_assets"] for r in reversed(rows) if r["net_assets"]), None)
    if not equity or not recent:
        return _check("(a) 減損の履歴", "不明", "純資産か年次の表が無く計算できない")
    total = sum(r["impairment"] for r in known)
    share = total / equity * 100
    gw = sum(1 for prev, cur in zip(rows, rows[1:]) if cur in recent and _goodwill_hit(prev, cur, equity))
    status = BAD if share >= IMPAIR_BAD or gw >= GOODWILL_IMPAIRS else WATCH if share >= IMPAIR_WATCH else OK
    span = f"{recent[0]['year']}〜{recent[-1]['year']}"
    note = "" if len(known) == len(recent) else f"（減損損失の記載がある年は {len(known)} 年。無い年は 0 として数えた）"
    return {**_check("(a) 減損の履歴", status, f"{span} の減損損失の累計 {total:,.0f} ÷ 純資産 {equity:,.0f} = "
                     f"{share:.1f}%、のれんの減損とみなした年 {gw} 回（のれんが減り、減損損失がその半分以上かつ純資産の 0.5% 以上）{note}"), "share": round(share, 1), "goodwill_hits": gw}


def goodwill(rows: list[dict], impaired: bool) -> dict:
    last = next((r for r in reversed(rows) if r["net_assets"] and r["goodwill"] is not None), None)
    if not last:
        return _check("(b) のれん", "不明", "のれんか純資産が無い")
    share = last["goodwill"] / last["net_assets"] * 100
    status = BAD if share >= GOODWILL_BAD and impaired else WATCH if share >= GOODWILL_WATCH else OK
    return {**_check("(b) のれん", status, f"{last['year']}: のれん {last['goodwill']:,.0f} ÷ 純資産 "
                     f"{last['net_assets']:,.0f} = {share:.1f}%"), "share": round(share, 1)}


def _falling_run(values: list[float]) -> int:
    run = 0
    for a, b in zip(values, values[1:]):
        run = run + 1 if b < a else 0
    return run


def turnover(rows: list[dict], growth_rows: list[dict]) -> dict:
    pairs = [(r["year"], r["sales"] / r["ppe"]) for r in rows if r["sales"] and r["ppe"]]
    if len(pairs) < 3:
        return _check("(c) 有形固定資産回転率", "不明", "有形固定資産の年が3年未満")
    run = _falling_run([v for _, v in pairs])
    margins = {g["year"]: g["operating_income"] / g["sales"] * 100 for g in growth_rows
               if g.get("sales") and g.get("operating_income") is not None}
    years = [y for y, _ in pairs][-TURNOVER_BAD - 1:]
    margin_down = (years[0] in margins and years[-1] in margins and margins[years[-1]] < margins[years[0]])
    status = BAD if run >= TURNOVER_BAD and margin_down else WATCH if run >= TURNOVER_WATCH else OK
    return {**_check("(c) 有形固定資産回転率", status, f"売上 ÷ 有形固定資産 {pairs[0][1]:.2f}（{pairs[0][0]}）→ "
                     f"{pairs[-1][1]:.2f}（{pairs[-1][0]}）、直近まで {run} 年続けて低下"
                     + ("、営業利益率も低下" if margin_down and run >= TURNOVER_BAD else "")), "falling_years": run}


def construction(rows: list[dict]) -> dict:
    ratios = [(r["year"], r["cip"] / r["ppe"] * 100) for r in rows if r["cip"] is not None and r["ppe"]]
    if len(ratios) < BASE_YEARS + 1:
        return _check("(d) 建設仮勘定", "不明", "建設仮勘定の年が4年未満")
    high = []
    for i in range(BASE_YEARS, len(ratios)):
        base = statistics.mean(v for _, v in ratios[i - BASE_YEARS:i])
        high.append(base > 0 and ratios[i][1] >= CIP_X * base)
    run = 0
    for h in high:
        run = run + 1 if h else 0
    status = BAD if run >= CIP_YEARS else WATCH if high[-1] else OK
    return {**_check("(d) 建設仮勘定", status, f"建設仮勘定 ÷ 有形固定資産 {ratios[-1][1]:.1f}%（{ratios[-1][0]}）、"
                     f"前3年平均の {CIP_X:.0f}倍以上が直近まで {run} 年"), "run": run}


def under_investment(rows: list[dict], asset_light: bool) -> dict:
    tail = [r["capex_to_dep"] for r in rows[-UNDER_YEARS:]]
    if len(tail) < UNDER_YEARS or any(t is None for t in tail):
        return _check("(e) 設備投資 ÷ 減価償却費", "不明", "直近3年の設備投資・減価償却費が揃わない")
    text = "、".join(f"{t:.2f}" for t in tail)
    if asset_light:
        return _check("(e) 設備投資 ÷ 減価償却費", OK, f"直近3年 {text}（設備が少ない業態のため投資不足の規則は使わない）")
    status = WATCH if all(t < UNDER_X for t in tail) else OK
    return _check("(e) 設備投資 ÷ 減価償却費", status, f"直近3年 {text}" + ("（3年続けて 0.8倍未満: 投資不足）"
                                                                       if status == WATCH else ""))


def funding(rows: list[dict], efficiency: str) -> dict:
    recent = [r for r in rows[-WINDOW:] if r["cfo"] is not None]
    if len(recent) < 3:
        return _check("(f) 資金源", "不明", "営業CF の年が3年未満")
    invested = sum(r["capex"] + r["acquisition"] for r in recent)
    cfo = sum(r["cfo"] for r in recent)
    if invested <= 0:
        return _check("(f) 資金源", OK, "設備投資・子会社の取得が無い")
    gap = max(0.0, invested - cfo) / invested * 100
    status = BAD if gap >= FUND_BAD and efficiency in ("普通", "問題あり", "不明") else WATCH if gap >= FUND_WATCH else OK
    return {**_check("(f) 資金源", status, f"{recent[0]['year']}〜{recent[-1]['year']} の設備投資＋子会社の取得 "
                     f"{invested:,.0f} に対し営業CF {cfo:,.0f}。営業CF で賄えなかった割合 {gap:.1f}%"), "gap": round(gap, 1)}


def continuity(year_themes: dict[str, list[str]] | None) -> dict:
    if not year_themes or len(year_themes) < 2:
        return _check("(g) 重点テーマの継続性", "不明", "年ごとの投資テーマが2年分無い（build で執筆者の分類から計算）")
    years = sorted(year_themes)
    shares = []
    for a, b in zip(years, years[1:]):
        now = year_themes[b]
        if now:
            shares.append((b, len(set(now) & set(year_themes[a])) / len(now) * 100))
    low = [y for y, s in shares if s < THEME_KEEP]
    status = WATCH if len(low) >= THEME_LOW_YEARS else OK
    text = "、".join(f"{y} {s:.0f}%" for y, s in shares)
    return {**_check("(g) 重点テーマの継続性", status, f"前年から続くテーマの割合: {text}"
                     + (f"（50%未満の年 {len(low)} 回）" if low else "")), "low_years": low}


def securities(rows: list[dict]) -> dict:
    have = [r for r in rows if r["securities"] is not None and r["net_assets"]]
    if len(have) < 2:
        return _check("(h) 政策保有株（投資有価証券で代用）", "不明", "投資有価証券か純資産が2年分無い")
    last, first = have[-1], have[max(0, len(have) - 1 - BASE_YEARS)]
    share = last["securities"] / last["net_assets"] * 100
    grew = last["securities"] > first["securities"]
    status = BAD if share >= SECURITIES_BAD and grew else WATCH if share >= SECURITIES_WATCH and grew else OK
    return {**_check("(h) 政策保有株（投資有価証券で代用）", status,
                     f"{last['year']}: 投資有価証券 ÷ 純資産 {share:.1f}%（{first['year']} の {first['securities']:,.0f} → "
                     f"{last['securities']:,.0f}、{'増加' if grew else '増加なし'}。銘柄ごとの政策保有株は brief の"
                     "「株式の保有状況」）"), "share": round(share, 1)}


def worst(checks: list[dict], cap: str | None = None) -> str:
    known = [c["status"] for c in checks if c["status"] != "不明"]
    if not known:
        return "不明"
    level = max(known, key=lambda s: SEVERITY[s])
    return WATCH if cap == WATCH and level == BAD else level


# ---------- axes ----------

def efficiency_axis(s5: dict, turnover_check: dict, top: dict | None) -> dict:
    eff = (s5.get("efficiency") or {})
    rating = eff.get("rating") or "不明"
    notes = []
    if rating == "良好" and turnover_check["status"] == BAD:
        rating = "普通"
        notes.append("有形固定資産回転率が下がり続け利益率も低下: 良好を普通に")
    if rating == "良好" and top and top.get("margin_change") is not None and top["margin_change"] < 0:
        rating = "普通"
        notes.append(f"設備投資が最も多い {top['segment']} の利益率が下がった: 良好を普通に")
    sentence = eff.get("sentence") or s5.get("sentence", "")
    return {"rating": rating, "basis": eff.get("basis") or "—", "notes": notes,
            "sentence": sentence + ("。" + "。".join(notes) if notes else "")}


def top_segment(seg: dict[str, dict[str, float]], revenue: dict, profit: dict, years: list[str]) -> dict | None:
    """The segment with the most capex over the newest WINDOW years, and its revenue CAGR and margin change."""
    window = [y for y in years if y in seg][-WINDOW:]
    if not window:
        return None
    totals: dict[str, float] = {}
    for y in window:
        for k, v in seg[y].items():
            totals[k] = totals.get(k, 0.0) + v
    name = max(totals, key=totals.get)
    rev, pro = revenue.get(name, {}), profit.get(name, {})
    span = [y for y in sorted(rev) if window[0] <= y <= window[-1] and y in pro and rev[y]]
    out = {"segment": name, "capex": round(totals[name]), "share": round(totals[name] / sum(totals.values()) * 100, 1),
           "span": f"{window[0]}〜{window[-1]}", "revenue_cagr": None, "margin_change": None}
    if len(span) >= 2:
        a, b = span[0], span[-1]
        n = (int(b[:4]) - int(a[:4])) or 1
        if rev[a] > 0 and rev[b] > 0:
            out["revenue_cagr"] = round(((rev[b] / rev[a]) ** (1 / n) - 1) * 100, 1)
        out["margin_change"] = round(pro[b] / rev[b] * 100 - pro[a] / rev[a] * 100, 1)
        out["margin_span"] = f"{a}〜{b}"
    return out


def peer_axis(ratio: dict | None) -> dict:
    if not ratio:
        return {"rating": "不明", "sentence": "成長投資の比率を計算できない"}
    level = {"高い": "高い", "低い": "低い", "標準": "同等"}.get(ratio["level"], "不明")
    peer = (f"同業の中央値 {ratio['peer_median']:.1f}%（{ratio['peer_count']}社）に対し自社 {ratio['peer_own']:.1f}%"
            if ratio.get("peer_median") is not None and ratio.get("peer_own") is not None else "同業の材料なし")
    past = (f"以前（{ratio['earlier_span']}）{ratio['earlier']:.1f}% → 直近 {ratio['recent_comparable']:.1f}%"
            if ratio.get("earlier") is not None and ratio.get("recent_comparable") is not None else "以前の5年と比べられない")
    return {"rating": level, "sentence": f"売上に対する成長投資（{ratio['span']}）: {peer}、{past}"}


def plan_axis(mtp_class: str | None, outcomes: list[str]) -> dict:
    """② from the writer's classes: the mid-term plan row and the outcome of each planned facility."""
    judged = [o for o in outcomes if o != "不明"]
    slipped = [o for o in judged if o in ("延期", "中止・縮小", "金額の膨張")]
    cls = mtp_class if mtp_class in PLAN_CLASSES else "不明"
    if cls == "乖離" or (judged and len(slipped) * 2 >= len(judged) and len(judged) >= 2):
        rating = "乖離"
    elif cls == "不明" and not judged:
        rating = "不明"
    elif cls == "整合" and not slipped:
        rating = "整合"
    else:
        rating = "一部"
    plans = f"設備計画 {len(judged)} 件のうち予定どおりでないもの {len(slipped)} 件" if judged else "設備計画の照合なし"
    return {"rating": rating, "sentence": f"中期経営計画との照合 {cls}、{plans}"}


def trend_axis(classes: list[str]) -> dict:
    judged = [c for c in classes if c in ("合う", "一部", "逆行")]
    if not judged:
        return {"rating": "不明", "sentence": "潮流と照合できたテーマなし"}
    fit, against = judged.count("合う"), judged.count("逆行")
    if against and not fit:
        rating = "逆行"
    elif not against and fit * 2 >= len(judged):
        rating = "合う"
    else:
        rating = "一部"
    return {"rating": rating, "sentence": f"照合できたテーマ {len(judged)} 件（合う {fit}・一部 {judged.count('一部')}・"
                                          f"逆行 {against}）"}


def final(axes: dict) -> tuple[str, str]:
    e, p, t, c, f, d = (axes[k]["rating"] for k in ("efficiency", "plan", "trend", "peer", "failure", "discipline"))
    bad = [name for name, v in (("投資効率", e), ("失敗の履歴", f), ("資金と規律", d)) if v == BAD]
    if bad:
        return "懸念", f"{'・'.join(bad)}が問題あり"
    unknown = sum(1 for v in (p, t, c) if v == "不明")
    if e == "不明" and unknown * 2 >= 3:
        return "判定保留", "投資効率が不明で、中計・潮流・競合の照合も半分以上が不明"
    if e == "良好" and p in ("整合", "一部") and t in ("合う", "一部"):
        if c == "低い":
            return "普通", "投資効率は良好だが、競合・以前と比べて投資が低い（投資を抑えて利益率を保っている可能性）"
        return "良好", f"投資効率 良好、中計との整合 {p}、潮流との整合 {t}、失敗の履歴・資金と規律に問題なし"
    why = [f"投資効率 {e}", f"中計との整合 {p}", f"潮流との整合 {t}"]
    return "普通", "、".join(why) + "（良好の条件を満たさない）"


# ---------- all together ----------

def financial(company) -> tuple[bool, str]:
    excluded, info = SR.applies(company, {SR.FINANCIAL})
    return excluded, (SR.note(info, "設備投資・M&A の効率で投資の質を見ない（資産は貸出・運用のため）") if excluded else "")


def candidates(company, growth_cands: dict, invest: dict | None, year_themes: dict[str, list[str]] | None = None,
               mtp_class: str | None = None, outcomes: list[str] = (), trend_classes: list[str] = ()) -> dict:
    """Every number of the investment md. The writer's classes (themes per year, the plan row, the planned
    facilities' outcomes, the themes against the trends) are None / empty at prepare and parsed from the md at build."""
    s5 = growth_cands["step5"]
    excluded, why = financial(company)
    extra = extra_values(company)
    seg = segment_capex(invest)
    rows = table(s5.get("rows") or [], extra, seg)
    ratio = s5.get("ratio")
    years = [r["year"] for r in rows]
    top = top_segment(seg, segment_series(invest, "revenue"), segment_series(invest, "profit"), years)
    a = impairment(rows) if rows else _check("(a) 減損の履歴", "不明", "年次の表が無い")
    b = goodwill(rows, a.get("share", 0) >= IMPAIR_WATCH or a.get("goodwill_hits", 0) > 0) if rows else \
        _check("(b) のれん", "不明", "年次の表が無い")
    c = turnover(rows, growth_cands["rows"])
    eff = efficiency_axis(s5, c, top)
    checks = {"a": a, "b": b, "c": c, "d": construction(rows),
              "e": under_investment(rows, bool(ratio and ratio.get("asset_light"))),
              "f": funding(rows, eff["rating"]), "g": continuity(year_themes), "h": securities(rows)}
    failure = worst([a, b])
    discipline = worst([checks[k] for k in ("d", "f", "h")] + [
        dict(checks[k], status=WATCH if checks[k]["status"] == BAD else checks[k]["status"]) for k in ("e", "g")])
    axes = {"efficiency": eff, "plan": plan_axis(mtp_class, list(outcomes)), "trend": trend_axis(list(trend_classes)),
            "peer": peer_axis(ratio),
            "failure": {"rating": failure, "sentence": f"{a['detail']}。{b['detail']}"},
            "discipline": {"rating": discipline, "sentence": "。".join(checks[k]["detail"] for k in "defgh")}}
    points = change_points(rows, combination_years(invest)) + theme_points(year_themes or {})
    points.sort(key=lambda p: p["year"])
    if excluded:
        verdict, reason = "判定保留", why
    elif not rows:
        verdict, reason = "判定保留", "設備投資・減価償却費の時系列が無く、投資の表を作れない"
    else:
        verdict, reason = final(axes)
    return {"rows": rows, "points": points, "checks": checks, "axes": axes, "top_segment": top, "ratio": ratio,
            "step5": s5, "verdict": verdict, "why": reason, "excluded": excluded,
            "plan_years": plan_years(invest), "has_texts": bool(invest and invest.get("years"))}


def plan_years(invest: dict | None) -> list[dict]:
    """[{year, next}] of the reports whose 設備の新設計画 names a plan, paired with the next report (where its outcome
    shows). The newest report has no next one yet and is left out."""
    years = (invest or {}).get("years", [])
    out = []
    for cur, nxt in zip(years, years[1:]):
        text = ((cur.get("texts") or {}).get("planned_facilities") or {}).get("text", "")
        if text and "重要な設備の新設" not in text[:60] and ("計画" in text) and len(text) > 200:
            out.append({"year": cur["period_end"][:7], "next": nxt["period_end"][:7]})
    return out[-3:]
