"""Convert a PDF or HTML document to UTF-8 text with page markers.

Usage:
  pdf_text.py <file.pdf|file.htm> [out.txt]

Output defaults to <file>.txt next to the input (inside sources/, git-ignored).
PDF pages are separated by lines '=====PAGE n====='. HTML becomes a single page
with one table row per line (cells separated by ' | ').
"""
from __future__ import annotations

import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts run with python -I
from common import utf8_stdout  # noqa: E402

PAGE_MARK = "=====PAGE {n}====="
BLOCK_TAGS = {"p", "div", "br", "tr", "h1", "h2", "h3", "h4", "li", "table"}


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data.strip())


def html_to_text(source: str) -> str:
    parser = _TextParser()
    parser.feed(source)
    lines = (line.strip() for line in "".join(parser.parts).splitlines())
    body = "\n".join(line for line in lines if line and line != "|")
    return f"{PAGE_MARK.format(n=1)}\n{body}\n"


def pdf_to_text(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "".join(f"{PAGE_MARK.format(n=i)}\n{page.extract_text() or ''}\n"
                   for i, page in enumerate(reader.pages, 1))


def convert(src: Path, out: Path | None = None) -> Path:
    if src.suffix.lower() == ".pdf":
        text = pdf_to_text(src)
    else:
        text = html_to_text(src.read_text(encoding="utf-8", errors="replace"))
    out = out or src.with_suffix(src.suffix + ".txt")
    out.write_text(text, encoding="utf-8")
    return out


def main() -> None:
    utf8_stdout()
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = Path(sys.argv[1])
    out = convert(src, Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    pages = out.read_text(encoding="utf-8").count("=====PAGE ")
    print(f"{out} ({pages} pages)")


if __name__ == "__main__":
    main()
