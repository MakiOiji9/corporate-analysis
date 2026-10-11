"""Shared helpers for tools/collect scripts (paths, .env, HTTP, manifest)."""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / ".cache"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
MANIFEST_FIELDS = [
    "fetched_date", "doc_type", "period", "published_date",
    "doc_id", "url", "sha256", "local_path", "note",
]
HTTP_TIMEOUT_SEC = 60


def utf8_stdout() -> None:
    """Make print() safe for Japanese text on Windows consoles."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def today() -> str:
    return dt.date.today().isoformat()


def load_env() -> None:
    """Load KEY=VALUE pairs from <repo>/.env without overriding real env vars."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() and not os.environ.get(key.strip()):
            os.environ[key.strip()] = value.strip()


def company_dir(arg: str) -> Path:
    """Accept 'companies/3798_uls-group', '3798_uls-group' or an absolute path."""
    path = Path(arg)
    if not path.is_absolute():
        path = REPO_ROOT / path if (REPO_ROOT / path).exists() else REPO_ROOT / "companies" / arg
    if not path.is_dir():
        raise SystemExit(f"company directory not found: {arg}")
    return path


def http_get(url: str, referer: str | None = None, params: dict | None = None):
    """GET with browser-like headers and certifi CA bundle. Raises on HTTP error."""
    import certifi
    import requests

    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    resp = requests.get(url, headers=headers, params=params,
                        timeout=HTTP_TIMEOUT_SEC, verify=certifi.where())
    resp.raise_for_status()
    return resp


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def manifest_path(company: Path) -> Path:
    return company / "sources" / "manifest.csv"


def read_manifest(company: Path) -> list[dict]:
    path = manifest_path(company)
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def append_manifest(company: Path, row: dict) -> None:
    path = manifest_path(company)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow({k: row.get(k, "") for k in MANIFEST_FIELDS})


def find_by_hash(company: Path, digest: str) -> dict | None:
    return next((r for r in read_manifest(company) if r.get("sha256") == digest), None)


def store_document(company: Path, data: bytes, filename: str, meta: dict) -> tuple[Path, bool]:
    """Save bytes under sources/<today>/ and register in manifest.

    Returns (path, is_new). Duplicate content (same sha256) is not saved again.
    """
    digest = sha256_bytes(data)
    existing = find_by_hash(company, digest)
    if existing:
        return company / existing["local_path"], False
    target = company / "sources" / today() / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    append_manifest(company, {
        **meta,
        "fetched_date": today(),
        "sha256": digest,
        "local_path": target.relative_to(company).as_posix(),
    })
    return target, True
