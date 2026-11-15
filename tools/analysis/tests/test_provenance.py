"""BL-01: raw front matter -> manifest.csv -> the saved original and its pages (front_matter, provenance,
an_evidence, ff_inputs.header_notes, the report's moat table)."""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "report"))

import an_evidence as EV  # noqa: E402
import cr_render as R  # noqa: E402
import ff_inputs as I  # noqa: E402
import front_matter as FM  # noqa: E402
import provenance as PV  # noqa: E402
from common import MANIFEST_FIELDS  # noqa: E402

BODY = ("# 有価証券報告書 抜粋 — 例示株式会社（1234）\n\n**収集日**: 2026-01-10\n**情報源**:\n"
        "- 有価証券報告書（https://example.com/yuho.pdf）— 確度: 一次\n\n"
        "> 単位: 百万円\n\n## 1. 主要な経営指標\n| 項目 | 2026年3月期 |\n|---|---|\n| 売上高 | 1,000 |\n\n"
        "## 6. 研究開発\n特許の記載なし\n\n## 8. 業界\n検索の要約\n")
META = {"provenance": 1, "collected": "2026-01-10",
        "sources": [{"id": "DOC1", "title": "有価証券報告書 第10期", "url": "https://example.com/yuho.pdf",
                     "published": "2025-06-20", "period": "2025-03", "confidence": "一次"},
                    {"id": "DOC2", "title": "決算説明資料", "confidence": "一次"},
                    {"id": "w1", "title": "業界の記事", "url": "https://example.com/news", "confidence": "検索要約"}],
        "sections": {"1": [{"source": "DOC1", "pages": "2"}], "6": [{"source": "DOC1", "pages": None}],
                     "8": [{"source": "w1", "pages": None}]}}
RAW = "2026-01-10_2025-03_yuho.md"


def _company(tmp_path: Path, text: str, originals: tuple[str, ...] = ("DOC1",)) -> Path:
    company = tmp_path / "1234_example"
    (company / "raw" / "filings").mkdir(parents=True)
    (company / "raw" / "filings" / RAW).write_text(text, encoding="utf-8")
    (company / "sources" / "2026-01-10").mkdir(parents=True)
    rows = []
    for doc in originals:
        local = f"sources/2026-01-10/{doc}.pdf"
        (company / local).write_bytes(b"%PDF")
        rows.append({"fetched_date": "2026-01-10", "doc_type": "yuho", "period": "2025-03",
                     "published_date": "2025-06-20", "doc_id": doc, "url": f"https://example.com/{doc}.pdf",
                     "sha256": doc, "local_path": local, "note": ""})
    with (company / "sources" / "manifest.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return company


# ---------- front_matter ----------

def test_front_matter_round_trip_keeps_the_body_byte_for_byte():
    text = FM.with_front_matter(BODY, META)
    meta, body = FM.parse(text)
    assert body == BODY
    assert meta["collected"] == "2026-01-10" and meta["sources"][0]["published"] == "2025-06-20"
    assert meta["sections"]["1"] == [{"source": "DOC1", "pages": "2"}]
    assert FM.with_front_matter(text, META) == text  # replacing is idempotent


def test_a_file_without_front_matter_is_all_body():
    assert FM.parse(BODY) == (None, BODY)
    assert FM.body_of(BODY) == BODY


@pytest.mark.parametrize("meta, message", [
    ({**META, "provenance": None}, "provenance"),
    ({**META, "sections": {"1": [{"source": "DOC9", "pages": "2"}]}}, "DOC9"),
    ({**META, "sources": [{"id": "DOC1", "confidence": "たぶん"}]}, "confidence"),
    ({**META, "sources": [META["sources"][0], META["sources"][0]]}, "重複"),
])
def test_front_matter_refuses_malformed_metadata(meta, message):
    with pytest.raises(FM.FrontMatterError, match=message):
        FM.validate(meta)


def test_front_matter_refuses_lines_a_table_reader_would_take_for_rows():
    text = "---\nprovenance: 1\nnote: |\n  | a | b |\n---\n" + BODY
    with pytest.raises(FM.FrontMatterError, match=r"\|"):
        FM.parse(text)


def test_hand_written_values_stay_the_strings_that_were_written():
    text = ("---\nprovenance: 1\nsources:\n- {id: 0012345, confidence: 一次}\n- {id: 1_0, confidence: 一次}\n"
            "sections:\n  6.10: [{source: 0012345, pages: 1:30}]\n  7: [{source: 1_0, pages: null}]\n---\n" + BODY)
    meta, _ = FM.parse(text)
    assert [s["id"] for s in meta["sources"]] == ["0012345", "1_0"]
    assert meta["sections"] == {"6.10": [{"source": "0012345", "pages": "1:30"}], "7": [{"source": "1_0", "pages": None}]}


def test_a_leading_rule_without_provenance_is_body():
    text = "---\nhello\n---\n" + BODY
    assert FM.parse(text) == (None, text) and FM.body_of(text) == text


def test_front_matter_without_closing_fence_is_refused():
    with pytest.raises(FM.FrontMatterError, match="閉じ"):
        FM.parse("---\nprovenance: 1\n" + BODY)


# ---------- provenance ----------

def test_split_refs_reads_raw_files_and_sections_and_skips_the_analysis_own_chapters():
    cell = f"{RAW}「6. 研究開発（p.42-43）」、2026-01-10_competitors.md「7.」「8.」、md 3.1・2.2"
    assert PV.split_refs(cell) == [PV.Ref(RAW, ("6",)), PV.Ref("2026-01-10_competitors.md", ("7", "8"))]
    assert PV.split_refs("md 2.1") == [] and PV.split_refs(None) == []
    assert PV.split_refs(f"{RAW}「７．」") == [PV.Ref(RAW, ("7",))]  # full-width digits and dot


def test_a_cell_is_not_used_as_a_glob(tmp_path):
    company = _company(tmp_path, FM.with_front_matter(BODY, META))
    assert [e.status for e in PV.Resolver(company).resolve("2026-01-10_*.md「1.」")] == [PV.MISSING]


def test_resolve_gives_every_status(tmp_path):
    company = _company(tmp_path, FM.with_front_matter(BODY, META))
    resolver = PV.Resolver(company)
    verified, = resolver.resolve(f"{RAW}「1.」")
    assert verified.status == PV.VERIFIED and verified.pages == "2"
    assert verified.local_path == "sources/2026-01-10/DOC1.pdf" and verified.published == "2025-06-20"
    assert [(e.status, e.reason) for e in resolver.resolve(f"{RAW}「6.」「8.」「3.」")] == [
        (PV.UNVERIFIED, PV.NO_PAGES), (PV.UNVERIFIED, PV.SEARCH_ONLY), (PV.UNVERIFIED, PV.NO_SECTION)]
    assert [(e.status, e.reason) for e in resolver.resolve(RAW)] == [(PV.UNVERIFIED, PV.NO_SECTION)]  # 3 documents
    assert [e.status for e in resolver.resolve("2026-01-10_typo.md「1.」")] == [PV.MISSING]


def test_a_document_missing_from_the_manifest_has_no_original(tmp_path):
    meta = {**META, "sections": {"1": [{"source": "DOC2", "pages": "5"}]}}
    company = _company(tmp_path, FM.with_front_matter(BODY, meta))
    e, = PV.Resolver(company).resolve(f"{RAW}「1.」")
    assert (e.status, e.reason, e.title, e.local_path) == (PV.UNVERIFIED, PV.NO_ORIGINAL, "決算説明資料", None)


def test_raw_without_or_with_broken_front_matter_is_unverified(tmp_path):
    company = _company(tmp_path, BODY)
    assert [e.reason for e in PV.Resolver(company).resolve(f"{RAW}「1.」")] == [PV.NO_FRONT_MATTER]
    (company / "raw" / "filings" / RAW).write_text("---\nprovenance: 2\n---\n" + BODY, encoding="utf-8")
    assert [e.reason for e in PV.Resolver(company).resolve(f"{RAW}「1.」")] == [PV.BAD_FRONT_MATTER]


# ---------- an_evidence ----------

def test_chapter_is_appended_once_and_stripped_before_the_checks(tmp_path):
    company = _company(tmp_path, FM.with_front_matter(BODY, META))
    chain = EV.claims_evidence(company, [("4. ブランド", f"{RAW}「1.」「6.」"), ("5. シェアの推移", "2026-01-10_x.md")])
    assert chain["summary"] == {"verified": 1, "unverified": 1, "missing": 1, "reasons": {PV.NO_PAGES: 1}}
    assert EV.missing(chain) == ["2026-01-10_x.md"]
    md = "## 11. 判定に効く欠損\n\n- なし\n"
    once = EV.apply(md, 12, chain)
    assert "## 12. 出典の連鎖（build が記入）" in once and "検証済み 1 件・未検証 1 件（ページなし 1）" in once
    assert "| 4. ブランド | 2026-01-10_2025-03_yuho.md「1.」 | DOC1 有価証券報告書 第10期 2025-06-20 | 2 |" in once
    assert EV.apply(once, 12, chain) == once
    assert EV.strip(once) == md


# ---------- readers of the raw header ----------

def test_header_notes_skips_front_matter_and_names_the_documents(tmp_path):
    company = _company(tmp_path, FM.with_front_matter(BODY, META))
    notes = I.header_notes(company / "raw" / "filings" / RAW)
    assert notes.startswith("資料 ID: DOC1 有価証券報告書 第10期 2025-06-20 一次／DOC2 決算説明資料 一次")
    assert "確度: 一次" in notes and "> 単位: 百万円" in notes
    plain = I.header_notes(_company(tmp_path / "b", BODY) / "raw" / "filings" / RAW)
    assert not plain.startswith("資料 ID") and "> 単位: 百万円" in plain


# ---------- report ----------

def test_report_moat_table_links_verified_sources_and_marks_the_rest():
    moat = {"moats": [{"type": "ブランド", "group": "無形資産", "rating": "弱", "mechanism": "m", "evidence": [
        {"status": "検証済み", "title": "有報", "pages": "42-43", "local_path": "sources/2026-01-10/DOC1.pdf",
         "url": "https://example.com/a.pdf?x=1&y=2"},
        {"status": "検証済み", "title": "説明会資料", "pages": "3", "local_path": "sources/2026-01-10/DOC3.pdf"},
        {"status": "未検証", "reason": "原本なし", "title": "記事", "url": "javascript:alert(1)"},
        {"status": "未検証", "reason": "ページなし", "title": "説明資料"},
        {"status": "未検証", "reason": "ページなし", "title": "説明資料"}]},  # cited from two sections
        {"type": "コスト優位", "group": "コスト優位", "rating": "該当なし", "mechanism": "m"}]}
    html = R._moat_sources(moat)
    assert "<th>出典</th>" in html
    # the public URL when there is one; the saved original only for a document without a URL
    assert '<a href="https://example.com/a.pdf?x=1&amp;y=2" rel="noopener">有報</a> p.42-43' in html
    assert "DOC1.pdf" not in html
    assert '<a href="../sources/2026-01-10/DOC3.pdf" rel="noopener">説明会資料</a> p.3' in html
    assert "javascript:" not in html and '<span class="ok-unk">未検証（原本の保存なし）</span> 記事' in html
    assert html.count('<span class="ok-unk">未検証（ページの記録なし）</span> 説明資料') == 1
    assert html.count("<td>—</td>") == 1  # a moat.json built before BL-01 has no evidence
