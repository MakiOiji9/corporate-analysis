"""Technical analysis cache: companies/{dir}/analysis/technical/technical.{json,md}.

The analysis is a pure function of the daily prices, so it is redone only when the latest close date moves on (or the
rules version changes), not when time passes. The saved file carries the analysis time (JST) and the close date."""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "collect")]

import cr_patterns as P  # noqa: E402
import cr_tech_views as V  # noqa: E402
from common import atomic_write_text  # noqa: E402

JST = dt.timezone(dt.timedelta(hours=9))
DIR = Path("analysis") / "technical"
JSON_NAME, MD_NAME = "technical.json", "technical.md"
VERSION = f"{P.VERSION}.1"


def needs_refresh(existing: dict | None, asof: str | None) -> bool:
    """True when nothing usable is saved, the rules changed, or the close date is not the saved one."""
    return not (existing and existing.get("version") == VERSION and existing.get("price_asof") == asof)


def alignment(daily: dict, weekly: dict) -> str | None:
    """A note when the daily and weekly trends point opposite ways (short-term moves against the larger flow)."""
    d, w = (v.get("aspects") or {} for v in (daily, weekly))
    dd, wd = (a.get("trend", {}).get("direction") for a in (d, w))
    if P.UP in (dd, wd) and P.DOWN in (dd, wd):
        up, down = ("日足", "週足") if dd == P.UP else ("週足", "日足")
        return (f"{up}は上向き、{down}は下向きで食い違っている。短い足の動きは、長い足の流れに押し戻されることもあるため、"
                "どちらの時間軸で見るかをそろえて判断する。")
    if dd and dd == wd and dd != P.FLAT:
        return "日足と週足の向きがそろっている。"
    return None


def analyze(rows: list[dict], now: dt.datetime | None = None) -> dict:
    daily, weekly = V.view(rows, P.DAILY), V.view(P.weekly(rows), P.WEEKLY)
    return {"version": VERSION, "ok": daily["ok"], "price_asof": rows[-1]["date"] if rows else None,
            "generated_at": (now or dt.datetime.now(JST)).astimezone(JST).isoformat(timespec="seconds"),
            "daily": daily, "weekly": weekly, "alignment": alignment(daily, weekly) if daily["ok"] else None}


def _md(t: dict) -> str:
    lines = ["# テクニカル分析", "", f"- 分析日時: {t['generated_at']}（日本時間）", f"- 終値の日付: {t['price_asof']}", ""]
    for key in ("daily", "weekly"):
        v = t[key]
        lines += [f"## {v['label']}", ""]
        if not v["ok"]:
            lines += ["- 本数が足りず判定しない", ""]
            continue
        lines += [f"- 総合: {v['overall']['headline']}"]
        lines += [f"- {a['name']}: {a['state']}（確度 {a['confidence']}）" for a in v["aspects"].values()]
        lines += [f"- {p['name']}（{p['status']}）: {p['sentence']}" for p in v["patterns"]["patterns"]] + [""]
    if t.get("alignment"):
        lines += [f"- 時間軸の関係: {t['alignment']}", ""]
    return "\n".join(lines)


def ensure(company_path: Path, rows: list[dict], now: dt.datetime | None = None, force: bool = False) -> dict:
    """The saved analysis when the close date is unchanged, else a fresh one (saved). Result has reused: bool."""
    path = company_path / DIR / JSON_NAME
    existing = None
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            existing = None
    asof = rows[-1]["date"] if rows else None
    if not rows:
        return {"version": VERSION, "ok": False, "price_asof": None, "reused": False}
    if not force and not needs_refresh(existing, asof):
        return {**existing, "reused": True}
    t = analyze(rows, now)
    atomic_write_text(path, json.dumps(t, ensure_ascii=False, indent=1) + "\n")
    atomic_write_text(path.with_name(MD_NAME), _md(t))
    return {**t, "reused": False}
