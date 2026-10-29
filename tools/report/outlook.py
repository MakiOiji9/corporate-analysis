"""Read and check a filled {week}_outlook.md.

Structure, leftover FILL markers and table shape reuse tools/collect/market/validate.py.
On top of that: the attention words (平常 / 注意 / 警戒) and the three axis labels, 3-5 key messages,
risk rows, and phrases the policy forbids (recommendations, guesses, price targets).
"""
from __future__ import annotations

import re

import glossary as G
import mdparse as M
import scoring as SC
from brief import handoff_rows, sector_rows
from validate import check_fill, check_structure, check_tables

JUDGMENTS = SC.ATTENTION_WORDS
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
    judgments = {MARKET_KEY[r["市場"]]: {"judgment": r.get("注意の度合い", ""), "summary": r.get("判断の要約", ""),
                                       "axes": {key: r.get(name, "") for key, name, _ in SC.AXES}}
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
    viewpoints = [{"market": MARKET_KEY.get(r.get("市場", ""), ""), "name": r.get("軸", ""),
                   "candidate": r.get("候補", ""), "adopted": r.get("採用", ""), "reason": r.get("変えた理由", "")}
                  for r in M.table_dicts(M.section(text, "8.")) if r.get("市場") in MARKET_KEY]
    changes = [{"period": r.get("期間", ""), "market": MARKET_KEY.get(r.get("市場", ""), ""),
                "before": r.get("前回", ""), "reason": r.get("変えた理由", "")}
               for r in M.table_dicts(M.section(text, "9.")) if r.get("市場") in MARKET_KEY]
    return {
        "judgments": judgments,
        "key_messages": M.bullets(M.section(text, "2.")),
        "trends": trends,
        "outlook": outlook,
        "risks": risks,
        "events": events,
        "limits": M.bullets(M.section(text, "7.")),
        "viewpoints": viewpoints,
        "changes": changes,
        "handoff": M.section(text, "10."),
        "plain_summary": _sub_bullets(text, "今週を3行で"),
        "plain_caution": _sub_bullets(text, "気をつけること"),
        "sector_table": M.section(text, "12."),
    }


def _sub_bullets(text: str, keyword: str) -> list[str]:
    found = M.section_by_title(text, keyword, level=3)
    return M.bullets(found[1]) if found else []


def _body(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(">"))


def _check_judgments(parsed: dict) -> list[str]:
    issues = []
    words = " / ".join(JUDGMENTS)
    for market, label in MARKETS:
        row = parsed["judgments"].get(market, {})
        j = row.get("judgment", "")
        if j not in JUDGMENTS:
            issues.append(f"1. 注意の度合い（{label}）は {words} のどれか: 「{j}」")
        for key, name, labels in SC.AXES:
            got = (row.get("axes") or {}).get(key, "")
            if got not in labels:
                issues.append(f"1. {name}（{label}）は {' / '.join(labels)} のどれか: 「{got}」")
    cells = {(r["period"], r["market"]) for r in parsed["outlook"]}
    issues += [f"4. 展望に {period}・{label} の行が無い"
               for period in PERIODS for market, label in MARKETS if (period, market) not in cells]
    issues += [f"4. 展望（{r['period']}・{r['market']}）の判断は {words} のどれか: 「{r['judgment']}」"
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


# ---------------------------------------------------------------- checks against facts.json

UNCHANGED = "変更なし"
MIN_REASON = 8  # characters; an override needs a real basis, not a word


def adopted_ratings(parsed: dict) -> dict[str, dict[str, str]]:
    """{market: {"money": label, ...}} from section 8 (rows are matched by the axis name)."""
    keys = {name: key for key, name, _ in SC.AXES}
    out: dict[str, dict[str, str]] = {}
    for v in parsed["viewpoints"]:
        key = keys.get(v["name"])
        if key and v["market"]:
            out.setdefault(v["market"], {})[key] = v["adopted"]
    return out


def _check_axis_row(where: str, got: dict, want: dict) -> list[str]:
    labels = SC.AXIS_LABELS[want["key"]]
    if not got["candidate"].startswith(want["rating"]):
        return [f"{where}: 候補はスクリプトの値（{want['rating']}）から変えない"]
    if got["adopted"] not in labels:
        return [f"{where}: 採用は {' / '.join(labels)} のどれか: 「{got['adopted']}」"]
    if got["adopted"] != want["rating"] and (M.is_blank(got["reason"]) or len(got["reason"]) < MIN_REASON):
        return [f"{where}: 候補（{want['rating']}）から変えたので、理由に根拠（指標と時点か文書名）を書く"]
    if got["adopted"] == want["rating"] and not M.is_blank(got["reason"]):
        return [f"{where}: 候補のまま採用した行の理由は「—」"]
    return []


def _check_viewpoints(parsed: dict, facts: dict) -> list[str]:
    issues = []
    label = dict(MARKETS)
    rows = {(v["market"], v["name"]): v for v in parsed["viewpoints"]}
    for market, name in MARKETS:
        for want in facts.get("scores", {}).get(market, {}).get("axes", []):
            got = rows.get((market, want["name"]))
            where = f"8. {name} {want['name']}"
            issues += [f"{where}: 行が無い"] if not got else _check_axis_row(where, got, want)
    for market, ratings in adopted_ratings(parsed).items():
        if len(ratings) != len(SC.AXES) or any(r not in SC.AXIS_LABELS[k] for k, r in ratings.items()):
            continue
        row = parsed["judgments"].get(market, {})
        for key, axis_name, _ in SC.AXES:
            if (row.get("axes") or {}).get(key) != ratings[key]:
                issues.append(f"1. {axis_name}（{label[market]}）は 8章の採用「{ratings[key]}」と同じにする")
        want = SC.attention(ratings)
        if row.get("judgment", "") != want:
            issues.append(f"1. 注意の度合い（{label[market]}）は 8章の採用から決まる「{want}」と同じにする"
                          f"（現在「{row.get('judgment', '')}」）")
    return issues


def _check_periods(parsed: dict) -> list[str]:
    issues = []
    label = dict(MARKETS)
    now = {(r["period"], r["market"]): r["judgment"] for r in parsed["outlook"]}
    for market, name in MARKETS:
        short, overall = now.get(("短期", market)), parsed["judgments"].get(market, {}).get("judgment")
        if short and overall and short != overall:
            issues.append(f"4. 展望（短期・{name}）の判断は 1章の注意の度合い（{overall}）と同じにする")
    for c in parsed["changes"]:
        if M.is_blank(c["before"]) or c["before"] not in JUDGMENTS:  # first week, or the former scale
            continue
        current = now.get((c["period"], c["market"]), "")
        where = f"9. {c['period']}・{label.get(c['market'], '')}"
        if current != c["before"] and (M.is_blank(c["reason"]) or c["reason"] == UNCHANGED):
            issues.append(f"{where}: 前回 {c['before']} → 今回 {current} に変えたので、理由を書く")
        elif current == c["before"] and c["reason"] != UNCHANGED:
            issues.append(f"{where}: 前回と同じ判断なので「{UNCHANGED}」と書く")
    return issues


def check_against_facts(parsed: dict, facts: dict) -> list[str]:
    issues = _check_viewpoints(parsed, facts) + _check_periods(parsed)
    if handoff_rows(facts) not in parsed["handoff"]:
        issues.append("10. 企業分析への引き継ぎがスクリプトの記入（facts.json）と違う。手で変えない")
    if "sectors" in facts and sector_rows(facts) not in parsed["sector_table"]:
        issues.append("12. 業種の動きがスクリプトの記入（facts.json）と違う。手で変えない")
    return issues + _check_plain(parsed)


PLAIN_SUMMARY, PLAIN_CAUTION, LIMIT_PLAIN = 3, 1, 60


def _check_plain(parsed: dict) -> list[str]:
    issues = []
    if len(parsed["plain_summary"]) != PLAIN_SUMMARY:
        issues.append(f"11. 今週を3行で は箇条書き {PLAIN_SUMMARY} つ（現在 {len(parsed['plain_summary'])}）")
    if len(parsed["plain_caution"]) != PLAIN_CAUTION:
        issues.append(f"11. 気をつけること は箇条書き {PLAIN_CAUTION} つ（現在 {len(parsed['plain_caution'])}）")
    return issues


def plain_warnings(parsed: dict) -> list[str]:
    """Beginner section: jargon from the glossary and over-long items (warnings; build still succeeds)."""
    items = parsed["plain_summary"] + parsed["plain_caution"]
    jargon = sorted({t for item in items for t in G.jargon_in(item)})
    long = [i for i, item in enumerate(items, start=1) if _length(item) > LIMIT_PLAIN]
    out = []
    if jargon:
        out.append(f"11. やさしい要約に専門用語がある: {'、'.join(jargon)}。ふだんの言葉に言い換える")
    if long:
        out.append(f"11. やさしい要約の {len(long)} 項目が目安 {LIMIT_PLAIN} 字を超える")
    return out


def source_warnings(parsed: dict) -> list[str]:
    label = dict(MARKETS)
    cells = [f"{number} {label[m]}" for number, topic in parsed["trends"].items()
             for m in ("japan", "us") if "brief" in (topic.get(m) or {}).get("source", "")]
    return ([f"3. 情報源に社内ファイル（brief.md）の節番号が残っている: {'、'.join(cells)}。原典の名前で書く"]
            if cells else [])


def judgment_payload(parsed: dict, facts: dict) -> dict:
    """{week}_judgment.json: the adopted ratings and judgements, read by next week's prepare."""
    adopted = adopted_ratings(parsed)
    axes = {}
    for market, _ in MARKETS:
        rows = {a["key"]: a for a in facts.get("scores", {}).get(market, {}).get("axes", [])}
        reasons = {v["name"]: v["reason"] for v in parsed["viewpoints"] if v["market"] == market}
        axes[market] = {key: {"name": name, "candidate": rows.get(key, {}).get("rating"),
                              "total": rows.get(key, {}).get("total"),
                              "adopted": adopted.get(market, {}).get(key),
                              "reason": "" if M.is_blank(reasons.get(name)) else reasons.get(name)}
                        for key, name, _ in SC.AXES}
    return {
        "week": facts["week"], "session": facts["session"],
        "judgments": {m: v["judgment"] for m, v in parsed["judgments"].items()},
        "candidates": {m: s["candidate"] for m, s in facts.get("scores", {}).items()},
        "axes": axes,
        "periods": {p: {r["market"]: r["judgment"] for r in parsed["outlook"] if r["period"] == p}
                    for p in PERIODS},
    }
