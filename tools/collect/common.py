"""Shared helpers for tools/collect scripts (paths, .env, HTTP, manifest)."""
from __future__ import annotations

import contextlib
import csv
import datetime as dt
import hashlib
import io
import os
import sys
import time
from pathlib import Path
from typing import Iterator

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
LOCK_TIMEOUT_SEC = 120
LOCK_STALE_SEC = 300  # a lock older than this is assumed abandoned by a crashed process
LOCK_POLL_SEC = 0.05
REPLACE_RETRIES = 50  # Windows: os.replace fails while another process has the file open


@contextlib.contextmanager
def file_lock(target: Path) -> Iterator[None]:
    """Cross-process lock for <target> using an exclusive '<target>.lock' file.

    Parallel sub-agents run fetch.py / tdnet_summary.py at the same time, so every
    read-modify-write of a shared file (manifest.csv, data/*.csv) must hold this lock.
    """
    lock = target.with_name(target.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + LOCK_TIMEOUT_SEC
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except (FileExistsError, PermissionError):  # Windows: PermissionError while being deleted
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > LOCK_STALE_SEC:
                    lock.unlink()
                    continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"could not acquire {lock} within {LOCK_TIMEOUT_SEC}s")
            time.sleep(LOCK_POLL_SEC)
    try:
        yield
    finally:
        for _ in range(REPLACE_RETRIES):
            try:
                lock.unlink()
                break
            except FileNotFoundError:
                break
            except PermissionError:
                time.sleep(LOCK_POLL_SEC)


def atomic_write_text(path: Path, text: str) -> None:
    """Write via a temp file + os.replace so readers never see a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    for attempt in range(REPLACE_RETRIES):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == REPLACE_RETRIES - 1:
                raise
            time.sleep(LOCK_POLL_SEC)


def write_csv_atomic(path: Path, fields: list[str], rows: list[dict]) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    writer.writerows({k: r.get(k, "") for k in fields} for r in rows)
    atomic_write_text(path, buf.getvalue())


def read_csv_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


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
    return read_csv_rows(manifest_path(company))


def find_by_hash(company: Path, digest: str) -> dict | None:
    return next((r for r in read_manifest(company) if r.get("sha256") == digest), None)


def _unique_target(directory: Path, filename: str) -> Path:
    """Different documents may share a name (e.g. two '00.pdf'); never overwrite."""
    target = directory / filename
    stem, suffix, n = target.stem, target.suffix, 2
    while target.exists():
        target = directory / f"{stem}_{n}{suffix}"
        n += 1
    return target


def store_document(company: Path, data: bytes, filename: str, meta: dict) -> tuple[Path, bool]:
    """Save bytes under sources/<today>/ and register in manifest (process-safe).

    Returns (path, is_new). Duplicate content (same sha256) is not saved again.
    """
    digest = sha256_bytes(data)
    manifest = manifest_path(company)
    with file_lock(manifest):
        rows = read_csv_rows(manifest)
        existing = next((r for r in rows if r.get("sha256") == digest), None)
        if existing:
            return company / existing["local_path"], False
        target_dir = company / "sources" / today()
        target_dir.mkdir(parents=True, exist_ok=True)
        target = _unique_target(target_dir, filename)
        target.write_bytes(data)
        rows.append({**meta, "fetched_date": today(), "sha256": digest,
                     "local_path": target.relative_to(company).as_posix()})
        write_csv_atomic(manifest, MANIFEST_FIELDS, rows)
    return target, True
