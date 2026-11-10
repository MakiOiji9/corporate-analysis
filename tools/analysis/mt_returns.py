"""Excess returns and pricing power behind the moat (企業分析フレームワーク.md 1-3 手順1・手順2).

  ROIC = 税引後営業利益 ÷ 投下資本. 税引後営業利益 = 営業利益 × (1 − 法定実効税率) (a loss is not reduced by the tax);
  投下資本 = 自己資本 + 有利子負債 + リース負債 − 余剰現金, the average of the year's opening and closing values when
  both are known. 余剰現金 = 現金 + 短期投資 − 売上高の5% (the cash the business needs), its deduction capped at half
  of the capital (a cash-rich company would otherwise show an inflated ROIC). Lease and short-term investments come
  from data/financials.csv when it has them. The peers' ROIC uses the same formula with what competitors.md gives
  (自己資本・有利子負債・現金・売上高; no lease), so their excess cash is deducted too.
  The cost of capital is fixed per market (HURDLE); the spread is ROIC minus it.

  超過収益 (the gate of the moat analysis), over the newest WINDOW years with a ROIC:
    不明: fewer than MIN_YEARS years (but なし when the last 3 years are all at or below the cost of capital, or all
          operating losses: no excess return needs no long history to be shown)
    なし: ROIC above the cost of capital in fewer than half of the years, or the mean spread of the last 3 years <= 0
    強い: STRONG_YEARS+ years, above in 80%+ of them, and the median spread >= STRONG_SPREAD
    弱い: otherwise
  堀の幅 from the mean spread of the last 3 years; the trend of the spread (拡大/安定/縮小) compares the last 5 years
  with the years before them.

  価格決定力 from the gross margin: its range over the years, its change through the cost inflation of 2021-2023
  (fiscal years ending in INFLATION) and the peers' gross margin (100 − 売上原価率 of competitors.md「コスト構造」).

The peers' ROIC: operating margin from competitors.md「売上高・営業利益」 × sales, equity and debt from「収益性の分解」
and「安全性の指標」, so that the amounts of one peer stay in one unit.
"""
from __future__ import annotations

import math
import statistics

import ff_metrics as FM
import sf_series as SS
from ff_metrics import _months_apart, peer_margins
from tc_metrics import _is_self, same_company

HURDLE = {"japan": 7.0, "us": 9.0}  # 資本コスト（%）。市場ごとの固定値
TAX = {"japan": 30.6, "us": 25.0}  # 法定実効税率（%）
OPERATING_CASH_SHARE = 0.05  # 事業に必要な手元資金とみなす売上高の割合（これを超える現金・短期投資が余剰現金）
EXCESS_CASH_CAP = 0.5  # 余剰現金の控除は控除前の投下資本の半分まで
WINDOW = 10
MIN_YEARS = 5
STRONG_YEARS = 7
STRONG_SHARE = 0.8
STRONG_SPREAD = 5.0
RECENT_YEARS = 3
TREND_YEARS = 5
TREND_PT = 2.0
BORDER_PT = 2.0  # a year whose spread is within this is 境界 (the cost of capital is an estimate)
WIDTH = ((10.0, "大"), (3.0, "中"))  # mean spread of the last 3 years: >= 10 大 / >= 3 中 / > 0 小 / <= 0 なし
MATCH_MONTHS = 6
GROSS_STABLE_PT = 5.0
GROSS_UNSTABLE_PT = 10.0
INFLATION = ("2021", "2023")
INFLATION_DROP_PT = 2.0


def market(company) -> str:
    return "japan" if SS.JAPAN_TICKER.match(company.ticker.upper()) else "us"


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 1) if values else None


def _nearest(series: list[dict], year: str) -> dict | None:
    near = [(abs(_months_apart(s["year"], year)), s) for s in series]
    near = [(d, s) for d, s in near if d <= MATCH_MONTHS]
    return min(near, key=lambda x: x[0])[1] if near else None


# ---------- ROIC ----------

def _nopat(operating: float, tax: float) -> float:
    return operating * (1 - tax / 100) if operating > 0 else operating


def _get(series: SS.S.Series, field: str, year: str) -> float:
    value = series.get(field, {}).get(year)
    return value.value if value is not None else 0.0


def excess_cash(series: SS.S.Series, year: str) -> float:
    """Cash and short-term investments above OPERATING_CASH_SHARE of sales (0 without sales or cash)."""
    sales = series.get("sales", {}).get(year)
    cash = _get(series, "cash", year) + _get(series, "short_investments", year)
    return max(0.0, cash - OPERATING_CASH_SHARE * sales.value) if sales is not None and cash else 0.0


def _capital(series: SS.S.Series) -> dict[str, float]:
    """投下資本 = 自己資本 + 有利子負債 + リース負債 − 余剰現金, the deduction capped at EXCESS_CASH_CAP of the
    capital before it (a cash-rich company would otherwise show an inflated ROIC)."""
    out = {}
    for y in series["equity"]:
        if y not in series["debt"]:
            continue
        gross = series["equity"][y].value + series["debt"][y].value + _get(series, "lease", y)
        out[y] = gross - min(excess_cash(series, y), EXCESS_CASH_CAP * gross) if gross > 0 else gross
    return out


def roic_rows(series: SS.S.Series, tax: float, hurdle: float) -> list[dict]:
    """One row per fiscal year with an operating income, equity and debt (newest WINDOW years)."""
    capital = _capital(series)
    rows = []
    for year, op in series["operating_income"].items():
        if year not in capital:
            continue
        prior = next((c for y, c in capital.items() if _months_apart(y, year) == 12), None)  # y is 12 months earlier
        invested = (capital[year] + prior) / 2 if prior is not None else capital[year]
        if invested <= 0:
            continue
        roic = round(_nopat(op.value, tax) / invested * 100, 1)
        rows.append({"year": year, "operating": op.value, "invested": invested, "roic": roic,
                     "spread": round(roic - hurdle, 1)})
    return rows[-WINDOW:]


def peer_roic(company, found: dict, tax: float) -> list[dict]:
    """[{name, rows: [{year, roic}]}]: the margin of「売上高・営業利益」 applied to the sales of the balance tables."""
    margins = [p for p in peer_margins(found["peers"]) if not _is_self(p["name"], company)]
    out = []
    for peer in SS.peer_series(company, found):
        margin = next((m for m in margins if same_company(m["name"], peer["name"])), None)
        if margin is None:
            continue
        actual = [s for s in margin["series"] if not s["forecast"]]
        capital = _capital(peer["series"])
        rows = []
        for year, sales in peer["series"]["sales"].items():
            match = _nearest(actual, year)
            if match is None or capital.get(year, 0) <= 0:
                continue
            operating = sales.value * match["margin"] / 100
            rows.append({"year": year, "roic": round(_nopat(operating, tax) / capital[year] * 100, 1)})
        if rows:
            out.append({"name": peer["name"], "rows": rows})
    return out


def with_peer_median(rows: list[dict], peers: list[dict]) -> list[dict]:
    """The rows with the median ROIC of the peers whose fiscal year ends within MATCH_MONTHS (a new list)."""
    out = []
    for r in rows:
        matched = [m["roic"] for p in peers if (m := _nearest(p["rows"], r["year"])) is not None]
        out.append(dict(r, peer_median=_median(matched), peer_count=len(matched)))
    return out


def width(recent: float | None) -> str:
    if recent is None:
        return "不明"
    if recent <= 0:
        return "なし"
    return next((word for limit, word in WIDTH if recent >= limit), "小")


def trend(spreads: list[float]) -> str:
    """拡大/安定/縮小/不明: the mean spread of the last TREND_YEARS years against the years before (3 at least)."""
    split = TREND_YEARS if len(spreads) >= TREND_YEARS + 3 else 3 if len(spreads) >= 6 else 0
    if not split:
        return "不明"
    diff = sum(spreads[-split:]) / split - sum(spreads[:-split]) / len(spreads[:-split])
    return "拡大" if diff >= TREND_PT else "縮小" if diff <= -TREND_PT else "安定"


def _short_history(rows: list[dict], operating: list[float], base: dict) -> dict:
    """Fewer than MIN_YEARS years of ROIC: 不明, unless the last 3 years already show no excess return (all at or
    below the cost of capital, or an operating loss in each of them)."""
    n = len(rows)
    recent = [r["spread"] for r in rows[-RECENT_YEARS:]]
    if len(recent) == RECENT_YEARS and all(s <= 0 for s in recent):
        return dict(base, rating="なし", width="なし", recent_spread=_mean(recent),
                    basis=f"ROIC を計算できた年は {n} 年だが、直近{RECENT_YEARS}年はすべて資本コスト {base['hurdle']:.0f}% 以下")
    losses = operating[-RECENT_YEARS:]
    if len(losses) == RECENT_YEARS and all(v <= 0 for v in losses):
        return dict(base, rating="なし", width="なし",
                    basis=f"直近{RECENT_YEARS}年はすべて営業赤字で、超過収益が無い（ROIC を計算できた年は {n} 年。"
                          f"自己資本がマイナスなどで投下資本が計算できない年は除いた）")
    return dict(base, rating=None,
                basis=f"ROIC を計算できた年が {n} 年（{MIN_YEARS} 年未満。営業利益・自己資本・有利子負債の時系列が要る）")


def rate_returns(rows: list[dict], hurdle: float, operating: list[float] = ()) -> dict:
    """超過収益 強い/弱い/なし (rating None when 不明) with the numbers behind it. operating: the operating income
    of every year (also those without a ROIC), oldest first."""
    n = len(rows)
    base = {"years": n, "hurdle": hurdle, "above": 0, "median_spread": None, "recent_spread": None,
            "border_years": [], "width": "不明", "trend": "不明"}
    if n < MIN_YEARS:
        return _short_history(rows, list(operating), base)
    spreads = [r["spread"] for r in rows]
    above = sum(1 for s in spreads if s > 0)
    median, recent = _median(spreads), _mean(spreads[-RECENT_YEARS:])
    if above * 2 < n or recent <= 0:
        rating = "なし"
    elif n >= STRONG_YEARS and above >= math.ceil(STRONG_SHARE * n) and median >= STRONG_SPREAD:
        rating = "強い"
    else:
        rating = "弱い"
    border = [r["year"] for r in rows if abs(r["spread"]) < BORDER_PT]
    basis = (f"{rows[0]['year']}〜{rows[-1]['year']} の {n} 年中 {above} 年で ROIC が資本コスト {hurdle:.0f}% を上回る"
             f"（差の中央値 {median:+.1f}pt、直近{RECENT_YEARS}年平均 {recent:+.1f}pt）。目安: {STRONG_YEARS}年以上・8割以上の年で"
             f"上回り中央値 +{STRONG_SPREAD:.0f}pt 以上 強い / 上回った年が半分未満か直近{RECENT_YEARS}年平均が0以下 なし / ほか 弱い")
    if border:
        basis += f"。差が ±{BORDER_PT:.0f}pt 以内の境界の年: {', '.join(border)}"
    return dict(base, rating=rating, above=above, median_spread=median, recent_spread=recent, border_years=border,
                width=width(recent), trend=trend(spreads), basis=basis)


def economic_profit(rows: list[dict]) -> dict:
    """(ROIC − 資本コスト) × 投下資本 of the newest year and the sum of the last 5 (the unit of the series)."""
    profits = [r["spread"] / 100 * r["invested"] for r in rows]
    return {"latest": round(profits[-1]) if profits else None, "year": rows[-1]["year"] if rows else None,
            "sum5": round(sum(profits[-5:])) if profits else None, "years5": min(len(profits), 5)}


def returns(company, found: dict) -> dict:
    mkt = market(company)
    hurdle, tax = HURDLE[mkt], TAX[mkt]
    peers = peer_roic(company, found, tax)
    series = SS.self_series(company)
    rows = with_peer_median(roic_rows(series, tax, hurdle), peers)
    operating = [v.value for v in series["operating_income"].values()]
    return {**rate_returns(rows, hurdle, operating), "rows": rows, "tax": tax, "market": mkt, "unit": SS.unit_label(company),
            "peers": [p["name"] for p in peers], "economic_profit": economic_profit(rows)}


# ---------- 価格決定力 ----------

def _inflation_change(margins: dict[str, float]) -> float | None:
    start = next((v for y, v in margins.items() if y.startswith(INFLATION[0])), None)
    end = next((v for y, v in margins.items() if y.startswith(INFLATION[1])), None)
    return round(end - start, 1) if start is not None and end is not None else None


def peer_gross(costs: list[dict]) -> float | None:
    """Median gross margin of each peer's first row in competitors.md「コスト構造」 (100 − 売上原価率)."""
    first: dict[str, dict] = {}
    for r in costs:
        if not r["self"] and r.get("cost") is not None and r["name"] not in first:
            first[r["name"]] = r
    return _median([round(100 - r["cost"], 1) for r in first.values()])


def rate_pricing(margins: dict[str, float], peer: float | None) -> dict:
    years = list(margins)[-WINDOW:]
    values = [margins[y] for y in years]
    change = _inflation_change(margins)
    base = {"years": len(values), "range": None, "inflation_change": change, "peer_gross": peer,
            "latest": values[-1] if values else None}
    if len(values) < MIN_YEARS:
        return dict(base, rating=None, basis=f"粗利率を計算できた年が {len(values)} 年（{MIN_YEARS} 年未満）")
    spread = round(max(values) - min(values), 1)
    below_peer = peer is not None and values[-1] < peer
    if (change is not None and change <= -INFLATION_DROP_PT) or spread > GROSS_UNSTABLE_PT:
        rating = "弱い"
    elif (change is None or change >= 0) and spread <= GROSS_STABLE_PT and not below_peer:
        rating = "強い"
    else:
        rating = "普通"
    parts = [f"{years[0]}〜{years[-1]} の粗利率は {min(values):.1f}〜{max(values):.1f}%（振れ幅 {spread:.1f}pt）",
             (f"原価高の局面（{INFLATION[0]}→{INFLATION[1]} 年度）の変化 {change:+.1f}pt" if change is not None
              else f"原価高の局面（{INFLATION[0]}・{INFLATION[1]} 年度）の粗利率がそろわない"),
             f"直近 {values[-1]:.1f}%、同業の中央値 {peer:.1f}%" if peer is not None else "同業の粗利率なし"]
    basis = ("。".join(parts) + f"。目安: 原価高の局面で {INFLATION_DROP_PT:.0f}pt 以上低下か振れ幅 {GROSS_UNSTABLE_PT:.0f}pt 超"
             f" 弱い / 低下せず振れ幅 {GROSS_STABLE_PT:.0f}pt 以内で同業以上 強い / ほか 普通")
    return dict(base, rating=rating, range=spread, basis=basis)


def pricing(company, costs: list[dict]) -> dict:
    margins, sources = FM._margins(company, "gross")
    margins = {y: round(v, 1) for y, v in sorted(margins.items())}
    return {**rate_pricing(margins, peer_gross(costs)), "rows": margins, "sources": sources}


# ---------- formatting ----------

def _p(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _amount(value: float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


def _peer_cell(row: dict) -> str:
    return f"{_p(row['peer_median'])}（{row['peer_count']}社）" if row["peer_count"] else "—"


def roic_table_rows(ret: dict) -> str:
    if not ret["rows"]:
        return "| — | — | — | — | — | — | 営業利益・自己資本・有利子負債の時系列が raw・data に無い |"
    return "\n".join(f"| {r['year']} | {_amount(r['operating'])} | {_amount(r['invested'])} | {_p(r['roic'])} | "
                     f"{r['spread']:+.1f}pt | {_peer_cell(r)} | {'境界' if r['year'] in ret['border_years'] else '—'} |"
                     for r in ret["rows"])


def roic_note(ret: dict) -> str:
    ep = ret["economic_profit"]
    profit = (f"経済的利益（(ROIC − 資本コスト) × 投下資本）: {ep['year']} {_amount(ep['latest'])}、直近{ep['years5']}年の合計 "
              f"{_amount(ep['sum5'])}" if ep["latest"] is not None else "経済的利益: —")
    peers = "、".join(ret["peers"]) or "なし（競合の自己資本・有利子負債・売上高が competitors.md に無い）"
    return (f"注: 金額の単位は {ret['unit']}。ROIC = 営業利益 × (1 − 法定実効税率 {ret['tax']:.1f}%) ÷ 投下資本（自己資本 + 有利子負債 + "
            f"リース負債 − 余剰現金（現金 + 短期投資 − 売上高の5%。控除は投下資本の半分まで）の期首と期末の平均）。資本コストは{'日本' if ret['market'] == 'japan' else '米国'}株の固定値 "
            f"{ret['hurdle']:.0f}%。同業中央値の対象: {peers}。{profit}。"
            f"スクリプトの判定（超過収益）: {ret['rating'] or '不明'}: {ret['basis']}。堀の幅 {ret['width']}、差の傾向 {ret['trend']}")


def gross_table_rows(pr: dict) -> str:
    years = list(pr["rows"])[-WINDOW:]
    if not years:
        return "| — | — | — | 売上高・売上原価の時系列が raw・data に無い |"
    out = []
    for i, year in enumerate(years):
        diff = f"{pr['rows'][year] - pr['rows'][years[i - 1]]:+.1f}pt" if i else "—"
        out.append(f"| {year} | {_p(pr['rows'][year])} | {diff} | {'原価高の局面' if year[:4] in INFLATION else '—'} |")
    return "\n".join(out)


def gross_note(pr: dict) -> str:
    return (f"注: 自社は {'、'.join(pr['sources']) or '—'} の売上高・売上原価から計算。"
            f"スクリプトの判定（価格決定力）: {pr['rating'] or '不明'}: {pr['basis']}")
