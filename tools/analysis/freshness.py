"""When a finished company analysis must be redone (triggered), by the kind of information it rests on.

  annual         (five-forces, three-c, moat, swot): a 有報 / 10-K of a newer fiscal period, or industry data or a
                 mid-term plan collected after the analysis.
  quarter        (growth, safety): a 決算短信 of a newer quarter (or a newer 10-Q / 10-K).
  half           (profitability, cash-flow): a newer interim (第2四半期・中間) or full-year 決算短信 (or 10-K).
  annual_results (valuation): a newer full-year 決算短信 (or 10-K).
Every kind is also triggered when an upstream analysis reached a different conclusion than the one in place when
this analysis was built, and when its judging rules changed after the analysis day (RULE_CHANGES). Peer, price and business-overview updates, and edits of numbers inside the same period,
never trigger: they wait for the validity period (each *_paths.VALID_DAYS).

The basis "at the analysis" is recomputed from the files dated on or before the analysis day, so results built
before this module (without any recorded basis) are judged the same way.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import unicodedata
from pathlib import Path
from types import ModuleType

import an_common as A

FILING = re.compile(r"^(\d{4}-\d{2}-\d{2})_(?:(.+?)_)?(yuho|10k|20f|424b4|s-1|10q)\.md$", re.I)
ANNUAL_FILINGS = ("yuho", "10k", "20f", "424b4", "s-1")
STEP1_KINDS = (("industry-overview", "業界データ"), ("mid-term-plan", "中期経営計画"))
JP_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
QUARTER_WORDS = (("第1四半期", 1), ("第2四半期", 2), ("中間", 2), ("第3四半期", 3))
UNIT_QUARTERS = {"quarter": (1, 2, 3, 4), "half": (2, 4), "annual_results": (4,)}
UNITS = ("annual", *UNIT_QUARTERS)
QUARTER_LABEL = {1: "第1四半期", 2: "第2四半期（中間）", 3: "第3四半期", 4: "通期"}


def _filed(text: str) -> str | None:
    m = JP_DATE.search(unicodedata.normalize("NFKC", text or ""))
    return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat() if m else None


def _quarter(document: str) -> int:
    text = unicodedata.normalize("NFKC", document or "")
    return next((q for word, q in QUARTER_WORDS if word in text), 4)


# ---------------------------------------------------------------- periods

def _fetched_dates(company_path: Path) -> dict[str, str]:
    """doc_id → the first day an original of it was saved (sources/manifest.csv)."""
    path = company_path / "sources" / "manifest.csv"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            doc, day = row.get("doc_id") or "", row.get("fetched_date") or ""
            if doc and day and (doc not in out or day < out[doc]):
                out[doc] = day
    return out


def tdnet_periods(company_path: Path) -> list[tuple[str, int, str]]:
    """(fiscal_year_end, quarter 1-4, known date) of every 決算短信 in data/tdnet_facts.csv. The known date is the
    later of the filing date and the day its original was first saved (manifest), so a 短信 collected after an
    analysis counts as new even when it was filed before the analysis day."""
    path = company_path / "data" / "tdnet_facts.csv"
    if not path.exists():
        return []
    fetched = _fetched_dates(company_path)
    seen: dict[str, tuple[str, int, str]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            filed = _filed(row.get("filing_date", ""))
            doc = row.get("doc_id")
            if doc and filed and row.get("fiscal_year_end"):
                known = max(filed, fetched.get(doc, filed))
                seen[doc] = (row["fiscal_year_end"], _quarter(row.get("document", "")), known)
    return sorted(seen.values())


def filings(company_path: Path) -> list[tuple[str, str, str]]:
    """(collected date, period, kind) of the annual and quarterly disclosures under raw/ (period = date if absent)."""
    raw = company_path / "raw"
    out = []
    for p in raw.rglob("*.md") if raw.exists() else ():
        m = FILING.match(p.name)
        if m:
            out.append((m.group(1), m.group(2) or m.group(1), m.group(3).lower()))
    return sorted(out)


def settled_period(company_path: Path, unit: str, until: str | None = None) -> tuple[str, int] | None:
    """The newest (fiscal period, quarter) of results known on `until` (inclusive) for the unit."""
    quarters = UNIT_QUARTERS[unit]
    periods = [(fy, q) for fy, q, filed in tdnet_periods(company_path)
               if q in quarters and (until is None or filed <= until)]
    if periods:
        return max(periods)
    kinds = ANNUAL_FILINGS + (("10q",) if unit == "quarter" else ())
    found = [(period, 0 if kind == "10q" else 4) for date, period, kind in filings(company_path)
             if kind in kinds and (until is None or date <= until)]
    return max(found) if found else None


def period_label(period: tuple[str, int] | None) -> str:
    if not period:
        return "なし"
    fy, q = period
    return f"{fy[:7]} 期 {QUARTER_LABEL[q]}" if q in QUARTER_LABEL else f"{fy} 期"


def annual_report_period(company_path: Path, until: str | None = None) -> str | None:
    periods = [period for date, period, kind in filings(company_path)
               if kind in ANNUAL_FILINGS and (until is None or date <= until)]
    return max(periods) if periods else None


# ---------------------------------------------------------------- triggers

def _raw_dates(company_path: Path, kind: str) -> list[tuple[str, Path]]:
    raw = company_path / "raw"
    out = []
    for p in raw.rglob(f"*_{kind}.md") if raw.exists() else ():
        m = A.DATED.match(p.name)
        if m:
            out.append((m.group(1), p))
    return sorted(out)


def material_triggers(company: A.Company, date: str, unit: str) -> list[str]:
    """Reasons a newer period of the unit's material exists than on the analysis day."""
    path = company.path
    if unit == "annual":
        out = []
        then, now = annual_report_period(path, date), annual_report_period(path)
        if now and (then is None or now > then):
            out.append(f"新しい期の有報（{now} 期。分析時は {then or 'なし'}）が収集された")
        for kind, label in STEP1_KINDS:
            newer = [company.rel(p) for d, p in _raw_dates(path, kind) if d > date]
            if newer:
                out.append(f"分析後に{label}が収集された: {', '.join(newer)}")
        return out
    then, now = settled_period(path, unit, date), settled_period(path, unit)
    if now and (then is None or now > then):
        return [f"新しい決算（{period_label(now)}。分析時は {period_label(then)}）が出た"]
    return []


def _day_after(date: str) -> str:
    return (dt.date.fromisoformat(date) + dt.timedelta(days=1)).isoformat()


def verdict_of(result: dict | None) -> str | None:
    if not result:
        return None
    return result.get("verdict") or result.get("attractiveness")


def upstream_triggers(company: A.Company, date: str, upstream: list[tuple[str, ModuleType]]) -> list[str]:
    """Upstream analyses whose conclusion now differs from the one in place on the analysis day."""
    out = []
    for label, paths in upstream:
        target = paths.Company(company.root, company.path)
        now = paths.latest_result(target)
        if not now or now[0] <= date:
            continue
        then = paths.latest_result(target, before=_day_after(date))
        # a result older than the two kept ones was deleted (an_common.prune): its verdict is in _history.json
        old = None if then else A.history_verdict(target.analysis_dir, date)
        before = verdict_of(then[1]) if then else (old[1] if old else None)
        after = verdict_of(now[1])
        if before != after:
            out.append(f"{label}の結論が {before or '未実施'} → {after} に変わった（{now[0]}）")
    return out


# analysis kind (its folder under analysis/) -> [(the day its judging rules changed, what changed)]: a result built
# before that day was judged by the old rules. Add a row whenever a rule of an analysis changes.
RULE_CHANGES: dict[str, list[tuple[str, str]]] = {
    "five-forces": [("2026-11-10", "売り手を粗利率の3年の変化で、業界内競争を上位3社の合計シェアで判定")],
    "moat": [("2026-11-10", "ROIC の投下資本にリース負債を加え余剰現金を控除、シェアの推移の候補を算出")],
    "profitability": [("2026-11-10", "営業利益率の同業比較を直近3年の差の平均と中央値で、業種別のレバレッジの扱い")],
    "growth": [("2026-11-10", "CAGR を全年の回帰で判定（端点 CAGR は併記）")],
    "safety": [("2026-11-10", "借入目的の運転資金の区分、ネットキャッシュに短期投資、同業の中央値、業種別の扱い"),
               ("2026-11-11", "自己資本比率 10% 未満は懸念")],
    "cash-flow": [("2026-11-10", "利益の質の成長補正、金融業の扱い"),
                  ("2026-11-11", "5年以内の公募増資・第三者割当は最大でも普通")],
    "valuation": [("2026-11-10", "EV にリース負債・非支配持分・短期投資、PER/PBR の過去レンジを日次株価から算出、金融業の扱い"),
                  ("2026-11-11", "資産ベースのネットキャッシュ比率を5つ目の指標に、PER に業態別の目安の軸")],
}


def rule_triggers(company: A.Company, date: str) -> list[str]:
    """The rule changes made after the analysis day (RULE_CHANGES of this analysis kind)."""
    folder = getattr(company, "analysis_dir", None)
    kind = folder.name if folder is not None else ""
    return [f"判定ルールが変わった（{changed}: {what}）" for changed, what in RULE_CHANGES.get(kind, ()) if date < changed]


def triggers(company: A.Company, date: str, unit: str,
             upstream: list[tuple[str, ModuleType]] | tuple = ()) -> list[str]:
    if unit not in UNITS:
        raise ValueError(f"unknown freshness unit: {unit}")
    return (material_triggers(company, date, unit) + upstream_triggers(company, date, list(upstream))
            + rule_triggers(company, date))
