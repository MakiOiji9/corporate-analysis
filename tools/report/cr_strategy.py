"""投資判断と行動計画: what an investor could do with the verdicts, as conditions and guides (never a recommendation
or a forecast). Every number comes from facts.json; the words are fixed templates.

  scenarios()      弱気・基本・強気 prices from the valuation band (cr_dashboard.fair_rows): the median low edge, the
                   median of each indicator's centre (the fair-PBR price for PBR) and the median high edge
  action()         the long horizon's verdict × where the price sits against the band -> a stance, buying in three
                   parts (a third each) when it is 投資検討, price alerts and the one-step movers otherwise
  sizing()         a conditional cap per stock: 0 / 小 (≤2%) / 中 (≤5%) / 大 (≤8%) of a portfolio, from conviction
                   (the long verdict, STEP 1・2 grades, warnings) and one step down on large daily moves
                   (ATR over VOLATILE_ATR of the price, or beta over VOLATILE_BETA)
  short_plan()     短期: the short verdict, entries and exits at the chart's prices (cr_scenarios, as in chapter 07)
  mid_plan()       中期: the mid verdict × the valuation band, take profit at its high edge, review on weak progress
  long_plan()      長期: action() plus the 3- and 5-year levels (cr_projection): take part at the base case's 3-year
                   level, review the rest above the bull case's 5-year level or when EPS grows slower than the bear case
  monitors()       what to watch: the next results' progress, the largest threat, the top buying factor, ROIC
  catalysts()      the next results and the market calendar of the weekly outlook
  legend_actions() what each investor's way of thinking would do, and how the three views split
"""
from __future__ import annotations

from statistics import median

import charts as C
import cr_dashboard as DB
import cr_judge as J
import cr_notes as N
import cr_projection as PJ
from cr_html import badge, bullet_list, esc
from slides import table

CAPS = {"0": "0%（今は持たない）", "小": "ポートフォリオの 2% まで", "中": "ポートフォリオの 5% まで",
        "大": "ポートフォリオの 8% まで"}
LEVELS = ("0", "小", "中", "大")
VOLATILE_ATR, VOLATILE_BETA = 0.03, 1.5
STEP_DOWN, DEEP_DOWN = 0.93, 0.86  # buying steps when there is no support below the price
SIZING_NOTE = ("1銘柄に入れる金額の上限の目安。確信度（判定・STEP 1・2・注意点）と値動きの大きさから3段階で示す。"
               "資産の状況や他の保有銘柄によって変わる一般的な目安。")
LEGEND_ACTIONS = {
    "buffett": {"好む": "長く持つ前提で、株価が目安の帯の下限 {low} 近くまで下がるのを待って買う",
                "保留": "事業の強さが数字で確かめられ、株価が {low} 以下になれば検討する",
                "避ける": "事業の強さか財務が条件を満たさないので、手を出さない"},
    "soros": {"好む": "流れに乗って買い、26週線を割ったら手じまう",
              "保留": "流れがはっきりするまで待つ（26週線を上回り、地合いが落ち着くか）",
              "避ける": "流れに逆らわない。下げ止まりが確かめられるまで手を出さない"},
    "rogers": {"好む": "長く安く放置されている今のうちに少しずつ買い、人気が戻るまで持つ",
               "保留": "安値圏が続くか、事業の変化の兆しが出るまで待つ",
               "避ける": "人気が過熱しているので、熱が冷めるまで手を出さない"},
}


def _yen(value: float | None, currency: str) -> str:
    return f"{C.fmt(value, 0)}{currency}"


def _price(facts: dict) -> tuple[float | None, str]:
    p = facts.get("price") or {}
    return p.get("value"), p.get("currency") or ""


def _band(facts: dict) -> tuple[list[dict], dict | None]:
    rows = DB.fair_rows(facts)
    return rows, DB.fair_band(rows, _price(facts)[0])


def _bear_line(bear: float) -> str:
    if bear == 0:
        return "決算ごとの EPS が前の年を下回る（悲観ケースの横ばいより悪い）年が続いたら、保有の理由を見直す"
    if bear < 0:
        return f"決算ごとの EPS の減り方が悲観ケースの年 {bear:.1f}% より大きい年が続いたら、保有の理由を見直す"
    return f"決算ごとの EPS の伸びが悲観ケースの年 {bear:.1f}% を下回り続けたら、保有の理由を見直す"


# ---------------------------------------------------------------- scenarios

FALL = 0.9  # the bear case when the price is already below the band: at least a tenth lower


def _lower_floor(facts: dict, price: float) -> float:
    """The lowest of the chart's stop, the 52-week low and a tenth below the price, among those under the price."""
    prices = facts.get("prices") or {}
    stop = (((prices.get("technicals") or {}).get("levels") or {}).get("stop") or {}).get("price")
    week = next((w.get("low") for w in prices.get("ranges") or [] if w.get("label") == "52週"), None)
    return min(p for p in (stop, week, price * FALL) if p is not None and p < price)


def _fair(row: dict) -> float:
    """A band's fair price: PEG 1 for PEG (改定 3), the fair PBR for PBR, else the middle of the band."""
    for key in ("fair", "mid"):
        if row.get(key) is not None:
            return row[key]
    return (row["low"] + row["high"]) / 2


def scenarios(facts: dict) -> dict | None:
    rows, band = _band(facts)
    price, _ = _price(facts)
    if not band:
        return None
    used = [r for r in rows if not r.get("alt")]
    mids = [(r["label"].split("（", 1)[0], _fair(r)) for r in used]
    base = median(m for _, m in mids)
    base_reading = ("指標ごとの目安の株価の中央値（PER は帯の中央・PBR は適正PBR・PEG は 1倍の株価。" + "・".join(f"{name} {m:,.0f}" for name, m in mids)
                    + f" → {base:,.0f}）")
    bear, bear_reading = band["low"], "指標が割安と見る水準まで評価が下がった場合"
    if price and price < band["low"]:  # already cheaper than the band: the bear case is a further fall
        bear, bear_reading = _lower_floor(facts, price), "割安なまま評価が戻らず、さらに下がった場合（損切りの目安・52週安値・1割安の低い方）"
    out = []
    for name, value, reading in (("弱気", bear, bear_reading),
                                 ("基本", base, base_reading),
                                 ("強気", band["high"], "指標が割高と見る水準まで評価が上がった場合")):
        out.append({"name": name, "price": value, "reading": reading,
                    "change": (value / price - 1) * 100 if price else None})
    return {"rows": out, "band": band}


# ---------------------------------------------------------------- action

def _supports_below(facts: dict, price: float) -> list[float]:
    levels = ((facts.get("prices") or {}).get("technicals") or {}).get("levels") or {}
    return sorted((s["price"] for s in levels.get("supports") or [] if s.get("price") and s["price"] < price),
                  reverse=True)


def _three_parts(facts: dict, price: float, band: dict, base: float) -> list[float]:
    if band["position"] == DB.ABOVE:  # the base can sit outside the median edges in odd data: keep the order
        return sorted({band["high"], min(max(base, band["low"]), band["high"]), band["low"]}, reverse=True)
    supports = _supports_below(facts, price)
    second = supports[0] if supports else price * STEP_DOWN
    lower = [p for p in supports[1:] + ([band["low"]] if band["low"] < second else []) if p < second]
    return [price, second, max(lower) if lower else price * DEEP_DOWN]


def action(facts: dict) -> dict:
    price, currency = _price(facts)
    s = scenarios(facts)
    long = facts["horizons"]["long"]["verdict"]
    position = s["band"]["position"] if s and price else None
    alerts = [f"株価が {_yen(s['band']['low'], currency)} 以下になれば、指標の上で割安側に入る"] if s else []
    if long == J.CONSIDER and s and price:
        stance = {DB.BELOW: "分割で買い始める", DB.INSIDE: "押し目を待って分割で買う",
                  DB.ABOVE: "下がるのを待つ"}[position]
        parts = _three_parts(facts, price, s["band"], s["rows"][1]["price"])
        steps = [f"{i}回目（3分の1）: {_yen(p, currency)}{'（今の株価）' if p == price else ''}"
                 for i, p in enumerate(parts, start=1)]
        return {"stance": stance, "steps": steps, "alerts": alerts if position == DB.ABOVE else []}
    if long == J.WATCH:
        stance = "条件がそろうのを待つ" if position == DB.BELOW else "価格と条件の両方を待つ"
        # the single-step movers are rows of the 判断が変わる条件 table (conditions_html): not repeated here
        return {"stance": stance, "steps": [], "alerts": [] if position == DB.BELOW else alerts}
    if long == J.PASS:
        return {"stance": "今は買わない", "steps": [], "alerts": []}
    return {"stance": "判断の材料がそろうのを待つ", "steps": [], "alerts": alerts}


# ---------------------------------------------------------------- sizing

def _volatile(facts: dict) -> str | None:
    t = (facts.get("prices") or {}).get("technicals") or {}
    atr, current = (t.get("levels") or {}).get("atr"), t.get("current")
    beta = ((facts.get("moves") or {}).get("split") or {}).get("beta")
    if atr and current and atr / current > VOLATILE_ATR:
        return f"1日の値動きが大きい（平均の値幅が株価の {atr / current * 100:.1f}%）"
    if beta is not None and beta > VOLATILE_BETA:
        return f"市場より値動きが大きい（β {beta:.2f}）"
    return None


def sizing(facts: dict) -> dict:
    long = facts["horizons"]["long"]
    s1, s2 = facts.get("step1") or {}, facts.get("step2") or {}
    if s2.get("flags"):
        return {"level": "0", "cap": CAPS["0"], "why": ["深刻な赤信号がある"]}
    if long["verdict"] in (J.PASS, J.PENDING):
        return {"level": "0", "cap": CAPS["0"], "why": [f"長期の判定が{long['verdict']}"]}
    points, why = 0, []
    if long["verdict"] == J.CONSIDER:
        points, why = 2, ["長期の判定が投資検討"]
    elif (long.get("score") or 0) > 0:
        points, why = 1, ["長期はウォッチだが点数はプラス"]
    for grade, name in ((s1.get("grade"), "STEP 1（事業）"), (s2.get("grade"), "STEP 2（財務）")):
        if grade == "A":
            points, why = points + 1, why + [f"{name}が A"]
        elif grade == "C":
            points, why = points - 1, why + [f"{name}が C"]
    if s2.get("cautions"):
        points, why = points - 1, why + ["注意点がある（" + "、".join(s2["cautions"])[:60] + "）"]
    level = "大" if points >= 4 else "中" if points >= 2 else "小" if points >= 1 else "0"
    volatile = _volatile(facts)
    if volatile and level != "0":
        level = LEVELS[LEVELS.index(level) - 1]
        why.append(f"{volatile}ため1段下げた")
    return {"level": level, "cap": CAPS[level], "why": why}


# ---------------------------------------------------------------- plans by horizon

BREAKS = "この章の頭の「判断が変わる条件」に当たれば、持ち続ける理由を見直す"
SHORT_STANCE = {J.CONSIDER: "押し目で買い、上の抵抗線で利益を確定する短い売買を考えられる",
                J.WATCH: "短期の材料（株価の流れ・地合い・決算の進み具合）がそろうまで様子を見る",
                J.PASS: "短期では手を出さない", J.PENDING: "判断の材料がそろうのを待つ"}
MID_PROGRESS = "次の決算で営業利益の進み具合が前年同期の 90% 未満なら、持ち続ける理由を見直す"


def _verdict(facts: dict, key: str) -> str:
    return (facts["horizons"].get(key) or {}).get("verdict") or J.PENDING


def _technical_levels(facts: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """(entries, takes, exits) as {label, price}: cr_scenarios' prices (the same as chapter 07), else the raw lines."""
    s = facts.get("scenarios") or {}
    if s.get("ok"):
        holder = s.get("holder") or {}
        return ([{"label": b["basis"], "price": b["price"]} for b in s["buys"][:2]],
                holder.get("take") or [], holder.get("exit") or [])
    levels = ((facts.get("prices") or {}).get("technicals") or {}).get("levels") or {}
    stop = levels.get("stop") or {}
    return ([{"label": x.get("label") or "支持線", "price": x["price"]} for x in (levels.get("supports") or [])[:2]],
            [{"label": x.get("label") or "抵抗線", "price": x["price"]} for x in (levels.get("resistances") or [])[:1]],
            [{"label": "損切りの目安", "price": stop["price"]}] if stop.get("price") else [])


def short_plan(facts: dict) -> dict:
    _, currency = _price(facts)
    verdict = _verdict(facts, "short")
    entries, takes, exits = _technical_levels(facts)
    buy = [f"{_yen(e['price'], currency)}（{e['label']}）" for e in entries] if verdict in (J.CONSIDER, J.WATCH) else []
    out = [f"{_yen(t['price'], currency)}（{t['label']}）付近で利益確定を考える" for t in takes[:1]]
    out += [f"{_yen(x['price'], currency)}（{x['label']}）を下回ったら損切りを考える" for x in exits[:1]]
    return {"key": "short", "verdict": verdict, "stance": SHORT_STANCE[verdict], "entries": buy,
            "exits": out or ["チャートの目安が計算できない（株価のデータが足りない）"]}


def _mid_stance(verdict: str, position: str | None) -> str:
    if verdict == J.CONSIDER:
        return {DB.BELOW: "指標の割安側にあり、買いを考えられる", DB.INSIDE: "目安の帯の下側まで下がるのを待って買う",
                DB.ABOVE: "下がるのを待つ"}.get(position, "株価の指標がそろうのを待つ")
    if verdict == J.WATCH:
        return "次の決算の進み具合と株価の位置を確かめてから考える"
    return "今は買わない" if verdict == J.PASS else "判断の材料がそろうのを待つ"


def mid_plan(facts: dict) -> dict:
    price, currency = _price(facts)
    verdict = _verdict(facts, "mid")
    s = scenarios(facts)
    band = (s or {}).get("band") or {}
    entries = ([f"{_yen(band['low'], currency)} 以下で指標の割安側に入る"]
               if s and verdict in (J.CONSIDER, J.WATCH) else [])
    exits = ([f"{_yen(band['high'], currency)}（強気シナリオ・指標が割高と見る水準）に届いたら一部の利益確定を考える"]
             if s else [])
    return {"key": "mid", "verdict": verdict, "stance": _mid_stance(verdict, band.get("position") if price else None),
            "entries": entries, "exits": exits + [MID_PROGRESS]}


def long_plan(facts: dict) -> dict:
    price, currency = _price(facts)
    a = action(facts)
    p = facts.get("projection") or PJ.build(facts)
    notes = []
    if p.get("ok"):
        base3, bull5 = PJ.level(p, "基本", 3), PJ.level(p, "楽観", 5)
        exits = [f"基本ケースの3年後の水準 {_yen(base3, currency)} に届いたら一部の利益確定を考える"
                 "（3年より早く届くほど、業績より先に株価の評価が上がっている）",
                 f"楽観ケースの5年後の水準 {_yen(bull5, currency)} を超えたら、残りも持ち続ける理由を見直す",
                 _bear_line(PJ.rate(p, '悲観'))]
        if price and price >= base3:
            notes.append("今の株価はすでに基本ケースの3年後の水準を上回っている（成長を先取りした株価）")
    else:
        s = scenarios(facts)
        exits = ([f"{_yen(s['band']['high'], currency)} 以上（指標が割高と見る水準）では一部の利益確定を考える"]
                 if s else [])
        notes.append(f"3年後・5年後の水準は出していない: {p.get('reason')}")
    return {"key": "long", "verdict": _verdict(facts, "long"), "stance": a["stance"], "entries": a["steps"],
            "alerts": a["alerts"], "exits": exits + [BREAKS], "notes": notes, "projection": p}


def plans(facts: dict) -> list[dict]:
    return [short_plan(facts), mid_plan(facts), long_plan(facts)]


# ---------------------------------------------------------------- monitors, catalysts


def monitors(facts: dict, breaks: list[str]) -> list[str]:
    a = facts["analyses"]
    out = []
    progress = ((a.get("growth") or {}).get("detail") or {}).get("progress") or {}
    if progress.get("quarter"):
        out.append("次の決算の営業利益の進み具合（前年同期の 110% 以上なら上向き、90% 未満なら下向き）")
    threat = ((a.get("swot") or {}).get("detail") or {}).get("top_threat") or {}
    if threat.get("fact"):
        out.append(f"最大の脅威の行方: {threat['fact']}")
    kbf = ((a.get("three_c") or {}).get("detail") or {}).get("top_kbf")
    if kbf:
        out.append(f"顧客が最も重視する点（{kbf}）で、競合より優れていると示す数字が出てくるか")
    returns = ((a.get("moat") or {}).get("detail") or {}).get("returns") or {}
    rows = [r for r in returns.get("rows") or [] if r.get("roic") is not None]
    if rows and returns.get("hurdle") is not None:
        out.append(f"ROIC（直近 {rows[-1]['roic']:.1f}%）が資本コスト {returns['hurdle']:.0f}% を上回り続けるか")
    return out + list(breaks)


# ---------------------------------------------------------------- 判断が変わる条件 (one table, 5.5)

PERIOD_WORDS = {"short": "短期", "mid": "中期", "long": "長期"}
CHECK_WHEN = {  # when the factor's material is renewed (the analyses' validity, CLAUDE.md)
    "market": "毎週の地合いレポート", "trend_daily": "日々の終値", "price": "日々の終値", "progress": "次の決算短信",
    "valuation": "株価の更新・本決算", "growth": "次の決算短信", "safety": "次の決算短信",
    "profitability": "中間・本決算", "cash_flow": "中間・本決算", "five_forces": "新しい有報・中期経営計画",
    "three_c": "新しい有報・中期経営計画", "moat": "新しい有報・中期経営計画", "swot": "新しい有報・中期経営計画"}
BREAK_RESULT = {"改善": "判定が上がりうる（改善の条件）", "悪化": "持ち続ける理由を見直す（悪化の条件）",
                "株価": "STEP 3 の判定が変わる"}
MONITOR_RESULT = "点数の外で見る（変化があれば分析を作り直す）"


def _first_sentence(text: str) -> str:
    """Up to the first 「。」 outside brackets ('なし（超過収益は強い。…）' stays whole)."""
    depth = 0
    for i, ch in enumerate(text):
        depth += {"（": 1, "）": -1}.get(ch, 0)
        if ch == "。" and depth == 0:
            return text[:i]
    return text


def _mover_rows(facts: dict) -> list[dict]:
    """判定を動かす要因 of every horizon; the same condition in several horizons is one row."""
    rows: dict[str, dict] = {}
    for key in ("short", "mid", "long"):
        h = facts["horizons"].get(key) or {}
        for m in (h.get("sensitivity") or {}).get("movers") or []:
            text = J.mover_text(m, h.get("rows") or [])
            condition = text[: -len(m["verdict"])] if text.endswith(m["verdict"]) else text
            row = next((r for r in h.get("rows") or [] if r["key"] == m["key"]), {})
            now = _first_sentence(row.get("value") or "—")  # the state word, not the evidence behind it
            entry = rows.setdefault(condition, {"condition": condition, "now": now,
                                                "results": [], "when": CHECK_WHEN.get(m["key"], "—")})
            entry["results"].append(f"{PERIOD_WORDS[key]}が{m['verdict']}")
    return [{**r, "result": "・".join(r.pop("results"))} for r in rows.values()]


def _split_now(condition: str) -> tuple[str, str]:
    """'営業利益率が同業の中央値を上回る（2026-03 は 18.3%、中央値 21.2%）' -> the condition and its value in brackets."""
    if not condition.endswith("）"):
        return condition, "—"
    depth = 0
    for i in range(len(condition) - 1, -1, -1):
        depth += {"）": 1, "（": -1}.get(condition[i], 0)
        if depth == 0:
            return condition[:i], condition[i + 1:-1]
    return condition, "—"


def _break_rows(breaks: list[str]) -> list[dict]:
    out = []
    for line in breaks:
        text = line.strip().lstrip("-").strip()
        kind = next((w for w in BREAK_RESULT if text.startswith(f"【{w}】")), None)
        condition = text[len(kind) + 2:] if kind else text
        if "の判定: " in condition:  # a horizon's single-step mover: already a row of _mover_rows
            continue
        when = "株価" if condition.endswith("株価で確認") else "次の決算短信" if "決算短信" in condition else "—"
        for tail in ("。次の決算短信で確認", "。株価で確認"):
            condition = condition.removesuffix(tail)
        condition, now = _split_now(condition)
        out.append({"condition": condition, "now": now, "result": BREAK_RESULT.get(kind, "見直す"), "when": when})
    return out


def _monitor_rows(facts: dict) -> list[dict]:
    when = {"次の決算": "次の決算短信", "最大の脅威": "決算説明会・有報", "顧客が最も重視": "新しい有報・中期経営計画",
            "ROIC": "本決算（有報）"}
    return [{"condition": m, "now": "—", "result": MONITOR_RESULT,
             "when": next((w for k, w in when.items() if m.startswith(k) or k in m[:12]), "—")}
            for m in monitors(facts, [])]


def conditions(facts: dict, breaks: list[str]) -> list[dict]:
    """判断が変わる条件: the single-step movers of the three horizons, the writer's 判断が崩れる条件 and the
    things to watch, as {condition, now, result, when} (docs/proposals/company-report-review-feedback.md 5.5)."""
    return _mover_rows(facts) + _break_rows(breaks) + _monitor_rows(facts)


def conditions_html(facts: dict, breaks: list[str]) -> str:
    rows = [[esc(r["condition"]), esc(r["now"]), esc(r["result"]), esc(r["when"])] for r in conditions(facts, breaks)]
    if not rows:
        return ""
    return ("<h3>判断が変わる条件</h3><p class=\"small\">点数の上で1段変わると判定が変わる要素、数字で見る悪化・改善の条件、"
            "点数の外で見ておく項目を1つの表にまとめた。</p>"
            + table(["条件", "今の値", "変わったときの判定", "確かめる時期"], rows))


def catalysts(facts: dict) -> list[str]:
    out = [f"{facts.get('review')}（次の決算。判定を見直す）"] if facts.get("review") else []
    rows = (facts.get("outlook") or {}).get("rows") or {}
    out += [f"{rows[p]['watch']}（地合いの{p}の注目点）" for p in ("短期", "中期") if (rows.get(p) or {}).get("watch")]
    return out


def legend_actions(facts: dict) -> dict:
    s = scenarios(facts)
    _, currency = _price(facts)
    low = _yen(s["band"]["low"], currency) if s else "目安の帯の下限"
    found = facts.get("legends") or {}
    actions = {k: LEGEND_ACTIONS[k][v["verdict"]].format(low=low)
               for k, v in found.items() if v.get("verdict") in LEGEND_ACTIONS.get(k, {})}
    counts = [sum(1 for v in found.values() if v.get("verdict") == w) for w in ("好む", "保留", "避ける")]
    return {"actions": actions, "split": f"好む {counts[0]}・保留 {counts[1]}・避ける {counts[2]}"}


# ---------------------------------------------------------------- html

def _scenario_table(s: dict, currency: str) -> str:
    rows = [[f"<b>{esc(r['name'])}</b>", f"<b>{esc(_yen(r['price'], currency))}</b>",
             esc("—" if r["change"] is None else f"{C.fmt(r['change'], 1, True)}%"), esc(r["reading"])]
            for r in s["rows"]]
    return table(["シナリオ", "株価の目安", "今の株価から", "前提"], rows, right=frozenset({1, 2}))


HORIZON_TITLES = {"short": "短期（〜3ヶ月）", "mid": "中期（6ヶ月〜1年）", "long": "長期（3年以上）"}
HORIZON_LEADS = {"short": "チャートの支持線・抵抗線で入り、出る。価格は下の「チャートから見た買いの候補の価格」と同じ。",
                 "mid": "指標の割安・割高の帯と、次の決算の進み具合で判断する。",
                 "long": "事業と成長が続く前提で持ち、成長の前提で描いた3年後・5年後の水準を売りの目安にする。"}


def action_card(facts: dict) -> str:
    """The short version for the first screen: the stance of each horizon, the sizing cap and the next review."""
    z = sizing(facts)
    lines = "".join(f'<span class="hz">{esc(HORIZON_TITLES[p["key"]][:2])}: <b>{esc(p["stance"])}</b></span>'
                    for p in plans(facts))
    return (f'<div class="action"><div><span class="k">今の行動の目安</span>{lines}</div>'
            f'<div><span class="k">1銘柄の配分の目安</span><b>{esc(z["cap"])}</b></div>'
            f'<div><span class="k">次に見直す日</span><span class="rv">{esc(facts.get("review") or "—")}</span></div>'
            '<a href="#thesis">行動計画を見る</a></div>')


def _projection_table(p: dict, currency: str) -> str:
    def cell(case: str, years: int) -> str:
        r = next(x for x in p["rows"] if x["case"] == case and x["years"] == years)
        tail = "" if r["annual"] is None else f'<br><span class="small muted">今から年 {C.fmt(r["annual"], 1, True)}%</span>'
        return f"<b>{esc(_yen(r['price'], currency))}</b>{tail}"
    rows = [[f"<b>{esc(c['name'])}</b>", esc(f"{c['rate']:.1f}%"), *(cell(c["name"], n) for n in p["years"]),
             f'<span class="small">{esc(c["basis"])}</span>'] for c in p["cases"]]
    return table(["ケース", "EPS の伸び（年）", *(f"{n}年後の水準" for n in p["years"]), "成長率の根拠"], rows,
                 right=frozenset({1, 2, 3}))


def _plan_block(plan: dict, facts: dict, currency: str) -> str:
    key = plan["key"]
    out = (f'<div class="hplan"><h4>{esc(HORIZON_TITLES[key])} {badge(plan["verdict"])}</h4>'
           f'<p class="small muted">{esc(HORIZON_LEADS[key])}</p><p>今の行動の目安: <b>{esc(plan["stance"])}</b></p>')
    if key == "mid":
        s = scenarios(facts)
        out += (_scenario_table(s, currency) + '<p class="small muted">指標の割安・割高の境目から計算した'
                f"{N.PRICE}。</p>") if s else '<p class="muted">株価の指標が足りず、目安の帯を計算できない。</p>'
    if key == "long":
        p = plan["projection"]
        if p.get("ok"):
            out += (f"<p>EPS {esc(C.fmt(p['eps0'], 1))}{esc(currency)} × {esc(p['per_basis'])} "
                    f"{esc(C.fmt(p['per'], 1))}倍 を起点に、成長が続いた場合の水準</p>"
                    + _projection_table(p, currency) + f'<p class="small muted">{esc(p["note"])}。</p>')
    if plan["entries"]:
        head = "分けて買う場合の価格の目安" if key == "long" else "買いを考える価格"
        if plan["verdict"] != J.CONSIDER:  # a ウォッチ lists the prices for when its conditions are met, not for now
            head = f"条件がそろったときに{head}（今の判定は{plan['verdict']}）"
        out += f"<h5>{esc(head)}</h5>" + bullet_list(plan["entries"])
    if plan.get("alerts"):
        out += "<h5>判断を変える条件（価格・事業）</h5>" + bullet_list(plan["alerts"])
    out += "<h5>売り・見直しの目安</h5>" + bullet_list(plan["exits"])
    if plan.get("notes"):
        out += bullet_list(plan["notes"])
    return out + "</div>"


def html(facts: dict, breaks: list[str]) -> str:
    _, currency = _price(facts)
    z = sizing(facts)
    out = "<h3>期間別の行動計画</h3>" + "".join(_plan_block(p, facts, currency) for p in plans(facts))
    out += (f"<h3>配分の目安: {esc(z['cap'])}</h3>" + bullet_list(z["why"])
            + f'<p class="small muted">{esc(SIZING_NOTE)}</p>')
    out += "<h3>近い予定</h3>" + bullet_list(catalysts(facts))
    return out


def legend_summary(facts: dict) -> str:
    out = legend_actions(facts)
    return f'<p><b>3人の見方の割れ方</b>: {esc(out["split"])}</p>' if out["actions"] else ""
