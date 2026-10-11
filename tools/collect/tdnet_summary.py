"""Extract the summary facts from a TDnet 決算短信 iXBRL (.htm).

Usage:
  tdnet_summary.py <file.htm>                              # print facts as a markdown table
  tdnet_summary.py <file.htm> --company <dir> --doc-id ID  # also upsert into data/tdnet_facts.csv

Values are normalised: JPY -> 百万円, Pure -> %, JPYPerShares -> 円, Shares -> 株.
"""
from __future__ import annotations

import argparse
import html
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import company_dir, file_lock, read_csv_rows, utf8_stdout, write_csv_atomic  # noqa: E402

FACT_FIELDS = ["doc_id", "document", "filing_date", "fiscal_year_end",
               "context", "element", "value", "unit"]
TAG_RE = re.compile(r"<[^>]+>")
NONFRACTION_RE = re.compile(
    r"<ix:nonFraction\b([^>]*?)(?:/>|>(.*?)</ix:nonFraction>)", re.DOTALL)
META_NAMES = ("DocumentName", "FilingDate", "FiscalYearEnd", "SecuritiesCode", "CompanyName")
ATTR_RE = re.compile(r'([\w:]+)="([^"]*)"')
UNIT_LABELS = {"JPY": "百万円", "Pure": "%", "JPYPerShares": "円", "Shares": "株"}
JPY_PER_MILLION = 1_000_000


@dataclass(frozen=True)
class Fact:
    context: str
    element: str
    value: float | None
    unit: str


def _number(attrs: dict, inner: str) -> float | None:
    if attrs.get("xsi:nil") == "true":
        return None
    digits = re.sub(r"[^\d.]", "", TAG_RE.sub("", inner or ""))
    if not digits:
        return None
    value = float(digits) * (10 ** int(attrs.get("scale", "0")))
    if attrs.get("sign") == "-":
        value = -value
    unit = attrs.get("unitRef", "")
    if unit == "JPY":
        return value / JPY_PER_MILLION
    if unit == "Pure":
        return round(value * 100, 6)
    return value


def parse_facts(source: str) -> list[Fact]:
    facts = []
    for attr_text, inner in NONFRACTION_RE.findall(source):
        attrs = dict(ATTR_RE.findall(attr_text))
        unit = attrs.get("unitRef", "")
        facts.append(Fact(
            context=attrs.get("contextRef", ""),
            element=attrs.get("name", "").split(":")[-1],
            value=_number(attrs, inner),
            unit=UNIT_LABELS.get(unit, unit),
        ))
    return facts


def parse_meta(source: str) -> dict:
    """Look up each meta tag separately: nonNumeric tags can be nested."""
    meta = {}
    for name in META_NAMES:
        tag = re.search(rf'<ix:nonNumeric\b[^>]*name="tse-ed-t:{name}"[^>]*>', source)
        if not tag:
            continue
        rest = source[tag.end():]
        end = min((i for i in (rest.find("</ix:nonNumeric>"), rest.find("<ix:nonNumeric")) if i >= 0),
                  default=len(rest))
        inner = rest[:end]
        meta[name] = html.unescape(TAG_RE.sub("", inner)).strip()
    return meta


def _fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def to_rows(facts: list[Fact], meta: dict, doc_id: str) -> list[dict]:
    return [{
        "doc_id": doc_id,
        "document": meta.get("DocumentName", ""),
        "filing_date": meta.get("FilingDate", ""),
        "fiscal_year_end": meta.get("FiscalYearEnd", ""),
        "context": f.context,
        "element": f.element,
        "value": "" if f.value is None else _fmt(f.value),
        "unit": f.unit,
    } for f in facts if f.value is not None]


def upsert_rows(csv_path: Path, rows: list[dict]) -> int:
    """Replace rows of the same doc_id, keep others (process-safe). Returns number written."""
    doc_ids = {r["doc_id"] for r in rows}
    with file_lock(csv_path):
        kept = [r for r in read_csv_rows(csv_path) if r["doc_id"] not in doc_ids]
        write_csv_atomic(csv_path, FACT_FIELDS, kept + rows)
    return len(rows)


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--company")
    ap.add_argument("--doc-id", default="")
    args = ap.parse_args()

    source = Path(args.file).read_text(encoding="utf-8", errors="replace")
    meta = parse_meta(source)
    rows = to_rows(parse_facts(source), meta, args.doc_id or Path(args.file).stem)
    print(f"# {meta.get('DocumentName', '')} / 提出日 {meta.get('FilingDate', '')} / 期末 {meta.get('FiscalYearEnd', '')}")
    print("| context | element | value | unit |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r['context']} | {r['element']} | {r['value']} | {r['unit']} |")
    if args.company:
        out = company_dir(args.company) / "data" / "tdnet_facts.csv"
        print(f"\nwrote {upsert_rows(out, rows)} rows -> {out}")


if __name__ == "__main__":
    main()
