"""Backtest of the viewpoint scoring: replay every past Friday with only the data published by then.

For each Friday the collected series are cut at "published by that day" (the point's date plus the
catalog's release lag), then the same code as the weekly report scores the four viewpoints
(facts.build_kpis / build_indicators, derived.build_derived, scoring.score_market, hysteresis
carried week to week). The index return over the next 4 / 13 / 26 weeks and the worst drawdown
over 13 weeks are grouped by the candidate judgement, by viewpoint rating and by signal score.

Searched values (forward P/E, AAII) have no history, so ④ runs without them; flows and CFTC
cover only what was collected. The result says so. Output: market/report/backtest/{date}_backtest.md/.json
"""
from __future__ import annotations

import bisect
import datetime as dt
import statistics

import derived as D
import facts as F
import scoring as SC
from state import Paths

# days from the stored date (the period's first day for monthly / quarterly) to publication.
# Japan's monthly releases (CI ~65-70, unemployment ~61, CPI ~54 days) come later than the US (CPI, payrolls
# within ~45); quarterly GDP and the Tankan come after the quarter ends. A catalog entry can set
# "release_lag_days" to override.
LAG_DAYS = {("japan", "monthly"): 70, ("us", "monthly"): 45, ("japan", "quarterly"): 135, ("us", "quarterly"): 120,
            "daily": 0, "weekly": 7}
HORIZONS = (4, 13, 26)        # weeks
MDD_WEEKS = 13
MAIN_HORIZON = 13
MIN_WEEKS_FOR_FLAG = 20
INDEX = {"japan": ("JP_NIKKEI225", "日経平均"), "us": ("US_SP500", "S&P500")}
JUDGEMENT_ORDER = ("強気", "中立", "慎重", "弱気")
Points = list[tuple[str, float]]


def fridays(start: str, end: str) -> list[str]:
    day = dt.date.fromisoformat(start)
    day += dt.timedelta(days=(4 - day.weekday()) % 7)
    last = dt.date.fromisoformat(end)
    out = []
    while day <= last:
        out.append(day.isoformat())
        day += dt.timedelta(days=7)
    return out


def lag_days(entry: dict) -> int:
    if "release_lag_days" in entry:
        return int(entry["release_lag_days"])
    freq = entry.get("frequency", "monthly")
    return int(LAG_DAYS.get(freq, LAG_DAYS.get((entry.get("market", "japan"), freq), 70)))


def cut(points: Points, dates: list[str], until: str) -> Points:
    """points with date <= until (dates is the presorted date column of points)."""
    return points[:bisect.bisect_right(dates, until)]


class Published:
    """Series sliced to what was public on a given day, without re-scanning every point each week.
    Transforms (year-on-year, differences) use only earlier points, so they are computed once."""

    def __init__(self, catalogs: dict[str, dict], raw: dict[str, Points], transformed: dict[str, Points]):
        self.catalogs = catalogs
        self.raw, self.transformed = raw, transformed
        self.raw_dates = {k: [d for d, _ in v] for k, v in raw.items()}
        self.tr_dates = {k: [d for d, _ in v] for k, v in transformed.items()}

    def at(self, asof: str) -> tuple[dict[str, Points], dict[str, Points]]:
        raw, tr = {}, {}
        for sid in self.raw:
            limit = D.shifted(asof, lag_days(self.catalogs.get(sid, {})))
            raw[sid] = cut(self.raw[sid], self.raw_dates[sid], limit)
            tr[sid] = cut(self.transformed.get(sid, []), self.tr_dates.get(sid, []), limit)
        return raw, tr


def forward(points: Points, dates: list[str], asof: str) -> dict:
    """Index return after asof over each horizon, and the worst drawdown over MDD_WEEKS (None past the data)."""
    i = bisect.bisect_right(dates, asof) - 1
    if i < 0:
        return {}
    base = points[i][1]
    out = {}
    for weeks in HORIZONS:
        target = (dt.date.fromisoformat(asof) + dt.timedelta(weeks=weeks)).isoformat()
        if target > dates[-1]:
            out[f"r{weeks}"] = None
            continue
        j = bisect.bisect_right(dates, target) - 1
        out[f"r{weeks}"] = (points[j][1] / base - 1) * 100
    end = (dt.date.fromisoformat(asof) + dt.timedelta(weeks=MDD_WEEKS)).isoformat()
    if end <= dates[-1]:
        window = points[i:bisect.bisect_right(dates, end)]
        out["mdd"] = (min(v for _, v in window) / base - 1) * 100
    else:
        out["mdd"] = None
    return out


def score_week(published: Published, asof: str, previous: dict[str, dict | None]) -> dict[str, dict]:
    raw, tr = published.at(asof)
    catalogs = published.catalogs
    kpis = F.build_kpis(catalogs, raw)
    indicators = F.build_indicators(catalogs, raw, asof)
    stale = frozenset(r["id"] for rows in indicators.values() for r in rows if r["stale"])
    derived = D.build_derived(tr, [], asof, stale)
    data = SC.Inputs({k["id"]: k for k in kpis if k["id"] not in stale}, {d["id"]: d for d in derived},
                     {sid: pts for sid, pts in tr.items() if sid not in stale and pts}, asof=asof)
    return {m: SC.score_market(m, data, previous.get(m)) for m in INDEX}


def replay(paths: Paths, years: int, today: str) -> list[dict]:
    catalogs, raw = F.load_catalogs(paths), F.load_series(paths)
    transformed = {sid: F.transformed_points(pts, catalogs.get(sid, {}).get("transform", "level"))
                   for sid, pts in raw.items()}
    published = Published(catalogs, raw, transformed)
    index_dates = {m: [d for d, _ in raw.get(sid, [])] for m, (sid, _) in INDEX.items()}
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=round(365.25 * years))).isoformat()
    previous: dict[str, dict | None] = {m: None for m in INDEX}
    weeks = []
    for asof in fridays(start, today):
        scores = score_week(published, asof, previous)
        previous = {m: {v["key"]: v["rating"] for v in s["viewpoints"]} for m, s in scores.items()}
        row = {"asof": asof}
        for m, (sid, _) in INDEX.items():
            s = scores[m]
            row[m] = {"candidate": s["candidate"], "ratings": previous[m],
                      "signals": {sig["name"]: sig["score"] for v in s["viewpoints"] for sig in v["signals"]
                                  if sig["available"]},
                      "forward": forward(raw.get(sid, []), index_dates[m], asof) if index_dates[m] else {}}
        weeks.append(row)
    return weeks


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {"n": len(values), "mean": statistics.fmean(values), "median": statistics.median(values),
            "down": sum(1 for v in values if v < 0) / len(values) * 100}


def summarize(weeks: list[dict]) -> dict:
    out = {}
    key = f"r{MAIN_HORIZON}"
    for m in INDEX:
        rows = [w[m] for w in weeks if w[m]["forward"]]
        by_judgement = {}
        for j in JUDGEMENT_ORDER:
            picked = [r for r in rows if r["candidate"] == j]
            by_judgement[j] = {f"r{h}": _stats([r["forward"][f"r{h}"] for r in picked
                                                if r["forward"].get(f"r{h}") is not None]) for h in HORIZONS}
            mdd = [r["forward"]["mdd"] for r in picked if r["forward"].get("mdd") is not None]
            by_judgement[j]["mdd"] = statistics.fmean(mdd) if mdd else None
        by_view = {k: {rating: _stats([r["forward"][key] for r in rows if r["ratings"].get(k) == rating
                                       and r["forward"].get(key) is not None]) for rating in SC.RATINGS}
                   for k, _ in SC.VIEWPOINTS}
        names = sorted({n for r in rows for n in r["signals"]})
        by_signal = {n: {score: _stats([r["forward"][key] for r in rows if r["signals"].get(n) == score
                                        and r["forward"].get(key) is not None]) for score in (-1, 0, 1)}
                     for n in names}
        base = _stats([r["forward"][key] for r in rows if r["forward"].get(key) is not None])
        out[m] = {"weeks": len(rows), "all": base, "by_judgement": by_judgement, "by_viewpoint": by_view,
                  "by_signal": by_signal, "coverage": {n: sum(1 for r in rows if n in r["signals"]) for n in names}}
    return out


def inverted(summary: dict) -> list[str]:
    """Signals whose −1 weeks were followed by a higher mean 13-week return than their +1 weeks."""
    flags = []
    for m, s in summary.items():
        for name, by in s["by_signal"].items():
            neg, pos = by[-1], by[1]
            if neg["n"] >= MIN_WEEKS_FOR_FLAG and pos["n"] >= MIN_WEEKS_FOR_FLAG and neg["mean"] > pos["mean"]:
                flags.append(f"{F.MARKET_LABEL[m]}: {name}（−1 のあと {_f(neg['mean'])} / +1 のあと {_f(pos['mean'])}）")
    return flags


def _f(value: float | None, unit: str = "%") -> str:
    return "—" if value is None else f"{value:+.1f}{unit}".replace("-", "−")


def _judgement_row(j: str, b: dict) -> str:
    r13 = b["r13"]
    if not r13["n"]:
        return f"| {j} | 0 | — | — | — | — | — | — |"
    return (f"| {j} | {r13['n']} | {_f(b['r4'].get('mean'))} | {_f(r13.get('mean'))} | {_f(r13.get('median'))} | "
            f"{r13.get('down', 0):.0f}% | {_f(b['r26'].get('mean'))} | {_f(b['mdd'])} |")


def render(summary: dict, years: int, today: str, weeks: list[dict]) -> str:
    span = f"{weeks[0]['asof']} 〜 {weeks[-1]['asof']}" if weeks else "—"
    lines = [f"# 観点の評価のバックテスト — {today}", "",
             f"**期間**: 過去 {years} 年（毎週金曜、{span}、{len(weeks)} 週）",
             "**方法**: 各金曜までに公表済みのデータ（日次 0日・週次 7日、月次は日本 70日・米国 45日、"
             "四半期は日本 135日・米国 120日の遅れを、期間の初日から仮定）だけで、"
             "週次レポートと同じコードで観点の評価の候補を出し直し、その後の指数の騰落率を集計した。",
             "", "> market_report.py backtest が生成する。手で編集しない。過去の結果は将来を保証しない。", "",
             "## 限界", "",
             "- 予想PER・AAII（web 検索の値）には過去分が無く、④ はそれらを除いて評価した",
             "- 投資部門別売買と CFTC は収集した期間の分だけ。それ以前の週はその信号が欠けている",
             "- 公表の遅れは頻度ごとの目安で、実際の公表日とは違う",
             "- 統計は今の改定後の値を使っている（雇用者数・CPI・GDP の速報値とは違う）",
             f"- {MAIN_HORIZON}週後の騰落率は毎週計算するため期間が重なり、週数ほど独立した標本は無い"
             "（向きが逆の信号の判定は弱い証拠）",
             "- 最初の数週はヒステリシスの前週の評価が無い",
             "- 指数の騰落率は配当を含まない", "",
             f"## 向きが逆の信号（−1 の週のほうが +1 の週よりその後の{MAIN_HORIZON}週の騰落率が高い。各{MIN_WEEKS_FOR_FLAG}週以上）", ""]
    lines += [f"- {f}" for f in inverted(summary)] or ["- なし"]
    for m, (_, index_name) in INDEX.items():
        s = summary[m]
        lines += ["", f"## {F.MARKET_LABEL[m]}（{index_name}、{s['weeks']} 週）", "",
                  f"全期間の{MAIN_HORIZON}週後の騰落率: 平均 {_f(s['all'].get('mean'))}・下落した割合 "
                  f"{s['all'].get('down', 0):.0f}%", "",
                  "### 総合判断の候補ごと", "",
                  "| 候補 | 週数 | 4週後 平均 | 13週後 平均 | 13週後 中央値 | 13週後 下落の割合 | 26週後 平均 | 13週の最大下落 平均 |",
                  "|---|---|---|---|---|---|---|---|"]
        lines += [_judgement_row(j, s["by_judgement"][j]) for j in JUDGEMENT_ORDER]
        lines += ["", f"### 観点の評価ごと（{MAIN_HORIZON}週後の平均）", "", "| 観点 | 追い風 | 中立 | 逆風 |",
                  "|---|---|---|---|"]
        for k, name in SC.VIEWPOINTS:
            cells = [f"{_f(st.get('mean'))}（{st['n']}週）" for st in (s["by_viewpoint"][k][r] for r in SC.RATINGS)]
            lines.append(f"| {name} | {' | '.join(cells)} |")
        lines += ["", f"### 信号ごと（{MAIN_HORIZON}週後の平均。かっこは週数）", "",
                  "| 信号 | −1 | 0 | +1 | 取れた週 |", "|---|---|---|---|---|"]
        for name, by in s["by_signal"].items():
            cells = [f"{_f(by[sc].get('mean'))}（{by[sc]['n']}）" for sc in (-1, 0, 1)]
            lines.append(f"| {name} | {' | '.join(cells)} | {s['coverage'][name]} |")
    return "\n".join(lines) + "\n"
