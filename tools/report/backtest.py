"""Check that each axis means what its label says: replay past Fridays with only the data published by then.

For each Friday the collected series are cut at "published by that day" (the point's date plus the
catalog's release lag), then the same code as the weekly report rates the three axes and the attention
level (facts.build_kpis / build_indicators, derived.build_derived, scoring.score_market, hysteresis
carried week to week). What happened next is then compared label by label:

  市場のストレス / 注意の度合い -> realised volatility of the index over the next 13 weeks and the
                                 share of weeks followed by a drawdown of 10% or more
  金融環境                       -> change of the policy rate and the 10-year yield over the next 26 weeks
  景気                           -> change of the unemployment rate over the next 26 weeks

Every 4th Friday is counted (fewer overlapping windows), the first and second halves of the span are
checked separately, and a label order that holds in both halves is reported as 意味どおり. The index
return is shown as a reference only; forecasting it is not the purpose of the axes.
Output: market/report/backtest/{date}_backtest.md / .json
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
# Japan's monthly releases (CI ~65-70, unemployment ~61, CPI ~54 days) come later than most US ones (CPI,
# payrolls within ~45); quarterly GDP and the Tankan come after the quarter ends. Later US releases (core PCE
# ~60, retail sales and industrial production ~50) set "release_lag_days" in the catalog.
LAG_DAYS = {("japan", "monthly"): 70, ("us", "monthly"): 45, ("japan", "quarterly"): 135, ("us", "quarterly"): 120,
            "daily": 0, "weekly": 7}
INDEX = {"japan": ("JP_NIKKEI225", "日経平均"), "us": ("US_SP500", "S&P500")}
POLICY = {"japan": "JP_CALL", "us": "US_FFR_UPPER"}
TEN_YEAR = {"japan": "JP_JGB10Y", "us": "US_10Y"}
UNEMPLOYMENT = {"japan": "JP_UNEMP", "us": "US_UNRATE"}
VOL_WEEKS, MACRO_WEEKS, RETURN_WEEKS = 13, 26, 13
DRAWDOWN = -10.0          # % a drawdown counts as large
STRIDE = 4                # every 4th Friday
MIN_N = 5                 # a label needs this many sampled weeks to enter the order check
MEANS_OK, MEANS_WEAK, MEANS_REVERSED, MEANS_UNKNOWN = "意味どおり", "弱い", "逆", "判定できない"
# (what is checked, labels in the order the outcome should fall, outcome keys)
CHECKS = (
    ("stress", "市場のストレス", SC.AXIS_LABELS["stress"], ("vol", "dd")),
    ("attention", "注意の度合い", (SC.ALERT, SC.WATCH, SC.CALM), ("vol", "dd")),
    ("money", "金融環境", SC.AXIS_LABELS["money"], ("policy", "ten")),
    ("economy", "景気", SC.AXIS_LABELS["economy"], ("unemp",)),
)
OUTCOME_LABEL = {"vol": f"次の{VOL_WEEKS}週の実現変動率（年率%）", "dd": f"次の{VOL_WEEKS}週に{-DRAWDOWN:g}%以上下落した割合",
                 "policy": f"次の{MACRO_WEEKS}週の政策金利の変化（%pt）", "ten": f"次の{MACRO_WEEKS}週の10年債利回りの変化（%pt）",
                 "unemp": f"次の{MACRO_WEEKS}週の失業率の変化（%pt）", "ret": f"次の{RETURN_WEEKS}週の騰落率（%、参考）"}
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


# ---------------------------------------------------------------- outcomes (what happened next)

def _later(asof: str, weeks: int) -> str:
    return (dt.date.fromisoformat(asof) + dt.timedelta(weeks=weeks)).isoformat()


def window(points: Points, dates: list[str], start: str, end: str) -> Points:
    """Points from the last one on or before start through end ([] when the data stops before end)."""
    if not dates or end > dates[-1]:
        return []
    i = max(bisect.bisect_right(dates, start) - 1, 0)
    return points[i:bisect.bisect_right(dates, end)]


def vol_and_drawdown(points: Points, dates: list[str], asof: str) -> tuple[float | None, bool | None, float | None]:
    """(annualised realised volatility, drawdown ≤ DRAWDOWN reached, return) over the next VOL_WEEKS."""
    pts = window(points, dates, asof, _later(asof, VOL_WEEKS))
    if len(pts) < 10:
        return None, None, None
    changes = [(b / a - 1) * 100 for (_, a), (_, b) in zip(pts, pts[1:]) if a]
    vol = statistics.stdev(changes) * D.TRADING_DAYS ** 0.5 if len(changes) > 1 else None
    base = pts[0][1]
    return vol, (min(v for _, v in pts) / base - 1) * 100 <= DRAWDOWN, (pts[-1][1] / base - 1) * 100


def level_change(points: Points, dates: list[str], asof: str, weeks: int) -> float | None:
    """Level weeks after asof minus the level at asof (both read from the full, revised series)."""
    end = _later(asof, weeks)
    if not dates or end > dates[-1]:
        return None
    i, j = bisect.bisect_right(dates, asof) - 1, bisect.bisect_right(dates, end) - 1
    return points[j][1] - points[i][1] if i >= 0 else None


def outcomes(raw: dict[str, Points], dates: dict[str, list[str]], market: str, asof: str) -> dict:
    index = INDEX[market][0]
    vol, dd, ret = vol_and_drawdown(raw.get(index, []), dates.get(index, []), asof)
    out = {"vol": vol, "dd": None if dd is None else (100.0 if dd else 0.0), "ret": ret}
    for key, sid in (("policy", POLICY[market]), ("ten", TEN_YEAR[market]), ("unemp", UNEMPLOYMENT[market])):
        out[key] = level_change(raw.get(sid, []), dates.get(sid, []), asof, MACRO_WEEKS)
    return out


# ---------------------------------------------------------------- replay

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
    dates = published.raw_dates
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=round(365.25 * years))).isoformat()
    previous: dict[str, dict | None] = {m: None for m in INDEX}
    weeks = []
    for asof in fridays(start, today):
        scores = score_week(published, asof, previous)
        previous = {m: {a["key"]: a["rating"] for a in s["axes"]} for m, s in scores.items()}
        row = {"asof": asof}
        for m in INDEX:
            labels = dict(previous[m])
            labels["attention"] = scores[m]["candidate"]
            row[m] = {"labels": labels, "after": outcomes(raw, dates, m, asof)}
        weeks.append(row)
    return weeks


# ---------------------------------------------------------------- summary

def episodes(labels: list[str | None], label: str) -> int:
    """Number of runs of `label` in the sampled sequence (an episode is a stretch of the same label)."""
    return sum(1 for i, lab in enumerate(labels) if lab == label and (i == 0 or labels[i - 1] != label))


def stat_of(outcome: str) -> str:
    """The share of weeks with a large drawdown is compared by its mean; levels by the median, so a few
    extreme weeks (e.g. the 2020 jump in US unemployment) do not decide the comparison."""
    return "mean" if outcome == "dd" else "median"


def group(rows: list[dict], key: str, labels: tuple[str, ...], outcome: str) -> dict[str, dict]:
    out = {}
    seq = [r["labels"].get(key) for r in rows]
    for label in labels:
        values = [r["after"][outcome] for r in rows
                  if r["labels"].get(key) == label and r["after"].get(outcome) is not None]
        out[label] = {"n": len(values), "mean": statistics.fmean(values) if values else None,
                      "median": statistics.median(values) if values else None, "episodes": episodes(seq, label)}
    return out


def ordered(groups: dict[str, dict], labels: tuple[str, ...], stat: str = "median") -> bool | None:
    """True when the label on the attention side shows a larger outcome than the label furthest from it,
    among labels with MIN_N weeks (the middle label is used when an end label is too rare); None when fewer
    than two labels qualify."""
    present = [lab for lab in labels if groups[lab]["n"] >= MIN_N]
    if len(present) < 2:
        return None
    return groups[present[0]][stat] > groups[present[-1]][stat]  # a tie (e.g. 0% vs 0%) shows nothing


def verdict(halves: list[bool | None]) -> str:
    if any(h is None for h in halves):
        return MEANS_UNKNOWN
    if all(halves):
        return MEANS_OK
    return MEANS_WEAK if any(halves) else MEANS_REVERSED


def summarize(weeks: list[dict]) -> dict:
    sampled = weeks[::STRIDE]
    mid = len(sampled) // 2
    halves = {"前半": sampled[:mid], "後半": sampled[mid:]}
    out = {}
    for m in INDEX:
        checks = []
        for key, name, labels, keys in CHECKS:
            for outcome in keys:
                by_half = {h: group([r[m] for r in rows], key, labels, outcome) for h, rows in halves.items()}
                order = {h: ordered(g, labels, stat_of(outcome)) for h, g in by_half.items()}
                checks.append({"key": key, "name": name, "labels": list(labels), "outcome": outcome,
                               "by_half": by_half, "ordered": order, "verdict": verdict(list(order.values()))})
        reference = {h: group([r[m] for r in rows], "attention", (SC.ALERT, SC.WATCH, SC.CALM), "ret")
                     for h, rows in halves.items()}
        out[m] = {"sampled": len(sampled), "checks": checks, "reference_return": reference,
                  "span": {h: (rows[0]["asof"], rows[-1]["asof"]) if rows else None for h, rows in halves.items()}}
    return out


def _f(value: float | None, decimals: int = 2) -> str:
    return "—" if value is None else f"{value:+.{decimals}f}".replace("-", "−")


def _cells(groups: dict[str, dict], labels: list[str], decimals: int, stat: str = "median") -> str:
    return " / ".join(f"{lab} {_f(groups[lab][stat], decimals)}（{groups[lab]['n']}週・{groups[lab]['episodes']}局面）"
                      for lab in labels)


def render(summary: dict, years: int, today: str, weeks: list[dict]) -> str:
    span = f"{weeks[0]['asof']} 〜 {weeks[-1]['asof']}" if weeks else "—"
    lines = [f"# 3つの軸の検証（バックテスト） — {today}", "",
             f"**期間**: 過去 {years} 年（毎週金曜を再現し、{STRIDE}週おきに数えた。{span}）",
             "**方法**: 各金曜までに公表済みのデータ（日次 0日・週次 7日、月次は日本 70日・米国 45日、"
             "四半期は日本 135日・米国 120日の遅れを期間の初日から仮定）だけで、週次レポートと同じコードで3つの軸と"
             "注意の度合いを出し直し、そのあとに起きたことをラベルごとに比べた。注意の側の端（高い・警戒・引き締め・減速）"
             f"と反対側の端（{MIN_N}週に満たないときは中間）を、値は中央値・下落の割合は平均で比べ、前半・後半の"
             "どちらでも注意の側が大きければ「意味どおり」、片方だけなら「弱い」、両方で小さければ「逆」。",
             "", "> market_report.py backtest が生成する。手で編集しない。軸は地合いの説明で、先行きの株価の予測ではない。", "",
             "## 限界", "",
             "- 予想PER・AAII（web 検索の値）には過去分が無い（軸には入れていないので影響は参考欄だけ）",
             "- HY・IG スプレッドは FRED で取れる期間（約3年）だけで、それ以前の週はその信号が欠けている",
             "- 公表の遅れは頻度ごとの目安で、実際の公表日とは違う。統計は今の改定後の値を使っている",
             f"- {STRIDE}週おきに数えても次の{MACRO_WEEKS}週の期間は重なる。局面の数が少ないラベルは弱い証拠",
             "- 最初の数週はヒステリシスの前週の評価が無い",
             "- 日本の金融環境はこの10年、実質政策金利がマイナスで「引き締め」にならず、中立と緩和の比較になっている"
             "（日本の金融環境の判定は弱い証拠）", ""]
    for m, (_, index_name) in INDEX.items():
        s = summary[m]
        lines += [f"## {F.MARKET_LABEL[m]}（{index_name}、{s['sampled']} 週を集計）", "",
                  "| 軸 | 見たもの | 判定 | 前半（ラベルごとの平均） | 後半（ラベルごとの平均） |", "|---|---|---|---|---|"]
        for c in s["checks"]:
            dec, stat = (1 if c["outcome"] in ("vol", "dd") else 2), stat_of(c["outcome"])
            lines.append(f"| {c['name']} | {OUTCOME_LABEL[c['outcome']]}（{'平均' if stat == 'mean' else '中央値'}） | "
                         f"**{c['verdict']}** | {_cells(c['by_half']['前半'], c['labels'], dec, stat)} | "
                         f"{_cells(c['by_half']['後半'], c['labels'], dec, stat)} |")
        ref = s["reference_return"]
        labels = [SC.ALERT, SC.WATCH, SC.CALM]
        lines += ["", f"参考（目標ではない）: 注意の度合いごとの{OUTCOME_LABEL['ret']} — 前半 {_cells(ref['前半'], labels, 1)}"
                      f"、後半 {_cells(ref['後半'], labels, 1)}", ""]
    return "\n".join(lines) + "\n"


def verdicts(summary: dict) -> dict[str, list[str]]:
    """{market: ['市場のストレス × 次の13週の実現変動率: 意味どおり', ...]} for the command's JSON line."""
    return {m: [f"{c['name']} × {OUTCOME_LABEL[c['outcome']]}: {c['verdict']}" for c in s["checks"]]
            for m, s in summary.items()}
