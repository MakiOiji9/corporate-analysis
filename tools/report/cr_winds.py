"""Whether the company's industry has a tailwind or a headwind, from the weekly market report.

The sector (sector_map) is looked up in the market report of the outlook week: its relative strength against the
index (facts.json sectors, 13.1 of outlook.md: 強い +1, 弱い −1) and the facts the writer listed for it in 13.2
(追い風 +1, 向かい風 −1 each). The sum decides 追い風 / 向かい風 / 中立. Risk and event rows of the outlook that
mention the company's business are listed beside it (not scored). Nothing is looked up on the web.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import mdparse as M
import outlook as O
import sector_map as SM

STRENGTH_SCORE = {"強い": 1, "弱い": -1}
DIRECTION_SCORE = {"追い風": 1, "向かい風": -1}
TAIL, HEAD, NEUTRAL, NONE = "追い風", "向かい風", "中立", "材料なし"
MARKET_LABEL = {"japan": "日本", "us": "米国"}
# words of the business worth matching in the outlook (katakana / latin runs, kanji runs that are not generic)
WORD = re.compile(r"[ァ-ヴー]{3,}|[A-Za-z][A-Za-z0-9]{2,}|[一-龥]{2,}")
GENERIC = frozenset({"市場", "業界", "事業", "製品", "国内", "世界", "産業", "関連", "分野", "サービス", "企業", "日本",
                     "米国", "向け", "全体"})
RELATED_MAX = 3


def _words(text: str) -> list[str]:
    return sorted({w for w in WORD.findall(text or "") if w not in GENERIC}, key=len, reverse=True)


def _related(text: str, words: list[str]) -> list[str]:
    """Risk (5.) and event (6.) rows of the outlook that mention one of the business words."""
    rows = [" / ".join(v for v in r.values() if v and not M.is_blank(v))
            for number in ("5.", "6.") for r in M.table_dicts(M.section(text, number))]
    return [r for r in rows if words and any(w in r for w in words)][:RELATED_MAX]


def _sector_row(root: Path, week: str, market: str, sid: str) -> dict | None:
    path = root / "market" / "report" / f"{week}_facts.json"
    if not path.exists():
        return None
    facts = json.loads(path.read_text(encoding="utf-8"))
    rows = ((facts.get("sectors") or {}).get(market) or {}).get("rows") or []
    return next((r for r in rows if r.get("id") == sid), None)


def _fail(why: str) -> dict:
    return {"ok": False, "verdict": NONE, "why": why, "items": [], "related": []}


def evaluate(root: Path, profile: dict, outlook: dict, business: str) -> dict:
    """{ok, week, sector, market, strength, m6, rel6, m12, rel12, items, related, score, verdict, why}."""
    sid = SM.sector_id(profile)
    if not sid:
        return _fail(f"会社の業種（{profile.get('sector_name') or profile.get('sic') or '不明'}）を地合いの業種に対応できない")
    if not outlook.get("path"):
        return _fail("地合いレポートが無い")
    market = profile.get("market") or ("us" if sid.startswith("US_") else "japan")
    row = _sector_row(root, outlook["week"], market, sid)
    if not row:
        return _fail(f"地合いレポート（{outlook['week']} の週）に業種の数値が無い")
    text = (root / outlook["path"]).read_text(encoding="utf-8")
    items = [w for w in O.parse_winds(text) if w["market"] == market and w["sector"] == row["name"]]
    strength = row.get("strength") or "不明"
    score = STRENGTH_SCORE.get(strength, 0) + sum(DIRECTION_SCORE.get(i["direction"], 0) for i in items)
    if strength == "不明" and not items:  # an outlook built before 13. existed: nothing to judge on
        return {**_fail(f"地合いレポート（{outlook['week']} の週）に業種の強さ・材料が無い"), "related": []}
    verdict = TAIL if score > 0 else HEAD if score < 0 else NEUTRAL
    parts = [f"株価の強さ {strength}"] + [f"{i['direction']}（{i['kind']}）" for i in items]
    return {"ok": True, "week": outlook["week"], "sector": row["name"], "market": MARKET_LABEL[market],
            "strength": strength, **{k: row.get(k) for k in ("m6", "rel6", "m12", "rel12")}, "items": items,
            "related": _related(text, _words(business)), "score": score, "verdict": verdict,
            "why": "・".join(parts) + f"（合計 {score:+d}）"}
