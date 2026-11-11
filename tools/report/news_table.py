"""The disclosures and news collect-ir writes to raw/news/*_press-releases.md, as one list.

Every file's table (日付・見出し・要旨・URL) is read; an update file holds only what is new, so the files are joined
and a row repeated in two files is kept once. Each item gets a kind from the words of its heading and summary.
"""
from __future__ import annotations

import re
from pathlib import Path

import mdparse as M

ISO = re.compile(r"(\d{4}-\d{2}-\d{2})")
KINDS = (("業績修正", ("修正", "下方", "上方")), ("決算", ("決算", "業績概要", "四半期報告", "半期報告", "有価証券報告書")),
         ("配当・自社株", ("配当", "自己株式", "自社株")), ("M&A・提携", ("買収", "合併", "株式交換", "提携", "子会社化", "譲渡")))


NO_REVISION = re.compile(r"(?:修正|変更)(?:は)?(?:なし|無し|ありません)")


def classify(title: str, summary: str) -> str:
    """業績修正 / 決算 / 配当・自社株 / M&A・提携 / その他 (a revision is told before the results it came with;
    「予想の修正なし」 is not one)."""
    text = NO_REVISION.sub("", f"{title} {summary}")
    return next((kind for kind, words in KINDS if any(w in text for w in words)), "その他")


def load(news_dir: Path) -> list[dict]:
    """[{date, title, summary, url, kind}] newest first, from every *_press-releases.md under news_dir."""
    seen, out = set(), []
    for path in sorted(news_dir.glob("*_press-releases.md")) if news_dir.exists() else []:
        for row in M.table_dicts(path.read_text(encoding="utf-8")):
            m = ISO.search(row.get("日付", ""))
            title = (row.get("見出し") or "").strip()
            if not m or M.is_blank(title) or (m.group(1), title) in seen:
                continue
            seen.add((m.group(1), title))
            summary = "" if M.is_blank(row.get("要旨")) else row["要旨"].strip()
            out.append({"date": m.group(1), "title": title, "summary": summary, "url": row.get("URL", ""),
                        "kind": classify(title, summary)})
    return sorted(out, key=lambda x: x["date"], reverse=True)
