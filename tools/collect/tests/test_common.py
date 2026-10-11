import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common import read_manifest, store_document  # noqa: E402
from edinet import scan_windows  # noqa: E402
from fetch import default_name  # noqa: E402


def test_store_document_dedupes_by_hash(tmp_path):
    meta = {"doc_type": "yuho", "doc_id": "S1", "url": "https://example.invalid/a.pdf"}
    first, is_new = store_document(tmp_path, b"%PDF-1", "S1.pdf", meta)
    second, again = store_document(tmp_path, b"%PDF-1", "S1-copy.pdf", meta)
    assert is_new and not again
    assert first == second and first.read_bytes() == b"%PDF-1"
    rows = read_manifest(tmp_path)
    assert len(rows) == 1 and rows[0]["local_path"].startswith("sources/")


def test_default_name_uses_parent_dir_for_eir_paths():
    url = "https://ssl4.eir-parts.net/doc/3798/yuho_pdf/S100YCBQ/00.pdf"
    assert default_name(url, "", "application/pdf") == "S100YCBQ.pdf"
    assert default_name("https://www2.jpx.co.jp/disc/37980/1401.pdf", "", "") == "1401.pdf"


def test_scan_windows_targets_filing_month():
    windows = scan_windows(fy_end_month=3, years=1)
    assert all(start.month == 6 and start.day == 1 for start, _ in windows)
