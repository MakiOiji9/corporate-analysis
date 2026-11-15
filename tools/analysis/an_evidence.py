"""The 出典の連鎖 chapter an analysis md ends with, and the same chain for its json (BL-01).

An analysis passes its claims as (label, 情報源 cell) pairs; provenance.Resolver turns each cell into Evidence and
this module renders the chapter build appends after the template's last chapter. The chapter is not part of the
template: build strips it before the structure checks and writes it again, so an md written before the chapter
existed still builds. The trial runs on moat only; the other analyses can pass their claims the same way.
"""
from __future__ import annotations

import re
from pathlib import Path

import provenance as PV

HEADING = "出典の連鎖（build が記入）"
# from the chapter heading to the next level-2 heading or the end: the chapter is always the md's last one, so
# nothing written after it survives a rebuild
CHAPTER = re.compile(r"^##\s+\d+\.\s+" + re.escape(HEADING) + r"[^\n]*\n.*?(?=^##\s|\Z)", re.M | re.S)
NOTE = ("注: 情報源の列の raw と節から、raw の Front Matter と sources/manifest.csv をたどった結果（スクリプトが記入）。"
        "「検証済み」は原本のファイルとページまでたどれた主張。「未検証」は理由を添える。")


def claims_evidence(company_dir: Path, claims: list[tuple[str, str]]) -> dict:
    """{'claims': [{'claim', 'source', 'evidence': [Evidence dict]}], 'summary': provenance.summary}."""
    resolver = PV.Resolver(company_dir)
    rows, every = [], []
    for claim, cell in claims:
        found = resolver.resolve(cell)
        every += found
        rows.append({"claim": claim, "source": cell, "evidence": [e.to_dict() for e in found]})
    return {"claims": rows, "summary": PV.summary(every)}


def missing(chain: dict) -> list[str]:
    """Raw files a 情報源 cell names that do not exist (build warns about them)."""
    return sorted({e["raw"] for c in chain["claims"] for e in c["evidence"] if e["status"] == PV.MISSING})


def _cell(text: object) -> str:
    return str(text or "—").replace("|", "／").replace("\n", " ")


def _document(e: dict) -> str:
    parts = [e.get("doc_id"), e.get("title"), e.get("published") or e.get("period")]
    return " ".join(p for p in parts if p) or "—"


def _original(e: dict) -> str | None:
    """Where the reader opens the document: its URL; the saved file under sources/ only when there is no URL."""
    return e.get("url") or e.get("local_path")


def _status(e: dict) -> str:
    return f"{e['status']}（{e['reason']}）" if e.get("reason") else e["status"]


def _rows(chain: dict) -> list[str]:
    rows = []
    for c in chain["claims"]:
        for e in c["evidence"]:
            number = e.get("section") or ""
            section = f"「{number}{'.' if number.isdigit() else ''}」" if number else ""  # as the 情報源 cell writes it
            rows.append(f"| {_cell(c['claim'])} | {_cell(e['raw'] + section)} | {_cell(_document(e))} "
                        f"| {_cell(e.get('pages'))} | {_cell(_original(e))} | {_cell(_status(e))} |")
    return rows


def _summary_line(summary: dict) -> str:
    reasons = "、".join(f"{k} {v}" for k, v in summary["reasons"].items())
    line = f"検証済み {summary['verified']} 件・未検証 {summary['unverified']} 件"
    line += f"（{reasons}）" if reasons else ""
    return line + (f"・参照先なし {summary['missing']} 件" if summary["missing"] else "")


def chapter(number: int, chain: dict) -> str:
    rows = _rows(chain) or ["| — | 情報源の列に raw のファイル名が無い | — | — | — | — |"]
    return "\n".join([f"## {number}. {HEADING}", "", _summary_line(chain["summary"]), "",
                      "| 主張 | raw・節 | 資料 | ページ | 原本（URL。無ければ保存先） | 状態 |", "|---|---|---|---|---|---|", *rows, "",
                      f"> {NOTE}", ""])


def strip(text: str) -> str:
    """The md without the chapter (what the template checks see)."""
    return CHAPTER.sub("", text).rstrip() + "\n"


def apply(text: str, number: int, chain: dict) -> str:
    return strip(text) + "\n" + chapter(number, chain)
