"""Front matter of the raw md files (BL-01): which documents each raw file and each of its sections rests on.

Usage:
  raw_provenance.py apply --company <dir> --file raw/filings/2026-11-01_2026-02_yuho.md --spec spec.json
  raw_provenance.py check --company <dir>

apply puts the front matter of spec.json ({"sources": [...], "sections": {...}}, the shape front_matter.py
documents) at the top of a raw file, or replaces the one already there. The body is kept byte for byte (checked
before writing), so this is the one sanctioned way to touch a raw file of an earlier day: write_guard.py keeps
refusing hand edits of those. `collected` defaults to the date of the file name.
check reports, for every raw md, whether it has front matter, whether it is well formed, and which document IDs
are neither in sources/manifest.csv nor raw-local IDs (w1 … web only, d1 … data/ tables). Each command prints
one line of JSON.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
import front_matter as FM  # noqa: E402
from common import atomic_write_text, company_dir, read_manifest, utf8_stdout  # noqa: E402

DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})_")


def _raw_file(company: Path, rel: str) -> Path:
    path = (company / rel).resolve()
    raw = (company / "raw").resolve()
    if raw not in path.parents or path.suffix != ".md" or not path.is_file():
        raise SystemExit(f"raw の md ではない: {rel}")
    return path


def _unregistered(company: Path, meta: dict) -> list[str]:
    known = {r.get("doc_id") for r in read_manifest(company)}
    return [s["id"] for s in meta["sources"] if s["id"] not in known and not FM.LOCAL_ID.match(s["id"])]


def apply(company: Path, rel: str, spec: dict) -> dict:
    path = _raw_file(company, rel)
    old = path.read_bytes().decode("utf-8")  # no newline translation: a CRLF body stays CRLF
    date = DATED.match(path.name)
    meta = {"provenance": FM.VERSION, "collected": date.group(1) if date else None, **spec}
    new = FM.with_front_matter(old, meta)
    if FM.split(new)[1].encode("utf-8") != FM.split(old)[1].encode("utf-8"):
        raise SystemExit("本文が変わるため書き込まない")
    checked, _ = FM.parse(new)
    atomic_write_text(path, new)  # written with newline="": the bytes above are the bytes on disk
    return {"ok": True, "file": path.relative_to(company).as_posix(), "sources": len(checked["sources"]),
            "sections": sorted(checked["sections"], key=lambda k: (len(k), k)),
            "unregistered": _unregistered(company, checked)}


def check(company: Path) -> dict:
    rows, issues = [], 0
    for path in sorted((company / "raw").rglob("*.md")):
        row: dict = {"file": path.relative_to(company).as_posix()}
        try:
            meta, _ = FM.parse(path.read_text(encoding="utf-8"))
        except FM.FrontMatterError as e:
            row["error"] = str(e)
            issues += 1
        else:
            row["front_matter"] = meta is not None
            if meta:
                row["sections"] = len(meta["sections"])
                unregistered = _unregistered(company, meta)
                if unregistered:
                    row["unregistered"] = unregistered
                    issues += 1
        rows.append(row)
    return {"ok": issues == 0, "with_front_matter": sum(bool(r.get("front_matter")) for r in rows),
            "files": len(rows), "rows": rows}


def main(argv: list[str] | None = None) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--company", required=True)
    p_apply.add_argument("--file", required=True, help="企業ディレクトリからの相対パス（raw/...）")
    p_apply.add_argument("--spec", required=True, help="sources と sections の JSON ファイル")
    p_check = sub.add_parser("check")
    p_check.add_argument("--company", required=True)
    args = parser.parse_args(argv)
    company = company_dir(args.company)
    try:
        if args.cmd == "apply":
            spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
            result = apply(company, args.file, spec)
        else:
            result = check(company)
    except FM.FrontMatterError as e:
        result = {"ok": False, "error": str(e)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
