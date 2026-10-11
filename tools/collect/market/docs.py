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
from validate import FILL, validate_file

POLICY_DIR = REPO_ROOT / "market" / "policy"
CHARSET = re.compile(rb"charset\s*=\s*[\"']?([\w-]+)", re.I)
TEMPLATE_FOR_LAYER = {"C": "raw/monetary-doc.md"}
DEFAULT_TEMPLATE = "raw/policy-doc.md"
MAX_FOLLOW_ATTEMPTS = 3  # candidates tried per watch entry when following into pages
BODY_DATE_CHARS = 6_000  # HTML texts start with site navigation, so look a little further than page 1
ISO_DATE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
PUBLISHED_CHECK = re.compile(r"^\*\*公表日（本文で確認）\*\*:[ \t]*\n(.+)$", re.M)
PENDING_SECTION = re.compile(r"^## \d+\. 未確認・保留事項[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)
NOTHING = ("なし", "—", "")


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


def refine_published(published: str, source: str, body: str, collected: str) -> tuple[str, str]:
    """(date, note): check a guessed publication date against the first date in the document text.

    A date read from the link label / feed (exact) is kept. A month-only date (gor2607a -> 07-01)
    takes the body date of the same month; a date taken from an index page, or no date at all,
    takes the body date. An index-page date the body does not confirm is dropped (the first date
    on such a page often belongs to another document); the summariser's 公表日（本文で確認）
    line can fill it later. note is '' when nothing changed.
    """
    found = W.find_date(body[:BODY_DATE_CHARS])
    if found > collected:
        found = ""
    if not found and source == W.DATE_FROM_PAGE and published:
        return "", f"索引ページの日付 {published} を本文で確認できないため公表日は空欄"
    if not found or found == published:
        return published, ""
    if not published:
        return found, f"公表日を本文から補完 {found}"
    if source == W.DATE_EXACT or (source == W.DATE_MONTH_ONLY and found[:7] != published[:7]):
        return published, ""
    return found, f"公表日を本文で補正 {published}→{found}"


def excerpt_options(catalog: dict, entry: dict) -> dict:
    return {"keywords": catalog.get("excerpt_keywords", []) + entry.get("keywords", []),
            "max_chars": entry.get("max_chars", X.DEFAULT_MAX_CHARS), "must_include": entry.get("must_include")}


def _summarize_one(market: str, cand: W.Candidate, entry: dict, rows: list[dict],
                   collected: str, options: dict) -> tuple[dict, str]:
    lib = library_dir(market)
    resp = http_get(cand.url, referer=cand.page_url or None)
    name = default_name(cand.url, "", resp.headers.get("Content-Type", ""))
    original, _ = store_document(lib, resp.content, name, {
        "doc_type": cand.watch_key, "published_date": cand.published, "doc_id": Path(name).stem,
        "url": cand.url, "note": cand.title[:80]})
    text = to_text(original)
    published, note = refine_published(cand.published, cand.date_source,
                                       text.read_text(encoding="utf-8", errors="replace"), collected)
    excerpt_file = X.write_excerpt(text, **options)
    doc_key = W.make_doc_key(cand.watch_key, published, collected, {r["doc_key"] for r in rows})
    raw = lib / "raw" / f"{collected}_{doc_key}.md"
    previous = _previous_raw(rows, cand.watch_key)
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not raw.exists():
        raw.write_text(R.render_doc_skeleton(
            template_for(cand.layer), title=cand.title, collected=collected, url=cand.url,
            source_path=R.rel(original), layer=cand.layer, published=published or "—",
            excerpt_path=R.rel(excerpt_file), previous=previous), encoding="utf-8")
    row = {"doc_key": doc_key, "watch_key": cand.watch_key, "layer": cand.layer, "title": cand.title,
           "published": published, "url": cand.url, "page_url": cand.page_url,
           "raw_path": R.rel(raw), "collected": collected, "status": "pending"}
    return row, note


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
    for entry in catalog.get("watch", []):
        try:
            cands = W.list_candidates(entry, http_get, variables)
            known, max_new = W.known_urls(rows), entry.get("max_new", 1)
            fresh = W.pick_new(cands, known)
            notes: list[str] = []
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
                    row, note = _summarize_one(market, cand, entry, rows + added, collected,
                                               excerpt_options(catalog, entry))
                    added.append(row)
                    notes += [note] if note else []
            rows.extend(added)
            result.new_docs.extend({**a, "market": market} for a in added)
            detail = "".join(f"（{n}）" for n in notes)
            result.watch_rows.append([market, entry["key"], f"候補 {len(cands)} 件 / 新規 {len(added)} 件{detail}"])
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


def reconcile_index(market: str) -> list[str]:
    """Mark pending rows done when their summary is already complete (e.g. a session that was
    summarised but never finalized). Returns the doc_keys that changed."""
    rows = W.load_index(index_path(market))
    fixed = []
    for r in rows:
        raw = REPO_ROOT / r["raw_path"]
        if r["status"] == "pending" and raw.exists() and not validate_file(
                raw, R.template_path(template_for(r["layer"]))):
            r["status"] = "done"
            fixed.append(r["doc_key"])
    if fixed:
        W.save_index(index_path(market), rows)
    return fixed


def pending_items(text: str) -> list[str]:
    """Bullets of the '未確認・保留事項' section of a finished raw file ([] when it says なし)."""
    m = PENDING_SECTION.search(text)
    if not m:
        return []
    lines = [line.strip() for line in m.group(1).splitlines() if line.strip() and not line.startswith(">")]
    items = [item for line in lines if line.startswith(("- ", "* "))
             if not _is_nothing(item := line[2:].strip())]
    if items or any(line.startswith(("- ", "* ")) for line in lines):
        return items
    return [] if not lines or _is_nothing(lines[0]) else [lines[0]]


def _is_nothing(text: str) -> bool:
    return text.strip("。.（）() ") in NOTHING


def published_check(text: str) -> str:
    """The date the summariser read in the document body ('' when same as header / not found)."""
    m = PUBLISHED_CHECK.search(text)
    date = ISO_DATE.search(m.group(1)) if m else None
    return date.group(1) if date else ""


def apply_published_checks(market: str, outputs: set[str]) -> list[str]:
    """Compare index.csv published with the summaries' '公表日（本文で確認）' line; returns notes.

    Only an empty published is filled in. A different date is reported for review and not
    written: the body often also names the meeting / decision date, which is not the publication date.
    """
    rows = W.load_index(index_path(market))
    notes, changed = [], False
    for r in rows:
        raw = REPO_ROOT / r["raw_path"]
        if r["raw_path"] not in outputs or not raw.exists():
            continue
        checked = published_check(raw.read_text(encoding="utf-8"))
        if not checked or checked == r["published"]:
            continue
        if r["published"]:
            notes.append(f"{r['raw_path']}: 公表日の不一致 台帳 {r['published']} / 本文 {checked}（台帳は変更せず）")
        else:
            notes.append(f"{r['raw_path']}: 公表日を本文の {checked} で補完")
            r["published"], changed = checked, True
    if changed:
        W.save_index(index_path(market), rows)
    return notes


def _header(text: str, label: str) -> str:
    m = re.search(rf"^\*\*{label}\*\*: (\S+)", text, re.M)
    return m.group(1) if m else ""


def reopen_doc(market: str, raw_rel: str, catalog: dict) -> dict:
    """Turn a finished summary back into a skeleton with a fresh excerpt; the next prepare
    re-creates its task. Only on the user's explicit request."""
    rows = W.load_index(index_path(market))
    row = next((r for r in rows if r["raw_path"] == raw_rel and r["status"] in ("done", "pending")), None)
    if row is None:
        raise SystemExit(f"index.csv に要旨化対象として載っていない: {raw_rel}")
    raw = REPO_ROOT / raw_rel
    if not raw.exists():
        raise SystemExit(f"要旨ファイルが無い: {raw_rel}")
    text = raw.read_text(encoding="utf-8")
    source, excerpt_rel = _header(text, "原本"), _header(text, "要旨化に使った抜粋")
    full_text = REPO_ROOT / excerpt_rel.replace(".excerpt.txt", ".txt")
    if not full_text.exists():
        raise SystemExit(f"全文テキストが無いので抜粋を作り直せない: {R.rel(full_text)}")
    entry = next((e for e in catalog.get("watch", []) if e["key"] == row["watch_key"]), {})
    X.write_excerpt(full_text, **excerpt_options(catalog, entry))
    raw.write_text(R.render_doc_skeleton(
        template_for(row["layer"]), title=row["title"], collected=row["collected"], url=row["url"],
        source_path=source, layer=row["layer"], published=row["published"] or "—",
        excerpt_path=excerpt_rel, previous=_header(text, "前回版") or "なし"), encoding="utf-8")
    row["status"] = "pending"
    W.save_index(index_path(market), rows)
    return {"reopened": raw_rel, "excerpt": excerpt_rel}


def latest_by_watch(market: str) -> list[dict]:
    latest: dict[str, dict] = {}
    for r in W.load_index(index_path(market)):
        if r["status"] in ("done", "listed", "pending"):
            current = latest.get(r["watch_key"])
            if current is None or (r["published"] or r["collected"]) >= (current["published"] or current["collected"]):
                latest[r["watch_key"]] = r
    return [latest[k] for k in sorted(latest)]
