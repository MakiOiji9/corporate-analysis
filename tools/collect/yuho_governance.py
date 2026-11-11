"""Shareholders, officers and new shares from the annual reports' XBRL (EDINET 'XBRL->CSV' packages under sources/).

Usage:
  yuho_governance.py --company <dir>     # every own annual report (第三号様式) under sources/ -> data/governance.json

data/governance.json (one JSON, rewritten each run):
  as_of, filed, doc_id   the newest annual report's fiscal year end, filing date and document id
  shareholders           the ten largest holders [{rank, name, ratio %}] (大株主の状況)
  officers               [{name, title, birth, age, shares, career}] (役員の状況), president: the 社長 / CEO row
  owner                  the holders that are an officer, share an officer's family name, or are a company carrying
                         it (資産管理会社): {ratio, members, is_owner (ratio ≥ OWNER_RATIO)}
  issued                 shares outstanding by fiscal year end (the 5-year summaries of every report)
  issuances              the years the count rose by more than ISSUE_MIN %, each with a kind read from the reports'
                         「発行済株式総数、資本金等の推移」: 株式分割 / 公募増資 / 第三者割当 / 新株予約権の行使 /
                         株式交換・合併 / 不明; offering_within_5y, offering_last
Only what the reports state; nothing is inferred beyond the family-name match (marked so in the members).
stdout is one JSON line.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
import xbrl_financials as XF  # noqa: E402
from common import atomic_write_text, company_dir, utf8_stdout  # noqa: E402

ANNUAL_FORM = "第三号様式"
OWNER_RATIO = 20.0
ISSUE_MIN = 1.0          # % rise of the share count that counts as new shares
SPLIT_RATIO = 1.9        # a count that grows this much at once is a split (or a merger, told by the text)
OFFERING_YEARS = 5
INSTITUTIONS = ("銀行", "信託", "証券", "保険", "持株会", "カストディ", "BANK", "TRUST", "SECURITIES", "FUND", "常任代理人")
PRESIDENT = ("社長", "CEO", "最高経営責任者")
KINDS = (("株式交換・合併", ("株式交換", "合併")), ("公募増資", ("一般募集", "公募")), ("第三者割当", ("第三者割当",)),
         ("新株予約権の行使", ("新株予約権", "ストック・オプション", "ストックオプション")))
REL = {"CurrentYear": 0, "Prior1Year": 1, "Prior2Year": 2, "Prior3Year": 3, "Prior4Year": 4}
SPACE = re.compile(r"[\s　]+")
NOTE = re.compile(r"[（(].*?[)）]")


def _value(rows: list[XF.Row], element: str, context: str | None = None) -> str | None:
    hit = next((r.value for r in rows if r.element.endswith(":" + element) and (context is None or r.context == context)
                and r.value not in ("", "－", "-")), None)
    return hit.strip() if hit else None


def _ratio(text: str | None) -> float | None:
    try:
        return round(float(text) * 100, 2) if text else None
    except ValueError:
        return None


def shareholders(rows: list[XF.Row]) -> list[dict]:
    out = []
    for rank in range(1, 11):
        ctx = f"CurrentYearInstant_No{rank}MajorShareholdersMember"
        name = _value(rows, "NameMajorShareholders", ctx)
        if name:
            out.append({"rank": rank, "name": name, "ratio": _ratio(_value(rows, "ShareholdingRatio", ctx))})
    return out


def _age(birth: str | None, on: str) -> int | None:
    try:
        b, d = dt.date.fromisoformat(birth), dt.date.fromisoformat(on)
    except (TypeError, ValueError):
        return None
    return d.year - b.year - ((d.month, d.day) < (b.month, b.day))


def officers(rows: list[XF.Row], on: str) -> list[dict]:
    contexts = [r.context for r in rows if r.element.endswith(":NameInformationAboutDirectorsAndCorporateAuditors")]
    out = []
    for ctx in dict.fromkeys(contexts):
        birth = _value(rows, "DateOfBirthInformationAboutDirectorsAndCorporateAuditors", ctx)
        shares = _value(rows, "NumberOfSharesHeldOrdinarySharesInformationAboutDirectorsAndCorporateAuditors", ctx)
        out.append({"name": _value(rows, "NameInformationAboutDirectorsAndCorporateAuditors", ctx),
                    "title": _value(rows, "OfficialTitleOrPositionInformationAboutDirectorsAndCorporateAuditors", ctx),
                    "birth": birth, "age": _age(birth, on),
                    "shares": int(shares) if shares and shares.isdigit() else None,
                    "career": _value(rows, "CareerSummaryInformationAboutDirectorsAndCorporateAuditorsTextBlock", ctx)})
    return out


def _family(name: str) -> str | None:
    """The family name of a Japanese officer written 「姓　名」 (None when there is no space to split on)."""
    parts = SPACE.split(NOTE.sub("", name).strip())
    return parts[0] if len(parts) >= 2 and len(parts[0]) >= 1 else None


def owner(holders: list[dict], people: list[dict]) -> dict:
    names = {SPACE.sub("", NOTE.sub("", p["name"] or "")) for p in people if p.get("name")}
    families = {f for p in people if p.get("name") and (f := _family(p["name"]))}
    members = []
    for h in holders:
        plain = SPACE.sub("", h["name"])
        institution = any(w in h["name"].upper() for w in INSTITUTIONS)
        if plain in names:
            members.append({**h, "why": "役員本人"})
        elif not institution and any(plain.startswith(f) for f in families):
            members.append({**h, "why": "役員と同じ姓（親族の可能性）"})
        elif not institution and any(f in plain for f in families if len(f) >= 2):
            members.append({**h, "why": "役員の姓を含む会社（資産管理会社の可能性）"})
    ratio = round(sum(m["ratio"] or 0 for m in members), 2)
    return {"ratio": ratio, "members": members, "is_owner": ratio >= OWNER_RATIO}


def issued_counts(filings: list[tuple[str, list[XF.Row]]]) -> dict[str, int]:
    """{fiscal year end: shares outstanding} from every report's 5-year summary (a later report wins)."""
    out: dict[str, int] = {}
    for _, rows in filings:
        fy_end = _value(rows, "CurrentFiscalYearEndDateDEI")
        for r in rows:
            if not r.element.endswith(":TotalNumberOfIssuedSharesSummaryOfBusinessResults"):
                continue
            rel = next((k for k in REL if r.context.startswith(k + "Instant")), None)
            if rel is not None and r.value.isdigit():
                out[XF._shift_year(fy_end, REL[rel])] = int(r.value)
    return dict(sorted(out.items()))


def _kind(change: float, texts: str) -> str:
    if change >= (SPLIT_RATIO - 1) * 100 and "分割" in texts:
        return "株式分割"
    return next((kind for kind, words in KINDS if any(w in texts for w in words)), "不明")


def issuances(counts: dict[str, int], texts: str) -> list[dict]:
    dates = list(counts)
    out = []
    for before, after in zip(dates, dates[1:]):
        change = (counts[after] / counts[before] - 1) * 100 if counts[before] else 0
        if change > ISSUE_MIN:
            out.append({"period_end": after, "from": counts[before], "to": counts[after],
                        "change_pct": round(change, 1), "kind": _kind(change, texts)})
    return out


def build(filings: list[tuple[str, list[XF.Row]]]) -> dict | None:
    """filings: [(doc_id, rows)] of the company's own reports, any order; None without an annual report."""
    annual = [(d, r) for d, r in filings if _value(r, "DocumentTypeDEI") == ANNUAL_FORM]
    if not annual:
        return None
    annual.sort(key=lambda f: (_value(f[1], "CurrentFiscalYearEndDateDEI") or "", f[0]))
    doc_id, rows = annual[-1]
    fy_end = _value(rows, "CurrentFiscalYearEndDateDEI")
    filed = _value(rows, "FilingDateCoverPage") or fy_end
    holders, people = shareholders(rows), officers(rows, filed)
    counts = issued_counts(annual)
    texts = " ".join(_value(r, "ChangesInNumberOfIssuedSharesStatedCapitalEtcTextBlock") or "" for _, r in annual)
    found = issuances(counts, texts)
    offerings = [i["period_end"] for i in found if i["kind"] in ("公募増資", "第三者割当")]
    cutoff = XF._shift_year(fy_end, OFFERING_YEARS)
    return {"as_of": fy_end, "filed": filed, "doc_id": doc_id, "shareholders": holders, "officers": people,
            "president": next((p for p in people if any(w in (p["title"] or "") for w in PRESIDENT)), None),
            "owner": owner(holders, people), "issued": [{"period_end": k, "shares": v} for k, v in counts.items()],
            "issuances": found, "offering_within_5y": any(d > cutoff for d in offerings),
            "offering_last": max(offerings) if offerings else None}


def main() -> None:
    utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company", required=True, help="企業ディレクトリ（companies/{ticker}_{name} またはその一部）")
    args = parser.parse_args()
    path = company_dir(args.company)
    ticker = path.name.split("_")[0]
    filings = []
    for source in XF.filing_sources(path / "sources"):
        rows = XF.load_rows(source)
        if XF.security_code(rows) == ticker.upper():
            filings.append((source.name.split("_")[0], rows))
    result = build(filings)
    if result is None:
        print(json.dumps({"ok": False, "error": "sources/ に自社の有価証券報告書（XBRL→CSV）が無い。"
                          "edinet.py fetch --kind csv で取得してから実行する"}, ensure_ascii=False))
        sys.exit(1)
    out = path / "data" / "governance.json"
    atomic_write_text(out, json.dumps(result, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"ok": True, "path": str(out), "as_of": result["as_of"], "filed": result["filed"],
                      "owner_ratio": result["owner"]["ratio"], "president": (result["president"] or {}).get("name"),
                      "issuances": len(result["issuances"]), "offering_within_5y": result["offering_within_5y"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
