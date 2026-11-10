"""需給（信用残・空売り）: the newest raw/market/*_positioning.md as a few figures beside the technical analysis.

The table is written by collect-peers-valuation from public pages (確度 二次), one row per week (any order):
  Japan:  | 日付 | 信用買い残 | 信用売り残 | 信用倍率 |                (株数; 倍率 = 買い残 ÷ 売り残)
  US:     | 日付 | 空売り残高 | 浮動株比率 | 日数 |                  (株数; % of the float; days to cover)
Shown only: nothing here enters the horizon scores (the weekly balance lags and is a secondary source).
"""
from __future__ import annotations

import re
from pathlib import Path

import mdparse as M

LONG, SHORT, RATIO = "信用買い残", "信用売り残", "信用倍率"
SHORT_INTEREST, FLOAT_SHARE, DAYS = "空売り残高", "浮動株比率", "日数"
TREND_WEEKS = 4
HIGH_RATIO, LOW_RATIO = 5.0, 1.0  # 信用倍率: 5倍超は将来の返済売りが多い、1倍未満は売り長（買い戻しが入りうる）
HIGH_FLOAT_SHORT, HIGH_DAYS = 10.0, 5.0  # 空売りが浮動株の10%超、買い戻しに5日超
NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _number(text: str | None) -> float | None:
    found = NUMBER.search(text or "")
    return float(found.group(0).replace(",", "")) if found else None


def newest(company_path: Path) -> Path | None:
    files = sorted((company_path / "raw" / "market").glob("*_positioning.md"))
    return files[-1] if files else None


def _cell(row: dict, key: str) -> str | None:
    return next((v for k, v in row.items() if key in k), None)


def parse(text: str) -> list[dict]:
    """[{date, long, short, ratio, short_interest, float_share, days}] oldest first."""
    rows = []
    for r in M.table_dicts(text):
        date = DATE.search(_cell(r, "日付") or "")
        if not date:
            continue
        get = {key: _number(_cell(r, key)) for key in (LONG, SHORT, RATIO, SHORT_INTEREST, FLOAT_SHARE, DAYS)}
        ratio = get[RATIO]
        if ratio is None and get[LONG] is not None and get[SHORT]:
            ratio = round(get[LONG] / get[SHORT], 2)
        rows.append({"date": date.group(0), "long": get[LONG], "short": get[SHORT], "ratio": ratio,
                     "short_interest": get[SHORT_INTEREST], "float_share": get[FLOAT_SHARE], "days": get[DAYS]})
    return sorted(rows, key=lambda r: r["date"])


def _change(rows: list[dict], key: str) -> float | None:
    """% change of `key` over the last TREND_WEEKS rows (from the row TREND_WEEKS back, or the oldest)."""
    known = [r for r in rows if r[key] is not None]
    if len(known) < 2:
        return None
    base = known[max(0, len(known) - 1 - TREND_WEEKS)][key]
    return round((known[-1][key] / base - 1) * 100, 1) if base else None


def _japan(rows: list[dict], last: dict) -> tuple[list[str], list[str]]:
    lines, notes = [], []
    if last["long"] is not None:
        change = _change(rows, "long")
        lines.append(f"信用買い残 {last['long']:,.0f}株" + (f"（{TREND_WEEKS}週前比 {change:+.1f}%）" if change is not None else ""))
    if last["short"] is not None:
        lines.append(f"信用売り残 {last['short']:,.0f}株")
    if last["ratio"] is not None:
        lines.append(f"信用倍率 {last['ratio']:.2f}倍")
        if last["ratio"] > HIGH_RATIO:
            notes.append(f"信用倍率 {last['ratio']:.1f}倍（{HIGH_RATIO:.0f}倍超: 将来の返済売りが多い）")
        elif last["ratio"] < LOW_RATIO:
            notes.append(f"信用倍率 {last['ratio']:.2f}倍（{LOW_RATIO:.0f}倍未満の売り長: 買い戻しが入りうる）")
    return lines, notes


def _us(rows: list[dict], last: dict) -> tuple[list[str], list[str]]:
    lines, notes = [], []
    if last["short_interest"] is not None:
        change = _change(rows, "short_interest")
        lines.append(f"空売り残高 {last['short_interest']:,.0f}株"
                     + (f"（{TREND_WEEKS}回前比 {change:+.1f}%）" if change is not None else ""))
    if last["float_share"] is not None:
        lines.append(f"浮動株に対する比率 {last['float_share']:.1f}%")
        if last["float_share"] > HIGH_FLOAT_SHORT:
            notes.append(f"空売りが浮動株の {last['float_share']:.1f}%（{HIGH_FLOAT_SHORT:.0f}%超）")
    if last["days"] is not None:
        lines.append(f"買い戻しに要する日数 {last['days']:.1f}日")
        if last["days"] > HIGH_DAYS:
            notes.append(f"買い戻しに {last['days']:.1f}日（{HIGH_DAYS:.0f}日超）")
    return lines, notes


def summarize(company_path: Path) -> dict:
    """{ok, source, date, text (one sentence for the brief / HTML), notes (levels worth a mention)}."""
    path = newest(company_path)
    rows = parse(path.read_text(encoding="utf-8")) if path else []
    if not rows:
        return {"ok": False, "text": "需給（信用残・空売り）: 材料なし（信用残・空売りのデータを集めていない）", "notes": []}
    last = rows[-1]
    jp_lines, jp_notes = _japan(rows, last)
    us_lines, us_notes = _us(rows, last)
    lines = jp_lines + us_lines
    if not lines:
        return {"ok": False, "text": "需給（信用残・空売り）: 表に数値が無い", "notes": []}
    return {"ok": True, "source": f"raw/market/{path.name}（二次）", "date": last["date"],
            "text": f"需給（{last['date']} 時点。表示のみ・点数に入れない）: " + "、".join(lines), "notes": jp_notes + us_notes}
