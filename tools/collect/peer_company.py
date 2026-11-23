"""The directory of a peer company, where its originals fetched for another company's peer comparison are kept.

Usage:
  peer_company.py ensure --ticker 6954 --name fanuc --peer-of 6506_yaskawa

ensure  finds companies/<ticker>_* (any name: one directory per ticker), else creates companies/<ticker>_<name>/
        with sources/manifest.csv and peer.json. Then fetch.py / edinet.py --company <that dir> store the peer's
        originals there (doc types as for the company itself: yuho, tanshin, presentation, edinet-csv, ...).
        When the peer is analysed later (collect-company-info / /company-report), the originals already in its
        manifest are not fetched again (fetch.py --doc-id / edinet.py fetch print EXISTING).
peer.json  {ticker, name, peer_of: [company dirs], created}: written only by this script. A directory with
        peer.json and no status.md is "未分析（同業として収集のみ）" (an_common.peer_only).
stdout is one JSON line: {ok, dir, created, peer_only}.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import (MANIFEST_FIELDS, REPO_ROOT, atomic_write_text, file_lock, today, utf8_stdout,  # noqa: E402
                    write_csv_atomic)

PEER_FILE = "peer.json"
TICKER = re.compile(r"^[0-9A-Z]{4}$|^[A-Z][A-Z.]{0,9}$")  # 4-character Japanese code (7203, 285A) or a US ticker
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def find_dir(root: Path, ticker: str) -> Path | None:
    base = root / "companies"
    hits = [p for p in base.glob("*_*") if p.is_dir() and p.name.split("_", 1)[0].upper() == ticker.upper()]
    if len(hits) > 1:
        raise SystemExit(f"more than one directory for {ticker}: {', '.join(sorted(h.name for h in hits))}")
    return hits[0] if hits else None


def peer_only(path: Path) -> bool:
    return (path / PEER_FILE).is_file() and not (path / "status.md").is_file()


def ensure(root: Path, ticker: str, name: str, peer_of: str) -> dict:
    ticker = ticker.upper()
    if not TICKER.match(ticker):
        raise SystemExit(f"ticker は4文字の証券コード（例 7203、285A）か米国のティッカー（例 AAPL）: {ticker}")
    if not NAME.match(name):
        raise SystemExit(f"name は半角小文字・数字・ハイフンだけ（例 fanuc）: {name}")
    path = find_dir(root, ticker)
    created = path is None
    if created:
        path = root / "companies" / f"{ticker}_{name}"
        (path / "sources").mkdir(parents=True)
        write_csv_atomic(path / "sources" / "manifest.csv", MANIFEST_FIELDS, [])
    info_path = path / PEER_FILE
    with file_lock(info_path):
        if info_path.is_file():
            info = json.loads(info_path.read_text(encoding="utf-8"))
        elif created:
            info = {"ticker": ticker, "name": name, "peer_of": [], "created": today()}
        else:
            info = None  # a company analysed on its own: no peer.json, its sources/ is used as is
        if info is not None:
            if peer_of and peer_of not in info["peer_of"]:
                info["peer_of"] = sorted(info["peer_of"] + [peer_of])
            atomic_write_text(info_path, json.dumps(info, ensure_ascii=False, indent=1) + "\n")
    if not (path / "sources" / "manifest.csv").is_file():
        (path / "sources").mkdir(parents=True, exist_ok=True)
        write_csv_atomic(path / "sources" / "manifest.csv", MANIFEST_FIELDS, [])
    return {"ok": True, "dir": path.relative_to(root).as_posix(), "created": created, "peer_only": peer_only(path)}


def main() -> None:
    utf8_stdout()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("ensure",))
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--name", required=True, help="英語名（半角小文字・数字・ハイフン）。既にディレクトリがあればそちらを使う")
    ap.add_argument("--peer-of", required=True, help="同業比較をしている企業のディレクトリ名（例 6506_yaskawa）")
    args = ap.parse_args()
    print(json.dumps(ensure(REPO_ROOT, args.ticker, args.name, args.peer_of), ensure_ascii=False))


if __name__ == "__main__":
    main()
