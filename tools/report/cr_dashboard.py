"""The report's first screen beyond the three verdict cards: the nine analyses at a glance, the fair-value range
(a football field of the valuation indicators against the current price) and a few key figures.

  analysis_strip()  one coloured cell per analysis (良い/中間/悪い/保留 from cr_judge.SCORE), linking to its chapter
  fair_rows()       the price ranges the valuation already computed: PER (過去5年レンジの割安圏〜割高圏の境目),
                    PBR (適正PBR −20%〜+20%, with the fair price as the middle tick), PEG (1倍〜2倍 = price ÷ PEG ×1・×2)
                    and, for reference, the 52-week low〜high
  fair_band()       the median low and median high of the valuation rows: the band the indicators point to, and
                    where the current price sits against it. A position, not a target price.
  key_figures()     ROE・営業利益率・自己資本比率・売上 CAGR・予想PER, skipping the unknown ones
"""
from __future__ import annotations

from statistics import median

import charts as C
import cr_judge as J
from cr_html import esc, figure

STRIP = (("five_forces", "業界の魅力度", "step1"), ("three_c", "勝てる理由", "step1"), ("moat", "モート", "step1"),
         ("swot", "SWOT", "step1"), ("profitability", "収益性", "step2"), ("growth", "成長性", "step2"),
         ("safety", "安全性", "step2"), ("cash_flow", "キャッシュフロー", "step2"), ("valuation", "株価の割安さ", "step3"))
FAIR_NOTE = ("帯は各指標で「割安」と「割高」の境目になる株価。縦線が今の株価、帯の中の短い線は適正PBR の株価。"
             "左にあるほど割安側。株価の予想や目標株価ではない。")
INSIDE, BELOW, ABOVE = "帯の中", "下限より下", "上限より上"


def tone(word: str | None) -> str:
    score = J.score_of(word) if word and word != J.PENDING else None
    if score is None:
        return "v-pending"
    return "v-consider" if score > 0 else "v-pass" if score < 0 else "v-watch"


def analysis_strip(facts: dict) -> str:
    cells = ""
    for key, label, anchor in STRIP:
        verdict = (facts["analyses"].get(key) or {}).get("verdict")
        cells += (f'<a class="cell {tone(verdict)}" href="#{anchor}"><span class="k">{esc(label)}</span>'
                  f'<span class="v">{esc(verdict or "未実施")}</span></a>')
    return f'<div class="strip" aria-label="9つの分析の結論">{cells}</div>'


def _valuation(facts: dict) -> dict:
    return (facts["analyses"].get("valuation") or {}).get("detail") or {}


def fair_rows(facts: dict) -> list[dict]:
    detail = _valuation(facts)
    flips = detail.get("flip_values") or {}
    price = (facts.get("price") or {}).get("value")
    rows = []
    if flips.get("per_cheap") is not None and flips.get("per_rich") is not None:
        rows.append({"label": "PER（過去5年の位置）", "low": flips["per_cheap"], "high": flips["per_rich"],
                     "note": "割安圏〜割高圏の境目"})
    if flips.get("pbr_cheap") is not None and flips.get("pbr_rich") is not None:
        rows.append({"label": "PBR（適正PBR ±20%）", "low": flips["pbr_cheap"], "high": flips["pbr_rich"],
                     "mid": flips.get("pbr_fair"), "note": "適正PBR の株価を中心に ±20%"})
    peg = detail.get("peg_standard")
    if peg and peg > 0 and price:
        rows.append({"label": "PEG（1倍〜2倍）", "low": price / peg, "high": 2 * price / peg,
                     "note": "成長率に見合う株価（PEG 1倍）から2倍まで"})
    week = next((w for w in (facts.get("prices") or {}).get("ranges") or [] if w.get("label") == "52週"), None)
    if week and week.get("low") is not None and week.get("high") is not None:
        rows.append({"label": "52週の安値〜高値", "low": week["low"], "high": week["high"], "alt": True,
                     "note": "参考: 実際の値動きの幅"})
    return [r for r in rows if 0 < r["low"] <= r["high"]]  # a price band below zero (a loss) is not a price


def fair_band(rows: list[dict], price: float | None) -> dict | None:
    used = [r for r in rows if not r.get("alt")]
    if not used:
        return None
    low, high = median(r["low"] for r in used), median(r["high"] for r in used)
    position = None
    if price:
        position = BELOW if price < low else ABOVE if price > high else INSIDE
    return {"low": low, "high": high, "count": len(used), "position": position}


def _band_text(band: dict, price: float | None, currency: str) -> str:
    text = (f"{band['count']}つの指標の境目の中央値で見ると、割安と割高の間は {C.fmt(band['low'], 0)}〜"
            f"{C.fmt(band['high'], 0)}{currency}")
    if not price or not band["position"]:
        return text + "。"
    reading = {INSIDE: "その間（妥当な水準）にある", BELOW: "下限より下（割安側）にある", ABOVE: "上限より上（割高側）にある"}
    return text + f"。今の株価 {C.fmt(price, 0)}{currency} は{reading[band['position']]}。"


def fair_value(facts: dict) -> str:
    rows = fair_rows(facts)
    if not rows:
        return ""
    price = (facts.get("price") or {}).get("value")
    currency = (facts.get("price") or {}).get("currency") or ""
    band = fair_band(rows, price)
    lead = f'<p class="fair-text">{esc(_band_text(band, price, currency))}</p>' if band else ""
    chart = C.range_chart(rows, price, "株価の目安の帯（指標ごと）")
    return lead + figure("株価の目安の帯（指標ごと）", chart, "バリュエーション分析・日々の株価", currency, FAIR_NOTE)


def _pct(value: float | None) -> str | None:
    return None if value is None else f"{value:.1f}%"


def key_figures(facts: dict) -> list[dict]:
    a = facts["analyses"]
    prof = (a.get("profitability") or {}).get("detail") or {}
    safety = (a.get("safety") or {}).get("detail") or {}
    growth = (a.get("growth") or {}).get("detail") or {}
    equity = next((i.get("value") for i in safety.get("items") or [] if i.get("name") == "自己資本比率"), None)
    per = _valuation(facts).get("per_forecast")
    tiles = [("ROE（平均）", _pct(prof.get("roe_average")), "株主のお金でどれだけ稼いだか"),
             ("営業利益率", _pct((prof.get("margin") or {}).get("self")), "売上のうち本業の利益の割合"),
             ("自己資本比率", _pct(equity), "借金に頼らない度合い"),
             ("売上の伸び（年率）", _pct((growth.get("cagr") or {}).get("sales")), "売上の年平均の成長率"),
             ("予想PER", None if per is None else f"{per:.1f}倍", "株価が今期の予想利益の何倍か")]
    return [{"name": n, "value": v, "note": note} for n, v, note in tiles if v is not None]


def key_figures_html(facts: dict) -> str:
    tiles = key_figures(facts)
    if not tiles:
        return ""
    return '<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="k">{esc(t["name"])}</div><div class="v">{esc(t["value"])}</div>'
        f'<div class="n">{esc(t["note"])}</div></div>' for t in tiles) + "</div>"
