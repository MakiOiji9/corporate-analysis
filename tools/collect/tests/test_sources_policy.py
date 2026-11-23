"""Originals kept in git (2026-11-23): the 20MB limit, the doc-id skip and the peer company directory."""
import json
import sys
from pathlib import Path

import pytest

COLLECT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(COLLECT), str(COLLECT.parents[0] / "analysis")]

import an_common  # noqa: E402
import common  # noqa: E402
import edinet  # noqa: E402
import fetch  # noqa: E402
import peer_company as PC  # noqa: E402
from common import find_by_doc_id, read_manifest, store_document  # noqa: E402


def test_large_file_goes_to_ignored_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "LARGE_FILE_BYTES", 10)
    small, _ = store_document(tmp_path, b"12345", "a.pdf", {"doc_type": "yuho", "doc_id": "A"})
    big, _ = store_document(tmp_path, b"x" * 11, "b.pdf", {"doc_type": "yuho", "doc_id": "B", "note": "EDINET"})
    assert "_large" not in small.parts and big.parts[-3] == "_large"
    notes = {r["doc_id"]: r["note"] for r in read_manifest(tmp_path)}
    assert notes == {"A": "", "B": "EDINET; git 管理外（20MB 超）"}


def test_gitignore_keeps_originals_but_not_large_or_extracted():
    text = (COLLECT.parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "companies/*/sources/**\n" not in text
    for line in ("companies/*/sources/**/_large/", "companies/*/sources/**/*_csv/", "companies/*/sources/_removed/"):
        assert line in text


def test_find_by_doc_id_needs_type_and_file(tmp_path):
    path, _ = store_document(tmp_path, b"zip", "S1_csv.zip", {"doc_type": "edinet-csv", "doc_id": "S1"})
    assert find_by_doc_id(tmp_path, "S1", "edinet-csv")["local_path"].endswith("S1_csv.zip")
    assert find_by_doc_id(tmp_path, "S1", "edinet-pdf") is None
    assert find_by_doc_id(tmp_path, "", "edinet-csv") is None
    path.unlink()
    assert find_by_doc_id(tmp_path, "S1", "edinet-csv") is None  # registered but not on disk: fetch again


def _no_network(*_a, **_k):
    raise AssertionError("must not download")


def test_fetch_skips_existing_doc_id(tmp_path, monkeypatch, capsys):
    store_document(tmp_path, b"%PDF", "S1.pdf", {"doc_type": "yuho", "doc_id": "S1"})
    monkeypatch.setattr(fetch, "http_get", _no_network)
    monkeypatch.setattr(sys, "argv", ["fetch.py", "https://example.invalid/S1.pdf", "--company", str(tmp_path),
                                      "--type", "yuho", "--doc-id", "S1"])
    fetch.main()
    assert capsys.readouterr().out.startswith("EXISTING ")


def test_edinet_fetch_skips_existing_without_key(tmp_path, monkeypatch, capsys):
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("XBRL_TO_CSV/jpcrp.csv", "x")
    store_document(tmp_path, buf.getvalue(), "S1_csv.zip", {"doc_type": "edinet-csv", "doc_id": "S1"})
    monkeypatch.setattr(edinet, "http_get", _no_network)
    monkeypatch.setattr(edinet, "api_key", _no_network)
    args = edinet.argparse.Namespace(doc_id="S1", company=str(tmp_path), kind="csv", period="", force=False)
    edinet.cmd_fetch(args)
    out = capsys.readouterr().out
    assert out.startswith("EXISTING ") and "EXTRACTED" in out


def test_peer_dir_created_once_per_ticker(tmp_path):
    (tmp_path / "companies").mkdir()
    first = PC.ensure(tmp_path, "6954", "fanuc", "6506_yaskawa")
    again = PC.ensure(tmp_path, "6954", "fanuc-corp", "6268_nabtesco")  # another name: the same directory
    assert first == {"ok": True, "dir": "companies/6954_fanuc", "created": True, "peer_only": True}
    assert again["dir"] == "companies/6954_fanuc" and not again["created"]
    info = json.loads((tmp_path / "companies/6954_fanuc/peer.json").read_text(encoding="utf-8"))
    assert info["peer_of"] == ["6268_nabtesco", "6506_yaskawa"]
    assert (tmp_path / "companies/6954_fanuc/sources/manifest.csv").read_text(encoding="utf-8").startswith(
        "fetched_date,")


def test_peer_of_an_analysed_company_uses_its_dir(tmp_path):
    own = tmp_path / "companies" / "6506_yaskawa"
    (own / "sources").mkdir(parents=True)
    (own / "status.md").write_text("x", encoding="utf-8")
    got = PC.ensure(tmp_path, "6506", "yaskawa-electric", "6954_fanuc")
    assert got == {"ok": True, "dir": "companies/6506_yaskawa", "created": False, "peer_only": False}
    assert not (own / "peer.json").exists()  # an analysed company gets no peer.json


def test_peer_only_until_analysed(tmp_path):
    (tmp_path / "companies").mkdir()
    path = tmp_path / PC.ensure(tmp_path, "AAPL", "apple", "CBRS_cerebras")["dir"]
    assert an_common.peer_only(path) and PC.peer_only(path)
    (path / "status.md").write_text("x", encoding="utf-8")
    assert not an_common.peer_only(path)


@pytest.mark.parametrize("ticker,name", [("69541", "fanuc"), ("6954", "Fanuc"), ("6954", "fanuc_corp")])
def test_peer_rejects_bad_names(tmp_path, ticker, name):
    (tmp_path / "companies").mkdir()
    with pytest.raises(SystemExit):
        PC.ensure(tmp_path, ticker, name, "6506_yaskawa")


class _Resp:
    def __init__(self, content: bytes, ctype: str = "application/octet-stream"):
        self.content, self.headers, self.text = content, {"Content-Type": ctype}, content.decode("latin-1")


def _registered(tmp_path, name: str, data: bytes, url: str) -> str:
    path, _ = store_document(tmp_path, data, name, {"doc_type": "yuho", "doc_id": name, "url": url})
    path.unlink()  # as before originals were kept in git: registered, not on disk
    return path.relative_to(tmp_path).as_posix()


def test_restore_writes_only_matching_content(tmp_path, monkeypatch):
    import sources_admin as SA
    monkeypatch.setenv("EDINET_API_KEY", "k")
    ok = _registered(tmp_path, "a.zip", b"same", "https://api.edinet-fsa.go.jp/api/v2/documents/S1?type=5")
    changed = _registered(tmp_path, "b.htm", b"old", "https://www.example.co.jp/ir/")
    other = _registered(tmp_path, "c.pdf", b"x", "https://other.example/c.pdf")
    seen = {}

    def get(url, params=None):
        seen[url] = params
        return _Resp({"https://api.edinet-fsa.go.jp/api/v2/documents/S1?type=5": b"same",
                      "https://www.example.co.jp/ir/": b"new"}[url])

    out = SA.restore(tmp_path, ["api.edinet-fsa.go.jp", "www.example.co.jp"], get=get)
    assert out["restored"] == [ok] and (tmp_path / ok).read_bytes() == b"same"
    assert [m["local_path"] for m in out["mismatch"]] == [changed] and not (tmp_path / changed).exists()
    assert out["skipped_host"] == 1 and not (tmp_path / other).exists()
    assert seen["https://api.edinet-fsa.go.jp/api/v2/documents/S1?type=5"] == {"Subscription-Key": "k"}
    assert seen["https://www.example.co.jp/ir/"] is None
    again = SA.restore(tmp_path, ["api.edinet-fsa.go.jp"], get=get)
    assert again["present"] == 1 and not again["restored"]


def test_restore_moves_large_files_aside(tmp_path, monkeypatch):
    import sources_admin as SA
    rel = _registered(tmp_path, "big.pdf", b"x" * 11, "https://a.example/big.pdf")
    monkeypatch.setattr(common, "LARGE_FILE_BYTES", 10)
    out = SA.restore(tmp_path, get=lambda url, params=None: _Resp(b"x" * 11))
    assert out["large"] == ["sources/_large/" + rel.split("/", 1)[1]]
    row = read_manifest(tmp_path)[0]
    assert row["local_path"] == out["large"][0] and row["note"].endswith("git 管理外（20MB 超）")
    assert (tmp_path / row["local_path"]).is_file()


def test_restore_reports_errors(tmp_path):
    import sources_admin as SA
    _registered(tmp_path, "a.pdf", b"x", "https://a.example/a.pdf")

    def get(url, params=None):
        raise RuntimeError("403")

    out = SA.restore(tmp_path, get=get)
    assert out["failed"][0]["error"] == "403" and not out["restored"]


def test_move_peer_moves_row_and_file(tmp_path):
    import sources_admin as SA
    own = tmp_path / "companies" / "3798_uls-group"
    (own / "sources").mkdir(parents=True)
    path, _ = store_document(own, b"%PDF", "t.pdf", {"doc_type": "peer-tanshin", "doc_id": "T1",
                                                     "url": "https://www2.jpx.co.jp/disc/60880/t.pdf"})
    path.with_name("t.pdf.txt").write_text("text", encoding="utf-8")
    ghost = _registered(own, "g.pdf", b"g", "https://irbank.net/6088/results")  # registered, not on disk
    rel = path.relative_to(own).as_posix()
    got = SA.move_peer(own, rel, "6088", "sigmaxyz", "tanshin", root=tmp_path)
    SA.move_peer(own, ghost, "6088", "sigmaxyz", "irbank", root=tmp_path)
    peer = tmp_path / "companies" / "6088_sigmaxyz"
    assert got == {"dir": "companies/6088_sigmaxyz", "local_path": rel, "dup": False}
    assert (peer / rel).read_bytes() == b"%PDF" and (peer / f"{rel}.txt").exists() and not path.exists()
    rows = {r["doc_id"]: r for r in read_manifest(peer)}
    assert rows["T1"]["doc_type"] == "tanshin" and rows["T1"]["note"] == f"移動元: companies/3798_uls-group/{rel}"
    assert rows["g.pdf"]["doc_type"] == "irbank" and not (peer / ghost).exists()
    assert read_manifest(own) == []
    assert json.loads((peer / "peer.json").read_text(encoding="utf-8"))["peer_of"] == ["3798_uls-group"]


def test_move_peer_skips_duplicate(tmp_path):
    import sources_admin as SA
    a = tmp_path / "companies" / "3798_uls-group"
    b = tmp_path / "companies" / "6532_baycurrent"
    for d in (a, b):
        (d / "sources").mkdir(parents=True)
    (b / "status.md").write_text("x", encoding="utf-8")
    store_document(b, b"same", "own.pdf", {"doc_type": "tanshin", "doc_id": "X"})
    path, _ = store_document(a, b"same", "x.pdf", {"doc_type": "peer-tanshin", "doc_id": "X"})
    got = SA.move_peer(a, path.relative_to(a).as_posix(), "6532", "baycurrent", "tanshin", root=tmp_path)
    assert got["dup"] and len(read_manifest(b)) == 1 and read_manifest(a) == []
    assert not (b / "peer.json").exists() and not path.exists()


def test_restore_falls_back_to_https(tmp_path):
    import sources_admin as SA
    rel = _registered(tmp_path, "a.pdf", b"doc", "http://www.boj.or.jp/a.pdf")

    def get(url, params=None):
        if url.startswith("http://"):
            raise RuntimeError("port 80 blocked")
        return _Resp(b"doc")

    out = SA.restore(tmp_path, get=get)
    assert out["restored"] == [rel] and not out["failed"]
