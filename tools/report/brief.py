"""Render {week}_brief.md (everything the writer reads, in one file) and the outlook.md skeleton."""
from __future__ import annotations

import datetime as dt
from string import Template

import mdparse as M
from charts import fmt
from facts import MARKET_LABEL
from state import Paths

DOC_SECTION_CHARS = 900
DOC_KEYWORDS = ("決定事項", "主要な施策", "リスク", "前回")
REVIEW_MAX, REVIEW_CHARS = 30, 160
OUTLOOK_EVENT_DAYS, OUTLOOK_EVENT_MAX = 28, 14
TREND_POINTS = 6


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


def kpi_rows(facts: dict) -> list[list[object]]:
    rows = []
    for k in facts["kpis"]:
        rng = (f"{fmt(k['high_1y'][1], k['decimals'])}（{k['high_1y'][0]}）/ "
               f"{fmt(k['low_1y'][1], k['decimals'])}（{k['low_1y'][0]}）") if k["high_1y"] else M.DASH
        rows.append([k["label"], k["date"] or M.DASH, f"{fmt(k['value'], k['decimals'])} {k['unit']}",
                     change_text(k, "1w"), change_text(k, "1m"), change_text(k, "1y"), rng, k["source"]])
    return rows


def indicator_rows(rows: list[dict]) -> list[list[object]]:
    out = []
    for r in rows:
        d = r["decimals"]
        out.append([r["group"], r["name"], r["date"] or M.DASH, fmt(r["value"], d),
                    f"{fmt(r['prev'], d)}（{r['prev_date'] or M.DASH}）",
                    f"{fmt(r['year'], d)}（{r['year_date'] or M.DASH}）", r["unit"]])
    return out


def trend_rows(facts: dict) -> list[list[object]]:
    out = []
    for chart in facts["charts"]:
        for s in chart["series"]:
            pts = s["points"][-TREND_POINTS:]
            if pts:
                out.append([chart["title"], s["label"], " → ".join(f"{d[2:]} {fmt(v, 2)}" for d, v in pts)])
    return out


def doc_digest(paths: Paths, doc: dict) -> str:
    head = (f"### {MARKET_LABEL.get(doc['market'], '')}｜{doc['title']}（公表日 {doc['date']}）\n\n"
            f"要旨ファイル: {doc['path']}\n")
    target = paths.root / doc["path"] if doc["path"] else None
    if not target or not target.is_file():
        return head + "\n（要旨ファイルが無い）\n"
    text = target.read_text(encoding="utf-8")
    summary = M.section_by_title(text, "要旨")
    parts = [f"**要旨**: {clip(summary[1], DOC_SECTION_CHARS)}" if summary
             else f"**内容**: {clip(M.section(text, '1.'), DOC_SECTION_CHARS)}"]
    for keyword in DOC_KEYWORDS:
        found = M.section_by_title(text, keyword)
        if found and not M.is_blank(found[1]):
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
        "変化は株価・為替が騰落率（%）、金利・スプレッド・VIX は差（ポイント）。",
        "",
        table(["指標", "時点", "値", "1週", "1か月", "1年", "1年の高値 / 安値", "出典"], kpi_rows(facts)),
    ]
    for number, market in (("2", "japan"), ("3", "us")):
        lines += ["", f"## {number}. マクロ指標・需給（{MARKET_LABEL[market]}）", "",
                  table(["区分", "指標", "時点", "値", "前回（時点）", "1年前（時点）", "単位"],
                        indicator_rows(facts["indicators"][market]))]
    lines += ["", "## 4. 時系列の推移（チャートの直近6点。日次系列は週末値）", "",
              table(["チャート", "系列", "推移"], trend_rows(facts)),
              "", "## 5. 今後12週の日程", "",
              table(["日付", "市場", "イベント", "内容", "種別", "確度"], event_rows(facts["events"])),
              "", "## 6. 直近の政治・政策の動き", "",
              table(["日付", "市場", "出来事", "内容", "種別", "確度"], event_rows(facts["politics"])),
              "", "## 7. スクリプトで取得できない市場指標（web 検索）", "",
              table(["市場", "指標", "値", "時点", "確度"],
                    [[MARKET_LABEL.get(e["market"], ""), e["indicator"], e["value"], e["date"], e["certainty"]]
                     for e in facts["extras"]]),
              "", "## 8. 政策文書（監視項目ごとの最新版）の要点", ""]
    lines += [doc_digest(paths, d) for d in facts["docs"]] or ["（文書なし）", ""]
    lines += ["## 9. データの欠損・要確認事項", "",
              "### 取得できなかった系列", "",
              table(["市場", "指標", "理由"],
                    [[MARKET_LABEL.get(f["market"], ""), f["name"], f["reason"]] for f in facts["series_failed"]]),
              "", f"### 収集時の要確認事項（status.md の 7. から {min(len(review), REVIEW_MAX)}/{len(review)} 件）", "",
              table(["ファイル", "内容"], [[r["file"], clip(r["content"], REVIEW_CHARS)] for r in review[:REVIEW_MAX]]),
              "", "## 10. 前回の判断", ""]
    if prev:
        lines.append(f"- {prev['week']} 週（{prev['path']}）: 日本 {prev.get('japan', M.DASH)} / "
                     f"米国 {prev.get('us', M.DASH)}")
    else:
        lines.append("- 前回の outlook.md なし（初回）")
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
    if facts["review_items"]:
        items.append(f"- 収集時の要確認事項 {len(facts['review_items'])} 件（brief.md の 9.）")
    return "\n".join(items) or "- なし"


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
    }
    return Template(template).safe_substitute(values)
