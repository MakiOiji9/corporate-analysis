"""Numbers behind the moat criteria (企業分析フレームワーク.md 1-3) and the candidates they imply.

The gate (超過収益: ROIC against the cost of capital) and the pricing power are computed in mt_returns.
Here the supporting operating-margin comparison (2.2): the share of the compared fiscal years in which the target's
operating margin is above the median of the peers (margin_candidate; the median, so that one outlier peer does not
decide it, and the share rather than a streak, so that one cyclical year does not cancel the rest). It is shown to
the writer and recorded, but the verdict rests on the ROIC gate.
The comparison table (2.2) and the cost-structure table (3.2) are computed here so the writer never calculates.
"""
from __future__ import annotations

import json
import math
import re
import statistics

import an_common as A
import mdparse as M
import mt_returns as R
import share_tables as ST
from ff_inputs import Found, raw_files
from ff_metrics import FORECAST, PERCENT, _margins_from_table, _months_apart, _peer_rows, _year, peer_margins
from tc_metrics import MAX_PEERS, _is_self, _series_from_data

STRONG_YEARS = 7  # framework: 過去10年（最低でも7年以上）
STRONG_SHARE = 0.8  # 強い: above the peer median in this share of the compared years
MATCH_MONTHS = 6  # a peer's fiscal year counts for the target's year when its end is at most this far away
SKIP_SECTION = re.compile(r"予想|計画|四半期|CAGR|提出会社|単体|個別")  # consolidated actuals only
SECTION = re.compile(r"^#{2,3}\s+(.+)$", re.M)  # ### too, so a 提出会社 sub-table is skipped on its own


# ---------- 自社の営業利益率 ----------

def _sections(text: str) -> list[tuple[str, str]]:
    marks = list(SECTION.finditer(text))
    return [(m.group(1), text[m.end():marks[i + 1].start() if i + 1 < len(marks) else len(text)])
            for i, m in enumerate(marks)]


def _from_raw_tables(company) -> dict[str, float]:
    """Actual operating margins from the P/L tables of financials-historical and yuho (newest file first).
    Year-per-row tables (10年サマリー) and year-per-column tables (主要な経営指標) are both read; sections
    and tables about forecasts / plans / quarters are skipped."""
    out: dict[str, float] = {}
    for kind in ("financials-historical", "yuho"):
        for _, path in raw_files(company, kind):
            for title, body in _sections(path.read_text(encoding="utf-8")):
                if SKIP_SECTION.search(title):
                    continue
                for table in M.tables(body):
                    if any(FORECAST.search(h) for h in table[0]):
                        continue
                    for row in _peer_rows(table):
                        if not row["forecast"]:
                            out.setdefault(row["year"], row["margin"])
                    for year, value in _margins_from_table(table, "operating").items():
                        out.setdefault(year, round(value, 1))
    return out


def self_series(company, listed: list[dict]) -> tuple[dict[str, float], list[str]]:
    """(margin by fiscal year end, sources): data/*.csv, then raw P/L tables, then the target's own block in
    competitors.md「売上高・営業利益」. Forecasts are excluded."""
    margins: dict[str, float] = {}
    sources: list[str] = []
    data = {s["year"]: s["margin"] for s in _series_from_data(company)}
    if data:
        margins.update(data)
        sources.append("data/*.csv")
    raw = {y: v for y, v in _from_raw_tables(company).items() if y not in margins}
    if raw:
        margins.update(raw)
        sources.append("raw の財務時系列・有報")
    own = next((p for p in listed if _is_self(p["name"], company)), None)
    extra = {s["year"]: s["margin"] for s in (own or {}).get("series", [])
             if not s["forecast"] and s["year"] not in margins}
    if extra:
        margins.update(extra)
        sources.append("competitors.md の自社欄")
    return dict(sorted(margins.items())), sources


# ---------- 同業比較 ----------

def peers(company, found: Found) -> list[dict]:
    """Up to MAX_PEERS peers in the order of competitors.md (the same set as the 3C comparison), actuals only."""
    listed = [p for p in peer_margins(found) if not _is_self(p["name"], company)][:MAX_PEERS]
    return [{"name": p["name"], "series": [s for s in p["series"] if not s["forecast"]]} for p in listed]


def _nearest(series: list[dict], year: str) -> dict | None:
    near = [(abs(_months_apart(s["year"], year)), s) for s in series]
    near = [(d, s) for d, s in near if d <= MATCH_MONTHS]
    return min(near, key=lambda x: x[0])[1] if near else None


def comparison_rows(margins: dict[str, float], peer_list: list[dict]) -> list[dict]:
    """One row per target fiscal year: the target's margin, each matched peer, their median (avg: the value the
    comparison uses) and their simple mean (shown for reference)."""
    rows = []
    for year, value in margins.items():
        matched = []
        for p in peer_list:
            s = _nearest(p["series"], year)
            if s:
                matched.append({"name": p["name"], "year": s["year"], "margin": s["margin"]})
        values = [m["margin"] for m in matched]
        avg = round(statistics.median(values), 1) if values else None
        mean = round(sum(values) / len(values), 1) if values else None
        rows.append({"year": year, "self": round(value, 1), "avg": avg, "mean": mean,
                     "diff": round(value - avg, 1) if avg is not None else None, "peers": matched})
    return rows


def margin_candidate(rows: list[dict]) -> dict:
    """強い: STRONG_YEARS+ years compared and above the peer median in STRONG_SHARE of them; なし: above in fewer
    than half; else 弱い. The share of years, not a streak: one cyclical year below does not cancel nine above."""
    compared = [r for r in rows if r["avg"] is not None]
    if not compared:
        return {"rating": None, "fixed": False, "years_above": 0, "compared_years": 0,
                "basis": "自社と競合の営業利益率を同じ年度で比べられない（自社または競合の推移が raw に無い）"}
    above = sum(1 for r in compared if r["self"] > r["avg"])
    n = len(compared)
    if above * 2 < n:
        rating = "なし"
    elif n >= STRONG_YEARS and above >= math.ceil(STRONG_SHARE * n):
        rating = "強い"
    else:
        rating = "弱い"
    latest = compared[-1]
    parts = [f"{compared[0]['year']}〜{latest['year']} の比較できた {n} 年中 {above} 年で同業中央値を上回る"
             f"（直近 {latest['year']} は{'上回る' if latest['self'] > latest['avg'] else '中央値以下'}）"]
    if rating == "弱い" and n < STRONG_YEARS and above == n:
        parts.append(f"比較できる年が {STRONG_YEARS} 年に満たないため「強い」にはならない")
    newer = [r["year"] for r in rows if r["year"] > latest["year"]]
    if newer:
        parts.append(f"競合の数値が無い新しい年度（比較から除外）: {', '.join(newer)}")
    basis = "。".join(parts) + (f"。目安: {STRONG_YEARS}年以上を比べて8割以上の年で上回る 強い / 上回った年が半分未満 なし"
                                " / ほか 弱い（連続年数ではなく上回った年の割合で見る）")
    return {"rating": rating, "fixed": True, "years_above": above, "compared_years": n, "basis": basis}


def candidates(company, found: dict[str, Found]) -> dict:
    listed = peer_margins(found["peers"])
    margins, sources = self_series(company, listed)
    rows = comparison_rows(margins, peers(company, found["peers"]))
    costs = cost_rows(company, found["peer_cost"])
    return {"margin": margin_candidate(rows), "rows": rows, "sources": sources, "costs": costs,
            "returns": R.returns(company, found), "pricing": R.pricing(company, costs),
            "share_trend": ST.share_trend(found["share"])}


# ---------- 収集の要求 ----------

ROIC_AGENT = "collect-filings"
ROIC_ITEM = f"財務時系列: 営業利益・自己資本・有利子負債（{R.MIN_YEARS}年以上。ROIC の計算）"
ROIC_UNAVAILABLE = "ROIC の財務時系列"  # collect-filings reports a short own history under this name


def needs_roic_history(returns: dict, unavailable: list[str]) -> bool:
    """The gate cannot be decided (超過収益 不明) and status.md does not yet say the history is unobtainable."""
    return returns["rating"] is None and not any(ROIC_UNAVAILABLE in item for item in unavailable)


def with_roic_request(requests: list[dict], returns: dict, unavailable: list[str]) -> list[dict]:
    """collect_requests plus the target's balance history when the ROIC gate lacks years (a new list)."""
    if not needs_roic_history(returns, unavailable):
        return requests
    if any(r["agent"] == ROIC_AGENT for r in requests):
        return [dict(r, items=r["items"] + [ROIC_ITEM]) if r["agent"] == ROIC_AGENT else r for r in requests]
    return requests + [{"agent": ROIC_AGENT, "items": [ROIC_ITEM]}]


# ---------- 材料の警告 ----------

MISMATCH_PT = 0.1  # the target's margin in 3.1 and 3.2 may differ by rounding only


def margin_digest(cands: dict) -> str:
    """The yearly comparison (3.1) behind the margin candidate. Recorded at build: the series is read from every
    P/L table and data/*.csv, not only from the sections in SPECS, so a new fiscal year re-opens the result."""
    rows = [[r["year"], r["self"], [[m["name"], m["year"], m["margin"]] for m in r["peers"]]] for r in cands["rows"]]
    rows += [[r["year"], r["roic"]] for r in cands["returns"]["rows"]]
    return A.digest(json.dumps(rows, ensure_ascii=False))


def warnings(cands: dict) -> list[str]:
    """Signs that the brief or the skeleton read the raw wrongly (shown to the writer and in prepare's output)."""
    out = []
    costs = cands["costs"]
    for key, label in (("cost", "売上原価率"), ("sga", "販管費率")):  # 営業利益率 may be left out of the table
        if costs and all(r[key] is None for r in costs):
            out.append(f"3.2 コスト構造の{label}が全社で読めない（competitors.md「コスト構造」の列名を確認）")
    series = {r["year"]: r["self"] for r in cands["rows"]}
    for r in costs:
        year = _year(r["year"])
        if (r["self"] and r["margin"] is not None and year in series
                and round(abs(series[year] - r["margin"]), 1) >= MISMATCH_PT):
            out.append(f"自社の営業利益率 {year} が 2.2（{series[year]:.1f}%）と 3.2（{r['margin']:.1f}%）で違う"
                       f"（出典が違う。比較は 2.2 の値で行われる）")
    return out


# ---------- コスト構造 ----------

# ratio columns only: the table may also carry the amounts (売上原価・販管費) in columns of their own
COST_COLUMNS = (("company", ("会社",)), ("year", ("年度",)), ("cost", ("原価率",)), ("sga", ("販管費率", "販管費比率")),
                ("margin", ("営業利益率",)), ("source", ("出典",)))


def _pct(cell: str) -> float | None:
    m = PERCENT.search(cell)
    return float(m.group(1)) if m else None


def cost_rows(company, found: Found) -> list[dict]:
    """Rows of competitors.md「コスト構造」: company, year, 原価率, 販管費率, 営業利益率, source."""
    if not found.body:
        return []
    out = []
    for table in M.tables(found.body):
        header = table[0]
        cols = {key: next((i for i, h in enumerate(header) if any(w in h for w in words)), None)
                for key, words in COST_COLUMNS}
        if cols["company"] is None or (cols["cost"] is None and cols["sga"] is None):
            continue
        for row in table[1:]:
            cell = {k: (row[i] if i is not None and i < len(row) else "") for k, i in cols.items()}
            out.append({"name": cell["company"], "self": _is_self(cell["company"], company),
                        "year": cell["year"] or "—", "cost": _pct(cell["cost"]), "sga": _pct(cell["sga"]),
                        "margin": _pct(cell["margin"]), "source": cell["source"] or "—"})
    return out


def cost_average(rows: list[dict], key: str) -> float | None:
    """Simple average over the peers (target excluded)."""
    values = [r[key] for r in rows if not r["self"] and r.get(key) is not None]
    return round(sum(values) / len(values), 1) if values else None


# ---------- formatting ----------

def _p(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _matched(row: dict) -> str:
    return "、".join(f"{m['name']} {m['year']} {m['margin']:.1f}%" for m in row["peers"]) or "—（同じ時期の競合の数値なし）"


def margin_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | 自社の営業利益率の時系列が raw に無い |"
    return "\n".join(f"| {r['year']} | {_p(r['self'])} | {_p(r['avg'])} | "
                     f"{'—' if r['diff'] is None else format(r['diff'], '+.1f') + 'pt'} | {_matched(r)} |"
                     for r in rows)


def cost_table_rows(rows: list[dict]) -> str:
    if not rows:
        return "| — | — | — | — | — | competitors.md「コスト構造」に表が無い |"
    lines = [f"| {'**' + r['name'] + '**' if r['self'] else r['name']} | {r['year']} | {_p(r['cost'])} | "
             f"{_p(r['sga'])} | {_p(r['margin'])} | {r['source']} |" for r in rows]
    if any(not r["self"] for r in rows):
        lines.append(f"| 競合の単純平均 | — | {_p(cost_average(rows, 'cost'))} | {_p(cost_average(rows, 'sga'))} | "
                     f"{_p(cost_average(rows, 'margin'))} | スクリプトが計算（対象企業を除く） |")
    return "\n".join(lines)
