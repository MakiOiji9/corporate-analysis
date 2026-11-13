"""投資判断と行動計画: what an investor could do with the verdicts, as conditions and guides (never a recommendation
or a forecast). Every number comes from facts.json; the words are fixed templates.

  scenarios()      弱気・基本・強気 prices from the valuation band (cr_dashboard.fair_rows): the median low edge, the
                   median of each indicator's centre (the fair-PBR price for PBR) and the median high edge
  action()         the long horizon's verdict × where the price sits against the band -> a stance, buying in three
                   parts (a third each) when it is 投資検討, price alerts and the one-step movers otherwise
  sizing()         a conditional cap per stock: 0 / 小 (≤2%) / 中 (≤5%) / 大 (≤8%) of a portfolio, from conviction
                   (the long verdict, STEP 1・2 grades, warnings) and one step down on large daily moves
                   (ATR over VOLATILE_ATR of the price, or beta over VOLATILE_BETA)
  holder()         for holders: add near the band's low edge, take profit near its high edge, exit at the stop
  monitors()       what to watch: the next results' progress, the largest threat, the top buying factor, ROIC
  catalysts()      the next results and the market calendar of the weekly outlook
  legend_actions() what each investor's way of thinking would do, and how the three views split
"""
from __future__ import annotations

from statistics import median

import charts as C
import cr_dashboard as DB
import cr_judge as J
from cr_html import badge, bullet_list, esc
from slides import table

CAPS = {"0": "0%（今は持たない）", "小": "ポートフォリオの 2% まで", "中": "ポートフォリオの 5% まで",
        "大": "ポートフォリオの 8% まで"}
LEVELS = ("0", "小", "中", "大")
VOLATILE_ATR, VOLATILE_BETA = 0.03, 1.5
STEP_DOWN, DEEP_DOWN = 0.93, 0.86  # buying steps when there is no support below the price
SIZING_NOTE = ("1銘柄に入れる金額の上限の目安。確信度（判定・STEP 1・2・注意点）と値動きの大きさから3段階で示す。"
               "資産の状況や他の保有銘柄によって変わる一般的な目安で、売買の推奨ではない。")
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


# ---------------------------------------------------------------- scenarios

FALL = 0.9  # the bear case when the price is already below the band: at least a tenth lower


def _lower_floor(facts: dict, price: float) -> float:
    """The lowest of the chart's stop, the 52-week low and a tenth below the price, among those under the price."""
    prices = facts.get("prices") or {}
    stop = (((prices.get("technicals") or {}).get("levels") or {}).get("stop") or {}).get("price")
    week = next((w.get("low") for w in prices.get("ranges") or [] if w.get("label") == "52週"), None)
    return min(p for p in (stop, week, price * FALL) if p is not None and p < price)


def scenarios(facts: dict) -> dict | None:
    rows, band = _band(facts)
    price, _ = _price(facts)
    if not band:
        return None
    used = [r for r in rows if not r.get("alt")]
    base = median(r["mid"] if r.get("mid") is not None else (r["low"] + r["high"]) / 2 for r in used)
    bear, bear_reading = band["low"], "指標が割安と見る水準まで評価が下がった場合"
    if price and price < band["low"]:  # already cheaper than the band: the bear case is a further fall
        bear, bear_reading = _lower_floor(facts, price), "割安なまま評価が戻らず、さらに下がった場合（損切りの目安・52週安値・1割安の低い方）"
    out = []
    for name, value, reading in (("弱気", bear, bear_reading),
                                 ("基本", base, "各指標の中心（適正）の水準"),
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


def _mover_lines(facts: dict) -> list[str]:
    out = []
    for key in ("long", "mid"):
        h = facts["horizons"].get(key) or {}
        for m in (h.get("sensitivity") or {}).get("movers") or []:
            if m["direction"] == "1段良くなれば":
                out.append(f"{'長期' if key == 'long' else '中期'}: {J.mover_text(m, h.get('rows') or [])}")
    return list(dict.fromkeys(out))[:4]


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
        return {"stance": stance, "steps": [], "alerts": ([] if position == DB.BELOW else alerts) + _mover_lines(facts)}
    if long == J.PASS:
        return {"stance": "今は買わない", "steps": [], "alerts": _mover_lines(facts)}
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


# ---------------------------------------------------------------- holders, monitors, catalysts

def holder(facts: dict) -> dict:
    s = scenarios(facts)
    _, currency = _price(facts)
    levels = ((facts.get("prices") or {}).get("technicals") or {}).get("levels") or {}
    stop = (levels.get("stop") or {}).get("price")
    return {"add": (f"{_yen(s['band']['low'], currency)} 近く（指標が割安と見る水準）まで下がり、事業の判定が変わらなければ"
                    "買い増しを考える") if s else "—",
            "take": (f"{_yen(s['band']['high'], currency)} 以上（指標が割高と見る水準）では一部の利益確定を考える"
                     if s else "—"),
            "exit": (f"{_yen(stop, currency)}（チャートの損切りの目安）を下回るか、上の「判断が崩れる条件」に当たれば"
                     "持ち続ける理由を見直す" if stop else "上の「判断が崩れる条件」に当たれば持ち続ける理由を見直す")}


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


def action_card(facts: dict) -> str:
    """The short version for the first screen: the stance, the sizing cap and the next review."""
    a, z = action(facts), sizing(facts)
    return (f'<div class="action"><div><span class="k">今の行動の目安</span><b>{esc(a["stance"])}</b></div>'
            f'<div><span class="k">1銘柄の配分の目安</span><b>{esc(z["cap"])}</b></div>'
            f'<div><span class="k">次に見直す日</span><span class="rv">{esc(facts.get("review") or "—")}</span></div>'
            '<a href="#thesis">行動計画を見る</a></div>')


def html(facts: dict, breaks: list[str]) -> str:
    _, currency = _price(facts)
    s, a, z, h = scenarios(facts), action(facts), sizing(facts), holder(facts)
    out = "<h3>3つのシナリオ（株価の目安）</h3>"
    out += (_scenario_table(s, currency) + '<p class="small muted">指標の割安・割高の境目から計算した目安で、'
            "株価の予想ではない。</p>") if s else '<p class="muted">株価の指標が足りず計算できない。</p>'
    long = facts["horizons"]["long"]
    out += (f'<h3>今の行動の目安</h3><p>長期の判定 {badge(long["verdict"])} × 株価の位置 '
            f'<b>{esc((s or {}).get("band", {}).get("position") or "—")}</b> → <b>{esc(a["stance"])}</b></p>')
    if a["steps"]:
        out += "<h4>分けて買う場合の価格の目安</h4>" + bullet_list(a["steps"])
    if a["alerts"]:
        out += "<h4>判断を変える条件（価格・事業）</h4>" + bullet_list(a["alerts"])
    out += (f"<h3>配分の目安: {esc(z['cap'])}</h3>" + bullet_list(z["why"])
            + f'<p class="small muted">{esc(SIZING_NOTE)}</p>')
    out += ("<h3>保有している場合</h3>" + table(["場面", "目安"], [["買い増し", esc(h["add"])], ["利益確定", esc(h["take"])],
                                                          ["見直し", esc(h["exit"])]]))
    out += "<h3>見ておく項目</h3>" + bullet_list(monitors(facts, breaks))
    out += "<h3>近い予定</h3>" + bullet_list(catalysts(facts))
    return out


def legend_summary(facts: dict) -> str:
    out = legend_actions(facts)
    return f'<p><b>3人の見方の割れ方</b>: {esc(out["split"])}</p>' if out["actions"] else ""
