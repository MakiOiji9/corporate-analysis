"""Parallel sub-agents call fetch.py / tdnet_summary.py at the same time.
These tests hammer the shared files from several processes."""
import csv
import multiprocessing as mp
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

WORKERS = 6
DOCS_PER_WORKER = 8


def _store_many(company: str, worker: int) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from common import store_document
    for i in range(DOCS_PER_WORKER):
        data = f"doc-{worker}-{i}".encode()
        store_document(Path(company), data, f"w{worker}_{i}.pdf", {"doc_type": "t", "doc_id": f"{worker}-{i}"})
        # every worker also stores one shared document -> must be saved exactly once
        store_document(Path(company), b"shared", "shared.pdf", {"doc_type": "t", "doc_id": "shared"})


def _upsert_many(csv_path: str, worker: int) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tdnet_summary import upsert_rows
    for i in range(DOCS_PER_WORKER):
        upsert_rows(Path(csv_path), [{
            "doc_id": f"{worker}-{i}", "document": "", "filing_date": "", "fiscal_year_end": "",
            "context": "c", "element": "NetSales", "value": str(i), "unit": "百万円"}])


def _run(target, *args) -> None:
    ctx = mp.get_context("spawn")
    procs = [ctx.Process(target=target, args=(*args, w)) for w in range(WORKERS)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=120)
        assert p.exitcode == 0


def test_parallel_store_document_keeps_manifest_consistent(tmp_path):
    _run(_store_many, str(tmp_path))
    with (tmp_path / "sources" / "manifest.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == WORKERS * DOCS_PER_WORKER + 1  # +1 shared doc saved once
    assert len({r["sha256"] for r in rows}) == len(rows)


def test_parallel_upsert_loses_no_rows(tmp_path):
    out = tmp_path / "data" / "tdnet_facts.csv"
    _run(_upsert_many, str(out))
    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == WORKERS * DOCS_PER_WORKER
