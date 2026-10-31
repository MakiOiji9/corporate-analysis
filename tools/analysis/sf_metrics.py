"""Every number and judgement of 企業分析フレームワーク.md 2-3 (安全性).

  自己資本比率 = 自己資本 ÷ 総資産, D/E = 有利子負債 ÷ 自己資本, 流動比率 = 流動資産 ÷ 流動負債,
  ネットキャッシュ = 現金及び現金同等物 − 有利子負債 (all year-end balances).

  手順1 (現状の水準, the newest year): each indicator against its 目安 (自己資本比率 >= 40%, D/E <= 1倍,
    流動比率 >= 120%) and against the peer average (up to 5 peers, fiscal years within 6 months): クリア when it
    meets either (同業平均と同等以上 within the band: -2pt / -5pt / x1.05), 未達 when it meets neither, 不明 when it
    misses the 目安 and there is no peer value (or the own value is missing). D/E is クリア whenever the net cash
    is positive (実質無借金). Banks, insurers, brokers, real estate and lessors use the peer average only.
  手順2 (推移, the newest 5 years, at least 3): 悪化傾向 when the equity ratio fell 10pt or more, or D/E rose in
    each of the last 3 years and ends above the first year.
  手順3 (借入の目的, the years whose debt rose by 1% of total assets or more): 営業CF < 0 or a net loss ->
    赤字補填・運転資金不足 (懸念); investing outflow >= half the increase -> 成長投資 (許容 when sales and operating
    income are higher within 2 years, else 要確認); otherwise その他 (要確認). Overall: 懸念 / 許容 / 要確認 / 不明.
  手順4 (結論): 懸念: 2 indicators or more 未達, or 悪化傾向 with 借入目的 懸念 / 良好: all 3 クリア and no 悪化傾向 /
    普通: otherwise. Two or more 不明 indicators -> 判定保留; with one 不明 (or an unknown trend / purpose) the rule
    is applied with every possible value and 判定保留 is returned unless they agree.
"""
from __future__ import annotations

import itertools
import json
import re

import an_common as A
import sf_inputs as I
import sf_series as SS
from ff_inputs import main_business
from ff_metrics import _months_apart
from pf_metrics import _nearest

TARGETS = {"equity_ratio": 40.0, "de": 1.0, "current_ratio": 120.0}
COMFORT_CURRENT = 150.0  # 流動比率 150% 以上は「余裕あり」と表示する（判定は 120%）
PEER_BAND = {"equity_ratio": 2.0, "current_ratio": 5.0}  # pt below the peer average still counts as 同等
DE_PEER_RATIO, DE_PEER_PT = 1.05, 0.05  # D/E up to x1.05 (or +0.05倍) of the peer average is 同等
BORDER = {"equity_ratio": 4.0, "current_ratio": 10.0, "de": 0.1}  # twice the band: borderline comparisons
NET_CASH_BORDER = 0.05  # |net cash| within 5% of total assets
INDICATORS = (("equity_ratio", "自己資本比率"), ("de", "D/E レシオ"), ("current_ratio", "流動比率"))
NAMES = dict(INDICATORS)
TREND_YEARS, MIN_TREND_YEARS = 5, 3
EQUITY_DROP_PT = 10.0
DE_RISES = 3
DEBT_MATERIAL = 0.01  # a debt increase below 1% of total assets is not examined
INVEST_SHARE = 0.5
RESULT_MONTHS = 24
MATCH_MONTHS = 6
MISMATCH_PT = 1.0
EXCLUDED_SECTOR = re.compile(r"銀行|保険|証券|不動産|(?<!リ)リース|信託|ノンバンク|クレジット|消費者金融")
OWN_UNAVAILABLE = "安全性の財務時系列"  # collect-filings reports a short own history under this name
OWN_ITEM = ("財務時系列 8章「貸借・CF の主要項目（安全性）」: 総資産・自己資本・有利子負債（借入が無ければ 0（科目なし））・"
            f"現金及び現金同等物・流動資産・流動負債・営業CF・投資CF・財務CF（{TREND_YEARS}年以上）")
PEER_ITEM = I.SPEC["peer_safety"].label
CLEAR, MISS, UNKNOWN = "クリア", "未達", "不明"
WORSE, STABLE = "悪化傾向", "悪化傾向なし"
OK_PURPOSE, CHECK_PURPOSE, BAD_PURPOSE = "許容", "要確認", "懸念"


# ---------- formatting ----------

def fmt(key: str, value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}倍" if key == "de" else f"{value:.1f}%"


def money(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


# ---------- yearly rows ----------

def _v(series: SS.S.Series, field: str, year: str) -> float | None:
    value = series[field].get(year)
    return value.value if value is not None else None


def balance_rows(series: SS.S.Series) -> list[dict]:
    """One row per fiscal year that gives at least one indicator, oldest first."""
    years = sorted(set(series["total_assets"]) | set(series["equity_ratio"]) | set(series["current_assets"]))
    rows = []
    for year in years:
        r = {f: _v(series, f, year) for f in ("total_assets", "equity", "debt", "cash", "current_assets",
                                               "current_liabilities", "cfo", "cfi", "cff", "sales",
                                               "operating_income", "net_income")}
        assets, equity, debt = r["total_assets"], r["equity"], r["debt"]
        reported = _v(series, "equity_ratio", year)
        r["equity_ratio"] = equity / assets * 100 if equity is not None and assets else reported
        r["reported_ratio"] = reported
        r["insolvent"] = equity is not None and equity <= 0
        r["de"] = debt / equity if debt is not None and equity is not None and equity > 0 else None
        r["current_ratio"] = (r["current_assets"] / r["current_liabilities"] * 100
                              if r["current_assets"] is not None and r["current_liabilities"] else None)
        r["net_cash"] = r["cash"] - debt if r["cash"] is not None and debt is not None else None
        if all(r[k] is None for k, _ in INDICATORS) and not r["insolvent"]:
            continue
        used = [series[f].get(year) for f in ("total_assets", "equity", "debt", "current_assets",
                                              "current_liabilities")]
        r.update(year=year, primary=all(v.primary for v in used if v is not None),
                 debt_source=series["debt"][year].source if year in series["debt"] else "—")
        rows.append(r)
    return rows


# ---------- 手順1 ----------

def sector_excluded(company) -> bool:
    return bool(EXCLUDED_SECTOR.search(main_business(company)))


def peer_values(own: dict | None, peers: list[dict]) -> list[dict]:
    """Each peer's row nearest to the target's newest year (within MATCH_MONTHS)."""
    if own is None:
        return []
    out = []
    for p in peers:
        row = _nearest(balance_rows(p["series"]), own["year"])
        if row is not None:
            out.append({"name": p["name"], "year": row["year"], "primary": row["primary"],
                        **{k: row[k] for k, _ in INDICATORS}, "net_cash": row["net_cash"],
                        "insolvent": row["insolvent"]})
    return out


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def peer_average(rows: list[dict]) -> dict[str, float | None]:
    return {k: _mean([r[k] for r in rows if r[k] is not None]) for k, _ in INDICATORS}


def meets_target(key: str, value: float) -> bool:
    return value <= TARGETS[key] if key == "de" else value >= TARGETS[key]


def meets_peer(key: str, value: float, peer: float) -> bool:
    if key == "de":
        return value <= max(peer * DE_PEER_RATIO, peer + DE_PEER_PT)
    return value >= peer - PEER_BAND[key]


def target_text(key: str, excluded: bool) -> str:
    if excluded:
        return "対象外（業種）"
    return f"{TARGETS[key]:.0f}倍以下" if key == "de" else f"{TARGETS[key]:.0f}%以上"


def assess(key: str, own: dict | None, peer: float | None, excluded: bool, unit: str = "百万円") -> dict:
    """クリア / 未達 / 不明 for one indicator, with the reason."""
    value = own[key] if own else None
    base = {"key": key, "name": NAMES[key], "value": value, "peer_avg": peer, "target": target_text(key, excluded),
            "by_target": value is not None and not excluded and meets_target(key, value),
            "by_peer": value is not None and peer is not None and meets_peer(key, value, peer)}
    if key == "de" and own and own["net_cash"] is not None and own["net_cash"] > 0:
        return {**base, "rating": CLEAR, "basis": f"ネットキャッシュ {money(own['net_cash'])} {unit}で実質無借金"}
    if own and own["insolvent"] and key in ("equity_ratio", "de"):
        return {**base, "rating": MISS, "basis": "自己資本がマイナス（債務超過）"}
    if value is None:
        return {**base, "rating": UNKNOWN, "basis": f"自社の{NAMES[key]}を計算できない（材料不足）"}
    by_target, by_peer = base["by_target"], base["by_peer"]
    peer_text = f"同業平均 {fmt(key, peer)}" if peer is not None else "同業比較なし"
    if by_target or by_peer:
        how = "目安をクリア" if by_target else "目安は未達だが同業平均と同等以上（業界特性として許容）"
        comfort = "。150%以上で余裕あり" if key == "current_ratio" and value >= COMFORT_CURRENT else ""
        return {**base, "rating": CLEAR, "basis": f"{fmt(key, value)}（{base['target']}、{peer_text}）で{how}{comfort}"}
    if peer is None:
        why = "業種が目安の対象外で" if excluded else "目安は未達で"
        return {**base, "rating": UNKNOWN, "basis": f"{fmt(key, value)}（{base['target']}）。{why}同業と比べられない"}
    return {**base, "rating": MISS, "basis": f"{fmt(key, value)}（{base['target']}、{peer_text}）で目安・同業平均とも未達"}


def latest_row(rows: list[dict]) -> dict | None:
    with_ratio = [r for r in rows if r["equity_ratio"] is not None or r["insolvent"]]
    return with_ratio[-1] if with_ratio else (rows[-1] if rows else None)


def step1(rows: list[dict], peers: list[dict], excluded: bool, unit: str = "百万円") -> dict:
    own = latest_row(rows)
    matched = peer_values(own, peers)
    avg = peer_average(matched)
    items = [assess(k, own, avg[k], excluded, unit) for k, _ in INDICATORS]
    counts = {r: sum(1 for i in items if i["rating"] == r) for r in (CLEAR, MISS, UNKNOWN)}
    net_cash = own["net_cash"] if own else None
    debt_free = net_cash is not None and net_cash > 0
    summary = "、".join(f"{i['name']} {fmt(i['key'], i['value'])} {i['rating']}" for i in items)
    year = own["year"] if own else "—"
    return {"year": year, "own": own, "peers": matched, "peer_avg": avg, "items": items, "counts": counts,
            "excluded": excluded, "net_cash": net_cash, "debt_free": debt_free, "unit": unit,
            "sentence": (f"{year}: {summary}（クリア {counts[CLEAR]}・未達 {counts[MISS]}・不明 {counts[UNKNOWN]}）。"
                         f"ネットキャッシュ {money(net_cash)} {unit}" + ("で実質無借金" if debt_free else ""))}


# ---------- 手順2 ----------

def step2(rows: list[dict]) -> dict:
    recent = [r for r in rows if r["equity_ratio"] is not None][-TREND_YEARS:]
    if len(recent) < MIN_TREND_YEARS:
        return {"rating": UNKNOWN, "years": [r["year"] for r in recent], "drop": None, "de_rising": None,
                "basis": f"自己資本比率が取れた年が {len(recent)} 年で {MIN_TREND_YEARS} 年に満たない",
                "sentence": f"推移は判定できない（自己資本比率が{len(recent)}年分のみ）"}
    drop = recent[0]["equity_ratio"] - recent[-1]["equity_ratio"]
    des = [round(r["de"], 2) for r in recent if r["de"] is not None]
    tail = des[-(DE_RISES + 1):]
    rising = len(tail) == DE_RISES + 1 and all(b > a for a, b in zip(tail, tail[1:])) and des[-1] > des[0]
    reasons = []
    if drop >= EQUITY_DROP_PT:
        reasons.append(f"自己資本比率が {drop:.1f}pt 低下（{EQUITY_DROP_PT:.0f}pt 以上）")
    if rising:
        reasons.append(f"D/E レシオが {DE_RISES} 期連続で上昇")
    rating = WORSE if reasons else STABLE
    span = f"{recent[0]['year']}〜{recent[-1]['year']}"
    if des:
        de_text = f"、D/E {des[0]:.2f}→{des[-1]:.2f}倍"
    elif any(r["insolvent"] for r in recent):
        de_text = "、D/E は債務超過の年があり計算できない"
    else:
        de_text = "、D/E は有利子負債が取れず不明"
    trend = (f"自己資本比率 {recent[0]['equity_ratio']:.1f}%→{recent[-1]['equity_ratio']:.1f}%"
             f"（{-drop:+.1f}pt）{de_text}")
    basis = "、".join(reasons) if reasons else f"自己資本比率の低下 {EQUITY_DROP_PT:.0f}pt 未満、D/E の継続的な上昇なし"
    return {"rating": rating, "years": [r["year"] for r in recent], "drop": round(drop, 1), "de_rising": rising,
            "basis": basis, "sentence": f"{span}（{len(recent)}年）: {trend}。{rating}"}


# ---------- 手順3 ----------

def _after(rows: list[dict], cur: dict) -> list[dict]:
    return [r for r in rows if 0 < _months_apart(cur["year"], r["year"]) <= RESULT_MONTHS
            and r["sales"] is not None and r["operating_income"] is not None]


def classify(rows: list[dict], prev: dict, cur: dict) -> dict:
    increase = cur["debt"] - prev["debt"]
    out = {"year": cur["year"], "from": prev["debt"], "to": cur["debt"], "increase": increase,
           "cfo": cur["cfo"], "cfi": cur["cfi"], "cff": cur["cff"], "net_income": cur["net_income"],
           "after": ""}
    later = _after(rows, cur)
    if later and cur["sales"] is not None and cur["operating_income"] is not None:
        last = later[-1]
        out["after"] = (f"売上高 {money(cur['sales'])}→{money(last['sales'])}、営業利益 "
                        f"{money(cur['operating_income'])}→{money(last['operating_income'])}（{last['year']}）")
    if (cur["cfo"] is not None and cur["cfo"] < 0) or (cur["net_income"] is not None and cur["net_income"] < 0):
        return {**out, "kind": "赤字補填・運転資金不足", "rating": BAD_PURPOSE}
    if cur["cfo"] is None or cur["cfi"] is None:
        return {**out, "kind": "不明（営業CF・投資CF の材料なし）", "rating": CHECK_PURPOSE}
    if -cur["cfi"] < INVEST_SHARE * increase:
        return {**out, "kind": "その他（投資CF の支出が増加額の半分未満）", "rating": CHECK_PURPOSE}
    if not later or cur["sales"] is None or cur["operating_income"] is None:
        return {**out, "kind": "成長投資（成果は未確認: 後の年の数値がまだ無い）", "rating": CHECK_PURPOSE}
    grew = any(r["sales"] > cur["sales"] and r["operating_income"] > cur["operating_income"] for r in later)
    if grew:
        return {**out, "kind": "成長投資（成果あり）", "rating": OK_PURPOSE}
    return {**out, "kind": "成長投資（売上高・営業利益の伸びが見えない）", "rating": CHECK_PURPOSE}


def step3(rows: list[dict]) -> dict:
    with_debt = [r for r in rows if r["debt"] is not None][-(TREND_YEARS + 1):]
    if len(with_debt) < 2:
        return {"rating": UNKNOWN, "years": [], "basis": "有利子負債の推移が取れない",
                "sentence": "借入の目的は判定できない（有利子負債の推移が取れない）"}
    years = [classify(rows, prev, cur) for prev, cur in zip(with_debt, with_debt[1:])
             if _months_apart(prev["year"], cur["year"]) == 12 and cur["debt"] > prev["debt"]
             and cur["total_assets"] and cur["debt"] - prev["debt"] >= DEBT_MATERIAL * cur["total_assets"]]
    span = f"{with_debt[0]['year']}〜{with_debt[-1]['year']}"
    if not years:
        return {"rating": OK_PURPOSE, "years": [], "basis": f"{span} に有利子負債が総資産の1%以上増えた年なし",
                "sentence": f"借入の目的: {span} に有利子負債が目立って増えた年はない（{OK_PURPOSE}）"}
    ratings = {y["rating"] for y in years}
    rating = BAD_PURPOSE if BAD_PURPOSE in ratings else OK_PURPOSE if ratings == {OK_PURPOSE} else CHECK_PURPOSE
    listed = "、".join(f"{y['year']} {y['kind']}" for y in years)
    return {"rating": rating, "years": years, "basis": listed,
            "sentence": f"借入の目的: {listed}で{rating}"}


# ---------- 手順4 ----------

def _rule(ratings: dict[str, str], trend: str, purpose: str) -> str:
    misses = [k for k, r in ratings.items() if r == MISS]
    if len(misses) >= 2 or (trend == WORSE and purpose == BAD_PURPOSE):
        return "懸念"
    if not misses and trend == STABLE:
        return "良好"
    return "普通"


def _options(value: str, unknown: str, choices: tuple[str, ...]) -> tuple[str, ...]:
    return choices if value == unknown else (value,)


WORST_FIRST = ("懸念", "普通", "良好")


def unknown_parts(s1: dict, s2: dict, s3: dict) -> list[str]:
    unknown = [NAMES[i["key"]] for i in s1["items"] if i["rating"] == UNKNOWN]
    return unknown + [label for label, s in (("推移", s2), ("借入の目的", s3)) if s["rating"] == UNKNOWN]


def judge(s1: dict, s2: dict, s3: dict) -> tuple[str, str]:
    """(良好/普通/懸念/判定保留, why). Every value an unknown could take is tried; when the outcomes differ the
    worst one is taken (policy.md 行動指針6). 判定保留 only when none of the three indicators is known."""
    ratings = {i["key"]: i["rating"] for i in s1["items"]}
    unknown = [NAMES[k] for k, r in ratings.items() if r == UNKNOWN]
    if ratings and len(unknown) == len(ratings):
        return "判定保留", f"{'・'.join(unknown)}をすべて判定できない（判断に使える事実が無い）"
    keys = list(ratings)
    choices = [_options(ratings[k], UNKNOWN, (CLEAR, MISS)) for k in keys]
    outcomes = {_rule(dict(zip(keys, combo)), trend, purpose)
                for combo in itertools.product(*choices)
                for trend in _options(s2["rating"], UNKNOWN, (STABLE, WORSE))
                for purpose in _options(s3["rating"], UNKNOWN, (OK_PURPOSE, BAD_PURPOSE))}
    verdict = next(v for v in WORST_FIRST if v in outcomes)
    if len(outcomes) > 1:
        return verdict, (f"{'・'.join(unknown_parts(s1, s2, s3))}が不明で結論が分かれるため、最も悪い「{verdict}」を採った"
                         "（材料不足のため保守的に判定）")
    return verdict, _why(verdict, s1, s2, s3, unknown)


def _why(verdict: str, s1: dict, s2: dict, s3: dict, unknown: list[str]) -> str:
    misses = [i["name"] for i in s1["items"] if i["rating"] == MISS]
    note = f"（{'・'.join(unknown)}は不明だが結論は変わらない）" if unknown else ""
    if verdict == "懸念":
        if len(misses) >= 2:
            return f"{'・'.join(misses)}が目安・同業平均とも未達{note}"
        return f"悪化傾向（{s2['basis']}）かつ借入の目的が懸念（{s3['basis']}）{note}"
    if verdict == "良好":
        return "3指標とも目安または同業平均をクリアし、悪化傾向なし"
    reasons = []
    if misses:
        reasons.append(f"{'・'.join(misses)}が未達")
    if s2["rating"] == WORSE:
        reasons.append(f"悪化傾向あり（{s2['basis']}。借入の目的は懸念でない）")
    return "、".join(reasons or ["良好の条件を満たさない"]) + note


# ---------- borderline / warnings ----------

def _near_paths(item: dict, excluded: bool) -> list[str]:
    """The comparisons of one indicator that could flip its rating: for a クリア, the only path that clears it
    (none when both the 目安 and the peer average clear it); for a 未達, any path within twice its band."""
    key, value, peer = item["key"], item["value"], item["peer_avg"]
    target_near = not excluded and abs(value - TARGETS[key]) <= BORDER[key]
    peer_near = peer is not None and abs(value - peer) <= BORDER[key]
    if item["rating"] == CLEAR:
        if item["by_target"] and item["by_peer"]:
            return []
        return (["target"] if item["by_target"] and target_near else []) + \
               (["peer"] if item["by_peer"] and peer_near else [])
    return (["target"] if target_near else []) + (["peer"] if peer_near else [])


def borderline(s1: dict, s2: dict) -> list[str]:
    """Comparisons within twice their band that could move the judgement one step (a small change in the data
    or the next fiscal year). A comparison the indicator clears with room, or one backed by a second path, is
    not listed."""
    out = []
    own = s1["own"]
    for item in s1["items"]:
        key, value = item["key"], item["value"]
        if value is None or item["rating"] == UNKNOWN or (key == "de" and s1["debt_free"]):
            continue
        for path in _near_paths(item, s1["excluded"]):
            against = f"目安 {item['target']}" if path == "target" else f"同業平均 {fmt(key, item['peer_avg'])}"
            out.append(f"手順1: {item['name']} {fmt(key, value)} が{against}に近い（{item['rating']}）")
    if own and own["net_cash"] is not None and own["total_assets"] \
            and abs(own["net_cash"]) <= NET_CASH_BORDER * own["total_assets"]:
        out.append(f"手順1: ネットキャッシュ {money(own['net_cash'])} {s1['unit']}が総資産の"
                   f"{NET_CASH_BORDER * 100:.0f}%以内（実質無借金の扱いが変わりうる）")
    if s2["drop"] is not None and abs(s2["drop"] - EQUITY_DROP_PT) <= BORDER["equity_ratio"]:
        out.append(f"手順2: 自己資本比率の低下 {s2['drop']:.1f}pt が基準 {EQUITY_DROP_PT:.0f}pt に近い")
    return out


def warnings(cands: dict) -> list[str]:
    """Signs that the series were read wrongly (shown in the brief and prepare's output)."""
    out = []
    for r in cands["rows"]:
        if r["reported_ratio"] is not None and r["equity_ratio"] is not None \
                and abs(r["reported_ratio"] - r["equity_ratio"]) > MISMATCH_PT:
            out.append(f"自己資本比率 {r['year']}: 開示 {r['reported_ratio']:.1f}% と計算 {r['equity_ratio']:.1f}% が "
                       f"{MISMATCH_PT:.0f}pt 超ずれる（総資産・自己資本の読み違いの可能性）")
    own = cands["step1"]["own"]
    if own and own["insolvent"]:
        out.append(f"自己資本 {own['year']}: {money(own['equity'])} {cands['step1']['unit']}でマイナス（債務超過）。資本の中身（優先株の区分など）を"
                   "brief の貸借・資本政策の記述で確かめる")
    if own and own["debt_source"].startswith("借入金・社債の内訳"):
        out.append(f"有利子負債 {own['year']}: 「有利子負債」の行が無く、借入金・社債の内訳の合計を使った（リース債務は含まない）")
    for p in cands["peer_names"]:
        if p not in {m["name"] for m in cands["step1"]["peers"]}:
            out.append(f"競合 {p}: 自社の直近期（±{MATCH_MONTHS}か月）に合う年度の指標を計算できない")
    return out


# ---------- everything ----------

def candidates(company, found: dict) -> dict:
    series = SS.self_series(company, found)
    rows = balance_rows(series)
    peers = SS.peer_series(company, found)
    s1 = step1(rows, peers, sector_excluded(company), SS.unit_label(company))
    s2, s3 = step2(rows), step3(rows)
    verdict, why = judge(s1, s2, s3)
    return {"series": series, "rows": rows, "peer_names": [p["name"] for p in peers],
            "step1": s1, "step2": s2, "step3": s3, "borderline": borderline(s1, s2), "verdict": verdict,
            "why": why, "conservative": ([f"{p}が不明 → 結論が分かれ、最も悪い方を採った" for p in unknown_parts(s1, s2, s3)]
                                         if "保守的" in why else [])}


def collect_requests(company, found: dict, cands: dict) -> list[dict]:
    """Missing required sections, plus an own series without the three indicators (or too short for the trend)
    and a peer section that yields no indicator."""
    unavailable = I.unavailable_items(company)
    s1 = cands["step1"]
    own_short = (s1["own"] is None or any(s1["own"][k] is None for k, _ in INDICATORS if not
                                          (k == "de" and s1["own"]["insolvent"]))
                 or cands["step2"]["rating"] == UNKNOWN or cands["step3"]["rating"] == UNKNOWN)
    extra: list[tuple[str, str]] = []
    if own_short and not any(OWN_UNAVAILABLE in u for u in unavailable):
        extra.append(("collect-filings", OWN_ITEM))
    peer_debt = any(p["de"] is not None or p["current_ratio"] is not None for p in s1["peers"])
    if found["peer_safety"].status == "ok" and not peer_debt:
        extra.append(("collect-peers-valuation", PEER_ITEM))
    out = [dict(r, items=list(r["items"])) for r in I.collect_requests(found)]
    for agent, item in extra:
        hit = next((r for r in out if r["agent"] == agent), None)
        if hit is None:
            out.append({"agent": agent, "items": [item]})
        elif item not in hit["items"]:
            hit["items"] = hit["items"] + [item]
    return out


def _r(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def series_digest(cands: dict) -> str:
    """Every number the result rests on: a new fiscal year or a corrected value re-opens the result."""
    own = [[r["year"], _r(r["equity_ratio"]), _r(r["de"], 3), _r(r["current_ratio"]), _r(r["net_cash"], 0),
            _r(r["cfo"], 0), _r(r["cfi"], 0)] for r in cands["rows"]]
    peers = [[p["name"], p["year"], _r(p["equity_ratio"]), _r(p["de"], 3), _r(p["current_ratio"])]
             for p in cands["step1"]["peers"]]
    return A.digest(json.dumps([own, peers], ensure_ascii=False))
