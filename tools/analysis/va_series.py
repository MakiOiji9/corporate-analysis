"""Numbers behind the valuation analysis (企業分析フレームワーク.md STEP 3).

The price side comes from raw/ir/{date}_valuation-data.md (collect-peers-valuation):
  1章 株価（確定終値）と基準日・時価総額・発行済株式数（自己株式を除く。無ければ 含む − 自己株式数）
  2章 EPS（実績・会社予想）・BPS（ラベルの日付が一番新しい行）
  3章 開示・集計サイトの PER・PBR・予想ROE（照合と予想ROE の代わりにだけ使う）
  4章 年次の PER・PBR の高値・安値、有報の期末PER
  5章 アナリスト予想の EPS 成長率（数値があるときだけ）
The peers come from competitors.md: 6章 PER・PBR・時価総額（同じ基準日）, 3章 売上高の3年CAGR, 5章 ROE,
11章 有利子負債・現金（sf_series.peer_series）, 12章 営業利益・減価償却費（EV/EBITDA の材料）.
The target's yearly numbers reuse the STEP 2 readers: net income / extraordinary items / equity (pf_series),
operating income / debt / cash (sf_series), depreciation (cf_series), EPS on the newest share basis (gr_series).
The forecast EPS: the newest 決算短信 forecast in data/tdnet_facts.csv for the next fiscal year, else 2章.
Amounts are in the unit of the yearly series (百万円 for a Japanese company, sf_series.unit_label for a US one).
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata

import cf_series as CS
import gr_series as GS
import mdparse as M
import pf_series as S
import sf_series as SS
from common import read_csv_rows
from ff_inputs import Found
from ff_metrics import _yen
from render_tables import forecast_records
from tc_metrics import _is_self, same_company

DATE = re.compile(r"(\d{4})\s*[-/年]\s*(\d{1,2})\s*[-/月]\s*(\d{1,2})")
INTRADAY = re.compile(r"取引中|日中|場中")
CLOSE = re.compile(r"確定終値\s*[:：]?\s*((?:US\$|\$)?\s*\d[\d,]*(?:\.\d+)?)")
CURRENCY_PREFIX = re.compile(r"^(US\$|\$|＄)\s*")
FORECAST_WORDS = re.compile(r"予想|予|見通し|ガイダンス|計画")
QUARTER_WORDS = re.compile(r"四半期|\dQ|Q\d|第[1-3１-３]|中間|累計")
DOLLAR = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(兆|億|百万|万|千)?\s*(?:米)?ドル")
DOLLAR_UNIT = {None: 1.0, "千": 1e3, "万": 1e4, "百万": 1e6, "億": 1e8, "兆": 1e12}
# the yearly series' unit -> currency units per unit (a market cap in 円 / ドル is divided by it)
SERIES_UNIT = {"百万円": 1e6, "千円": 1e3, "千米ドル": 1e3, "千ドル": 1e3, "百万米ドル": 1e6, "百万ドル": 1e6,
               "米ドル": 1.0, "ドル": 1.0}
PEER_COLUMNS = {"company": ("会社",), "price": ("株価",), "market_cap": ("時価総額",),
                "per_actual": ("PER（実績）", "実績PER", "PER(実績)"), "per_forecast": ("PER（予想）", "予想PER", "PER(予想)"),
                "pbr": ("PBR",), "ev_ebitda": ("EV/EBITDA",),
                "eps_actual": ("EPS（実績）", "実績EPS", "EPS(実績)"), "eps_forecast": ("EPS（予想）", "予想EPS", "EPS(予想)"),
                "bps": ("BPS",)}
# a peer multiple is price ÷ the per-share figure when 6章 gives it (the shown PER of a site may use another date)
PEER_RATIOS = (("per_actual", "eps_actual"), ("per_forecast", "eps_forecast"), ("pbr", "bps"))
UNCONFIRMED = "未確認"
NO_ACTION = re.compile(r"^\s*(—|-|なし|該当なし)?\s*$")
TDNET_BPS_CONTEXT = re.compile(r"^(CurrentYearInstant|CurrentAccumulatedQ\dInstant)_ConsolidatedMember_ResultMember$")


# ---------- cells ----------

def number(cell: str) -> float | None:
    """The leading number of a cell: '526円（終値）' / '14.69倍' / '$146.62' / '(4.28)' -> float; '—' -> None."""
    text = CURRENCY_PREFIX.sub("", cell.replace("*", "").strip())
    if not text or text.startswith(("—", "－")):
        return None
    return GS.plain(text)


def date_in(text: str) -> str | None:
    """The first real calendar date in the text ('2026-02-31' is not one)."""
    for m in DATE.finditer(text):
        try:
            return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
        except ValueError:
            continue
    return None


def close_price(cell: str) -> float | None:
    """The confirmed close of a 株価 cell: an intraday value written first ('147.15ドル（取引中の値）。前営業日の
    確定終値 146.62ドル') gives way to the number after 確定終値."""
    m = CLOSE.search(cell)
    if INTRADAY.search(cell) and m:
        return number(m.group(1))
    return number(cell)


def money(cell: str) -> tuple[float, str] | None:
    """(amount, currency) of a market cap cell: '336億351万円' -> (33,603,510,000, 円); '279.5億ドル' -> (2.795e10, ドル)."""
    text = cell.replace("*", "").strip()
    if "ドル" in text or "$" in text:
        m = DOLLAR.search(text)
        return (float(m.group(1).replace(",", "")) * DOLLAR_UNIT[m.group(2)], "ドル") if m else None
    if "円" not in text:
        return None
    yen = _yen(text)
    return (yen, "円") if yen is not None else None


def kv_rows(found: Found) -> list[tuple[str, str, str]]:
    """(label, value, note) of the 項目 / 値 tables of a valuation-data section."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    out = []
    for table in M.tables(found.body):
        for row in table[1:]:
            if len(row) >= 2:
                out.append((row[0].replace("*", "").strip(), row[1], row[2] if len(row) > 2 else ""))
    return out


# ---------- 1章・2章・3章・5章 ----------

def price_data(found: Found) -> dict:
    """1章. shares_uncertain: the share count is marked 未確認, or a corporate action after the period is written
    (a share exchange or a buyback can change it); total_shares (自己株式を含む) is then its upper bound."""
    out = {"price": None, "date": None, "currency": "円", "shares": None, "shares_source": "", "market_cap": None,
           "source": "", "price_cell": "", "intraday": False, "total_shares": None, "shares_uncertain": False,
           "uncertain_note": ""}
    total = treasury = None
    for label, value, note in kv_rows(found):
        if label.startswith("期末後のコーポレートアクション") and not NO_ACTION.match(value):
            out.update(shares_uncertain=True, uncertain_note=f"期末後のコーポレートアクション: {value[:80]}")
        elif ("自己株式" in label or label.startswith("発行済株式")) and UNCONFIRMED in value + note:
            out.update(shares_uncertain=True, uncertain_note=out["uncertain_note"] or f"{label}が未確認")
        if label.startswith("株価") and "指標" not in label and out["price"] is None:
            out.update(price=close_price(value), date=date_in(note) or date_in(value), price_cell=value,
                       intraday=bool(INTRADAY.search(value)) and not CLOSE.search(value),
                       source=note, currency="ドル" if ("ドル" in value or "$" in value) else "円")
        elif label.startswith("時価総額"):
            out["market_cap"] = money(value)
        elif "自己株式を除く" in label:
            out.update(shares=number(value), shares_source=f"株価データ 1章「{label}」")
        elif label.startswith("発行済株式"):
            total = number(value)
        elif label.startswith("自己株式"):
            treasury = number(value)
    if out["shares"] is None and total is not None:
        out.update(shares=total - (treasury or 0.0),
                   shares_source="発行済株式数 − 自己株式数" if treasury is not None else "発行済株式数（自己株式の行なし）")
    out["total_shares"] = total
    return out


def _label_date(label: str) -> str:
    m = re.search(r"(\d{4})年(\d{1,2})月", label)
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}" if m else ""


def per_share_data(found: Found) -> dict:
    """EPS actual / forecast and BPS of 2章: {key: {value, label}}; quarterly EPS rows are skipped."""
    out: dict = {"eps_actual": None, "eps_forecast": None, "bps": None}
    bps_rows = []
    for label, value, _ in kv_rows(found):
        v = number(value)
        if v is None:
            continue
        if "BPS" in label or "1株当たり純資産" in label:
            bps_rows.append((_label_date(label), {"value": v, "label": label}))
        elif ("EPS" in label or "1株当たり当期純" in label) and not QUARTER_WORDS.search(label):
            key = "eps_forecast" if FORECAST_WORDS.search(label) else "eps_actual"
            out[key] = out[key] or {"value": v, "label": label}
    if bps_rows:
        out["bps"] = max(bps_rows, key=lambda r: r[0])[1]
    return out


def reported_data(found: Found) -> dict:
    """The PER / PBR / forecast ROE written in 3章 (collected values: used to cross-check and as a fallback)."""
    out = {"per_actual": None, "per_forecast": None, "pbr": None, "roe_forecast": None}
    for label, value, _ in kv_rows(found):
        if label.startswith("PER"):
            if "予想" in label and "実績" not in label:
                out["per_forecast"] = number(value)
            elif "実績" in label and "予想" not in label:
                out["per_actual"] = number(value)
            else:  # 'PER（実績／予想）' with '14.69倍 ／ 12.95倍'
                nums = [number(p) for p in re.split(r"[／/]", value)]
                out["per_actual"], out["per_forecast"] = (nums + [None, None])[:2]
        elif label.startswith("PBR"):
            out["pbr"] = number(value)
        elif label.startswith("ROE"):
            parts = [S.percent(p) for p in re.split(r"[／/]", value) if S.percent(p) is not None]
            out["roe_forecast"] = parts[-1] if len(parts) >= 2 else None
    return out


def analyst_growth(found: Found) -> dict | None:
    for label, value, note in kv_rows(found):
        if "EPS" in label and "成長率" in label:
            v = None if value.strip().startswith("—") else S.percent(value)
            return {"value": v, "label": label, "source": note} if v is not None else None
    return None


# ---------- 4章 ----------

def _subsections(body: str) -> list[tuple[str, str]]:
    """('', text before the first ###) and (### title, its body)."""
    parts = re.split(r"^###\s+(.+)$", body, flags=re.M)
    return [("", parts[0])] + [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def _col(header: list[str], *words: str) -> int | None:
    return next((i for i, h in enumerate(header) if all(w in h for w in words)), None)


def _any_col(header: list[str], metric: str, words: tuple[str, ...]) -> int | None:
    """'PER 低' / 'PER 安値' / 'PER最低' -> the first column with the metric and one of the words."""
    return next((i for i, h in enumerate(header) if metric in h and any(w in h for w in words)), None)


HIGH_WORDS, LOW_WORDS = ("高",), ("低", "安")


def history_data(found: Found) -> list[dict]:
    """[{year, per_high, per_low, pbr_high, pbr_low, per_end}] oldest first (per_end: the 有報's 期末PER)."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    rows: dict[str, dict] = {}
    for title, body in _subsections(found.body):
        for table in M.tables(body):
            header = table[0]
            periods = [S.period(h) for h in header]
            if all(periods) and "期末PER" in title.replace(" ", "") and len(table) > 1:  # years as columns
                for year, cell in zip(periods, table[1]):
                    if (v := number(cell)) is not None:
                        rows.setdefault(year, {})["per_end"] = v
                continue
            year_col = next((c for c in (_col(header, "年度"), _col(header, "決算期")) if c is not None), None)
            if year_col is None:
                continue
            cols = {"per_high": _any_col(header, "PER", HIGH_WORDS), "per_low": _any_col(header, "PER", LOW_WORDS),
                    "pbr_high": _any_col(header, "PBR", HIGH_WORDS), "pbr_low": _any_col(header, "PBR", LOW_WORDS),
                    "per_end": _col(header, "期末", "PER")}
            for row in table[1:]:
                year = S.period(row[year_col]) if year_col < len(row) else None
                if not year:
                    continue
                for key, col in cols.items():
                    if col is not None and col < len(row) and (v := number(row[col])) is not None:
                        rows.setdefault(year, {})[key] = v
    return [{"year": y, **{k: v.get(k) for k in ("per_high", "per_low", "pbr_high", "pbr_low", "per_end")}}
            for y, v in sorted(rows.items())]


# ---------- the target's years ----------

def _value(series: dict, field: str, year: str) -> float | None:
    v = series.get(field, {}).get(year)
    return v.value if v is not None else None


def _forecast_eps_tdnet(company, after: str | None) -> dict | None:
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists() or after is None:
        return None
    records = [r for r in forecast_records(read_csv_rows(path))
               if r["kind"] in ("期初予想", "期中予想") and r["target"][:7] > after and r.get("NetIncomePerShare")]
    if not records:
        return None
    target = min(r["target"][:7] for r in records)
    newest = max((r for r in records if r["target"][:7] == target), key=lambda r: r["filing_date"])
    try:
        value = float(newest["NetIncomePerShare"])
    except ValueError:
        return None
    return {"value": value, "label": f"{target} の{newest['kind']}（決算短信 {newest['filing_date']}）", "target": target}


def _filing_key(row: dict) -> str:
    """'2026年８月12日' (full-width digits) -> '2026-08-12' for ordering the 決算短信."""
    return date_in(unicodedata.normalize("NFKC", row.get("filing_date") or "")) or ""


def bps_tdnet(company) -> dict | None:
    """The newest consolidated BPS of a 決算短信 (year end or a quarter end) in data/tdnet_facts.csv (primary)."""
    path = company.path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return None
    rows = [r for r in read_csv_rows(path)
            if r.get("element") == "NetAssetsPerShare" and TDNET_BPS_CONTEXT.match(r.get("context", ""))]
    if not rows:
        return None
    newest = max(rows, key=_filing_key)
    try:
        value = float(newest["value"])
    except ValueError:
        return None
    return {"value": value, "label": f"{newest.get('document', '決算短信')}（{newest.get('filing_date', '')}）",
            "source": "data/tdnet_facts.csv（決算短信）"}


def self_years(company) -> dict:
    """{rows: [{year, net_income, extra_gain, extra_loss, operating_income, depreciation, debt, cash, equity, eps}],
    splits, odd, unit}. EPS is on the newest share basis."""
    pf, sf, cf, gr = S.self_series(company), SS.self_series(company), CS.self_series(company), GS.self_series(company)
    eps, splits, odd = GS.adjusted_eps(gr)
    years = sorted(set(pf["net_income"]) | set(gr["net_income"]) | set(sf["operating_income"]))
    rows = []
    for y in years:
        rows.append({
            "year": y,
            "net_income": _value(pf, "net_income", y) if y in pf["net_income"] else _value(gr, "net_income", y),
            "extra_gain": _value(pf, "extra_gain", y), "extra_loss": _value(pf, "extra_loss", y),
            "operating_income": (_value(sf, "operating_income", y) if y in sf["operating_income"]
                                 else _value(gr, "operating_income", y)),
            "depreciation": _value(cf, "depreciation", y), "debt": _value(sf, "debt", y), "cash": _value(sf, "cash", y),
            "equity": _value(sf, "equity", y) if y in sf["equity"] else _value(pf, "equity", y),
            "eps": eps.get(y)})
    return {"rows": rows, "splits": splits, "odd": odd, "unit": SS.unit_label(company)}


def forecast_eps(company, per_share: dict, latest_year: str | None) -> dict | None:
    """The forecast EPS for the next fiscal year: 決算短信 first, else 2章."""
    tdnet = _forecast_eps_tdnet(company, latest_year)
    if tdnet:
        return tdnet
    row = per_share["eps_forecast"]
    return {"value": row["value"], "label": f"株価データ 2章「{row['label']}」", "target": None} if row else None


def market_cap(price: dict, unit: str) -> dict | None:
    """The market cap in the unit of the yearly series: price × shares (excl. treasury), else 1章's 時価総額.
    max: price × the shares including treasury, when the count is uncertain (its upper bound)."""
    per_unit = SERIES_UNIT.get(unit)
    if per_unit is None:
        return None
    if price["price"] is not None and price["shares"]:
        upper = price["total_shares"] if price["shares_uncertain"] and price["total_shares"] else None
        return {"value": price["price"] * price["shares"] / per_unit,
                "basis": f"株価 × 株式数（{price['shares_source']}）",
                "max": price["price"] * upper / per_unit if upper and upper > price["shares"] else None,
                "max_shares": upper}
    if price["market_cap"] and price["market_cap"][1] == price["currency"]:
        return {"value": price["market_cap"][0] / per_unit, "basis": "株価データ 1章の時価総額", "max": None,
                "max_shares": None}
    return None


# ---------- peers ----------

def _peer_cols(header: list[str]) -> dict[str, int | None]:
    return {key: next((i for i, h in enumerate(header) if any(h.replace(" ", "").startswith(w) for w in words)), None)
            for key, words in PEER_COLUMNS.items()}


def peer_table(found: Found) -> list[dict]:
    """competitors 6章: [{name, price, market_cap (円 or None), per_actual, per_forecast, pbr, ev_ebitda}]."""
    if found.status not in ("ok", "thin", "unavailable") or not found.body:
        return []
    out = []
    for table in M.tables(found.body):
        cols = _peer_cols(table[0])
        if cols["company"] is None:
            continue
        for row in table[1:]:
            cells = {k: (row[c] if c is not None and c < len(row) else "—") for k, c in cols.items()}
            cap = money(cells["market_cap"])
            price = number(cells["price"])
            row = {"name": cells["company"].replace("*", "").strip(), "price": price,
                   "market_cap": cap[0] if cap and cap[1] == "円" else None, "ev_ebitda": number(cells["ev_ebitda"]),
                   "computed": []}
            for ratio, per_share in PEER_RATIOS:
                shown, base_value = number(cells[ratio]), number(cells[per_share])
                row[f"{ratio}_shown"] = shown
                if price and base_value and base_value > 0:
                    row[ratio] = price / base_value
                    row["computed"].append(ratio)
                else:
                    row[ratio] = shown
            out.append(row)
    return out


def base_date(found: Found) -> str | None:
    return date_in(found.heading) or date_in(found.body or "")


def _tables(found: Found) -> list[list[list[str]]]:
    return M.tables(found.body) if found.status in ("ok", "thin") and found.body else []


def peer_cagr(found: Found) -> list[tuple[str, float]]:
    """competitors 3章: (name, 3-year sales CAGR %)."""
    out = []
    for table in _tables(found):
        old, new = _col(table[0], "3年前"), _col(table[0], "直近")
        if old is None or new is None:
            continue
        for row in table[1:]:
            a = GS.amount(row[old], 1.0) if old < len(row) else None
            b = GS.amount(row[new], 1.0) if new < len(row) else None
            if a and b and a > 0 and b > 0:
                out.append((row[0].replace("*", "").strip(), ((b / a) ** (1 / 3) - 1) * 100))
    return out


def peer_roe(found: Found) -> list[tuple[str, float]]:
    out = []
    for table in _tables(found):
        roe = _col(table[0], "ROE")
        if roe is not None:
            out += [(row[0].replace("*", "").strip(), v) for row in table[1:]  # a ROE cell is written in %
                    if roe < len(row) and "%" in row[roe] and (v := S.percent(row[roe])) is not None]
    return out


def peer_ebitda(found: Found) -> list[dict]:
    """competitors 12章: [{name, year, operating_income, depreciation}] (百万円 unless the header or cell says
    otherwise)."""
    out = []
    for table in _tables(found):
        header = table[0]
        cols = {"company": _col(header, "会社"), "year": next((c for c in (_col(header, "年度"), _col(header, "決算期"))
                                                              if c is not None), None),
                "operating_income": _col(header, "営業利益"), "depreciation": _col(header, "減価償却")}
        if None in (cols["company"], cols["year"]):
            continue
        for row in table[1:]:
            year = S.period(row[cols["year"]]) if cols["year"] < len(row) else None
            if not year:
                continue
            values = {}
            for key in ("operating_income", "depreciation"):
                col = cols[key]
                values[key] = (GS.amount(row[col], GS.unit_of(header[col]) or 1.0)
                               if col is not None and col < len(row) else None)
            out.append({"name": row[cols["company"]].replace("*", "").strip(), "year": year, **values})
    return out


def _match(name: str, pairs: list[tuple[str, float]]) -> float | None:
    return next((v for n, v in pairs if same_company(n, name)), None)


def _latest_value(series: dict, field: str) -> float | None:
    values = series.get(field) or {}
    return values[max(values)].value if values else None


def _peer_ev(p: dict, debt: float | None, cash: float | None, eb: dict | None) -> float | None:
    """(時価総額 + 有利子負債 − 現金) ÷ (営業利益 + 減価償却費), in 百万円; None when a part is missing or EBITDA <= 0."""
    if p["market_cap"] is None or debt is None or cash is None or not eb:
        return None
    if eb["operating_income"] is None or eb["depreciation"] is None:
        return None
    ebitda = eb["operating_income"] + eb["depreciation"]
    return (p["market_cap"] / 1e6 + debt - cash) / ebitda if ebitda > 0 else None


def _is_own(name: str, company) -> bool:
    return _is_self(name, company) or same_company(name, company.display_name())


def peers(company, found: dict[str, Found]) -> dict:
    """The peers of 6章 with their growth / ROE / EV parts, and the target's own 3章・5章・6章 values."""
    cagr, roe = peer_cagr(found["peer_cagr"]), peer_roe(found["peer_roe"])
    ebitda = peer_ebitda(found["peer_ebitda"])
    balance = SS.peer_series(company, found)
    table = peer_table(found["peer_valuation"])
    out = []
    for p in table:
        if _is_own(p["name"], company):
            continue
        bal = next((b["series"] for b in balance if same_company(b["name"], p["name"])), {})
        eb = max((e for e in ebitda if same_company(e["name"], p["name"])), key=lambda e: e["year"], default=None)
        debt, cash = _latest_value(bal, "debt"), _latest_value(bal, "cash")
        out.append({**p, "cagr": _match(p["name"], cagr), "roe": _match(p["name"], roe), "debt": debt, "cash": cash,
                    "ebitda_year": eb["year"] if eb else None, "ev_ebitda_calc": _peer_ev(p, debt, cash, eb)})
    own = {"cagr": next((v for n, v in cagr if _is_own(n, company)), None),
           "roe": next((v for n, v in roe if _is_own(n, company)), None),
           "row": next((p for p in table if _is_own(p["name"], company)), None)}
    return {"peers": out, "own": own, "date": base_date(found["peer_valuation"]),
            "has_ebitda_section": found["peer_ebitda"].status in ("ok", "thin")}


# ---------- everything ----------

def base(company, found: dict[str, Found]) -> dict:
    years = self_years(company)
    latest = max((r["year"] for r in years["rows"] if r["net_income"] is not None), default=None)
    per_share = per_share_data(found["per_share"])
    tdnet = bps_tdnet(company)  # primary: the 決算短信's BPS beats a re-written 2章
    if tdnet:
        per_share = {**per_share, "bps": tdnet}
    price = price_data(found["price"])
    return {"price": price, "per_share": per_share, "reported": reported_data(found["current"]),
            "history": history_data(found["history"]), "analyst": analyst_growth(found["analyst"]),
            "years": years, "latest_year": latest, "forecast_eps": forecast_eps(company, per_share, latest),
            "market_cap": market_cap(price, years["unit"]), "peers": peers(company, found)}
