"""Warnings on a built company report: chapters that disagree, and wording the reader stumbles on.

The report's judgements and prices come from one facts.json, but several chapters render them through their own
code; a reviewer found the same thing named two ways (moat なし / 狭い, take-profit 488 / 549, もみ合い / 下降).
check() looks for that kind of disagreement and for wording that is not wrong but hard to read. Unlike
cr_plain.leaks() (which stops the build), these are warnings: the build goes on and the report shows them at the
top (docs/proposals/company-report-review-feedback.md 6., 決定 Q7).

  verdict_words()  each "（今は「X」）" of 判定を動かす要因 names the analysis' own verdict word
  take_profits()   03 章の売買シナリオ (the current price's first target) and 付録A の利益確定の目安 name one price
  trend()          the short horizon's technical factor and 付録B's daily trend name one state
  wording()        internal words (raw・スクリプト・判定候補・json・版N), a sentence repeated back to back,
                   brackets nested two deep
"""
from __future__ import annotations

import html
import re

import cr_judge as J
import cr_plain as P

FAIR_LABEL_PREFIX = "適正PBR"  # a valuation target (cr_scenarios.FAIR_LABEL) is not a chart line
WORD_PATTERNS = {
    "raw": r"(?<![A-Za-z])raw(?![A-Za-z])", "スクリプト": r"スクリプト", "判定候補": r"判定候補",
    "json": r"(?<![A-Za-z])json(?![A-Za-z])", "版N": r"(?<![出])版\s*\d",
}
_WORDS = {name: re.compile(p) for name, p in WORD_PATTERNS.items()}
_NOW = re.compile(r"（今は「([^」]+)」）")
_SEGMENT = re.compile(r"[^、。\n]{10,}")
REPEAT_MIN = 10  # characters: shorter repeats (「良好、良好」) are lists, not a duplicated sentence
EXAMPLES = 3     # examples shown per kind of warning


def _context(text: str, start: int, end: int) -> str:
    return " ".join(text[max(0, start - 20):end + 20].split())


def verdict_words(facts: dict) -> list[str]:
    out = []
    for key, h in (facts.get("horizons") or {}).items():
        rows = h.get("rows") or []
        for m in (h.get("sensitivity") or {}).get("movers") or []:
            row = next((r for r in rows if r["key"] == m["key"]), None)
            word = J._verdict_word(row) if row else None
            found = _NOW.search(J.mover_text(m, rows))
            if found and word and found.group(1) != word and found.group(1) in (J.LADDERS.get(m["key"]) or ()):
                out.append(f"判定の言葉が食い違う（{key}）: 判定を動かす要因は「今は「{found.group(1)}」」、"
                           f"{m['label']}の判定は「{word}」")
    return out


def take_profits(facts: dict) -> list[str]:
    buys = (facts.get("scenarios") or {}).get("buys") or []
    levels = (((facts.get("prices") or {}).get("technicals") or {}).get("levels") or {})
    resistances = levels.get("resistances") or []
    now = next((b for b in buys if b.get("label") == "今の株価"), buys[0] if buys else None)
    target = (now or {}).get("target1")
    if not target or str(target.get("label", "")).startswith(FAIR_LABEL_PREFIX):
        return []
    if not resistances:
        return [f"利益確定の目安が食い違う: 03章は {target['price']:,.0f}、付録A は抵抗線なし"]
    if abs(resistances[0]["price"] - target["price"]) > 0.5:
        return [f"利益確定の目安が食い違う: 03章の売買シナリオは {target['price']:,.0f}、"
                f"付録A の目安は {resistances[0]['price']:,.0f}"]
    return []


def trend(facts: dict) -> list[str]:
    """The short horizon's technical factor is 付録B's daily trend (判定ルールの改定 3): the two name one state."""
    daily = ((((facts.get("technical_analysis") or {}).get("daily") or {}).get("aspects") or {})
             .get("trend") or {}).get("state") or ""
    rows = ((facts.get("horizons") or {}).get("short") or {}).get("rows") or []
    row = next((r for r in rows if r.get("key") == "trend_daily"), None)
    if not daily or not row or row.get("score") is None:
        return []
    if not str(row.get("value") or "").startswith(daily):
        return [f"トレンドの読みが食い違う: 短期の点数のテクニカルは「{row.get('value')}」、付録B の日足のトレンドは「{daily}」"]
    return []


def _nested(text: str) -> list[tuple[int, int]]:
    """Spans of full-width brackets nested two deep or more."""
    spans, depth, start = [], 0, 0
    for i, ch in enumerate(text):
        if ch == "（":
            depth += 1
            if depth == 2:
                start = i
        elif ch == "）" and depth:
            if depth == 2:
                spans.append((start, i + 1))
            depth -= 1
        elif ch in "\n":
            depth = 0
    return spans


def wording(page: str) -> list[str]:
    text = P.visible_text(page)
    out = []
    for name, pattern in _WORDS.items():
        hits = list(pattern.finditer(text))
        for m in hits[:EXAMPLES]:
            out.append(f"作る側の言葉（{name}）: …{_context(text, m.start(), m.end())}…")
    repeats = []
    blocks = html.unescape(P._TAGS.sub("\n", page))  # one line per element: a repeat stays inside its sentence
    for line in blocks.splitlines():
        segments = [s.strip() for s in _SEGMENT.findall(line)]
        repeats += [a for a, b in zip(segments, segments[1:]) if a == b and len(a) >= REPEAT_MIN]
    out += [f"同じ文の繰り返し: {s}" for s in repeats[:EXAMPLES]]
    nested = _nested(blocks)  # per element: one bracket left open does not carry over the rest of the page
    if nested:
        examples = "／".join(blocks[a:b] for a, b in nested[:EXAMPLES])
        out.append(f"2重の括弧が {len(nested)} か所（例: {examples}）")
    return out


def check(page: str, facts: dict) -> list[str]:
    return verdict_words(facts) + take_profits(facts) + trend(facts) + wording(page)
