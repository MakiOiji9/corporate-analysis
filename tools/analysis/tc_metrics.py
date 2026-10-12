"""Numbers behind the 3C criteria and the ratings they imply (the "script candidates").

企業分析フレームワーク.md 1-2:
  手順1 成長性: market growth >=3% 高 / 0-3% 中 / <0 低 (which market is the main one is the writer's
        call, so the candidate is never fixed)
  手順2 競合: operating margin and share ranked in the comparison set (target + peers);
        both top 優位 / both bottom 劣位 / otherwise 同等. Fixed only when both metrics are known.
The comparison table (2.1) is computed here so the writer never calculates.
"""
from __future__ import annotations

import re

import mdparse as M
from common import read_csv_rows
from ff_inputs import Found
from ff_metrics import PERCENT, _months_apart, market_growth, peer_margins
from tc_paths import Company

GROWTH_LIMITS = (0.0, 3.0)  # <0 低 / 0-3 中 / >=3 高
GROWTH_ORDER = {"高": 2, "中": 1, "低": 0}
COMPETITOR_ORDER = {"優位": 2, "同等": 1, "劣位": 0}
MAX_PEERS = 3
CAGR_MONTHS = 36
UNIT_YEN = {"円": 1.0, "千円": 1e3, "百万円": 1e6, "億円": 1e8}
CSV_ITEMS = (("financials.csv", "item", "net_sales", "operating_income"),
             ("tdnet_facts.csv", "element", "NetSales", "OperatingIncome"))
CODE = re.compile(r"[（(]\s*([0-9A-Z]{1,5})\s*[)）]")
NOISE = re.compile(r"[（(].*?[)）]|参考[:：]|株式会社|ホールディングス|HD|グループ|\s")


# ---------- 手順1 成長性 ----------

def _growth_rating(value: float) -> str:
    low, high = GROWTH_LIMITS
    return "低" if value < low else "中" if value < high else "高"


def growth(found: Found) -> dict:
    """Candidate from the first market growth figure in industry-overview「市場規模と成長率」."""
    lines = market_growth(found)
    for line in lines:
        m = PERCENT.search(line.split(":", 1)[-1])
        if m:
            value = float(m.group(1))
            others = "; ".join(x for x in lines[:4] if x != line)
            return {"rating": _growth_rating(value), "fixed": False, "value": value,
                    "basis": (f"先頭の市場の成長率 {value:.1f}%（{line}）。主力事業の市場が別なら書き手が選ぶ。"
                              f"目安: 3%以上 高 / 0〜3% 中 / マイナス 低" + (f"。他の市場: {others}" if others else ""))}
    return {"rating": None, "fixed": False, "value": None,
            "basis": "市場規模の表に成長率（CAGR）の列・行が無い" if found.status == "ok" else "市場規模の記載が無い"}


# ---------- 手順2 競合: 比較表 ----------

def _key(name: str) -> str:
    return NOISE.sub("", name).lower()


def same_company(a: str, b: str) -> bool:
    """Loose match of company names written differently across sections ('シグマクシスHD' / 'シグマクシス・…')."""
    ca, cb = CODE.search(a), CODE.search(b)
    if ca and cb:
        return ca.group(1) == cb.group(1)
    ka, kb = _key(a).replace("・", ""), _key(b).replace("・", "")
    short, long_ = sorted((ka, kb), key=len)
    return len(short) >= 3 and short[:4] in long_


def _is_self(name: str, company: Company) -> bool:
    code = CODE.search(name)
    if code:
        return code.group(1).lower() == company.ticker.lower()
    return same_company(name, company.display_name())  # heading written without the code


def _series_from_data(company: Company) -> list[dict]:
    """Actual sales / operating margin by fiscal year end from data/ CSVs (EDINET XBRL, TDnet)."""
    by_year: dict[str, dict[str, float]] = {}
    for name, column, sales_key, profit_key in CSV_ITEMS:
        path = company.path / "data" / name
        if not path.exists():
            continue
        for row in read_csv_rows(path):
            context = row.get("context", "")
            if name == "tdnet_facts.csv" and not ("CurrentYear" in context and "Result" in context
                                                  and "NonConsolidated" not in context):
                continue
            period = (row.get("period_end") or row.get("fiscal_year_end") or "")[:7]
            item = row.get(column, "")
            if item not in (sales_key, profit_key) or not period:
                continue
            try:
                value = float(row.get("value", "")) * UNIT_YEN.get(row.get("unit", "円"), 1.0)
            except ValueError:
                continue
            by_year.setdefault(period, {}).setdefault("sales" if item == sales_key else "profit", value)
    return [{"year": y, "sales": v["sales"], "margin": round(v["profit"] / v["sales"] * 100, 1), "forecast": False}
            for y, v in sorted(by_year.items()) if v.get("sales") and "profit" in v]


def _cagr(actual: list[dict]) -> float | None:
    latest = actual[-1]
    old = next((s for s in actual if _months_apart(s["year"], latest["year"]) == CAGR_MONTHS), None)
    if not old or not old.get("sales") or not latest.get("sales") or old["sales"] <= 0:
        return None
    return round(((latest["sales"] / old["sales"]) ** (1 / 3) - 1) * 100, 1)


def _shares(found: Found) -> list[tuple[str, float]]:
    out = []
    for table in M.tables(found.body) if found.status == "ok" else []:
        col = next((i for i, h in enumerate(table[0]) if "シェア" in h), None)
        for row in table[1:] if col is not None else []:
            m = PERCENT.search(row[col]) if col < len(row) else None
            if m:
                out.append((row[0], float(m.group(1))))
    return out


def _row(name: str, series: list[dict], is_self: bool, source: str, shares: list[tuple[str, float]]) -> dict:
    actual = [s for s in series if not s["forecast"]]
    latest = actual[-1] if actual else {}
    share = next((v for n, v in shares if same_company(n, name)), None)
    return {"name": name, "self": is_self, "year": latest.get("year"), "sales": latest.get("sales"),
            "margin": latest.get("margin"), "share": share, "cagr": _cagr(actual) if actual else None,
            "source": source}


def comparison(company: Company, found: dict[str, Found]) -> list[dict]:
    """Target first, then up to MAX_PEERS peers in the order of competitors.md「売上高・営業利益」."""
    peers_found = found["peers"]
    source = f"{peers_found.path.name}「{peers_found.heading}」" if peers_found.path else "—"
    shares = _shares(found["peer_share"])
    listed = peer_margins(peers_found)
    self_listed = next((p for p in listed if _is_self(p["name"], company)), None)
    data = _series_from_data(company)
    merged = {s["year"]: s for s in (self_listed or {}).get("series", []) if not s["forecast"]}
    merged.update({s["year"]: s for s in data})  # the company's own filings win over the peer table
    self_source = ", ".join(x for x in (source if self_listed else "", "data/*.csv" if data else "") if x) or "—"
    rows = [_row(f"{company.display_name()}（対象）", [merged[y] for y in sorted(merged)], True, self_source, shares)]
    for peer in [p for p in listed if p is not self_listed][:MAX_PEERS]:
        rows.append(_row(peer["name"], peer["series"], False, source, shares))
    # the target's share row may be written under its short name
    if rows[0]["share"] is None and self_listed:
        rows[0]["share"] = next((v for n, v in shares if same_company(n, self_listed["name"])), None)
    return rows


def peer_names(rows: list[dict]) -> list[str]:
    return [r["name"] for r in rows if not r["self"]]


# ---------- 手順2 競合: 判定候補 ----------

def _position(rows: list[dict], key: str) -> tuple[str | None, int, int]:
    """(上位/中位/下位 or None, rank, count) of the target among rows that have the value."""
    known = [r for r in rows if r.get(key) is not None]
    target = next((r for r in known if r["self"]), None)
    if target is None or len(known) < 2:
        return None, 0, len(known)
    value = target[key]
    rank = 1 + sum(1 for r in known if r[key] > value)
    ties = sum(1 for r in known if r[key] == value) > 1
    if not ties and rank == 1:
        return "上位", rank, len(known)
    if not ties and rank == len(known):
        return "下位", rank, len(known)
    return "中位", rank, len(known)


def _years_apart(rows: list[dict]) -> list[str]:
    years = [r["year"] for r in rows if r.get("year")]
    if len(years) < 2:
        return []
    newest = max(years)
    return [f"{r['name']}（{r['year']}）" for r in rows if r.get("year") and _months_apart(r["year"], newest) > 12]


def competitor(rows: list[dict]) -> dict:
    margin_pos, m_rank, m_count = _position(rows, "margin")
    share_pos, s_rank, s_count = _position(rows, "share")
    target = rows[0] if rows and rows[0]["self"] else {}
    if margin_pos is None:
        return {"rating": None, "fixed": False, "margin_position": None, "share_position": share_pos,
                "basis": "自社または競合の営業利益率がそろわない（比較表を作れない）"}
    stale = _years_apart(rows)
    parts = [f"営業利益率 {target['margin']:.1f}%（{m_count}社中 {m_rank}位: {margin_pos}）"]
    if share_pos:
        parts.append(f"シェア {target['share']:.1f}%（{s_count}社中 {s_rank}位: {share_pos}）")
        if margin_pos == share_pos == "上位":
            rating = "優位"
        elif margin_pos == share_pos == "下位":
            rating = "劣位"
        else:
            rating = "同等"
        fixed = not stale
    else:
        parts.append("シェア: 比較できる数値なし（営業利益率だけで判定）")
        rating = "劣位" if margin_pos == "下位" else "同等"  # one metric cannot make 優位; bottom -> 不利な方
        fixed = False
    if stale:
        parts.append(f"年度が1年以上古い会社あり: {', '.join(stale)}")
    basis = "、".join(parts) + "。目安: 両方上位 優位 / 片方上位・中位 同等 / 両方下位 劣位"
    return {"rating": rating, "fixed": fixed, "margin_position": margin_pos, "share_position": share_pos,
            "basis": basis}


# ---------- formatting ----------

def _amount(yen: float | None) -> str:
    if yen is None:
        return "—"
    return f"{yen / 1e8:,.1f}億円" if abs(yen) >= 1e8 else f"{yen:,.0f}"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def table_rows(rows: list[dict]) -> str:
    if not rows or all(r.get("margin") is None for r in rows):
        return "| — | — | — | — | — | — | 比較できる数値が raw に無い（brief.md の抜粋を見る） |"
    return "\n".join(
        f"| {'**' + r['name'] + '**' if r['self'] else r['name']} | {r['year'] or '—'} | {_amount(r['sales'])} | "
        f"{_pct(r['margin'])} | {_pct(r['share'])} | {_pct(r['cagr'])} | {r['source']} |" for r in rows)


def candidates(company: Company, found: dict[str, Found]) -> dict:
    rows = comparison(company, found)
    return {"growth": growth(found["market_size"]), "competitor": competitor(rows), "rows": rows}
