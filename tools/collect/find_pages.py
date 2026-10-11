"""Locate and print only the relevant pages of a text produced by pdf_text.py.

Usage:
  find_pages.py find  <file.txt> <regex>        # 'page: line' for every match
  find_pages.py pages <file.txt> <from> [<to>]  # print pages from..to
  find_pages.py toc   <file.txt>                # 有報の見出し（【...】）とページ
  find_pages.py fin   <file.txt>                # 連結財務諸表の主要科目の行
  find_pages.py cover <file.txt>                # 表紙（提出書類・事業年度・提出日）

Reading only the pages you need keeps token usage low (a 有報 is ~85k chars).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import utf8_stdout  # noqa: E402

PAGE_SPLIT = re.compile(r"\n?=====PAGE (\d+)=====\n")
STATEMENT_HEADS = ("【連結貸借対照表】", "【連結損益計算書", "【連結キャッシュ・フロー計算書】")
FIN_ITEMS = re.compile(
    r"^(売上高|売上収益|営業収益|売上原価|売上総利益|販売費及び一般管理費|営業利益|経常利益|"
    r"特別利益合計|特別損失合計|親会社株主に帰属する当期純利益|当期純利益|現金及び預金|"
    r"売掛金|受取手形|契約資産|商品|製品|仕掛品|原材料|棚卸資産|流動資産合計|資産合計|"
    r"流動負債合計|負債合計|純資産合計|株主資本合計|短期借入金|長期借入金|社債|"
    r"減価償却費|有形固定資産の取得|無形固定資産の取得|連結の範囲の変更を伴う子会社株式の取得|"
    r"配当金の支払額|自己株式の取得|営業活動によるキャッシュ・フロー|"
    r"投資活動によるキャッシュ・フロー|財務活動によるキャッシュ・フロー|現金及び現金同等物の期末残高)"
)
COVER_KEYS = re.compile(r"【(提出書類|事業年度|四半期会計期間|中間会計期間|提出日|会社名)】")


def load_pages(path: Path) -> dict[int, str]:
    parts = PAGE_SPLIT.split(path.read_text(encoding="utf-8"))
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def find(pages: dict[int, str], pattern: str) -> list[str]:
    rx = re.compile(pattern)
    return [f"{n}: {line.strip()[:100]}"
            for n, body in pages.items() for line in body.splitlines() if rx.search(line)]


def fin_lines(pages: dict[int, str]) -> list[str]:
    heads = [n for n, body in pages.items() if any(h in body for h in STATEMENT_HEADS)]
    if not heads:
        return ["NO_CONSOLIDATED_STATEMENTS"]
    seen, out = set(), []
    for n, body in pages.items():
        if not heads[0] <= n <= heads[-1] + 1:
            continue
        for line in (raw.strip() for raw in body.splitlines()):
            if FIN_ITEMS.match(line) and re.search(r"\d", line) and line not in seen:
                seen.add(line)
                out.append(f"p{n}: {line[:120]}")
    return out


def main() -> None:
    utf8_stdout()
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd, pages = sys.argv[1], load_pages(Path(sys.argv[2]))
    if cmd == "find":
        lines = find(pages, sys.argv[3])
    elif cmd == "pages":
        start = int(sys.argv[3])
        end = int(sys.argv[4]) if len(sys.argv) > 4 else start
        lines = [f"--- p{n} ---\n{pages.get(n, '')}" for n in range(start, end + 1)]
    elif cmd == "toc":
        lines = find(pages, r"^\s*[（(]?[０-９0-9一二三四五六七八九十]*[）)]?\s*[①-⑳]?【[^】]+】")
    elif cmd == "fin":
        lines = fin_lines(pages)
    elif cmd == "cover":
        first = pages.get(min(pages), "") if pages else ""
        lines = [line.strip() for line in first.splitlines() if COVER_KEYS.search(line)]
    else:
        raise SystemExit(__doc__)
    print("\n".join(lines))


if __name__ == "__main__":
    main()
