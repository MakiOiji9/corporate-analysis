"""raw_provenance.py: front matter put on a raw file of an earlier day, the body untouched (BL-01)."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import front_matter as FM  # noqa: E402
import raw_provenance as RP  # noqa: E402

BODY = "# 事業概要 — 例示株式会社（1234）\n\n**収集日**: 2026-01-10\n\n## 7. 継続率\n| 指標 | 当期 |\n|---|---|\n| 継続率 | — |\n"
SPEC = {"sources": [{"id": "DOC1", "title": "質疑応答", "confidence": "一次"},
                    {"id": "w1", "title": "記事", "url": "https://example.com", "confidence": "二次"}],
        "sections": {"7": [{"source": "DOC1", "pages": "3"}]}}
REL = "raw/ir/2026-01-10_business-overview.md"


def _company(tmp_path: Path) -> Path:
    company = tmp_path / "1234_example"
    (company / "raw" / "ir").mkdir(parents=True)
    (company / REL).write_bytes(BODY.encode("utf-8"))
    (company / "sources").mkdir()
    (company / "sources" / "manifest.csv").write_text(
        "fetched_date,doc_type,period,published_date,doc_id,url,sha256,local_path,note\n"
        "2026-01-10,qa,,,DOC1,https://example.com/qa.pdf,x,sources/2026-01-10/qa.pdf,\n", encoding="utf-8")
    return company


def test_apply_prefixes_front_matter_and_keeps_the_body(tmp_path):
    company = _company(tmp_path)
    out = RP.apply(company, REL, SPEC)
    assert out == {"ok": True, "file": REL, "sources": 2, "sections": ["7"], "unregistered": []}
    meta, body = FM.parse((company / REL).read_text(encoding="utf-8"))
    assert body == BODY and meta["collected"] == "2026-01-10"


def test_apply_keeps_crlf_line_endings_byte_for_byte(tmp_path):
    company = _company(tmp_path)
    crlf = BODY.replace("\n", "\r\n").encode("utf-8")
    (company / REL).write_bytes(crlf)
    RP.apply(company, REL, SPEC)
    assert (company / REL).read_bytes().endswith(crlf)


def test_apply_replaces_an_existing_front_matter(tmp_path):
    company = _company(tmp_path)
    RP.apply(company, REL, SPEC)
    RP.apply(company, REL, {**SPEC, "sections": {"7": [{"source": "w1", "pages": None}]}})
    meta, body = FM.parse((company / REL).read_text(encoding="utf-8"))
    assert body == BODY and meta["sections"] == {"7": [{"source": "w1", "pages": None}]}


def test_apply_refuses_files_outside_raw_and_malformed_specs(tmp_path):
    company = _company(tmp_path)
    with pytest.raises(SystemExit, match="raw の md"):
        RP.apply(company, "sources/manifest.csv", SPEC)
    with pytest.raises(FM.FrontMatterError):
        RP.apply(company, REL, {**SPEC, "sections": {"7": [{"source": "DOC9", "pages": "1"}]}})
    assert (company / REL).read_text(encoding="utf-8") == BODY


def test_check_lists_ids_neither_in_the_manifest_nor_local(tmp_path, capsys):
    company = _company(tmp_path)
    RP.apply(company, REL, {**SPEC, "sources": SPEC["sources"] + [{"id": "DOC5", "confidence": "一次"}]})
    (company / "raw" / "ir" / "2026-01-11_other.md").write_text(BODY, encoding="utf-8")
    assert RP.main(["check", "--company", str(company)]) == 1
    out = json.loads(capsys.readouterr().out)
    assert out["with_front_matter"] == 1 and out["files"] == 2
    assert out["rows"][0]["unregistered"] == ["DOC5"] and out["rows"][1] == {"file": "raw/ir/2026-01-11_other.md",
                                                                             "front_matter": False}
