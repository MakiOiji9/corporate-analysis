"""Every judgement of 企業分析フレームワーク.md 2-4 (キャッシュフロー分析). FCF = 営業CF + 投資CF.

  The years: the newest MAX_YEARS fiscal years with an operating CF (at least MIN_YEARS for 手順1).
  手順1 (営業CF の安定性): 全年プラス -> 良好 / マイナスが1回で、翌年にプラスへ戻り、直近年でない (一時要因の
    代理指標) -> 普通 / マイナスが2回以上、または1回でも直近年か翌年に戻っていない -> 懸念
  手順2 (FCF の創出力, the newest WINDOW years with FCF): 累計プラスで過半数の年がプラス -> 良好 / 累計プラスで
    マイナスの年が多い -> 普通 / 累計マイナス: 成長投資期の代理指標 (投資CF の流出が営業CF を超えた年があり、
    売上 CAGR >= GROWTH_CAGR、直近の営業CF > 期初の営業CF) を満たせば 普通、満たさなければ 懸念
  手順3 (利益の質, WINDOW years): 営業CF ÷ 純利益 の平均 (純損失の年があれば 累計営業CF ÷ 累計純利益):
    >= 1.0 良好 / >= 0.8 普通 / < 0.8 懸念 / 累計純利益 <= 0 -> 判定不能 (純損失). The growth of receivables and
    inventories against sales is always shown; above the sales growth it is flagged when 手順3 is 懸念.
  手順4 (CF パターン): each year's signs (営業・投資・財務) rated by the framework's table (営業CF マイナスの年は
    懸念, (+,+,+) は 普通); the most frequent rating of the newest WINDOW years (at least PATTERN_MIN_YEARS),
    a tie going to the more conservative one.
  手順5 (株主還元の持続性, WINDOW years): 還元額 = 配当金の支払額 + 自己株式の取得. 累計還元 > 累計FCF and 還元 >
    FCF in OVER_YEARS years or more -> 注意 / otherwise 問題なし / no return at all -> 対象外 / no data -> 不明
  手順6 (結論): 懸念: 手順1〜4のいずれかが懸念 / 判定保留: 手順1・2・4、または純損失以外の理由で手順3を判定できない /
    良好: 手順1〜4がすべて良好で手順5が問題なし・対象外 / 普通: それ以外
"""
from __future__ import annotations

import json
from collections import Counter

import an_common as A
import cf_inputs as I
import cf_series as S

MIN_YEARS, MAX_YEARS = 5, 10
WINDOW = 5  # 手順2〜5 は直近5年
PATTERN_MIN_YEARS = 3
GROWTH_CAGR = 5.0  # % 成長投資期とみなす売上 CAGR（2-2 の高成長の基準）
GOOD_RATIO, FAIR_RATIO = 1.0, 0.8
RATIO_NEAR = 0.05  # 営業CF対純利益比率が基準からこの幅以内なら境界
FCF_NEAR_SHARE = 0.05  # 累計FCF が累計営業CF の絶対値のこの割合以内なら境界
RETURN_NEAR_SHARE = 0.10  # 累計還元と累計FCF の差が累計FCF のこの割合以内なら境界
UNIT_JUMP = 100  # 隣り合う年の営業CF がこの倍率を超えて違えば単位の読み違いを疑う
OVER_YEARS = 3
RATING_ORDER = ("懸念", "普通", "良好")  # conservative first (a tie goes to the left)
PATTERNS = {
    ("+", "−", "−"): ("良好", "本業で稼ぎ、投資と返済・還元ができている"),
    ("+", "−", "+"): ("普通", "本業で稼ぎつつ、借入でも積極投資（成長期。投資成果を要確認）"),
    ("+", "+", "−"): ("普通", "資産売却で返済している（事業再編期。理由を要確認）"),
    ("+", "+", "+"): ("普通", "営業・投資・財務とも流入（資金を積み上げている。理由を要確認）"),
    ("−", "+", "+"): ("懸念", "本業で稼げず、資産売却と借入で凌いでいる"),
    ("−", "−", "+"): ("懸念", "本業で稼げず、借入・増資で投資している"),
    ("−", "+", "−"): ("懸念", "本業で稼げず、資産売却で返済している"),
    ("−", "−", "−"): ("懸念", "本業で稼げず、手元資金を取り崩している"),
}
OWN_UNAVAILABLE = ("CFの財務時系列", "収益性の財務時系列")  # collect-filings reports a short history under these
OWN_ITEM = f"財務時系列: 営業CF・投資CF・財務CF・当期純利益（{MIN_YEARS}年以上）"
RETURN_UNAVAILABLE = "株主還元"
RETURN_ITEM = f"財務時系列: 株主還元（配当金の支払額・自己株式の取得、{WINDOW}年）"


# ---------- rows ----------

def _v(series: dict, field: str, year: str) -> float | None:
    value = series[field].get(year)
    return value.value if value else None


def cf_rows(series: dict) -> list[dict]:
    """One row per fiscal year with an operating CF, newest MAX_YEARS, oldest first."""
    rows = []
    for year in sorted(series["cfo"])[-MAX_YEARS:]:
        cfo, cfi, ni = _v(series, "cfo", year), _v(series, "cfi", year), _v(series, "net_income", year)
        used = [series[f][year] for f in ("cfo", "cfi", "cff", "net_income") if year in series[f]]
        rows.append({"year": year, "cfo": cfo, "cfi": cfi, "cff": _v(series, "cff", year),
                     "fcf": cfo + cfi if cfi is not None else None, "net_income": ni,
                     "ratio": cfo / ni if ni is not None and ni > 0 else None,
                     "sales": _v(series, "sales", year), "capex": _v(series, "capex", year),
                     "acquisitions": _v(series, "acquisitions", year),
                     "dividends": _v(series, "dividends", year), "buybacks": _v(series, "buybacks", year),
                     "primary": all(v.primary for v in used), "source": series["cfo"][year].source})
    return rows


def cagr(first: float | None, last: float | None, years: int) -> float | None:
    """% per year; None when either end is missing or not positive."""
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return ((last / first) ** (1 / years) - 1) * 100


def _span_years(first: str, last: str) -> int:
    return round((int(last[:4]) * 12 + int(last[5:7]) - int(first[:4]) * 12 - int(first[5:7])) / 12)


def fmt_amount(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


# ---------- 手順1 ----------

def step1(rows: list[dict]) -> dict:
    negatives = [i for i, r in enumerate(rows) if r["cfo"] <= 0]
    years = [rows[i]["year"] for i in negatives]
    base = {"years": len(rows), "negative_years": years,
            "first": rows[0]["year"] if rows else None, "last": rows[-1]["year"] if rows else None}
    if len(rows) < MIN_YEARS:
        return {**base, "rating": None, "basis": f"営業CF が取れた年が {len(rows)} 年で {MIN_YEARS} 年に満たない",
                "sentence": f"営業CF が取れた年が{len(rows)}年で、{MIN_YEARS}年に満たず判定できない"}
    span = f"{len(rows)}年（{rows[0]['year']}〜{rows[-1]['year']}）"
    if not negatives:
        rating, why = "良好", "すべての年がプラス"
    elif len(negatives) == 1 and negatives[0] < len(rows) - 1 and rows[negatives[0] + 1]["cfo"] > 0 \
            and _span_years(rows[negatives[0]]["year"], rows[negatives[0] + 1]["year"]) == 1:
        rating, why = "普通", f"マイナスは {years[0]} の1回で、翌年にプラスへ戻った（一時要因とみなす）"
    elif len(negatives) == 1:
        rating = "懸念"
        why = (f"マイナスは {years[0]} の1回だが直近年で、回復を確認できない" if negatives[0] == len(rows) - 1
               else f"マイナスは {years[0]} の1回だが、翌年にプラスへ戻ったことを確認できない（翌年がマイナスか、翌年の値が無い）")
    else:
        rating, why = "懸念", f"マイナスが {len(negatives)} 回（{'、'.join(years)}）"
    return {**base, "rating": rating, "basis": why, "sentence": f"営業CF は{span}で、{why}。{rating}"}


# ---------- 手順2 ----------

def growth_phase(window: list[dict]) -> dict:
    """成長投資期の代理指標: an investing outflow above the operating CF in some year, sales CAGR >= GROWTH_CAGR
    and the latest operating CF above the first one."""
    heavy = [r["year"] for r in window if r["cfi"] < 0 and -r["cfi"] > r["cfo"]]
    growth = cagr(window[0]["sales"], window[-1]["sales"], _span_years(window[0]["year"], window[-1]["year"]))
    rising = window[-1]["cfo"] > window[0]["cfo"]
    met = bool(heavy) and growth is not None and growth >= GROWTH_CAGR and rising
    growth_text = "—（売上高が取れない）" if growth is None else f"{growth:.1f}%"
    text = (f"投資CF の流出が営業CF を超えた年 {'、'.join(heavy) or 'なし'} / 売上 CAGR {growth_text}"
            f"（基準 {GROWTH_CAGR:.0f}%以上） / 営業CF {fmt_amount(window[0]['cfo'])} → {fmt_amount(window[-1]['cfo'])}"
            f"（{'増加' if rising else '増加していない'}）")
    return {"met": met, "heavy_years": heavy, "sales_cagr": None if growth is None else round(growth, 1),
            "cfo_rising": rising, "text": text}


def step2(rows: list[dict]) -> dict:
    window = [r for r in rows if r["fcf"] is not None][-WINDOW:]
    if len(window) < WINDOW:
        return {"rating": None, "window": [r["year"] for r in window], "total": None, "growth": None,
                "positive_years": None,
                "basis": f"FCF（営業CF と投資CF）が取れた年が {len(window)} 年で {WINDOW} 年に満たない",
                "sentence": f"FCF が取れた年が{len(window)}年で、{WINDOW}年累計を計算できない"}
    total = sum(r["fcf"] for r in window)
    positive = sum(1 for r in window if r["fcf"] > 0)
    growth = growth_phase(window)
    summary = f"{WINDOW}年累計 {fmt_amount(total)}、プラスの年 {positive}/{WINDOW}"
    if total > 0 and positive > WINDOW / 2:
        rating, why = "良好", f"{summary}（累計プラスで過半数の年がプラス）"
    elif total > 0:
        rating, why = "普通", f"{summary}（累計プラスだがマイナスの年が多い）"
    elif growth["met"]:
        rating, why = "普通", f"{summary}（累計マイナスだが成長投資期の条件を満たす）"
    else:
        rating, why = "懸念", f"{summary}（累計マイナスで、成長投資期の条件を満たさない）"
    return {"rating": rating, "window": [r["year"] for r in window], "total": total, "positive_years": positive,
            "growth": growth, "basis": why,
            "sentence": f"FCF は{window[0]['year']}〜{window[-1]['year']}の{why}。{rating}"}


# ---------- 手順3 ----------

def working_capital(series: dict, years: list[str]) -> list[dict]:
    """Sales, receivables and inventories: the first and last value within the years and the growth per year."""
    out = []
    for field, name in (("sales", "売上高"), ("receivables", "売上債権"), ("inventories", "棚卸資産")):
        known = [y for y in years if y in series[field]]
        first = known[0] if known else None
        last = known[-1] if len(known) >= 2 else None
        growth = cagr(_v(series, field, first), _v(series, field, last), _span_years(first, last)) if last else None
        out.append({"field": field, "name": name, "first_year": first, "last_year": last,
                    "first": _v(series, field, first) if first else None,
                    "last": _v(series, field, last) if last else None,
                    "cagr": None if growth is None else round(growth, 1)})
    return out


def step3(rows: list[dict], series: dict) -> dict:
    window = [r for r in rows if r["net_income"] is not None][-WINDOW:]
    years = [r["year"] for r in window]
    base = {"window": years, "working_capital": working_capital(series, years), "loss": False, "ratio": None,
            "method": None, "flagged": []}
    if len(window) < WINDOW:
        return {**base, "rating": None,
                "basis": f"営業CF と当期純利益が揃った年が {len(window)} 年で {WINDOW} 年に満たない",
                "sentence": f"営業CF と当期純利益が揃った年が{len(window)}年で、{WINDOW}年平均を計算できない"}
    if all(r["net_income"] > 0 for r in window):
        ratio, method = sum(r["ratio"] for r in window) / len(window), f"{WINDOW}年平均"
    else:
        total_ni = sum(r["net_income"] for r in window)
        if total_ni <= 0:
            return {**base, "rating": None, "loss": True, "method": "累計",
                    "basis": f"{WINDOW}年累計の当期純利益が {fmt_amount(total_ni)} でマイナス（純損失）",
                    "sentence": f"{WINDOW}年累計の当期純利益がマイナスで、営業CF対純利益比率は判定できない（純損失）"}
        ratio, method = sum(r["cfo"] for r in window) / total_ni, f"{WINDOW}年累計（純損失の年を含むため）"
    rating = "良好" if ratio >= GOOD_RATIO else "普通" if ratio >= FAIR_RATIO else "懸念"
    wc = base["working_capital"]
    sales_growth = wc[0]["cagr"]
    flagged = [w["name"] for w in wc[1:] if rating == "懸念" and w["cagr"] is not None and sales_growth is not None
               and w["cagr"] > sales_growth]
    flag_text = (f"。{'・'.join(flagged)}の増加率が売上高を上回る（売れていない在庫・回収できていない売上の可能性。要確認）"
                 if flagged else "")
    return {**base, "rating": rating, "ratio": round(ratio, 2), "method": method, "flagged": flagged,
            "basis": f"営業CF対純利益比率 {ratio:.2f}倍（{method}。1.0倍以上 良好 / 0.8倍以上 普通）{flag_text}",
            "sentence": f"営業CF対純利益比率は{method}で{ratio:.2f}倍。{rating}{flag_text}"}


# ---------- 手順4 ----------

def _sign(value: float) -> str:
    return "+" if value > 0 else "−"


def pattern_rows(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if r["cfi"] is None or r["cff"] is None:
            continue
        signs = (_sign(r["cfo"]), _sign(r["cfi"]), _sign(r["cff"]))
        rating, state = PATTERNS[signs]
        out.append({"year": r["year"], "signs": list(signs), "rating": rating, "state": state})
    return out


def step4(rows: list[dict]) -> dict:
    window = pattern_rows(rows)[-WINDOW:]
    if len(window) < PATTERN_MIN_YEARS:
        return {"rating": None, "rows": window, "counts": {},
                "basis": f"営業・投資・財務CF が揃った年が {len(window)} 年で {PATTERN_MIN_YEARS} 年に満たない",
                "sentence": f"3つの CF が揃った年が{len(window)}年で、パターンを判定できない"}
    counts = Counter(r["rating"] for r in window)
    top = max(counts.values())
    rating = next(r for r in RATING_ORDER if counts.get(r) == top)
    count_text = "、".join(f"{r} {counts[r]}年" for r in RATING_ORDER if counts.get(r))
    latest = window[-1]
    why = f"直近{len(window)}年の評価が {count_text}（最も多い評価を採る。同数なら保守的な方）"
    return {"rating": rating, "rows": window, "counts": dict(counts), "basis": why,
            "sentence": (f"CF パターンは{why}で{rating}。直近 {latest['year']} は（{'、'.join(latest['signs'])}）"
                         f"{latest['state']}")}


# ---------- 手順5 ----------

def return_rows(rows: list[dict]) -> list[dict]:
    """Per year: dividends + buybacks (a missing line counts as 0 when the other is known)."""
    out = []
    for r in rows[-WINDOW:]:
        known = r["dividends"] is not None or r["buybacks"] is not None
        total = (r["dividends"] or 0.0) + (r["buybacks"] or 0.0) if known else None
        out.append({"year": r["year"], "dividends": r["dividends"], "buybacks": r["buybacks"], "total": total,
                    "fcf": r["fcf"],
                    "gap": total - r["fcf"] if total is not None and r["fcf"] is not None else None})
    return out


def step5(rows: list[dict]) -> dict:
    window = return_rows(rows)
    known = [r for r in window if r["total"] is not None and r["fcf"] is not None]
    base = {"rows": window, "total_return": None, "total_fcf": None, "over_years": []}
    if not known:
        return {**base, "rating": "不明", "basis": "配当金の支払額・自己株式の取得（または FCF）が raw に無い",
                "sentence": "株主還元額か FCF が取れず、持続性を確認できない"}
    total_return = sum(r["total"] for r in known)
    total_fcf = sum(r["fcf"] for r in known)
    over = [r["year"] for r in known if r["total"] > r["fcf"]]
    base = {**base, "total_return": total_return, "total_fcf": total_fcf, "over_years": over}
    span = f"{known[0]['year']}〜{known[-1]['year']}（{len(known)}年）"
    if total_return == 0:
        return {**base, "rating": "対象外", "basis": f"{span}に配当・自社株買いの支出なし",
                "sentence": "株主還元の支出が無く、持続性の確認は対象外"}
    summary = (f"{span}の還元額 累計 {fmt_amount(total_return)}、FCF 累計 {fmt_amount(total_fcf)}、"
               f"還元が FCF を上回った年 {len(over)}年")
    if total_return > total_fcf and len(over) >= OVER_YEARS:
        rating, why = "注意", f"{summary}（還元が FCF を継続的に上回る。借入・手元資金の取り崩しで還元）"
    else:
        rating, why = "問題なし", f"{summary}（還元は継続的には FCF を上回っていない）"
    return {**base, "rating": rating, "basis": why, "sentence": f"株主還元は{why}。{rating}"}


# ---------- 手順6 ----------

def judge(s1: dict, s2: dict, s3: dict, s4: dict, s5: dict) -> tuple[str, str]:
    """(良好/普通/懸念/判定保留, why)."""
    steps = (("手順1", s1), ("手順2", s2), ("手順3", s3), ("手順4", s4))
    bad = [f"{name}（{s['basis']}）" for name, s in steps if s["rating"] == "懸念"]
    if bad:
        return "懸念", f"{'・'.join(bad)}が懸念"
    if s1["rating"] is None:
        return "判定保留", f"手順1を判定できない（{s1['basis']}）"
    missing = [name for name, s in steps if s["rating"] is None and not s.get("loss")]
    if missing:
        return "判定保留", f"{'・'.join(missing)}を判定できない（材料不足。普通・懸念という意味ではない）"
    if all(s["rating"] == "良好" for _, s in steps) and s5["rating"] in ("問題なし", "対象外"):
        return "良好", f"手順1〜4がすべて良好で、株主還元は{s5['rating']}"
    reasons = [f"{name}が普通" for name, s in steps if s["rating"] == "普通"]
    if s3["rating"] is None:
        reasons.append("手順3が純損失で判定できない")
    if s5["rating"] in ("注意", "不明"):
        reasons.append(f"株主還元が{s5['rating']}")
    return "普通", "、".join(reasons)


def borderline(s2: dict, s3: dict, s5: dict, rows: list[dict]) -> list[str]:
    """Comparisons a small change in the data (a new fiscal year, a corrected value) could move by one step."""
    out = []
    if s3["ratio"] is not None:
        for limit in (GOOD_RATIO, FAIR_RATIO):
            if abs(s3["ratio"] - limit) <= RATIO_NEAR:
                out.append(f"手順3: 営業CF対純利益比率 {s3['ratio']:.2f}倍 が基準 {limit:.1f}倍 に近い")
    if s2["total"] is not None:
        cfo_total = sum(abs(r["cfo"]) for r in rows if r["year"] in s2["window"])
        if cfo_total and abs(s2["total"]) <= cfo_total * FCF_NEAR_SHARE:
            out.append(f"手順2: FCF の{WINDOW}年累計 {fmt_amount(s2['total'])} がゼロに近い（累計営業CF の"
                       f"{FCF_NEAR_SHARE * 100:.0f}%以内）")
    if s5["total_fcf"] and s5["rating"] in ("注意", "問題なし") \
            and abs(s5["total_return"] - s5["total_fcf"]) <= abs(s5["total_fcf"]) * RETURN_NEAR_SHARE:
        out.append(f"手順5: 還元額の累計 {fmt_amount(s5['total_return'])} が FCF の累計 "
                   f"{fmt_amount(s5['total_fcf'])} に近い")
    return out


# ---------- STEP 2 の他の分析 ----------

def relation(s1: dict, s3: dict, profitability: dict | None) -> list[dict]:
    """収益性分析（2-1）の結論とキャッシュフローの数値が食い違っていないか."""
    verdict = (profitability or {}).get("verdict")
    source = ((profitability or {}).get("step3") or {}).get("source")
    if not verdict:
        first = second = "未実施（収益性分析の結果なし）"
    else:
        first = ("判断できない（手順3を判定できない）" if s3["rating"] is None else
                 "不整合（利益が現金を伴っていない。収益性の評価を割り引く候補）"
                 if verdict == "良好" and s3["rating"] == "懸念" else "整合")
        second = ("対象外（ROE の源泉が本業由来ではない）" if source != "本業由来" else
                  "判断できない（手順1を判定できない）" if s1["rating"] is None else
                  "不整合（本業の稼ぐ力が営業CF に表れていない）" if s1["rating"] == "懸念" else "整合")
    ratio = "—" if s3["ratio"] is None else f"{s3['ratio']:.2f}倍"
    return [{"check": "収益性が良好 ⇔ 利益の質", "step2": f"収益性 {verdict or '—'}",
             "cash": f"営業CF対純利益比率 {ratio}（手順3 {s3['rating'] or '判定不能'}）", "result": first},
            {"check": "ROE が本業由来 ⇔ 営業CF の安定", "step2": f"ROE の源泉 {source or '—'}",
             "cash": f"手順1 {s1['rating'] or '判定不能'}", "result": second}]


# ---------- everything ----------

def candidates(company) -> dict:
    series = S.self_series(company)
    rows = cf_rows(series)
    s1, s2, s3, s4, s5 = step1(rows), step2(rows), step3(rows, series), step4(rows), step5(rows)
    verdict, why = judge(s1, s2, s3, s4, s5)
    return {"series": series, "rows": rows, "step1": s1, "step2": s2, "step3": s3, "step4": s4, "step5": s5,
            "borderline": borderline(s2, s3, s5, rows), "verdict": verdict, "why": why}


def collect_requests(company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, plus a short own history or no shareholder-return data (once each)."""
    unavailable = I.unavailable_items(company)
    extra: list[str] = []
    if cands["step1"]["years"] < MIN_YEARS and not any(w in u for w in OWN_UNAVAILABLE for u in unavailable):
        extra.append(OWN_ITEM)
    if cands["step5"]["rating"] == "不明" and not any(RETURN_UNAVAILABLE in u for u in unavailable):
        extra.append(RETURN_ITEM)
    out = [dict(r, items=list(r["items"])) for r in I.collect_requests(found)]
    for item in extra:
        hit = next((r for r in out if r["agent"] == "collect-filings"), None)
        if hit is None:
            out.append({"agent": "collect-filings", "items": [item]})
        elif item not in hit["items"]:
            hit["items"] = hit["items"] + [item]
    return out


def series_digest(cands: dict) -> str:
    """Every number the result rests on: a new fiscal year or a corrected value re-opens the result."""
    keys = ("cfo", "cfi", "cff", "net_income", "sales", "dividends", "buybacks")
    rows = [[r["year"]] + [None if r[k] is None else round(r[k], 1) for k in keys] for r in cands["rows"]]
    wc = [[w["field"], w["first"], w["last"]] for w in cands["step3"]["working_capital"]]
    return A.digest(json.dumps([rows, wc], ensure_ascii=False))


def warnings(cands: dict) -> list[str]:
    """Signs that the series were read wrongly (shown in the brief and prepare's output)."""
    out = []
    rows = cands["rows"]
    for prev, cur in zip(rows, rows[1:]):
        small, large = sorted((abs(prev["cfo"]), abs(cur["cfo"])))
        if small > 0 and large / small > UNIT_JUMP:
            out.append(f"営業CF {prev['year']}→{cur['year']}: {fmt_amount(prev['cfo'])} → {fmt_amount(cur['cfo'])} と"
                       f"{UNIT_JUMP}倍超の差（単位（千円・百万円・億円）の読み違いの可能性）")
    secondary = [r["year"] for r in rows if not r["primary"]]
    if secondary:
        out.append(f"二次情報（集計サイト）の値を使った年: {'、'.join(secondary)}")
    return out
