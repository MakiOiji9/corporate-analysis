"""issue_request: read a company-analysis request from a GitHub Issue (Issue Forms) and validate it.

Usage:
  issue_request.py parse --body-file F

The body comes from .github/ISSUE_TEMPLATE/company-analysis.yml: one "### {label}" heading per field followed by
its value ("_No response_" when left empty). Only the four fields that collect-company-info needs without asking
(ticker, name, url, market) are taken, and each is checked against a strict pattern, because the values become
arguments of a Claude Code command in .github/workflows/issue-company-report.yml. The rest of the body is ignored.
dir: the companies/ directory to work in: the existing one whose ticker matches, else "{ticker}_{name}". Whether
the collection is needed is not decided here (tools/collect/collect_progress.py looks at what is collected).
stdout is one JSON line. Exit 1 when not ok.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "analysis"), str(HERE.parent / "collect")]

import an_common as A  # noqa: E402
from common import utf8_stdout  # noqa: E402

# Must match the `label` of each field in .github/ISSUE_TEMPLATE/company-analysis.yml
LABELS = {"ticker": "銘柄コード", "name": "企業名（英語）", "url": "ホームページ URL", "market": "市場"}
MARKETS = ("japan", "us")
NO_RESPONSE = "_No response_"
HEADING = re.compile(r"^###\s+(.+?)\s*$", re.M)
TICKER = {"japan": re.compile(r"^[0-9]{3}[0-9A-Z]$"), "us": re.compile(r"^[A-Z][A-Z.\-]{0,9}$")}
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}$")
URL = re.compile(r"^https://[A-Za-z0-9.\-]+(:[0-9]+)?(/[A-Za-z0-9._~%/?#&=+\-]*)?$")


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload.get("ok", True) else 1


def sections(body: str) -> dict[str, str]:
    """{heading: value} of an Issue Forms body; an empty field is ''."""
    text = body.replace("\r\n", "\n")
    marks = list(HEADING.finditer(text))
    out = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        value = text[m.end():end].strip()
        out[m.group(1)] = "" if value == NO_RESPONSE else value
    return out


def existing_dir(root: Path, ticker: str) -> str | None:
    hits = [d.name for d in A.company_dirs(root) if d.name.split("_", 1)[0].lower() == ticker.lower()]
    return hits[0] if len(hits) == 1 else None


def validate(fields: dict[str, str]) -> list[str]:
    errors = [f"「{LABELS[k]}」が未記入" for k in LABELS if not fields.get(k)]
    market, ticker = fields.get("market", ""), fields.get("ticker", "")
    if market and market not in MARKETS:
        errors.append(f"「{LABELS['market']}」は {' / '.join(MARKETS)} のどちらか: {market}")
    elif market and ticker and not TICKER[market].match(ticker):
        example = "4桁の証券コード（例 7203、285A）" if market == "japan" else "英大文字のティッカー（例 AAPL、BRK.B）"
        errors.append(f"「{LABELS['ticker']}」は {example}: {ticker}")
    if fields.get("name") and not NAME.match(fields["name"]):
        errors.append(f"「{LABELS['name']}」は半角小文字・数字・ハイフンだけ（例 toyota）: {fields['name']}")
    if fields.get("url") and not URL.match(fields["url"]):
        errors.append(f"「{LABELS['url']}」は https:// で始まる URL（空白・引用符などを含まない）: {fields['url']}")
    return errors


def parse(body: str, root: Path) -> dict:
    found = sections(body)
    fields = {key: found.get(label, "").strip() for key, label in LABELS.items()}
    fields = {**fields, "ticker": fields["ticker"].upper(), "market": fields["market"].lower()}
    errors = validate(fields)
    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, **fields,
            "dir": existing_dir(root, fields["ticker"]) or f"{fields['ticker']}_{fields['name']}"}


def main(argv: list[str] | None = None, root: Path = A.REPO_ROOT) -> int:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("parse")
    p.add_argument("--body-file", required=True, help="Issue の本文を保存したファイル")
    args = parser.parse_args(argv)
    try:
        body = Path(args.body_file).read_text(encoding="utf-8")
    except OSError as exc:
        return emit({"ok": False, "errors": [f"本文を読めない: {exc}"]})
    return emit(parse(body, root))


if __name__ == "__main__":
    sys.exit(main())
