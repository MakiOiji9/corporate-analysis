"""Industry groups and the rules that depend on them, shared by every analysis.

The group comes from companies/{dir}/data/profile.json (tools/collect/company_profile.py: the TSE 33 業種 of the
EDINET code list for Japan, the SEC SIC code for the US). Without profile.json the group is None and each
analysis keeps its own fallback (safety: the 主力事業 text).

  financial    銀行・保険・証券・その他金融（リース・クレジット）: debt is the business's raw material, so the
               leverage limits, the operating CF tests, EV/EBITDA and ROIC do not apply
  real_estate  不動産・REIT: heavy borrowing is normal (safety compares with peers only, leverage is not 借入依存)
  trading      卸売業（総合商社など）: leverage is not 借入依存
  utility      電気・ガス: leverage is not 借入依存
  general      everything else
"""
from __future__ import annotations

import json
from pathlib import Path

FINANCIAL, REAL_ESTATE, TRADING, UTILITY, GENERAL = "financial", "real_estate", "trading", "utility", "general"
JP_SECTORS = {"銀行業": FINANCIAL, "保険業": FINANCIAL, "証券、商品先物取引業": FINANCIAL, "その他金融業": FINANCIAL,
              "不動産業": REAL_ESTATE, "卸売業": TRADING, "電気・ガス業": UTILITY}
US_SIC = ((6000, 6411, FINANCIAL), (6500, 6553, REAL_ESTATE), (6798, 6798, REAL_ESTATE), (4900, 4991, UTILITY),
          (5000, 5199, TRADING))
GROUP_LABELS = {FINANCIAL: "金融業", REAL_ESTATE: "不動産業", TRADING: "卸売業（商社など）", UTILITY: "電気・ガス業",
                GENERAL: "一般事業会社"}

PEER_ONLY_SAFETY = {FINANCIAL, REAL_ESTATE}                   # safety: no fixed 目安, peers only
LEVERAGE_NORMAL = {FINANCIAL, REAL_ESTATE, TRADING, UTILITY}  # profitability: high leverage is not 借入依存
NO_CASH_FLOW = {FINANCIAL}  # cash-flow analysis: 判定保留 (operating CF carries deposits and loans)
NO_EV = {FINANCIAL}         # valuation: EV/EBITDA 評価対象外
NO_ROIC = {FINANCIAL}       # moat: ROIC − cost of capital is not meaningful


def load(company_path: Path) -> dict | None:
    path = company_path / "data" / "profile.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError):
        return None


def group_of(profile: dict | None) -> str | None:
    if not profile:
        return None
    if profile.get("market") == "us" or profile.get("sic") is not None:
        sic = profile.get("sic")
        if not isinstance(sic, int):
            return None
        return next((g for lo, hi, g in US_SIC if lo <= sic <= hi), GENERAL)
    name = profile.get("sector_name")
    return JP_SECTORS.get(name, GENERAL) if name else None


def sector(company) -> dict:
    """{group (None without profile.json), name (業種 as filed), label (group in words), source}."""
    profile = load(company.path)
    group = group_of(profile)
    return {"group": group, "name": (profile or {}).get("sector_name"),
            "label": GROUP_LABELS.get(group, "不明"), "source": (profile or {}).get("sector_source")}


def note(info: dict, what: str) -> str:
    """「業種（銀行業）は …」: the sentence an analysis adds when a sector rule changed its result."""
    return f"業種（{info.get('name') or info['label']}）は{what}"


def applies(company, groups: set[str]) -> tuple[bool, dict]:
    info = sector(company)
    return info["group"] in groups, info
