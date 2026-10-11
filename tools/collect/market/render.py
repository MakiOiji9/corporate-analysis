"""Fill .ai/templates/collect-market-info/ templates (string.Template ${var}) with tables.

All raw files are produced here so that every output keeps the template's headings
and table columns. The LLM only replaces <!-- FILL:... --> lines in skeletons.
"""
from __future__ import annotations

from pathlib import Path
from string import Template

from common import REPO_ROOT
from store import Summary

TEMPLATE_DIR = REPO_ROOT / ".ai" / "templates" / "collect-market-info"
MARKET_LABEL = {"japan": "日本", "us": "米国"}
LAYER_LABEL = {"A": "A 国家方針", "B": "B 財政・税制", "C": "C 金融政策",
               "D": "D マクロ指標", "E": "E 需給・センチメント・政治"}
DASH = "—"


def template_path(rel: str) -> Path:
    return TEMPLATE_DIR / rel


def render_template(rel: str, **values: object) -> str:
    text = template_path(rel).read_text(encoding="utf-8")
    return Template(text).safe_substitute({k: str(v) for k, v in values.items()})


def cell(value: object) -> str:
    text = str(value if value is not None else "").replace("|", "／").replace("\n", " ").strip()
    return text or DASH


def table(rows: list[list[object]], width: int) -> str:
    if not rows:
        rows = [[DASH] * width]
    return "\n".join("| " + " | ".join(cell(c) for c in row) + " |" for row in rows)


def num(value: float | None, decimals: int) -> str:
    if value is None:
        return DASH
    return f"{value:,.{decimals}f}"


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def indicator_row(entry: dict, summary: Summary | None) -> list[object]:
    d = entry.get("decimals", 1)
    if summary is None:
        return [entry.get("group", ""), entry["name"], DASH, DASH, DASH, DASH, entry.get("unit", ""),
                entry.get("source", "")]
    return [entry.get("group", ""), entry["name"], summary.latest_date, num(summary.latest, d),
            f"{num(summary.prev, d)}（{summary.prev_date}）", f"{num(summary.year, d)}（{summary.year_date}）",
            entry.get("unit", ""), entry.get("source", "")]


def render_indicators(market: str, entries: list[dict], summaries: dict[str, Summary | None],
                      failures: dict[str, str], collected: str, data_csv: Path) -> str:
    sources = sorted({e.get("source_url", "") for e in entries if e.get("source_url")})
    source_lines = "\n".join(f"- {u} — 確度: 一次" for u in sources) or f"- {DASH}"
    rows = [indicator_row(e, summaries.get(e["id"])) for e in entries]
    failed = [[e["name"], failures[e["id"]]] for e in entries if e["id"] in failures]
    return render_template("raw/series-table.md", market_label=MARKET_LABEL[market],
                           collected=collected, source_lines=source_lines, data_csv=rel(data_csv),
                           rows=table(rows, 8), failed_rows=table(failed or [["なし", DASH]], 2))


def render_doc_skeleton(template: str, **values: object) -> str:
    values.setdefault("layer_label", LAYER_LABEL.get(str(values.get("layer", "")), DASH))
    return render_template(template, **values)


def render_doc_list(title: str, source_title: str, source_url: str, layer: str,
                    items: list[tuple[str, str, str]], collected: str) -> str:
    return render_template("raw/doc-list.md", title=title, collected=collected, source_title=source_title,
                           source_url=source_url, layer_label=LAYER_LABEL.get(layer, DASH),
                           rows=table([list(i) for i in items], 3))


def render_digest(session: str, collected: str, new_rows: list[list[object]],
                  latest_rows: list[list[object]]) -> str:
    return render_template("policy-digest.md", session=session, collected=collected,
                           new_rows=table(new_rows, 6), latest_rows=table(latest_rows, 6))


def bullets(items: list[str], empty: str = "なし") -> str:
    return "\n".join(f"- {i}" for i in items) if items else f"- {empty}"


def render_status(session: str, updated: str, stage: str, summary_rows: list[list[object]],
                  series_rows: list[list[object]], watch_rows: list[list[object]],
                  task_rows: list[list[object]], validation: list[str], out_of_scope: list[str]) -> str:
    return render_template("status.md", session=session, updated=updated, stage=stage,
                           summary_rows=table(summary_rows, 2), series_rows=table(series_rows, 4),
                           watch_rows=table(watch_rows, 3), task_rows=table(task_rows, 4),
                           validation=bullets(validation, "問題なし"),
                           out_of_scope=bullets(out_of_scope, "なし"))
