"""Document library (market/policy/{market}/): store originals, excerpt, skeleton, index.

Layer A/B/C documents found by watch.py are saved once and summarised once; later
sessions only reference them. index.csv status: pending (skeleton has FILL) /
done (summary validated) / listed (kind=list, no summary needed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import excerpt as X
import render as R
import watch as W
from common import REPO_ROOT, http_get, store_document
from fetch import default_name
from pdf_text import convert, html_to_text
from validate import FILL

POLICY_DIR = REPO_ROOT / "market" / "policy"
CHARSET = re.compile(rb"charset\s*=\s*[\"']?([\w-]+)", re.I)
TEMPLATE_FOR_LAYER = {"C": "raw/monetary-doc.md"}
DEFAULT_TEMPLATE = "raw/policy-doc.md"
MAX_FOLLOW_ATTEMPTS = 3  # candidates tried per watch entry when following into pages


@dataclass
class WatchResult:
    tasks: list[dict] = field(default_factory=list)
    new_docs: list[dict] = field(default_factory=list)
    watch_rows: list[list[str]] = field(default_factory=list)


def library_dir(market: str) -> Path:
    return POLICY_DIR / market


def index_path(market: str) -> Path:
    return library_dir(market) / "index.csv"


def template_for(layer: str) -> str:
    return TEMPLATE_FOR_LAYER.get(layer, DEFAULT_TEMPLATE)


def to_text(path: Path) -> Path:
    """PDF -> pdf_text.convert; HTML -> decode by its meta charset (gov sites still use Shift_JIS)."""
    if path.suffix.lower() == ".pdf":
        return convert(path)
    data = path.read_bytes()
    m = CHARSET.search(data[:4000])
    encoding = m.group(1).decode() if m else "utf-8"
    try:
        html = data.decode(encoding, errors="replace")
    except LookupError:
        html = data.decode("utf-8", errors="replace")
    out = path.with_suffix(path.suffix + ".txt")
    out.write_text(html_to_text(html), encoding="utf-8")
    return out


def _previous_raw(rows: list[dict], watch_key: str) -> str:
    done = [r for r in rows if r["watch_key"] == watch_key and r["status"] == "done"]
    return done[-1]["raw_path"] if done else "なし"


def _summarize_one(market: str, cand: W.Candidate, entry: dict, rows: list[dict],
                   collected: str, keywords: list[str]) -> dict:
    lib = library_dir(market)
    resp = http_get(cand.url, referer=cand.page_url or None)
    name = default_name(cand.url, "", resp.headers.get("Content-Type", ""))
    original, _ = store_document(lib, resp.content, name, {
        "doc_type": cand.watch_key, "published_date": cand.published, "doc_id": Path(name).stem,
        "url": cand.url, "note": cand.title[:80]})
    text = to_text(original)
    excerpt_file = X.write_excerpt(text, keywords + entry.get("keywords", []),
                                   entry.get("max_chars", X.DEFAULT_MAX_CHARS))
    doc_key = W.make_doc_key(cand.watch_key, cand.published, collected, {r["doc_key"] for r in rows})
    raw = lib / "raw" / f"{collected}_{doc_key}.md"
    previous = _previous_raw(rows, cand.watch_key)
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        raw.write_text(R.render_doc_skeleton(
            template_for(cand.layer), title=cand.title, collected=collected, url=cand.url,
            source_path=R.rel(original), layer=cand.layer, published=cand.published or "—",
            excerpt_path=R.rel(excerpt_file), previous=previous), encoding="utf-8")
    return {"doc_key": doc_key, "watch_key": cand.watch_key, "layer": cand.layer, "title": cand.title,
            "published": cand.published, "url": cand.url, "page_url": cand.page_url,
            "raw_path": R.rel(raw), "collected": collected, "status": "pending"}


def _list_new(market: str, entry: dict, fresh: list[W.Candidate], rows: list[dict], collected: str) -> list[dict]:
    lib = library_dir(market)
    raw = lib / "raw" / f"{collected}_{entry['key']}.md"
    n = 2
    while raw.exists():
        raw, n = lib / "raw" / f"{collected}_{entry['key']}-{n}.md", n + 1
    raw.parent.mkdir(parents=True, exist_ok=True)
    items = [(c.published or "—", c.title, c.url) for c in fresh]
    raw.write_text(R.render_doc_list(entry["title"], entry["title"], entry["url"], entry.get("layer", ""),
                                     items, collected), encoding="utf-8")
    taken = {r["doc_key"] for r in rows}
    out = []
    for c in fresh:
        key = W.make_doc_key(c.watch_key, c.published, collected, taken)
        taken.add(key)
        out.append({"doc_key": key, "watch_key": c.watch_key, "layer": c.layer, "title": c.title,
                    "published": c.published, "url": c.url, "page_url": "", "raw_path": R.rel(raw),
                    "collected": collected, "status": "listed"})
    return out


def process_watches(market: str, catalog: dict, collected: str) -> WatchResult:
    result, rows = WatchResult(), W.load_index(index_path(market))
    variables, errors = W.resolve_vars(catalog.get("vars", {}), http_get)
    result.watch_rows.extend([market, "vars", f"失敗: {e}"] for e in errors)
    keywords = catalog.get("excerpt_keywords", [])
    for entry in catalog.get("watch", []):
        try:
            cands = W.list_candidates(entry, http_get, variables)
            known, max_new = W.known_urls(rows), entry.get("max_new", 1)
            fresh = W.pick_new(cands, known)
            if entry.get("kind") == "list":
                added = _list_new(market, entry, fresh[:max_new], rows, collected) if fresh else []
            else:
                added = []
                for attempt, cand in enumerate(fresh):
                    if len(added) >= max_new or attempt >= MAX_FOLLOW_ATTEMPTS:
                        break
                    if entry.get("follow"):
                        try:
                            cand = W.follow(cand, entry["follow"], http_get)
                        except Exception:  # noqa: BLE001 - e.g. an old page moved to an archive; try the next one
                            continue
                        if cand is None or cand.url in known:
                            continue
                    added.append(_summarize_one(market, cand, entry, rows + added, collected, keywords))
            rows.extend(added)
            result.new_docs.extend({**a, "market": market} for a in added)
            result.watch_rows.append([market, entry["key"], f"候補 {len(cands)} 件 / 新規 {len(added)} 件"])
        except Exception as exc:  # noqa: BLE001 - record and continue with the next watch entry
            result.watch_rows.append([market, entry["key"], f"失敗: {type(exc).__name__}: {str(exc)[:120]}"])
        W.save_index(index_path(market), rows)
    return result


def pending_doc_tasks(market: str) -> list[dict]:
    """Summaries not finished yet (this run or an interrupted earlier run)."""
    tasks = []
    for r in W.load_index(index_path(market)):
        raw = REPO_ROOT / r["raw_path"]
        if r["status"] == "pending" and raw.exists() and FILL.search(raw.read_text(encoding="utf-8")):
            header = raw.read_text(encoding="utf-8")
            m = re.search(r"\*\*要旨化に使った抜粋\*\*: (\S+)", header)
            p = re.search(r"\*\*前回版\*\*: (\S+)", header)
            inputs = [m.group(1)] if m else []
            if p and p.group(1) != "なし":
                inputs.append(p.group(1))
            tasks.append({"type": "summarize-doc", "market": market, "title": r["title"],
                          "doc_key": r["doc_key"], "output": r["raw_path"], "inputs": inputs,
                          "template": f".ai/templates/collect-market-info/{template_for(r['layer'])}",
                          "allowed_files": [r["raw_path"]]})
    return tasks


def mark_done(market: str, done_outputs: set[str]) -> None:
    rows = W.load_index(index_path(market))
    if not rows:
        return
    changed = False
    for r in rows:
        if r["status"] == "pending" and r["raw_path"] in done_outputs:
            r["status"] = "done"
            changed = True
    if changed:
        W.save_index(index_path(market), rows)


def latest_by_watch(market: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for r in W.load_index(index_path(market)):
        if r["status"] in ("done", "listed", "pending"):
            current = latest.get(r["watch_key"])
            if current is None or (r["published"] or r["collected"]) >= (current["published"] or current["collected"]):
                latest[r["watch_key"]] = r
    return [latest[k] for k in sorted(latest)]
