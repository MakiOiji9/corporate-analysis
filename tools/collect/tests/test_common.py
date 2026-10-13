import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

import common  # noqa: E402
from common import USER_AGENT, read_manifest, store_document, user_agent_for  # noqa: E402
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


def test_sources_admin_remove_allows_refetch(tmp_path):
    from sources_admin import remove

    meta = {"doc_type": "CBRS_x", "doc_id": "--company", "url": "https://example.invalid/a.htm"}
    path, _ = store_document(tmp_path, b"<html>1</html>", "--company", meta)
    keep, _ = store_document(tmp_path, b"<html>2</html>", "keep.htm", {"doc_type": "10q"})
    removed = remove(tmp_path, path.relative_to(tmp_path).as_posix())
    assert removed["doc_id"] == "--company" and not path.exists()
    assert [r["local_path"] for r in read_manifest(tmp_path)] == [keep.relative_to(tmp_path).as_posix()]
    _, is_new = store_document(tmp_path, b"<html>1</html>", "a.htm", {"doc_type": "s-1"})
    assert is_new


def test_default_name_uses_parent_dir_for_eir_paths():
    url = "https://ssl4.eir-parts.net/doc/3798/yuho_pdf/S100YCBQ/00.pdf"
    assert default_name(url, "", "application/pdf") == "S100YCBQ.pdf"
    assert default_name("https://www2.jpx.co.jp/disc/37980/1401.pdf", "", "") == "1401.pdf"


def test_user_agent_is_browser_like_outside_sec():
    assert user_agent_for("https://www2.jpx.co.jp/disc/37980/1401.pdf") == USER_AGENT


def test_user_agent_uses_contact_agent_for_sec_hosts(monkeypatch):
    monkeypatch.setattr(common, "load_env", lambda: None)
    monkeypatch.setenv("SEC_USER_AGENT", "corporate-analysis research test@example.invalid")
    for url in ("https://www.sec.gov/Archives/edgar/data/1/a.htm",
                "https://data.sec.gov/submissions/CIK0000000001.json"):
        assert user_agent_for(url) == "corporate-analysis research test@example.invalid"
    assert user_agent_for("https://notsec.gov.example.invalid/") == USER_AGENT


def test_user_agent_for_sec_requires_setting(monkeypatch):
    monkeypatch.setattr(common, "load_env", lambda: None)
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        user_agent_for("https://www.sec.gov/")


def test_scan_windows_targets_filing_month():
    windows = scan_windows(fy_end_month=3, years=1)
    assert all(start.month == 6 and start.day == 1 for start, _ in windows)
