"""Read and check a filled {week}_outlook.md.

Structure, leftover FILL markers and table shape reuse tools/collect/market/validate.py.
On top of that: the four judgement words, 3-5 key messages, risk rows, and phrases the
policy forbids (recommendations, guesses, price targets).
"""
from __future__ import annotations

import re

import mdparse as M
from validate import check_fill, check_structure, check_tables

JUDGMENTS = ("強気", "中立", "慎重", "弱気")
IMPACTS = ("大", "中", "小")
RISK_MARKETS = ("日本", "米国", "日米")
PERIODS = ("短期", "中期", "長期")
TOPICS = (("3.1", "株価・需給・バリュエーション"), ("3.2", "金利・為替"), ("3.3", "金融政策"),
          ("3.4", "マクロ（物価・雇用・景気）"), ("3.5", "財政・政策・政治"))
KEY_MESSAGES = (3, 5)
MIN_RISKS = 3
FORBIDDEN = ("買うべき", "売るべき", "買い推奨", "売り推奨", "買い時", "売り時", "おそらく", "と思われる")
PRICE_TARGET = re.compile(r"\d[\d,.]*\s*(?:円|ドル|ポイント|%)\s*(?:に|まで|を)\s*(?:上昇|下落|到達|なる|上回る|下回る)"
                          r"(?:する|す|だろう|見込み|と予想|と予測)")
MARKET_KEY = {"日本": "japan", "米国": "us"}
MARKETS = (("japan", "日本"), ("us", "米国"))
# characters a slide can show without crowding (warnings only; the template states the same numbers)
LIMIT_SUMMARY, LIMIT_MESSAGE, LIMIT_SEEN, LIMIT_CONCLUSION, LIMIT_OUTLOOK = 80, 100, 120, 60, 60
OUTLOOK_FIELDS = (("scenario", "基本シナリオ"), ("upside", "上振れ要因"), ("downside", "下振れ要因"),
                  ("watch", "確認する指標・イベント"))


def parse(text: str) -> dict:
    s1 = M.table_dicts(M.section(text, "1."))
    judgments = {MARKET_KEY[r["市場"]]: {"judgment": r.get("地合い判断", ""), "summary": r.get("判断の要約", "")}
                 for r in s1 if r.get("市場") in MARKET_KEY}
    trends = {}
    for number, title in TOPICS:
        rows = M.table_dicts(M.section(text, number, level=3))
        trends[number] = {"title": title,
                          **{MARKET_KEY[r["市場"]]: {"seen": r.get("見たもの", ""), "source": r.get("情報源", ""),
                                                    "conclusion": r.get("結論", "")}
                             for r in rows if r.get("市場") in MARKET_KEY}}
    outlook = [{"period": r.get("期間", ""), "market": MARKET_KEY.get(r.get("市場", ""), ""),
                "judgment": r.get("判断", ""), "scenario": r.get("基本シナリオ", ""),
                "upside": r.get("上振れ要因", ""), "downside": r.get("下振れ要因", ""),
                "watch": r.get("確認する指標・イベント", "")}
               for r in M.table_dicts(M.section(text, "4."))]
    risks = [{"risk": r.get("リスク", ""), "market": r.get("市場", ""), "impact": r.get("影響", ""),
              "signal": r.get("兆候を確認する指標", ""), "basis": r.get("根拠（情報源）", "")}
             for r in M.table_dicts(M.section(text, "5.")) if not M.is_blank(r.get("リスク"))]
    events = [{"date": r.get("日付", ""), "market": r.get("市場", ""), "event": r.get("イベント", ""),
               "point": r.get("注目点", "")}
              for r in M.table_dicts(M.section(text, "6.")) if not M.is_blank(r.get("日付"))]
    return {
        "judgments": judgments,
        "key_messages": M.bullets(M.section(text, "2.")),
        "trends": trends,
        "outlook": outlook,
        "risks": risks,
        "events": events,
        "limits": M.bullets(M.section(text, "7.")),
    }


def _body(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def _check_judgments(parsed: dict) -> list[str]:
    issues = []
    for market, label in MARKETS:
        j = parsed["judgments"].get(market, {}).get("judgment", "")
        if j not in JUDGMENTS:
            issues.append(f"1. 総合判断（{label}）が4段階の語ではない: 「{j}」")
    cells = {(r["period"], r["market"]) for r in parsed["outlook"]}
    issues += [f"4. 展望に {period}・{label} の行が無い"
               for period in PERIODS for market, label in MARKETS if (period, market) not in cells]
    issues += [f"4. 展望（{r['period']}・{r['market']}）の判断が4段階の語ではない: 「{r['judgment']}」"
               for r in parsed["outlook"] if r["judgment"] not in JUDGMENTS]
    return issues


def _check_lists(parsed: dict) -> list[str]:
    issues = []
    lo, hi = KEY_MESSAGES
    if not lo <= len(parsed["key_messages"]) <= hi:
        issues.append(f"2. キーメッセージは {lo}〜{hi} 項目（現在 {len(parsed['key_messages'])}）")
    if len(parsed["risks"]) < MIN_RISKS:
        issues.append(f"5. リスク要因は {MIN_RISKS} 行以上（現在 {len(parsed['risks'])}）")
    for r in parsed["risks"]:
        if r["impact"] not in IMPACTS:
            issues.append(f"5. リスク「{r['risk'][:20]}」の影響は 大/中/小: 「{r['impact']}」")
        if r["market"] not in RISK_MARKETS:
            issues.append(f"5. リスク「{r['risk'][:20]}」の市場は 日本/米国/日米: 「{r['market']}」")
    if not parsed["limits"]:
        issues.append("7. データの限界に箇条書きが無い")
    return issues


def _check_words(text: str) -> list[str]:
    body = _body(text)
    found = sorted({w for w in FORBIDDEN if w in body})
    issues = [f"推奨・推測の表現が含まれる: {', '.join(found)}"] if found else []
    return issues + [f"水準の予想に読める表現: 「{m.group(0)}」" for m in PRICE_TARGET.finditer(body)]


def _length(text: str) -> int:
    return len(text.replace("**", "").strip())


def _cells(parsed: dict) -> list[tuple[str, int, str, int]]:
    """(category, limit, location, length) for every cell the slides show as running text."""
    label = dict(MARKETS)
    out = [("1. 判断の要約", LIMIT_SUMMARY, label[m], _length(j.get("summary", "")))
           for m, j in parsed["judgments"].items()]
    out += [("2. キーメッセージ", LIMIT_MESSAGE, f"{i}項目め", _length(msg))
            for i, msg in enumerate(parsed["key_messages"], start=1)]
    for number, topic in parsed["trends"].items():
        for m, name in MARKETS:
            row = topic.get(m) or {}
            out.append(("3. 見たもの", LIMIT_SEEN, f"{number} {name}", _length(row.get("seen", ""))))
            out.append(("3. 結論", LIMIT_CONCLUSION, f"{number} {name}", _length(row.get("conclusion", ""))))
    out += [("4. 展望の各欄", LIMIT_OUTLOOK, f"{r['period']}・{label.get(r['market'], '')} {name}",
             _length(r[key])) for r in parsed["outlook"] for key, name in OUTLOOK_FIELDS]
    return out


def length_warnings(parsed: dict) -> list[str]:
    """One line per category whose cells run over the slide budget (the build still succeeds)."""
    over: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for category, limit, where, size in _cells(parsed):
        if size > limit:
            over.setdefault((category, limit), []).append((where, size))
    warnings = []
    for (category, limit), cells in over.items():
        where, size = max(cells, key=lambda c: c[1])
        warnings.append(f"{category}: {len(cells)} か所が目安 {limit} 字を超える（最長 {where} {size} 字）。"
                        "スライドが読みにくくなる")
    return warnings


def validate(text: str, template_text: str) -> list[str]:
    issues = check_structure(text, template_text) + check_fill(text) + check_tables(text)
    if issues:
        return issues  # content checks are meaningless while the skeleton is incomplete
    parsed = parse(text)
    return _check_judgments(parsed) + _check_lists(parsed) + _check_words(text)
