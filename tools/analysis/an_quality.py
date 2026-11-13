"""Quality marks every STEP 1 analysis (five-forces, three-c, moat, swot) records with its verdict.

  dated()       a source names a date (2026-06-20, 2025年3月, FY2025) or a page (p12, p.8, 12ページ)
  effective()   the evidence grade a row really has: 一次・二次 without a date or page count as 参考 (a primary
                document that cannot be found again is not better than a reference)
  confidence()  高/中/低 from the rated rows: the share of 一次 among the known rows, the share of 参考, the share of
                unknown rows. 高: unknown ≤ HIGH_UNKNOWN, 一次 ≥ HIGH_PRIMARY, 参考 ≤ HIGH_REFERENCE; 低: unknown ≥
                LOW_UNKNOWN or 参考 ≥ LOW_REFERENCE (or nothing known); else 中. Shown next to the verdict.
  outdated()    the result was built under an older rule set (its version), so check() asks for a rebuild
  counter_issue()  the writer's counter-argument (「この結論が間違っているとしたら」) is missing or empty
"""
from __future__ import annotations

import re

PRIMARY, SECONDARY, REFERENCE = "一次", "二次", "参考"
UNKNOWN_RATINGS = ("不明", "？", "判定保留")
DATE = re.compile(r"(19|20)\d{2}\s*[-年/.]|FY\s?\d{2,4}|\bp\.?\s?\d+|\d+\s*ページ")
HIGH_UNKNOWN, HIGH_PRIMARY, HIGH_REFERENCE = 0.1, 0.5, 0.2
LOW_UNKNOWN, LOW_REFERENCE = 0.3, 0.5
COUNTER_MIN = 10  # characters of a real counter-argument


def dated(source: str | None) -> bool:
    return bool(source) and DATE.search(source) is not None


def effective(confidence: str | None, source: str | None) -> str | None:
    if confidence in (PRIMARY, SECONDARY) and not dated(source):
        return REFERENCE
    return confidence


def confidence(items: list[dict]) -> dict:
    """items: [{confidence, source, rating}] -> {level, primary, reference, unknown, known, total, why}."""
    total = len(items)
    unknown = sum(1 for i in items if (i.get("rating") or "").strip() in UNKNOWN_RATINGS)
    grades = [effective(i.get("confidence"), i.get("source")) for i in items
              if (i.get("rating") or "").strip() not in UNKNOWN_RATINGS]
    known = len(grades)
    primary = sum(1 for g in grades if g == PRIMARY)
    reference = sum(1 for g in grades if g not in (PRIMARY, SECONDARY))
    why = f"一次資料 {primary}/{known}・参考 {reference}・不明 {unknown}/{total}"
    base = {"primary": primary, "reference": reference, "unknown": unknown, "known": known, "total": total, "why": why}
    if not known or unknown / total >= LOW_UNKNOWN or reference / known >= LOW_REFERENCE:
        return {**base, "level": "低"}
    if unknown / total <= HIGH_UNKNOWN and primary / known >= HIGH_PRIMARY and reference / known <= HIGH_REFERENCE:
        return {**base, "level": "高"}
    return {**base, "level": "中"}


def outdated(result: dict, version: int) -> str | None:
    old = result.get("version") or 1
    return None if old == version else f"判定の基準が新しくなった（版 {old} → {version}）。作り直す"


def counter_issue(text: str | None) -> str | None:
    body = (text or "").strip()
    if not body or "FILL:" in body or body in ("なし", "—", "-") or len(body) < COUNTER_MIN:
        return "反論（この結論が間違っているとしたら）を1〜2文で書く（反対の事実・別の読み方・崩れる条件）"
    return None
