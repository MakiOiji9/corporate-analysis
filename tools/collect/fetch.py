"""Download a document into companies/<dir>/sources/<today>/ and register it in manifest.csv.

Usage:
  fetch.py <url> --company <dir> --type <doc_type> [--period 2026-03] [--published 2026-05-13]
           [--doc-id ID] [--referer URL] [--name FILE] [--note TEXT] [--text]

doc_type examples: yuho, hanki, tanshin, presentation, qa, disclosure, press, other
Identical content (same sha256) is not saved twice; the existing path is printed.
--text also writes <file>.txt via pdf_text.py (page-delimited).
Exit code 2 on HTTP failure (message tells which route to try next).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import company_dir, http_get, store_document, utf8_stdout  # noqa: E402

SAFE_NAME = re.compile(r"[^\w.\-]+")


def default_name(url: str, doc_id: str, content_type: str) -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix.lower()
    if suffix not in (".pdf", ".htm", ".html", ".zip", ".csv", ".xml"):
        suffix = ".pdf" if "pdf" in content_type else ".htm"
    stem = doc_id or Path(path).stem
    if stem in ("00", "index", ""):  # e.g. eir-parts .../S100YCBQ/00.pdf
        stem = Path(path).parent.name
    return SAFE_NAME.sub("_", stem) + suffix


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("url")
    ap.add_argument("--company", required=True)
    ap.add_argument("--type", required=True, dest="doc_type")
    ap.add_argument("--period", default="")
    ap.add_argument("--published", default="")
    ap.add_argument("--doc-id", default="")
    ap.add_argument("--referer")
    ap.add_argument("--name")
    ap.add_argument("--note", default="")
    ap.add_argument("--text", action="store_true")
    args = ap.parse_args()

    company = company_dir(args.company)
    try:
        resp = http_get(args.url, referer=args.referer)
    except Exception as exc:  # noqa: BLE001 - report any network/HTTP failure to the caller
        print(f"FETCH_FAILED {args.url}: {exc}\n"
              "-> see .ai/templates/collect-company-info/source-access.md for alternative routes")
        sys.exit(2)

    name = args.name or default_name(args.url, args.doc_id, resp.headers.get("Content-Type", ""))
    path, is_new = store_document(company, resp.content, name, {
        "doc_type": args.doc_type, "period": args.period, "published_date": args.published,
        "doc_id": args.doc_id or Path(name).stem, "url": args.url, "note": args.note,
    })
    print(f"{'SAVED' if is_new else 'DUPLICATE'} {path}")
    if args.text and path.suffix.lower() in (".pdf", ".htm", ".html"):
        from pdf_text import convert
        print(f"TEXT {convert(path)}")


if __name__ == "__main__":
    main()
