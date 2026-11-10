"""Market-share numbers from the industry raw「シェア」section, shared by five-forces (concentration) and moat
(the target's share trend). collect-market writes them as:

  ### 上位企業とシェア            | 会社 | シェア | 年度 | 出典 |      (the newest year; at least the top 3)
  ### 自社シェアの推移            | 年度 | シェア | 出典 |              (3 years or more)

Any table with 会社 and シェア columns counts for the first, any table under a title with「推移」and 年度 and
シェア columns for the second. Shares are percentages (「12.3%」「12.3」).
"""
from __future__ import annotations

import re

import mdparse as M
from ff_inputs import Found

PERCENT = re.compile(r"(\d+(?:\.\d+)?)")
YEAR = re.compile(r"(\d{4})")
CR3_LIMITS = (30.0, 60.0)  # 上位3社の合計シェア: 30%未満 強（分散）/ 30〜60% 中 / 60%以上 弱（寡占）
TREND_UP, TREND_DOWN, TREND_SLIP = 1.0, -2.0, -0.5  # pt over the series
MIN_TREND_YEARS = 3


def _percent(cell: str | None) -> float | None:
    found = PERCENT.search(cell or "")
    value = float(found.group(1)) if found else None
    return value if value is not None and 0 <= value <= 100 else None


def _col(header: list[str], word: str) -> int | None:
    return next((i for i, h in enumerate(header) if word in h), None)


def _subsections(body: str) -> list[tuple[str, str]]:
    """(title, text) of every ### / #### subsection, plus the text before the first one under an empty title."""
    parts = re.split(r"^#{3,4}\s+(.+)$", body, flags=re.M)
    return [("", parts[0])] + [(parts[i].strip(), parts[i + 1]) for i in range(1, len(parts) - 1, 2)]


def _usable(found: Found) -> bool:
    return found.status in ("ok", "thin") and bool(found.body)


def top_shares(found: Found) -> list[tuple[str, float]]:
    """(company, share %) of the first table with 会社 and シェア columns, largest first."""
    if not _usable(found):
        return []
    for table in M.tables(found.body):
        name, share = _col(table[0], "会社"), _col(table[0], "シェア")
        if name is None or share is None:
            continue
        rows = [(r[name].strip(), v) for r in table[1:] if max(name, share) < len(r)
                if (v := _percent(r[share])) is not None and r[name].strip()]
        if rows:
            return sorted(rows, key=lambda x: -x[1])
    return []


def concentration(found: Found) -> dict:
    """Five-forces ⑤ 業界内の競争 candidate from the top-3 share (not fixed: the writer may rate it stronger)."""
    shares = top_shares(found)
    if len(shares) < 3:
        return {"rating": None, "fixed": False, "cr3": None,
                "basis": f"上位企業のシェアが{len(shares)}社分しかなく、上位3社の合計を出せない"}
    cr3 = round(sum(v for _, v in shares[:3]), 1)
    low, high = CR3_LIMITS
    rating = "強" if cr3 < low else "中" if cr3 < high else "弱"
    names = "・".join(f"{n} {v:.1f}%" for n, v in shares[:3])
    return {"rating": rating, "fixed": False, "cr3": cr3,
            "basis": (f"上位3社の合計シェア {cr3:.1f}%（{names}）。目安: {low:.0f}%未満 強（分散して競争が激しい）/ "
                      f"{low:.0f}〜{high:.0f}% 中 / {high:.0f}%以上 弱（寡占）")}


def own_share_series(found: Found) -> list[tuple[str, float]]:
    """(year, share %) of the first table under a「推移」title with 年度 and シェア columns, oldest first."""
    if not _usable(found):
        return []
    for title, text in _subsections(found.body):
        if "推移" not in title:
            continue
        for table in M.tables(text):
            year, share = _col(table[0], "年"), _col(table[0], "シェア")
            if year is None or share is None:
                continue
            rows = [(y.group(1), v) for r in table[1:] if max(year, share) < len(r)
                    if (y := YEAR.search(r[year])) and (v := _percent(r[share])) is not None]
            if rows:
                return sorted(rows)
    return []


def share_trend(found: Found) -> dict:
    """Moat「シェアの推移」candidate: 拡大 / 安定 / 横ばい〜微減 / 低下, or 不明 with fewer than 3 years."""
    series = own_share_series(found)
    if len(series) < MIN_TREND_YEARS:
        return {"trend": "不明", "series": series,
                "basis": f"自社シェアの推移が{len(series)}年分しかない（{MIN_TREND_YEARS}年以上で判定）"}
    (first_year, first), (last_year, last) = series[0], series[-1]
    delta = round(last - first, 1)
    trend = ("拡大" if delta >= TREND_UP else "低下" if delta <= TREND_DOWN else
             "横ばい〜微減" if delta <= TREND_SLIP else "安定")
    return {"trend": trend, "series": series, "delta": delta,
            "basis": (f"自社シェア {first_year} {first:.1f}% → {last_year} {last:.1f}%（{delta:+.1f}pt）。目安: "
                      f"+{TREND_UP:.0f}pt 以上 拡大 / {TREND_DOWN:.0f}pt 以下 低下 / {TREND_SLIP}pt 以下 横ばい〜微減 / "
                      "それ以外 安定")}
