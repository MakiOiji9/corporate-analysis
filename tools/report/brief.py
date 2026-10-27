"""Render {week}_brief.md (everything the writer reads, in one file) and the outlook.md skeleton."""
from __future__ import annotations

import datetime as dt
import re
from string import Template

import mdparse as M
import scoring as SC
from charts import fmt
from facts import MARKET_LABEL, period_label, streak
from state import Paths

DOC_SECTION_CHARS = 700
DOC_SUMMARY_CHARS = 350        # documents published before the recent window: summary only
DOC_KEYWORDS = ("決定事項", "主要な施策", "リスク", "前回")
DOC_RECENT_DAYS = 35           # first report (no previous week): documents this recent get the full digest
EMPTY_PREVIOUS = "前回版なし"
REVIEW_MAX, REVIEW_CHARS = 30, 160
OUTLOOK_EVENT_DAYS, OUTLOOK_EVENT_MAX = 28, 14
TREND_POINTS = 6
STALE_MARK = "（古い）"
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def cell(value: object) -> str:
    text = str(value if value is not None else "").replace("|", "／").replace("\n", " ").strip()
    return text or M.DASH


def row(cells: list[object]) -> str:
    return "| " + " | ".join(cell(c) for c in cells) + " |"


def table(header: list[str], rows: list[list[object]]) -> str:
    lines = [row(header), "|" + "---|" * len(header)]
    lines += [row(r) for r in rows] if rows else [row([M.DASH] * len(header))]
    return "\n".join(lines)


def clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + "…（以下略。全文は要旨ファイル）"


def change_text(kpi: dict, key: str) -> str:
    ch = kpi["changes"].get(key)
    if not ch:
        return M.DASH
    if kpi["change"] == "pct":
        return f"{fmt(ch['delta'], 1, signed=True)}%"
    return fmt(ch["delta"], max(kpi["decimals"], 2), signed=True)


def from_high_text(kpi: dict) -> str:
    if kpi.get("from_high") is None:
        return M.DASH
    if kpi["change"] == "pct":
        return f"{fmt(kpi['from_high'], 1, signed=True)}%"
    return fmt(kpi["from_high"], max(kpi["decimals"], 2), signed=True)


def streak_text(run: int, unit: str) -> str:
    if abs(run) < 2:
        return M.DASH
    return f"{abs(run)}{unit}連続{'上昇' if run > 0 else '低下'}"


def kpi_rows(facts: dict) -> list[list[object]]:
    rows = []
    for k in facts["kpis"]:
        rng = (f"{fmt(k['high_1y'][1], k['decimals'])}（{k['high_1y'][0]}）/ "
               f"{fmt(k['low_1y'][1], k['decimals'])}（{k['low_1y'][0]}）") if k["high_1y"] else M.DASH
        rows.append([k["label"], k["date"] or M.DASH, f"{fmt(k['value'], k['decimals'])} {k['unit']}",
                     change_text(k, "1w"), change_text(k, "1m"), change_text(k, "1y"), rng,
                     from_high_text(k), streak_text(k.get("streak", 0), "週"), k["source"]])
    return rows


def date_text(r: dict) -> str:
    shown = period_label(r["date"], r.get("frequency", "daily"))
    return f"{shown}{STALE_MARK}" if shown and r.get("stale") else (shown or M.DASH)


def indicator_rows(rows: list[dict]) -> list[list[object]]:
    out = []
    for r in rows:
        d, freq = r["decimals"], r.get("frequency", "daily")
        out.append([r["group"], r["name"], date_text(r), fmt(r["value"], d),
                    f"{fmt(r['prev'], d)}（{period_label(r['prev_date'], freq) or M.DASH}）",
                    f"{fmt(r['year'], d)}（{period_label(r['year_date'], freq) or M.DASH}）", r["unit"], r["source"]])
    return out


def extra_rows(facts: dict) -> list[list[object]]:
    return [[MARKET_LABEL.get(e["market"], ""), e["indicator"], e["value"], e.get("note") or M.DASH,
             f"{e['date']}{STALE_MARK}" if e.get("stale") else e["date"], e["certainty"], e["source"]]
            for e in facts["extras"]]


def derived_rows(facts: dict) -> list[list[object]]:
    rows = []
    for d in facts.get("derived", []):
        inputs = "、".join(f"{i['id']} {fmt(i['value'], 2)}（{i['date'] or M.DASH}）" for i in d["inputs"])
        note = "時点が古く評価に使わない" if d["stale"] else ("入力が無い" if d["value"] is None else M.DASH)
        signed = not d["id"].endswith("_PCTL")  # a position in the distribution has no direction
        rows.append([MARKET_LABEL.get(d["market"], ""), d["label"], d["date"] or M.DASH,
                     f"{fmt(d['value'], d['decimals'], signed=signed)} {d['unit']}" if d["value"] is not None else M.DASH,
                     d["formula"], inputs or M.DASH, note])
    return rows


def score_lines(facts: dict) -> list[str]:
    lines = [f"信号は −1 / 0 / +1。観点の合計が −{SC.THRESHOLD} 以下で逆風、+{SC.THRESHOLD} 以上で追い風、"
             "それ以外は中立。前週が逆風（追い風）の観点は、合計が 0 に戻るまで逆風（追い風）を保つ。"
             "取れない信号は 0 点（推測しない）。総合判断の候補は判断基準の表をスクリプトが当てはめた結果。", ""]
    for market, label in (("japan", "日本"), ("us", "米国")):
        score = facts.get("scores", {}).get(market)
        if not score:
            continue
        rows = [[v["name"], s["name"], s["value"], s["rule"].replace("-", "−"),
                 f"{s['score']:+d}".replace("-", "−") if s["score"] else "0"]
                for v in score["viewpoints"] for s in v["signals"]]
        lines += [f"### 12.{1 if market == 'japan' else 2} {label}（総合判断の候補: {score['candidate']}）", "",
                  table(["観点", "信号", "見たもの", "規則", "点数"], rows), ""]
        for v in score["viewpoints"]:
            held = "。前週の評価を保った（ヒステリシス）" if v["held"] else ""
            prev = f"、前週 {v['previous']}" if v["previous"] else ""
            gaps = f"。未取得: {'、'.join(v['missing'])}" if v["missing"] else ""
            lines.append(f"- {v['name']}: 合計 {v['total']:+d} → 候補 **{v['rating']}**{prev}{held}{gaps}"
                         .replace("合計 -", "合計 −"))
        lines.append("")
    return lines


def check_rows(facts: dict) -> list[list[object]]:
    return [[MARKET_LABEL.get(c["market"], ""), c["item"], c["detail"]]
            for c in facts.get("moved", []) + facts.get("checks", [])]


def trend_rows(facts: dict) -> list[list[object]]:
    out = []
    for chart in facts["charts"]:
        for s in chart["series"]:
            pts = s["points"][-TREND_POINTS:]
            if pts:
                out.append([chart["title"], s["label"], " → ".join(f"{d[2:]} {fmt(v, 2)}" for d, v in pts),
                            streak_text(streak(s["points"]), "回")])
    return out


def stale_rows(facts: dict) -> list[list[object]]:
    return [[MARKET_LABEL.get(m, ""), r["name"], r["date"]]
            for m, rows in facts["indicators"].items() for r in rows if r.get("stale")]


def unconfirmed_rows(facts: dict) -> list[list[object]]:
    rows = [[MARKET_LABEL.get(u["market"], ""), f"動き: {u['event']}", f"{u['date']} {u['detail']}"]
            for u in facts.get("unconfirmed", [])]
    return rows + [[MARKET_LABEL.get(e["market"], ""), f"指標: {e['indicator']}", e.get("note") or M.DASH]
                   for e in facts["extras"] if M.is_blank(e["value"])]


def recent_cutoff(facts: dict) -> str:
    """Documents published on or after this date get the full digest (new since the previous report)."""
    prev = facts.get("previous") or {}
    if prev.get("week"):
        return prev["week"]
    return (dt.date.fromisoformat(facts["week"]) - dt.timedelta(days=DOC_RECENT_DAYS)).isoformat()


def is_empty_section(body: str) -> bool:
    return M.is_blank(body) or (EMPTY_PREVIOUS in body and len(body.strip()) <= len(EMPTY_PREVIOUS) + 6)


def doc_digest(paths: Paths, doc: dict, cutoff: str) -> str:
    recent = bool(ISO_DATE.match(doc["date"] or "")) and doc["date"] >= cutoff
    label = "直近の公表" if recent else "要旨のみ"
    head = (f"### {MARKET_LABEL.get(doc['market'], '')}｜{doc['title']}（公表日 {doc['date']}・{label}）\n\n"
            f"要旨ファイル: {doc['path']}\n")
    target = paths.root / doc["path"] if doc["path"] else None
    if not target or not target.is_file():
        return head + "\n（要旨ファイルが無い）\n"
    text = target.read_text(encoding="utf-8")
    limit = DOC_SECTION_CHARS if recent else DOC_SUMMARY_CHARS
    summary = M.section_by_title(text, "要旨")
    parts = [f"**要旨**: {clip(summary[1], limit)}" if summary
             else f"**内容**: {clip(M.section(text, '1.'), limit)}"]
    for keyword in DOC_KEYWORDS if recent else ():
        found = M.section_by_title(text, keyword)
        if found and not is_empty_section(found[1]):
            parts.append(f"**{found[0]}**: {clip(found[1], DOC_SECTION_CHARS)}")
    return head + "\n" + "\n\n".join(parts) + "\n"


def event_rows(events: list[dict]) -> list[list[object]]:
    return [[e["date"], MARKET_LABEL.get(e["market"], ""), e["event"], e["detail"], e["kind"], e["certainty"]]
            for e in events]


def render_brief(paths: Paths, facts: dict) -> str:
    prev = facts.get("previous") or {}
    review = facts["review_items"]
    lines = [
        f"# 地合いレポートの材料 — {facts['week']} 週",
        "",
        f"**作成日**: {facts['generated']}",
        f"**材料**: 収集セッション {facts['session']}（market/LATEST.md）、market/data/*.csv、market/policy/*/raw/",
        "",
        "> market_report.py prepare が生成する。手で編集しない。outlook.md はこのファイルだけを根拠に書く。",
        "> 値は収集データの転記と単純計算（変化幅・前年比）だけ。—は未取得。",
        "",
        "## 1. 主要指標（ダッシュボード）",
        "",
        "変化は株価・為替が騰落率（%）、金利・スプレッド・VIX は差（ポイント）。1年高値比も同じ単位。"
        "連続は週末値の連続上昇・低下（2週以上）。",
        "",
        table(["指標", "時点", "値", "1週", "1か月", "1年", "1年の高値 / 安値", "1年高値比", "連続", "出典"],
              kpi_rows(facts)),
    ]
    for number, market in (("2", "japan"), ("3", "us")):
        lines += ["", f"## {number}. マクロ指標・需給（{MARKET_LABEL[market]}）", "",
                  f"時点に{STALE_MARK}が付いた指標は、通常の公表の遅れより古い（足元の判断に使わない）。", "",
                  table(["区分", "指標", "時点", "値", "前回（時点）", "1年前（時点）", "単位", "出典"],
                        indicator_rows(facts["indicators"][market]))]
    lines += ["", "## 4. 時系列の推移（チャートの直近6点。日次系列は週末値）", "",
              "連続はチャートの点（週末値・月次値）の連続上昇・低下（2回以上）。", "",
              table(["チャート", "系列", "推移", "連続"], trend_rows(facts)),
              "", "## 5. 今後12週の日程", "",
              table(["日付", "市場", "イベント", "内容", "種別", "確度"], event_rows(facts["events"])),
              "", "## 6. 直近の政治・政策の動き（日付を確認できたもの）", "",
              table(["日付", "市場", "出来事", "内容", "種別", "確度"], event_rows(facts["politics"])),
              "", "## 7. スクリプトで取得できない市場指標（web 検索）", "",
              table(["市場", "指標", "値", "注記", "時点", "確度", "出典"], extra_rows(facts)),
              "", "## 8. 政策文書（監視項目ごとの最新版）の要点", "",
              f"{recent_cutoff(facts)} 以降の公表は要点まで、それより前は要旨だけ（全文は要旨ファイル）。", ""]
    cutoff = recent_cutoff(facts)
    lines += [doc_digest(paths, d, cutoff) for d in facts["docs"]] or ["（文書なし）", ""]
    lines += ["## 9. データの欠損・要確認事項", "",
              "### 取得できなかった系列", "",
              table(["市場", "指標", "理由"],
                    [[MARKET_LABEL.get(f["market"], ""), f["name"], f["reason"]] for f in facts["series_failed"]]),
              "", "### 時点が古い指標", "",
              table(["市場", "指標", "時点"], stale_rows(facts)),
              "", "### 確認できなかった動き・指標（web 検索）", "",
              table(["市場", "項目", "理由・内容"], unconfirmed_rows(facts)),
              "", f"### 収集時の要確認事項（status.md の 7. から {min(len(review), REVIEW_MAX)}/{len(review)} 件）", "",
              table(["ファイル", "内容"], [[r["file"], clip(r["content"], REVIEW_CHARS)] for r in review[:REVIEW_MAX]]),
              "", "## 10. 前回の判断", ""]
    if prev:
        lines.append(f"- {prev['week']} 週（{prev['path']}）: 日本 {prev.get('japan', M.DASH)} / "
                     f"米国 {prev.get('us', M.DASH)}")
    else:
        lines.append("- 前回の outlook.md なし（初回）")
    lines += ["", "## 11. 計算した指標（スクリプトが計算。outlook.md にはこの値を転記する）", "",
              table(["市場", "指標", "時点", "値", "計算式", "入力", "注記"], derived_rows(facts)),
              "", "## 12. 観点の評価候補", ""]
    lines += score_lines(facts)
    lines += ["## 13. 前週との食い違い・データの点検（要確認）", "",
              table(["市場", "項目", "内容"], check_rows(facts)),
              "", "## 14. 値動きの材料と市場予想（web 検索）", "",
              "値動きの理由として書いてよいのは、14.1 の行（確度が一次・二次）にある報道の記述だけ。検索要約の行は"
              "「〜と報じられた（検索要約）」と書き、断定しない。", "",
              "### 14.1 値動きの主な材料（報道）", "",
              table(["市場", "日付", "市場の動き", "報道された材料", "出典", "確度"],
                    [[MARKET_LABEL.get(d["market"], ""), d.get("日付"), d.get("市場の動き"), d.get("報道された材料"),
                      d.get("出典"), d.get("確度")] for d in facts.get("drivers", [])]),
              "", "### 14.2 主要統計の市場予想と会合の織り込み", "",
              table(["市場", "イベント", "日付", "市場予想", "前回", "出典", "確度"],
                    [[MARKET_LABEL.get(c["market"], ""), c.get("イベント"), c.get("日付"), c.get("市場予想"),
                      c.get("前回"), c.get("出典"), c.get("確度")] for c in facts.get("consensus", [])])]
    return "\n".join(lines) + "\n"


def outlook_event_rows(facts: dict) -> str:
    end = (dt.date.fromisoformat(facts["week"]) + dt.timedelta(days=OUTLOOK_EVENT_DAYS)).isoformat()
    picked = [e for e in facts["events"] if e["date"][:10] <= end][:OUTLOOK_EVENT_MAX]
    if not picked:
        return row([M.DASH, M.DASH, "今後4週に記録された日程なし", M.DASH])
    return "\n".join(f"| {cell(e['date'])} | {cell(MARKET_LABEL.get(e['market'], ''))} | {cell(e['event'])} "
                     f"| <!-- FILL:event-{i} --> |" for i, e in enumerate(picked, start=1))


def limits_bullets(facts: dict) -> str:
    items = [f"- 未取得の系列（{MARKET_LABEL.get(f['market'], '')}）: {f['name']} — {f['reason']}"
             for f in facts["series_failed"]]
    items += [f"- 主要指標が未取得: {k['label']}" for k in facts["kpis"] if k["value"] is None]
    stale = stale_rows(facts)
    if stale:
        items.append("- 時点が古い指標（足元の判断に使わない）: " + "、".join(f"{r[1]}（{r[2]}）" for r in stale))
    items += [f"- 確認できなかった（{r[0]}）: {r[1]}" for r in unconfirmed_rows(facts)]
    items += [f"- 要確認（{r[0]}）: {r[1]} — {r[2]}" for r in check_rows(facts)]
    if facts["review_items"]:
        items.append(f"- 収集時の要確認事項 {len(facts['review_items'])} 件（brief.md の 9.）")
    return "\n".join(items) or "- なし"


def viewpoint_rows(facts: dict) -> str:
    rows = []
    for market, label in (("japan", "日本"), ("us", "米国")):
        for v in facts.get("scores", {}).get(market, {}).get("viewpoints", []):
            total = f"{v['total']:+d}".replace("-", "−")
            rows.append(f"| {label} | {v['name']} | {v['rating']}（合計 {total}） | {v['rating']} "
                        f"| <!-- FILL:reason-{market}-{v['key']} 採用を変えたときだけ根拠（指標と時点、または文書名）。"
                        "変えなければ — --> |")
    return "\n".join(rows) or row([M.DASH] * 5)


def change_rows(facts: dict) -> str:
    periods = (facts.get("previous") or {}).get("periods") or {}
    rows = []
    for period, key in (("短期", "short"), ("中期", "mid"), ("長期", "long")):
        for market, label in (("japan", "日本"), ("us", "米国")):
            before = periods.get(period, {}).get(market)
            if before:
                rows.append(f"| {period} | {label} | {cell(before)} | <!-- FILL:change-{key}-{market} "
                            "4章の判断を前回から変えたら理由。変えなければ「変更なし」 --> |")
            else:
                rows.append(f"| {period} | {label} | {M.DASH} | 初回 |")
    return "\n".join(rows)


def _kpi(facts: dict, sid: str) -> dict:
    return next((k for k in facts["kpis"] if k["id"] == sid), {})


def _indicator(facts: dict, sid: str) -> dict:
    return next((r for rows in facts["indicators"].values() for r in rows if r["id"] == sid), {})


def _derived(facts: dict, did: str) -> dict:
    return next((d for d in facts.get("derived", []) if d["id"] == did), {})


def handoff_rows(facts: dict) -> str:
    """Section 10 of outlook.md (script-filled): the market context a company analysis quotes."""
    out = []

    def add(market: str, item: str, value: str, date: str | None, source: str) -> None:
        out.append(row([market, item, value, date or M.DASH, source]))

    for market, label, policy, ten, real, index in (
            ("japan", "日本", "JP_CALL", "JP_JGB10Y", "JP_REAL_POLICY", "JP_NIKKEI225"),
            ("us", "米国", "US_FFR_UPPER", "US_10Y", "US_REAL_POLICY", "US_SP500")):
        p = _indicator(facts, policy)
        add(label, "政策金利", f"{fmt(p.get('value'), 2)}%", p.get("date"), p.get("source", M.DASH))
        r = _derived(facts, real)
        add(label, "実質政策金利", f"{fmt(r.get('value'), 2, signed=True)}%", r.get("date"), r.get("formula", M.DASH))
        k = _kpi(facts, ten)
        add(label, "10年債利回り（1か月の変化）", f"{fmt(k.get('value'), 2)}%（{change_text(k, '1m') if k else M.DASH}）",
            k.get("date"), k.get("source", M.DASH))
        k = _kpi(facts, index)
        add(label, "株価指数（1か月・1年高値比）",
            f"{change_text(k, '1m') if k else M.DASH}・{from_high_text(k) if k else M.DASH}", k.get("date"),
            k.get("source", M.DASH))
    k = _kpi(facts, "JP_USDJPY")
    add("日米", "ドル円（1か月・1年）", f"{fmt(k.get('value'), 2)}円（{change_text(k, '1m') if k else M.DASH}・"
        f"{change_text(k, '1y') if k else M.DASH}）", k.get("date"), k.get("source", M.DASH))
    k = _kpi(facts, "US_HY_OAS")
    add("米国", "HYスプレッド（1か月の変化）", f"{fmt(k.get('value'), 2)}（{change_text(k, '1m') if k else M.DASH}）",
        k.get("date"), k.get("source", M.DASH))
    r = _indicator(facts, "US_REAL10Y")
    if r:
        add("米国", "実質10年金利（TIPS）", f"{fmt(r.get('value'), 2)}%", r.get("date"), r.get("source", M.DASH))
    k = _kpi(facts, "US_WTI")
    if k:
        add("日米", "WTI 原油（1か月・1年）", f"{fmt(k.get('value'), 2)}ドル（{change_text(k, '1m')}・"
            f"{change_text(k, '1y')}）", k.get("date"), k.get("source", M.DASH))
    return "\n".join(out)


def render_outlook(paths: Paths, facts: dict, template: str, today: str) -> str:
    week = facts["week"]
    prev = facts.get("previous") or {}
    values = {
        "week": week, "today": today, "session": facts["session"],
        "brief": paths.rel(paths.report_file(week, "brief.md")),
        "html": paths.rel(paths.report_file(week, "market-report.html")),
        "prev_week": prev.get("week", "なし"),
        "prev_japan": prev.get("japan", M.DASH), "prev_us": prev.get("us", M.DASH),
        "event_rows": outlook_event_rows(facts), "limits": limits_bullets(facts),
        "viewpoint_rows": viewpoint_rows(facts), "change_rows": change_rows(facts),
        "handoff_rows": handoff_rows(facts),
    }
    return Template(template).safe_substitute(values)
