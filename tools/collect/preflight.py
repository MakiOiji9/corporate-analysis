"""Pre-flight check for collect-company-info. Run before Phase 0.

Usage:  preflight.py

Prints which collection routes are available in this environment so the AI
does not spend tool calls discovering them by trial and error.
Playwright cannot be checked from Python: the AI should try one
browser_navigate call and treat any error as 'unavailable'.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import REPO_ROOT, load_env, utf8_stdout  # noqa: E402

PROBES = {
    "TDnet/JPX 開示PDF": "https://www2.jpx.co.jp/",
    "E-IR 文書（eir-parts）": "https://ssl4.eir-parts.net/",
    "EDINET API v2": "https://api.edinet-fsa.go.jp/api/v2/documents.json",
    "IRBANK": "https://irbank.net/",
}
PROBE_TIMEOUT_SEC = 10


def check_python() -> tuple[bool, str]:
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    ok = sys.version_info >= (3, 10) and in_venv
    return ok, f"Python {sys.version.split()[0]} / venv={'yes' if in_venv else 'no'} ({sys.prefix})"


def check_modules() -> tuple[bool, str]:
    missing = [m for m in ("pypdf", "requests", "certifi") if importlib.util.find_spec(m) is None]
    return not missing, "all installed" if not missing else f"missing: {', '.join(missing)}"


def check_edinet_key() -> tuple[bool, str]:
    load_env()
    if os.environ.get("EDINET_API_KEY"):
        return True, "EDINET_API_KEY is set -> Phase 2/3 use edinet.py + xbrl_financials.py"
    return False, "not set -> Phase 2/3 use fetch.py + pdf_text.py + find_pages.py (PDF route)"


def probe(url: str) -> tuple[bool, str]:
    try:
        import certifi
        import requests
        resp = requests.get(url, timeout=PROBE_TIMEOUT_SEC, verify=certifi.where(),
                            headers={"User-Agent": "Mozilla/5.0"})
        # Root URLs often answer 403/404; any non-5xx reply means the host is reachable.
        return resp.status_code < 500, f"reachable (root HTTP {resp.status_code})"
    except Exception as exc:  # noqa: BLE001 - any failure means route unavailable
        return False, type(exc).__name__


def main() -> int:
    utf8_stdout()
    rows = [("Python/venv", *check_python()), ("依存ライブラリ", *check_modules()),
            ("EDINET API キー", *check_edinet_key())]
    modules_ok = rows[1][1]
    for label, url in PROBES.items():
        rows.append((label, *(probe(url) if modules_ok else (False, "skipped (modules missing)"))))

    print(f"repo: {REPO_ROOT}")
    print("| check | ok | detail |\n|---|---|---|")
    for label, ok, detail in rows:
        print(f"| {label} | {'OK' if ok else 'NG'} | {detail} |")
    if not (rows[0][1] and modules_ok):
        print("\nFix: run tools/setup.ps1 (Windows) or tools/setup.sh, then use .venv's python.")
    print("\nPlaywright: not checkable here. Try one browser_navigate; on error use the non-browser routes.")
    return 0 if modules_ok else 1


if __name__ == "__main__":
    sys.exit(main())
