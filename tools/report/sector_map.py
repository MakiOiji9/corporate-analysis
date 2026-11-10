"""A company's industry -> the market report's sector series (the sector ETF the market report follows).

Japan: the TSE 33 industries (profile.json sector_name, from the EDINET code list) grouped into the TOPIX-17
series (NEXT FUNDS TOPIX-17 ETF, JP_SEC_1617〜1633). The US: the SEC SIC code (profile.json sic) into the Select
Sector SPDR ETF (US_SEC_XL*). Unknown industries map to None (the report then shows no sector).
"""
from __future__ import annotations

TOPIX17 = {
    "JP_SEC_1617": ("水産・農林業", "食料品"),
    "JP_SEC_1618": ("鉱業", "石油・石炭製品"),
    "JP_SEC_1619": ("建設業", "金属製品", "ガラス・土石製品"),
    "JP_SEC_1620": ("繊維製品", "パルプ・紙", "化学"),
    "JP_SEC_1621": ("医薬品",),
    "JP_SEC_1622": ("ゴム製品", "輸送用機器"),
    "JP_SEC_1623": ("鉄鋼", "非鉄金属"),
    "JP_SEC_1624": ("機械",),
    "JP_SEC_1625": ("電気機器", "精密機器"),
    "JP_SEC_1626": ("その他製品", "情報・通信業", "サービス業"),
    "JP_SEC_1627": ("電気・ガス業",),
    "JP_SEC_1628": ("陸運業", "海運業", "空運業", "倉庫・運輸関連業"),
    "JP_SEC_1629": ("卸売業",),
    "JP_SEC_1630": ("小売業",),
    "JP_SEC_1631": ("銀行業",),
    "JP_SEC_1632": ("証券、商品先物取引業", "証券・商品先物取引業", "保険業", "その他金融業"),
    "JP_SEC_1633": ("不動産業",),
}
JP33 = {name: sid for sid, names in TOPIX17.items() for name in names}

# (first SIC, last SIC, sector ETF): the first matching range wins, so narrow ranges come before wide ones
SIC_RANGES = (
    (6798, 6798, "US_SEC_XLRE"), (6500, 6553, "US_SEC_XLRE"), (6000, 6799, "US_SEC_XLF"),
    (4900, 4949, "US_SEC_XLU"), (4800, 4899, "US_SEC_XLC"), (7810, 7829, "US_SEC_XLC"), (2710, 2799, "US_SEC_XLC"),
    (3570, 3579, "US_SEC_XLK"), (3600, 3699, "US_SEC_XLK"), (7370, 7379, "US_SEC_XLK"),
    (2830, 2836, "US_SEC_XLV"), (3841, 3851, "US_SEC_XLV"), (8000, 8099, "US_SEC_XLV"),
    (1300, 1399, "US_SEC_XLE"), (2900, 2999, "US_SEC_XLE"),
    (2000, 2199, "US_SEC_XLP"), (2840, 2844, "US_SEC_XLP"), (5400, 5499, "US_SEC_XLP"),
    (3711, 3716, "US_SEC_XLY"), (5200, 5999, "US_SEC_XLY"), (7000, 7099, "US_SEC_XLY"), (2300, 2399, "US_SEC_XLY"),
    (1000, 1299, "US_SEC_XLB"), (1400, 1499, "US_SEC_XLB"), (2600, 2699, "US_SEC_XLB"), (2800, 2829, "US_SEC_XLB"),
    (3300, 3399, "US_SEC_XLB"),
    (1500, 1799, "US_SEC_XLI"), (3400, 3569, "US_SEC_XLI"), (3580, 3599, "US_SEC_XLI"), (3700, 3799, "US_SEC_XLI"),
    (4000, 4799, "US_SEC_XLI"), (8700, 8799, "US_SEC_XLI"),
)


def sector_id(profile: dict) -> str | None:
    """The sector series id of a company's profile.json, or None when the industry is not known."""
    if profile.get("market") == "us":
        try:
            sic = int(profile.get("sic"))
        except (TypeError, ValueError):
            return None
        return next((sid for lo, hi, sid in SIC_RANGES if lo <= sic <= hi), None)
    return JP33.get((profile.get("sector_name") or "").strip())
