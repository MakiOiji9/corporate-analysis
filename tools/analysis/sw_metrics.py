"""The yardstick for the SWOT impact ratings (企業分析フレームワーク.md 1-4 手順2).

  大: may affect 20% or more of the main business's sales or profit
  中: 5-20%
  小: under 5%
The script finds the newest actual consolidated sales and operating profit and computes the 20% / 5% amounts, so
the writer compares each item's affected amount with them instead of calculating. With several segments the
writer reads the main segment's figures in the brief instead (a single segment equals the consolidated figures).
"""
from __future__ import annotations

import re

import mdparse as M
from ff_inputs import COMMENT, Found, header_notes, raw_files
from ff_metrics import FORECAST, _peer_rows
from mt_metrics import SKIP_SECTION, _sections
from tc_metrics import _series_from_data

LARGE, MEDIUM = 0.20, 0.05  # 大 / 中 lower bounds
MILLION = 1e6
YEN_LIKE = 1e8  # raw cells without a unit: values this large are taken as yen, smaller ones keep the table's unit

# 影響度の候補: amount columns of the raw tables (sales-like, newest period last), not ratios, profit or assets
AMOUNT_HEADER = re.compile(r"売上|金額|収益|\d{4}年|期")
NOT_AMOUNT_HEADER = re.compile(r"比率|構成比|%|％|率|増減|前年|比$|利益|資産|人数|名|議決権|株")
AMOUNT_CELL = re.compile(r"^(?P<num>[△▲-]?[\d,]+(?:\.\d+)?)\s*(?P<unit>百万円|億円)?$")
UNIT_SCALE = {"百万円": 1.0, "億円": 100.0}  # to 百万円
TOTAL_ROW = re.compile(r"^(合計|計|総計)$")
UNIT_NOISE = re.compile(r"[\s:：は（）()\[\]【】、,]")  # 「単位は百万円」「（単位：百万円）」 -> 単位百万円
CANDIDATE_LIMIT = 20


def _from_raw(company) -> dict | None:
    """Newest actual (sales, operating profit) in the P/L tables of financials-historical and yuho."""
    best: dict | None = None
    for kind in ("financials-historical", "yuho"):
        for _, path in raw_files(company, kind):
            for title, body in _sections(path.read_text(encoding="utf-8")):
                if SKIP_SECTION.search(title):
                    continue
                for table in M.tables(body):
                    if any(FORECAST.search(h) for h in table[0]):
                        continue
                    for row in _peer_rows(table):
                        if row["forecast"] or (best and row["year"] <= best["year"]):
                            continue
                        best = {"year": row["year"], "sales": row["sales"], "profit": row["profit"],
                                "source": f"raw の財務表（{path.name}）"}
    return best


def scale(company) -> dict | None:
    """{year, sales, profit, source, yen}: data/*.csv first (amounts in yen), then the raw P/L tables."""
    data = _series_from_data(company)
    if data:
        last = data[-1]
        return {"year": last["year"], "sales": last["sales"], "profit": last["profit"],
                "source": "data/*.csv（連結・実績）", "yen": True}
    raw = _from_raw(company)
    if raw:
        return dict(raw, yen=raw["sales"] >= YEN_LIKE)
    return None


def _amount(value: float, yen: bool) -> str:
    if yen:
        return f"{value / MILLION:,.0f}百万円"
    return f"{value:,.0f}（単位は出典の表のまま）"


def scale_rows(s: dict | None) -> str:
    if not s:
        return "| — | — | — | — | — | 直近の売上高・営業利益が data/ にも raw の財務表にも無い |"
    rows = []
    for label, key in (("売上高", "sales"), ("営業利益", "profit")):
        value = s[key]
        if value <= 0:  # a loss gives no yardstick: the writer uses the sales row
            rows.append(f"| {label} | {s['year']} | {_amount(value, s['yen'])}（赤字） | — | — | {s['source']} |")
            continue
        rows.append(f"| {label} | {s['year']} | {_amount(value, s['yen'])} | {_amount(value * LARGE, s['yen'])} | "
                    f"{_amount(value * MEDIUM, s['yen'])} | {s['source']} |")
    return "\n".join(rows)


def _amount_column(header: list[str]) -> int | None:
    """Rightmost sales-like amount column (the newest period comes last in the raw tables)."""
    cols = [i for i, h in enumerate(header) if i > 0 and AMOUNT_HEADER.search(h) and not NOT_AMOUNT_HEADER.search(h)]
    return cols[-1] if cols else None


def _million(cell: str, default_unit: str | None) -> float | None:
    m = AMOUNT_CELL.match(cell.replace("*", "").replace(" ", "").strip())
    unit = (m.group("unit") or default_unit) if m else None
    if not m or unit is None:
        return None
    number = float(m.group("num").replace(",", "").replace("△", "-").replace("▲", "-"))
    return number * UNIT_SCALE[unit]


def _default_unit(f: Found) -> str | None:
    """The unit of cells without one: stated in the section or in the raw file's header (単位は百万円 etc.)."""
    text = UNIT_NOISE.sub("", f.body + " " + (header_notes(f.path) if f.path is not None else ""))
    return next((u for u in UNIT_SCALE if f"単位{u}" in text or f"特記なき限り{u}" in text), None)


def _band(ratio: float) -> str:
    return "大" if ratio >= LARGE else "中" if ratio >= MEDIUM else "小"


def impact_candidates(found: list[Found], s: dict | None) -> list[dict]:
    """Amounts in the raw tables of the given sections, banded against the sales yardstick (no new figures for the
    writer to compute). Only when the yardstick is in yen and the table's unit is known."""
    if not s or not s.get("yen") or s["sales"] <= 0:
        return []
    sales = s["sales"] / MILLION
    out = []
    for f in found:
        if f.status != "ok":
            continue
        unit = _default_unit(f)
        for table in M.tables(COMMENT.sub("", f.body)):
            col = _amount_column(table[0])
            if col is None:
                continue
            for row in table[1:]:
                if col >= len(row) or not row[0].strip() or TOTAL_ROW.match(row[0].strip()):
                    continue
                value = _million(row[col], unit)
                if value is None or value <= 0:
                    continue
                out.append({"section": f.spec.label, "column": table[0][col].strip(), "row": row[0].strip(),
                            "amount": value, "band": _band(value / sales)})
    return out[:CANDIDATE_LIMIT]


def candidate_rows(candidates: list[dict], s: dict | None) -> list[str]:
    if not candidates:
        return ["（候補なし: 売上高の目安が無いか、brief の表に単位の分かる金額が無い）"]
    head = (f"売上高 {_amount(s['sales'], True)}（{s['year']}）の目安（大 = 20%以上 / 中 = 5〜20% / 小 = 5%未満）と"
            "比べた区分。金額の大きさだけの区分で、その項目が金額のどれだけに影響するかは執筆者が判断する")
    lines = [head, "", "| 出典の節 | 列 | 行 | 金額 | 区分 |", "|---|---|---|---|---|"]
    lines += [f"| {c['section']} | {c['column']} | {c['row'].replace('|', '／')} | {c['amount']:,.0f}百万円 | {c['band']} |"
              for c in candidates]
    return lines


def scale_note(s: dict | None) -> str:
    base = ("注: 影響度の目安は 大 = 主力事業の売上・利益の20%以上、中 = 5〜20%、小 = 5%未満（企業分析フレームワーク.md 1-4）。"
            "上の表は連結の実績からスクリプトが計算。")
    if not s:
        return base + " 数値が無いので、brief の「事業の内容・セグメント」の記述から影響度を判断し、判断できなければ「不明」にする。"
    loss = " 営業利益が赤字（0以下）のときは、売上高の目安だけで判断する。" if s["profit"] <= 0 else ""
    return base + loss + (" セグメントが複数あるときは、brief の「事業の内容・セグメント」にある主力セグメントの売上・利益で読み替える"
                   "（単一セグメントなら連結の数値のまま）。")
