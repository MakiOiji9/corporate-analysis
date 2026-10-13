"""ROE, the DuPont decomposition and every judgement of 企業分析フレームワーク.md 2-1 (収益性).

  ROE = 当期純利益 ÷ 自己資本 = 売上高純利益率 × 総資産回転率 × 財務レバレッジ
  The balance sheet side is the average of the opening and closing balance (the year before is the opening);
  the first year of a series uses the closing balance and says so. The three factors multiply to that ROE.

  手順1 (ROE の水準と安定性, the latest MAX_YEARS years, at least MIN_YEARS):
    懸念: 平均 < 8% または赤字の年 / 良好: 平均 >= 10% かつ最低 >= 5% / 普通: それ以外
    ROE per year: the primary reported value, else the computed one, else a secondary reported value.
  手順2 (営業利益率の同業比較): the newest year compared with the peer average (mt_metrics): diff > +1pt 上回る,
    within +-1pt 同等, below -1pt 下回る; the 5-year trend is reported alongside.
  手順3 (源泉): the target's factors averaged over the years compared with the peers (up to 5) against the
    peer average: leverage over 3x in the newest year and above the peers -> 借入依存; else net margin or asset
    turnover above the peers -> 本業由来; else 特定できず. No peer data -> 不明 (借入依存 when over 3x anyway).
    "Above" needs a lead beyond the band (net margin > 1pt, turnover / leverage > 5%); a smaller lead is 同等.
  Comparisons within twice their band are listed as borderline; the 要確認 years of the extraordinary items get
  手順1 recomputed without them (before tax effects).
  手順4 (結論): 懸念: 手順1 懸念 or 借入依存 / 良好: 手順1 良好, 手順2 上回る・同等, 本業由来 /
    判定保留: 手順1 良好 and the rest could not be compared (or 手順1 lacks years) / 普通: otherwise
"""
from __future__ import annotations

import json
import math

import an_common as A
import mt_metrics as MT
import pf_inputs as I
import pf_series as S
from ff_metrics import _months_apart, peer_margins

MIN_YEARS, MAX_YEARS = 5, 10
GOOD_AVG, FAIR_AVG, GOOD_MIN = 10.0, 8.0, 5.0
TREND_PT = 1.0  # 直近3年・5年の方向: a change within this is 横ばい / 安定
SAME_PT = 1.0  # 営業利益率・純利益率の同業比較: within this is 同等
FACTOR_SAME_RATIO = 1.05  # 総資産回転率・財務レバレッジ: within ±5% of the peer average is 同等
BORDERLINE_WIDTH = 2.0  # a comparison within twice its band is reported as borderline
CHANGE_PT = 2.0  # ROE moves of this size are decomposed (3.3)
LEVERAGE_LIMIT = 3.0  # 自己資本比率 33% 未満に相当
MARGIN_YEARS = 5
COMPARE_YEARS = 5
MATCH_MONTHS = 6
MISMATCH_PT = 1.0  # reported vs computed ROE
ONE_OFF_SHARE = 10.0  # 特別損益の純額が純利益のこの割合以上なら要確認
FACTORS = (("margin", "売上高純利益率"), ("turnover", "総資産回転率"), ("leverage", "財務レバレッジ"))
OWN_UNAVAILABLE = "収益性の財務時系列"  # collect-filings reports a short own history under this name
OWN_ITEM = f"財務時系列: 売上高・当期純利益・総資産・自己資本（{MIN_YEARS}年以上）"
PEER_ITEM = I.SPEC["peer_dupont"].label


# ---------- ROE and the factors ----------

def _prior(year: str) -> str:
    total = int(year[:4]) * 12 + int(year[5:7]) - 13
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def dupont_rows(series: S.Series) -> list[dict]:
    """One row per fiscal year with sales, net income, total assets and equity."""
    rows = []
    for year in sorted(series["net_income"]):
        needed = [series[f].get(year) for f in ("sales", "net_income", "total_assets", "equity")]
        if any(v is None for v in needed) or needed[0].value <= 0:
            continue
        sales, ni, assets, equity = (v.value for v in needed)
        prior_assets, prior_equity = series["total_assets"].get(_prior(year)), series["equity"].get(_prior(year))
        averaged = prior_assets is not None and prior_equity is not None
        avg_assets = (assets + prior_assets.value) / 2 if averaged else assets
        avg_equity = (equity + prior_equity.value) / 2 if averaged else equity
        if avg_assets <= 0 or avg_equity <= 0:
            continue
        rows.append({"year": year, "sales": sales, "net_income": ni, "avg_assets": avg_assets,
                     "avg_equity": avg_equity, "margin": ni / sales * 100, "turnover": sales / avg_assets,
                     "leverage": avg_assets / avg_equity, "roe": ni / avg_equity * 100, "averaged": averaged,
                     "primary": all(v.primary for v in needed)})
    return rows


def roe_rows(series: S.Series, dupont: list[dict]) -> list[dict]:
    """The ROE used for 手順1, newest MAX_YEARS years: reported (primary) -> computed -> reported (secondary)."""
    computed = {r["year"]: r for r in dupont}
    years = sorted(set(series["roe"]) | set(computed))[-MAX_YEARS:]
    out = []
    for year in years:
        reported, calc = series["roe"].get(year), computed.get(year)
        if reported is not None and reported.primary:
            value, basis = reported.value, "開示（一次）"
        elif calc is not None:
            value, basis = calc["roe"], "計算"
        else:
            value, basis = reported.value, "開示（二次）"
        ni = series["net_income"].get(year)
        out.append({"year": year, "roe": round(value, 1), "basis": basis,
                    "reported": round(reported.value, 1) if reported else None,
                    "reported_primary": bool(reported and reported.primary),
                    "computed": round(calc["roe"], 1) if calc else None,
                    "net_income": ni.value if ni else None, "avg_equity": calc["avg_equity"] if calc else None,
                    "averaged": calc["averaged"] if calc else None,
                    "source": reported.source if basis.startswith("開示") else (ni.source if ni else "—")})
    return out


# ---------- 手順1 ----------

def _direction(values: list[float], flat: float, words: tuple[str, str, str]) -> str:
    if len(values) < 2:
        return "—"
    change = values[-1] - values[0]
    return words[0] if change > flat else words[2] if change < -flat else words[1]


def step1(rows: list[dict]) -> dict:
    values = [r["roe"] for r in rows]
    losses = [r["year"] for r in rows if (r["net_income"] is not None and r["net_income"] < 0) or r["roe"] < 0]
    if len(rows) < MIN_YEARS:
        return {"rating": None, "years": len(rows), "losses": losses,
                "basis": f"ROE が取れた年が {len(rows)} 年で {MIN_YEARS} 年に満たない",
                "sentence": f"ROE が取れた年が{len(rows)}年で、{MIN_YEARS}年に満たず判定できない"}
    avg = sum(values) / len(values)
    low = min(rows, key=lambda r: r["roe"])
    recent = values[-3:]
    direction = _direction(recent, TREND_PT, ("上昇", "横ばい", "低下"))
    if avg < FAIR_AVG or losses:
        rating = "懸念"
        why = f"平均 {avg:.1f}% が {FAIR_AVG:.0f}% 未満" if avg < FAIR_AVG else f"赤字の年あり（{'、'.join(losses)}）"
    elif avg >= GOOD_AVG and low["roe"] >= GOOD_MIN:
        rating, why = "良好", f"平均 {GOOD_AVG:.0f}% 以上かつ最低 {GOOD_MIN:.0f}% 以上、赤字の年なし"
    elif avg >= GOOD_AVG:
        rating, why = "普通", f"平均 {GOOD_AVG:.0f}% 以上だが最低が {GOOD_MIN:.0f}% 未満（変動が大きい）"
    else:
        rating, why = "普通", f"平均 {FAIR_AVG:.0f}〜{GOOD_AVG:.0f}%"
    return {"rating": rating, "years": len(rows), "first": rows[0]["year"], "last": rows[-1]["year"],
            "average": round(avg, 1), "minimum": low["roe"], "minimum_year": low["year"], "losses": losses,
            "recent": recent, "direction": direction, "basis": why,
            "sentence": (f"ROE は平均{avg:.1f}%、最低{low['roe']:.1f}%（{low['year']}）で{rating}。"
                         f"直近3年は{direction}傾向（{' → '.join(f'{v:.1f}%' for v in recent)}）")}


# ---------- 手順2 ----------

def step2(company, found: dict) -> dict:
    listed = peer_margins(found["peers"])
    margins, sources = MT.self_series(company, listed)
    rows = MT.comparison_rows(margins, MT.peers(company, found["peers"]))[-MARGIN_YEARS:]
    trend = _direction([r["self"] for r in rows], TREND_PT, ("改善", "安定", "悪化"))
    compared = [r for r in rows if r["avg"] is not None]
    base = {"rows": rows, "sources": sources, "trend": trend, "margins": margins}
    if not compared:
        return {**base, "rating": None, "basis": "自社と競合の営業利益率を同じ年度で比べられない",
                "sentence": f"営業利益率は同業と比べられない（自社の{len(rows)}年の推移は{trend}）"}
    latest = compared[-1]
    rating = "上回る" if latest["diff"] > SAME_PT else "下回る" if latest["diff"] < -SAME_PT else "同等"
    return {**base, "rating": rating, "year": latest["year"], "self": latest["self"], "avg": latest["avg"],
            "diff": latest["diff"],
            "basis": f"{latest['year']} の差 {latest['diff']:+.1f}pt（±{SAME_PT:.0f}pt 以内は同等）",
            "sentence": (f"営業利益率は{latest['self']:.1f}%（{latest['year']}）で、同業平均{latest['avg']:.1f}%を"
                         f"{rating}（差 {latest['diff']:+.1f}pt）。{len(rows)}年の推移は{trend}")}


# ---------- 手順3 ----------

def _nearest(rows: list[dict], year: str) -> dict | None:
    near = [(abs(_months_apart(r["year"], year)), r) for r in rows]
    near = [(d, r) for d, r in near if d <= MATCH_MONTHS]
    return min(near, key=lambda x: x[0])[1] if near else None


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def peer_comparison(own: list[dict], peers: list[dict]) -> dict:
    """The target's factors and the peers' over the target's newest years that have at least one peer."""
    peer_rows = [{"name": p["name"], "rows": dupont_rows(p["series"])} for p in peers]
    years, per_peer = [], {p["name"]: [] for p in peer_rows}
    for r in own[-COMPARE_YEARS:]:
        matched = [(p["name"], _nearest(p["rows"], r["year"])) for p in peer_rows]
        matched = [(name, m) for name, m in matched if m]
        if matched:
            years.append(r)
            for name, m in matched:
                per_peer[name].append(m)
    keys = [k for k, _ in FACTORS] + ["roe"]
    self_avg = {k: _mean([r[k] for r in years]) for k in keys}
    peers_out = [{"name": name, "years": [m["year"] for m in rows], "primary": all(m["primary"] for m in rows),
                  **{k: _mean([m[k] for m in rows]) for k in keys}} for name, rows in per_peer.items() if rows]
    peer_avg = {k: _mean([p[k] for p in peers_out]) for k in keys}
    return {"years": [r["year"] for r in years], "self": self_avg, "peers": peers_out, "peer_avg": peer_avg,
            "peer_rows": peer_rows}


def is_above(key: str, own: float, peer: float) -> bool:
    """Above the peer average beyond the band: net margin by more than SAME_PT points, turnover and leverage by
    more than FACTOR_SAME_RATIO times. A smaller lead counts as 同等 (迷ったら保守的に)."""
    if key in ("margin", "roe"):
        return own - peer > SAME_PT
    return peer > 0 and own / peer > FACTOR_SAME_RATIO


def compare_text(key: str, own: float, peer: float) -> str:
    name = dict(FACTORS).get(key, "ROE")
    if key in ("margin", "roe"):
        gap = f"{own - peer:+.1f}pt、±{SAME_PT:.0f}pt 以内は同等"
    else:
        gap = f"比 {own / peer:.2f}、±{(FACTOR_SAME_RATIO - 1) * 100:.0f}% 以内は同等" if peer else "比較不可"
    return f"{name} {fmt_factor(own, key)} と同業平均 {fmt_factor(peer, key)}（{gap}）"


def step3(own: list[dict], comparison: dict) -> dict:
    lev = own[-1]["leverage"] if own else None
    base = {"latest_leverage": lev, "comparison": comparison}
    if not own:
        return {**base, "source": "不明", "drivers": [], "basis": "自社の3要素を計算できない",
                "sentence": "ROE の源泉は不明（自社の3要素を計算できない）"}
    if not comparison["peers"]:
        if lev > LEVERAGE_LIMIT:
            return {**base, "source": "借入依存", "drivers": ["財務レバレッジ"],
                    "basis": f"同業と比べられないが、財務レバレッジが {lev:.2f} 倍（{LEVERAGE_LIMIT:.0f}倍超）",
                    "sentence": f"ROE の源泉は財務レバレッジ（{lev:.2f}倍。同業比較なし）で借入依存"}
        return {**base, "source": "不明", "drivers": [], "basis": "競合の3要素が無く同業と比べられない",
                "sentence": "ROE の源泉は不明（同業と比べられない）"}
    own_avg, peer = comparison["self"], comparison["peer_avg"]
    above = [name for key, name in FACTORS[:2] if is_above(key, own_avg[key], peer[key])]
    compared = "、".join(compare_text(key, own_avg[key], peer[key]) for key, _ in FACTORS)
    if lev > LEVERAGE_LIMIT and is_above("leverage", own_avg["leverage"], peer["leverage"]):
        source, drivers = "借入依存", ["財務レバレッジ"]
        why = f"財務レバレッジが {lev:.2f} 倍（{LEVERAGE_LIMIT:.0f}倍超）で同業平均を上回る（{compared}）"
    elif above:
        source, drivers = "本業由来", above
        why = f"{'・'.join(above)}が同業平均を上回る（{compared}）"
    else:
        source, drivers = "特定できず", []
        why = f"売上高純利益率・総資産回転率とも同業平均を上回らない（{compared}）"
    label = {"本業由来": "（本業の強さ）", "借入依存": "（借入依存）", "特定できず": ""}[source]
    named = "・".join(drivers) or "特定できず（純利益率・回転率とも同業平均を上回らない）"
    return {**base, "source": source, "drivers": drivers, "basis": why, "sentence": f"ROE の源泉は{named}{label}"}


# ---------- 3.3 / 3.4 ----------

def fmt_factor(value: float | None, key: str) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}%" if key in ("margin", "roe") else f"{value:.2f}{'回' if key == 'turnover' else '倍'}"


def _extra_net(series: S.Series, year: str) -> float | None:
    gain, loss = series["extra_gain"].get(year), series["extra_loss"].get(year)
    if gain is None and loss is None:
        return None
    return (gain.value if gain else 0.0) - (loss.value if loss else 0.0)


def _context(series: S.Series, margins: dict[str, float], prev: str, cur: str) -> list[str]:
    """What the writer needs beside the factors: the operating margin and the extraordinary items of both years."""
    out = []
    if prev in margins and cur in margins:
        out.append(f"営業利益率 {margins[prev]:.1f}%→{margins[cur]:.1f}%")
    before, after = _extra_net(series, prev), _extra_net(series, cur)
    if before is not None or after is not None:
        out.append(f"特別損益の純額 {'—' if before is None else f'{before:,.0f}'}→"
                   f"{'—' if after is None else f'{after:,.0f}'}百万円")
    return out


def change_years(own: list[dict], series: S.Series | None = None, margins: dict[str, float] | None = None) -> list[dict]:
    """Years whose ROE moved CHANGE_PT or more from the year before, with the factor that moved it most and the
    operating margin / extraordinary items of both years (so the writer need not look elsewhere)."""
    out = []
    for prev, cur in zip(own, own[1:]):
        if _months_apart(prev["year"], cur["year"]) != 12 or abs(cur["roe"] - prev["roe"]) < CHANGE_PT:
            continue
        moves = [f"{name} {fmt_factor(prev[k], k)}→{fmt_factor(cur[k], k)}" for k, name in FACTORS]
        if series is not None:
            moves += _context(series, margins or {}, prev["year"], cur["year"])
        moves = "、".join(moves)
        if cur["net_income"] <= 0 or prev["net_income"] <= 0:
            main = "（赤字を含むため分解できない）"
        else:
            contrib = {name: math.log(cur[k] / prev[k]) for k, name in FACTORS}
            sign = 1 if cur["roe"] > prev["roe"] else -1
            main = max(contrib, key=lambda n: contrib[n] * sign)
        out.append({"year": cur["year"], "from": round(prev["roe"], 1), "to": round(cur["roe"], 1),
                    "main": main, "moves": moves})
    return out


def one_off_rows(series: S.Series, years: list[str], dupont: list[dict] = ()) -> list[dict]:
    """Extraordinary items per year; for a year whose net amount is ONE_OFF_SHARE% or more of the net income,
    the ROE without it (net income minus the net amount, before tax effects, over the same average equity)."""
    equity = {r["year"]: r["avg_equity"] for r in dupont}
    out = []
    for year in years:
        gain, loss = series["extra_gain"].get(year), series["extra_loss"].get(year)
        ni = series["net_income"].get(year)
        net = _extra_net(series, year)
        if net is None:
            continue
        share = net / ni.value * 100 if ni and ni.value else None
        check = share is not None and abs(share) >= ONE_OFF_SHARE
        adjusted = ((ni.value - net) / equity[year] * 100 if check and year in equity and equity[year] > 0 else None)
        out.append({"year": year, "gain": gain.value if gain else None, "loss": loss.value if loss else None,
                    "net_income": ni.value if ni else None, "share": round(share, 1) if share is not None else None,
                    "check": check, "adjusted_roe": round(adjusted, 1) if adjusted is not None else None})
    return out


def adjusted_step1(roes: list[dict], one_off: list[dict]) -> dict | None:
    """手順1 again with the ROE of the 要確認 years replaced by the ROE without the extraordinary items."""
    adjusted = {r["year"]: r["adjusted_roe"] for r in one_off if r["adjusted_roe"] is not None}
    if not adjusted:
        return None
    rows = [dict(r, roe=adjusted.get(r["year"], r["roe"])) for r in roes]
    result = step1(rows)
    return {"years": sorted(adjusted), "rating": result["rating"], "sentence": result["sentence"]}


# ---------- 手順4 / STEP 1 ----------

def judge(s1: dict, s2: dict, s3: dict) -> tuple[str, str]:
    """(良好/普通/懸念/判定保留, why)."""
    if s1["rating"] == "懸念":
        return "懸念", f"手順1が懸念（{s1['basis']}）"
    if s3["source"] == "借入依存":
        return "懸念", f"ROE が借入依存（{s3['basis']}）"
    if s1["rating"] is None:
        return "判定保留", f"手順1を判定できない（{s1['basis']}）"
    if s1["rating"] == "普通":
        return "普通", f"手順1が普通（{s1['basis']}）"
    if s2["rating"] == "下回る":
        return "普通", "手順1は良好だが、営業利益率が同業平均を下回る"
    if s3["source"] == "特定できず":
        return "普通", "手順1は良好だが、純利益率・回転率とも同業平均を上回らず本業由来と言えない"
    unknown = [label for label, missing in (("営業利益率の同業比較", s2["rating"] is None),
                                            ("ROE の源泉の同業比較", s3["source"] == "不明")) if missing]
    if unknown:
        return "判定保留", f"手順1は良好だが、{'・'.join(unknown)}ができない（競合の材料不足。普通・懸念という意味ではない）"
    return "良好", "手順1が良好、営業利益率が同業平均以上、ROE の源泉が本業由来"


def borderline(s1: dict, s2: dict, s3: dict) -> list[str]:
    """Comparisons that sit within BORDERLINE_WIDTH times their band: a small change in the data (a secondary
    value, a new fiscal year) could move the judgement by one step."""
    out = []
    if s1["rating"] is not None:
        for name, value, limit in (("ROE の平均", s1["average"], GOOD_AVG), ("ROE の平均", s1["average"], FAIR_AVG),
                                   ("ROE の最低", s1["minimum"], GOOD_MIN)):
            if abs(value - limit) <= TREND_PT * BORDERLINE_WIDTH:
                out.append(f"手順1: {name} {value:.1f}% が基準 {limit:.0f}% に近い")
    if s2["rating"] is not None and abs(s2["diff"]) <= SAME_PT * BORDERLINE_WIDTH:
        out.append(f"手順2: 営業利益率の差 {s2['diff']:+.1f}pt（±{SAME_PT:.0f}pt が同等の幅）")
    comparison = s3["comparison"]
    if comparison["peers"]:
        own, peer = comparison["self"], comparison["peer_avg"]
        for key, _ in FACTORS:
            if key == "margin":
                near = abs(own[key] - peer[key]) <= SAME_PT * BORDERLINE_WIDTH
            else:
                near = peer[key] > 0 and abs(own[key] / peer[key] - 1) <= (FACTOR_SAME_RATIO - 1) * BORDERLINE_WIDTH
            if near:
                out.append(f"手順3: {compare_text(key, own[key], peer[key])}")
    return out


def consistency(s2: dict, s3: dict, moat: dict | None, three_c: dict | None) -> list[dict]:
    """企業分析フレームワーク.md「STEP 1 との整合性チェック」のうち 2-1 に関わる2行."""
    moat_v = (moat or {}).get("verdict")
    if not moat_v:
        result = "未実施（モート分析の結果なし）"
    elif moat_v != "広い":
        result = f"対象外（モート {moat_v}）"
    elif s2["rating"] is None:
        result = "判断できない（営業利益率を同業と比べられない）"
    else:
        result = "整合" if s2["rating"] == "上回る" else "不整合（STEP 1 見直し候補）"
    rows = [{"check": "モートが広い ⇔ 高い利益率", "step1": f"モート {moat_v or '—'}",
             "step2": f"営業利益率 {s2['rating'] or '比較不可'}", "result": result}]
    tc_v = (three_c or {}).get("verdict")
    own_roe, peer_roe = s3["comparison"]["self"].get("roe"), s3["comparison"]["peer_avg"].get("roe")
    roe_text = (f"ROE {own_roe:.1f}%（同業平均 {peer_roe:.1f}%）" if own_roe is not None and peer_roe is not None
                else "ROE 同業比較不可")
    if not tc_v:
        result = "未実施（3C分析の結果なし）"
    elif tc_v != "明確":
        result = f"対象外（勝てる理由 {tc_v}）"
    elif s2["rating"] is None or peer_roe is None:
        result = "判断できない（ROE・営業利益率を同業と比べられない）"
    else:
        ok = own_roe >= peer_roe and s2["rating"] in ("上回る", "同等")
        result = "整合" if ok else "不整合（STEP 1 見直し候補）"
    rows.append({"check": "勝てる理由が明確 ⇔ 収益性", "step1": f"勝てる理由 {tc_v or '—'}",
                 "step2": f"{roe_text}、営業利益率 {s2['rating'] or '比較不可'}", "result": result})
    return rows


# ---------- everything ----------

def candidates(company, found: dict) -> dict:
    series = S.self_series(company, found["peer_dupont"])
    own = dupont_rows(series)
    roes = roe_rows(series, own)
    comparison = peer_comparison(own, S.peer_series(company, found["peer_dupont"]))
    s1, s2, s3 = step1(roes), step2(company, found), step3(own, comparison)
    verdict, why = judge(s1, s2, s3)
    one_off = one_off_rows(series, [r["year"] for r in roes], own)
    return {"series": series, "dupont": own, "roe_rows": roes, "step1": s1, "step2": s2, "step3": s3,
            "changes": change_years(own, series, s2["margins"]), "one_off": one_off,
            "one_off_step1": adjusted_step1(roes, one_off), "borderline": borderline(s1, s2, s3),
            "verdict": verdict, "why": why}


def collect_requests(company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, plus a short own history or a peer section that yields no factor."""
    unavailable = I.unavailable_items(company)
    extra: list[tuple[str, str]] = []
    if cands["step1"]["years"] < MIN_YEARS and not any(OWN_UNAVAILABLE in u for u in unavailable):
        extra.append(("collect-filings", OWN_ITEM))
    if found["peer_dupont"].status == "ok" and not cands["step3"]["comparison"]["peers"]:
        extra.append(("collect-peers-valuation", PEER_ITEM))
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
    own = [[r["year"], round(r["roe"], 2), round(r["margin"], 2), round(r["turnover"], 3)] for r in cands["dupont"]]
    roes = [[r["year"], r["roe"]] for r in cands["roe_rows"]]
    margins = [[r["year"], r["self"], r["avg"]] for r in cands["step2"]["rows"]]
    peers = [[p["name"], p["years"], round(p["roe"], 2)] for p in cands["step3"]["comparison"]["peers"]]
    return A.digest(json.dumps([own, roes, margins, peers], ensure_ascii=False))


def warnings(cands: dict) -> list[str]:
    """Signs that the series were read wrongly (shown in the brief and prepare's output)."""
    out = []
    for r in cands["roe_rows"]:
        if r["reported_primary"] and r["computed"] is not None and r["averaged"] \
                and abs(r["reported"] - r["computed"]) > MISMATCH_PT:
            out.append(f"ROE {r['year']}: 開示 {r['reported']:.1f}% と計算 {r['computed']:.1f}% が "
                       f"{MISMATCH_PT:.0f}pt 超ずれる（純利益・総資産・自己資本の読み違いの可能性。手順1は開示値）")
    for p in cands["step3"]["comparison"]["peer_rows"]:
        if not p["rows"]:
            out.append(f"競合 {p['name']}: 「収益性の分解」の行から3要素を計算できない（売上高・当期純利益・総資産・"
                       "自己資本（または自己資本比率）のどれかが読めない）")
    return out
