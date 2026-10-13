"""Repair sources/manifest.csv: remove a mis-registered row (the only sanctioned way to change the manifest by hand).

Usage:
  sources_admin.py remove --company <dir> --local-path sources/2026-10-14/--company [--dry-run]

The row is dropped from manifest.csv and its file moved to sources/_removed/<date>/ (kept for inspection,
git-ignored like all of sources/). Afterwards the document can be fetched again with fetch.py, because the
sha256 duplicate check no longer finds it. Run only when the user asked for the repair.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import (MANIFEST_FIELDS, company_dir, file_lock, manifest_path, read_csv_rows,  # noqa: E402
                    today, utf8_stdout, write_csv_atomic)


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


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("remove",))
    ap.add_argument("--company", required=True)
    ap.add_argument("--local-path", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    row = remove(company_dir(args.company), args.local_path, args.dry_run)
    print(f"{'WOULD REMOVE' if args.dry_run else 'REMOVED'} {row.get('local_path')} url={row.get('url')}")


if __name__ == "__main__":
    main()
