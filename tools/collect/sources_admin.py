"""Repair sources/manifest.csv: remove a mis-registered row (the only sanctioned way to change the manifest by hand),
and restore originals that are registered but not on disk.

Usage:
  sources_admin.py remove --company <dir> --local-path sources/2026-10-14/--company [--dry-run]
  sources_admin.py restore --company <dir> [--host api.edinet-fsa.go.jp ...] [--text] [--dry-run]

restore  downloads each manifest row whose file is missing (from before originals were kept in git) from its URL
         (EDINET rows get EDINET_API_KEY), and writes it back to its local_path only when the sha256 matches the
         manifest. A changed document (e.g. an IR list page updated since) is reported as mismatch and not written.
         A file above 20MB goes to sources/_large/ and the row's local_path and note are updated. --host limits the
         rows to those hosts; --text also writes <file>.txt for PDF / HTML (as fetch.py --text). <dir> may also be a
         market policy library (market/policy/japan). stdout is one JSON line.

The row is dropped from manifest.csv and its file moved to sources/_removed/<date>/ (kept for inspection,
git-ignored). Afterwards the document can be fetched again with fetch.py, because the
sha256 duplicate check no longer finds it. Run only when the user asked for the repair.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
import common  # noqa: E402
from common import (MANIFEST_FIELDS, company_dir, file_lock, http_get, load_env, manifest_path,  # noqa: E402
                    read_csv_rows, sha256_bytes, today, utf8_stdout, write_csv_atomic)

EDINET_HOST = "api.edinet-fsa.go.jp"


def remove(company: Path, local_path: str, dry_run: bool = False) -> dict:
    """Drop the manifest row whose local_path matches; move its file (and .txt) aside. Returns the row."""
    manifest = manifest_path(company)
    with file_lock(manifest):
        rows = read_csv_rows(manifest)
        match = [r for r in rows if r.get("local_path") == local_path]
        if len(match) != 1:
            raise SystemExit(f"expected exactly one manifest row with local_path={local_path}, found {len(match)}")
        if dry_run:
            return match[0]
        target_dir = company / "sources" / "_removed" / today()
        for src in (company / local_path, company / f"{local_path}.txt"):
            if src.exists():
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(target_dir / src.name))
        write_csv_atomic(manifest, MANIFEST_FIELDS, [r for r in rows if r is not match[0]])
    return match[0]


def _download(url: str, get) -> bytes:
    host = urlparse(url).hostname or ""
    params = None
    if host == EDINET_HOST:
        load_env()
        key = os.environ.get("EDINET_API_KEY", "")
        if not key:
            raise RuntimeError("EDINET_API_KEY not set")
        params = {"Subscription-Key": key}
    resp = get(url, params=params)
    if "application/json" in resp.headers.get("Content-Type", ""):
        raise RuntimeError(f"error response: {resp.text[:200]}")
    return resp.content


def restore(base: Path, hosts: list[str] | None = None, text: bool = False, dry_run: bool = False,
            get=http_get) -> dict:
    """Re-download the registered originals that are not on disk; write only those whose sha256 matches."""
    manifest = manifest_path(base)
    out = {"restored": [], "mismatch": [], "failed": [], "skipped_host": 0, "present": 0, "large": []}
    for row in read_csv_rows(manifest):
        path = base / row["local_path"]
        if path.is_file():
            out["present"] += 1
            continue
        if hosts and (urlparse(row["url"]).hostname or "") not in hosts:
            out["skipped_host"] += 1
            continue
        if dry_run:
            out["restored"].append(row["local_path"])
            continue
        try:
            data = _download(row["url"], get)
        except Exception as exc:  # noqa: BLE001 - report every failure and go on with the next row
            out["failed"].append({"local_path": row["local_path"], "url": row["url"], "error": str(exc)[:200]})
            continue
        if sha256_bytes(data) != row["sha256"]:
            out["mismatch"].append({"local_path": row["local_path"], "url": row["url"]})
            continue
        if len(data) > common.LARGE_FILE_BYTES:
            rel = Path(row["local_path"])
            new_rel = Path("sources", common.LARGE_DIR, *rel.parts[1:]).as_posix()
            with file_lock(manifest):
                rows = read_csv_rows(manifest)
                for r in rows:
                    if r["local_path"] == row["local_path"]:
                        r["local_path"] = new_rel
                        r["note"] = "; ".join(n for n in (r.get("note", ""), common.LARGE_NOTE) if n)
                write_csv_atomic(manifest, MANIFEST_FIELDS, rows)
            path = base / new_rel
            out["large"].append(new_rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if text and path.suffix.lower() in (".pdf", ".htm", ".html"):
            from pdf_text import convert
            try:
                convert(path)
            except Exception as exc:  # noqa: BLE001 - the original is restored; the text can be made later
                out["failed"].append({"local_path": row["local_path"], "url": row["url"],
                                      "error": f"text: {str(exc)[:200]}"})
        out["restored"].append(path.relative_to(base).as_posix())
    return out


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("remove", "restore"))
    ap.add_argument("--company", required=True)
    ap.add_argument("--local-path")
    ap.add_argument("--host", action="append", help="restore: only rows from this host (repeatable)")
    ap.add_argument("--text", action="store_true", help="restore: also write <file>.txt for PDF / HTML")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.command == "restore":
        result = restore(company_dir(args.company), args.host, args.text, args.dry_run)
        summary = {k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}
        print(json.dumps({"ok": not result["failed"], **summary, "mismatch_rows": result["mismatch"],
                          "failed_rows": result["failed"]}, ensure_ascii=False))
        return
    if not args.local_path:
        ap.error("remove needs --local-path")
    row = remove(company_dir(args.company), args.local_path, args.dry_run)
    print(f"{'WOULD REMOVE' if args.dry_run else 'REMOVED'} {row.get('local_path')} url={row.get('url')}")


if __name__ == "__main__":
    main()
