"""The yardstick for the SWOT impact ratings (企業分析フレームワーク.md 1-4 手順2).

  大: may affect 20% or more of the main business's sales or profit
  中: 5-20%
  小: under 5%
The script finds the newest actual consolidated sales and operating profit and computes the 20% / 5% amounts, so
the writer compares each item's affected amount with them instead of calculating. With several segments the
writer reads the main segment's figures in the brief instead (a single segment equals the consolidated figures).
"""
from __future__ import annotations

import mdparse as M
from ff_inputs import raw_files
from ff_metrics import FORECAST, _peer_rows
from mt_metrics import SKIP_SECTION, _sections
from tc_metrics import _series_from_data

LARGE, MEDIUM = 0.20, 0.05  # 大 / 中 lower bounds
MILLION = 1e6
YEN_LIKE = 1e8  # raw cells without a unit: values this large are taken as yen, smaller ones keep the table's unit


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


def scale_note(s: dict | None) -> str:
    base = ("注: 影響度の目安は 大 = 主力事業の売上・利益の20%以上、中 = 5〜20%、小 = 5%未満（企業分析フレームワーク.md 1-4）。"
            "上の表は連結の実績からスクリプトが計算。")
    if not s:
        return base + " 数値が無いので、brief の「事業の内容・セグメント」の記述から影響度を判断し、判断できなければ「不明」にする。"
    loss = " 営業利益が赤字（0以下）のときは、売上高の目安だけで判断する。" if s["profit"] <= 0 else ""
    return base + loss + (" セグメントが複数あるときは、brief の「事業の内容・セグメント」にある主力セグメントの売上・利益で読み替える"
                   "（単一セグメントなら連結の数値のまま）。")
