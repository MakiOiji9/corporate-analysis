"""Numbers behind the moat criteria (企業分析フレームワーク.md 1-3 手順2) and the candidate they imply.

  強い裏付け: operating margin above the peer average for the last 10 years (at least 7)
  弱い裏付け: above the peer average for about the last 5 years
  裏付けなし: at or below the peer average
Here only the margin side is decided: the number of consecutive fiscal years, counted back from the newest
year that can be compared, in which the target's operating margin is above the simple average of the peers
(7+ 強い / 1-6 弱い / 0 なし). The share trend is the writer's rating and build combines the two.
The comparison table (3.1) and the cost-structure table (3.2) are computed here so the writer never calculates.
"""
from __future__ import annotations

import re

import mdparse as M
from ff_inputs import Found, raw_files
from ff_metrics import FORECAST, PERCENT, _margins_from_table, _months_apart, _peer_rows, peer_margins
from tc_metrics import MAX_PEERS, _is_self, _series_from_data

STRONG_YEARS = 7  # framework: 過去10年（最低でも7年以上）
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
    """One row per target fiscal year: the target's margin, each matched peer and their simple average."""
    rows = []
    for year, value in margins.items():
        matched = []
        for p in peer_list:
            s = _nearest(p["series"], year)
            if s:
                matched.append({"name": p["name"], "year": s["year"], "margin": s["margin"]})
        avg = round(sum(m["margin"] for m in matched) / len(matched), 1) if matched else None
        rows.append({"year": year, "self": round(value, 1), "avg": avg,
                     "diff": round(value - avg, 1) if avg is not None else None, "peers": matched})
    return rows


def consecutive_above(rows: list[dict]) -> tuple[int, str | None]:
    """(years, newest compared year): consecutive years above the peer average, counted back from the newest
    year that has a peer average. A missing year or a year without peers ends the run."""
    compared = [r for r in rows if r["avg"] is not None]
    if not compared:
        return 0, None
    newest = compared[-1]["year"]
    count, previous = 0, None
    for r in reversed([r for r in rows if r["year"] <= newest]):
        if r["avg"] is None or r["self"] <= r["avg"]:
            break
        if previous and _months_apart(r["year"], previous) != 12:
            break
        count, previous = count + 1, r["year"]
    return count, newest


def margin_candidate(rows: list[dict]) -> dict:
    count, newest = consecutive_above(rows)
    compared = sum(1 for r in rows if r["avg"] is not None)
    if newest is None:
        return {"rating": None, "fixed": False, "years_above": 0, "compared_years": 0,
                "basis": "自社と競合の営業利益率を同じ年度で比べられない（自社または競合の推移が raw に無い）"}
    rating = "強い" if count >= STRONG_YEARS else "弱い" if count >= 1 else "なし"
    parts = [f"{newest} から遡って {count} 年連続で同業平均を上回る（比較できた年 {compared}）"]
    if 1 <= count < STRONG_YEARS and compared < STRONG_YEARS:
        parts.append(f"比較できる年が {STRONG_YEARS} 年に満たないため「強い」にはならない")
    newer = [r["year"] for r in rows if r["year"] > newest]
    if newer:
        parts.append(f"競合の数値が無い新しい年度（比較から除外）: {', '.join(newer)}")
    basis = "。".join(parts) + f"。目安: {STRONG_YEARS}年以上 強い / 1〜{STRONG_YEARS - 1}年 弱い / 直近が平均以下 なし"
    return {"rating": rating, "fixed": True, "years_above": count, "compared_years": compared, "basis": basis}


def candidates(company, found: dict[str, Found]) -> dict:
    listed = peer_margins(found["peers"])
    margins, sources = self_series(company, listed)
    rows = comparison_rows(margins, peers(company, found["peers"]))
    costs = cost_rows(company, found["peer_cost"])
    return {"margin": margin_candidate(rows), "rows": rows, "sources": sources, "costs": costs}


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
