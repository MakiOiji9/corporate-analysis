"""Repair sources/manifest.csv: remove a mis-registered row (the only sanctioned way to change the manifest by hand),
and restore originals that are registered but not on disk.

Usage:
  sources_admin.py remove --company <dir> --local-path sources/2026-10-14/--company [--dry-run]
  sources_admin.py restore --company <dir> [--host api.edinet-fsa.go.jp ...] [--text] [--dry-run]

  sources_admin.py move-peer --company <dir> --local-path <path> --ticker 6954 --name fanuc --doc-type tanshin

move-peer  moves a peer's original registered in <dir> (before 2026-11-23 peers' originals were kept in the
         comparing company's sources/ with a peer-* type) to the peer's own directory (peer_company.py ensure):
         the manifest row (doc type renamed, note "移動元: companies/<dir>/<path>") and the file with its .txt when on
         disk. The row is dropped from <dir>'s manifest. A document already in the peer's manifest (same sha256) is
         not registered twice.
restore  downloads each manifest row whose file is missing (from before originals were kept in git) from its URL
         (EDINET rows get EDINET_API_KEY), and writes it back to its local_path only when the sha256 matches the
         manifest. A changed document (e.g. an IR list page updated since) is reported as mismatch and not written.
         A file above 20MB goes to sources/_large/ and the row's local_path and note are updated. --host limits the
         rows to those hosts; --text also writes <file>.txt for PDF / HTML (as fetch.py --text). <dir> may also be a
         market policy library (market/policy/japan). An http:// URL that fails is tried once over https://.
         stdout is one JSON line.

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


def move_peer(company: Path, local_path: str, ticker: str, name: str, doc_type: str, root: Path | None = None) -> dict:
    """Move one manifest row (and its file) of `company` to the peer's directory. Returns {dir, local_path, dup}."""
    import peer_company
    root = root or company.parents[1]
    target = root / peer_company.ensure(root, ticker, name, company.name)["dir"]
    src_manifest, dst_manifest = manifest_path(company), manifest_path(target)
    with file_lock(src_manifest):
        rows = read_csv_rows(src_manifest)
        match = [r for r in rows if r.get("local_path") == local_path]
        if len(match) != 1:
            raise SystemExit(f"expected exactly one manifest row with local_path={local_path}, found {len(match)}")
        row = match[0]
        with file_lock(dst_manifest):
            dst_rows = read_csv_rows(dst_manifest)
            dup = next((r for r in dst_rows if r.get("sha256") == row["sha256"]), None)
            new_path = dup["local_path"] if dup else local_path
            if not dup:
                dest = target / local_path
                stem, suffix, n = dest.stem, dest.suffix, 2
                while dest.exists() or any(r["local_path"] == dest.relative_to(target).as_posix() for r in dst_rows):
                    dest = dest.with_name(f"{stem}_{n}{suffix}")
                    n += 1
                new_path = dest.relative_to(target).as_posix()
                note = f"移動元: companies/{company.name}/{local_path}"
                dst_rows.append({**row, "doc_type": doc_type, "local_path": new_path,
                                 "note": "; ".join(x for x in (row.get("note", ""), note) if x)})
                write_csv_atomic(dst_manifest, MANIFEST_FIELDS, dst_rows)
            for suffix in ("", ".txt"):
                src = company / f"{local_path}{suffix}"
                if not src.exists():
                    continue
                if dup:  # the peer already has it: keep the copy aside like remove does
                    aside = company / "sources" / "_removed" / today()
                    aside.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(aside / src.name))
                else:
                    dest = target / f"{new_path}{suffix}"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(src), str(dest))
        write_csv_atomic(src_manifest, MANIFEST_FIELDS, [r for r in rows if r is not row])
    return {"dir": target.relative_to(root).as_posix(), "local_path": new_path, "dup": bool(dup)}


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
            # an http:// URL may be reachable only over https (the sha256 check below still guards the content)
            data = None
            if row["url"].startswith("http://"):
                try:
                    data = _download("https://" + row["url"][len("http://"):], get)
                except Exception:  # noqa: BLE001
                    data = None
            if data is None:
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
    ap.add_argument("command", choices=("remove", "restore", "move-peer"))
    ap.add_argument("--ticker", help="move-peer: the peer's code")
    ap.add_argument("--name", help="move-peer: the peer's English name (used only when its directory is new)")
    ap.add_argument("--doc-type", help="move-peer: the type in the peer's manifest (tanshin, presentation, ...)")
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
        ap.error(f"{args.command} needs --local-path")
    if args.command == "move-peer":
        if not (args.ticker and args.name and args.doc_type):
            ap.error("move-peer needs --ticker, --name and --doc-type")
        moved = move_peer(company_dir(args.company), args.local_path, args.ticker, args.name, args.doc_type)
        print(json.dumps({"ok": True, **moved}, ensure_ascii=False))
        return
    row = remove(company_dir(args.company), args.local_path, args.dry_run)
    print(f"{'WOULD REMOVE' if args.dry_run else 'REMOVED'} {row.get('local_path')} url={row.get('url')}")


if __name__ == "__main__":
    main()
