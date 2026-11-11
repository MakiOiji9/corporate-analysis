"""Markdown of the result comment posted to a company-analysis Issue (.github/workflows/issue-company-report.yml).

Usage: issue_comment.py --outcome success|failure --ticker T --repo OWNER/REPO --run-url URL [--result JSON ...]

success: the three horizon verdicts from today's companies/{dir}/reports/{date}_company-report.json, links to the
html/md on main, and Claude's completion reports. failure: where to look and how to retry.
Exit 0 when the comment reports a finished report (the workflow then closes the Issue), 3 when it reports a failure
(the Issue stays open). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HORIZONS = (("short", "短期（〜3ヶ月）"), ("mid", "中期（6ヶ月〜1年）"), ("long", "長期（3年以上）"))
REPORT_LIMIT = 6000  # GitHub comments are capped at 65536 characters; keep each quoted report short
EXIT_FAILURE_COMMENT = 3


def company_dir(ticker: str) -> Path | None:
    hits = [d for d in (ROOT / "companies").glob(f"{ticker}_*") if d.is_dir()]
    return hits[0] if len(hits) == 1 else None


def todays_report(directory: Path) -> dict | None:
    path = directory / "reports" / f"{dt.date.today().isoformat()}_company-report.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def completion_reports(paths: list[str]) -> list[str]:
    out = []
    for p in paths:
        try:
            text = json.loads(Path(p).read_text(encoding="utf-8")).get("result") or ""
        except (OSError, ValueError):
            continue
        if text.strip():
            out.append(text.strip()[:REPORT_LIMIT])
    return out


def success_lines(args: argparse.Namespace, directory: Path, report: dict) -> list[str]:
    blob = f"https://github.com/{args.repo}/blob/main/{directory.relative_to(ROOT).as_posix()}"
    lines = [f"## 企業分析レポートを作成した — {report.get('name') or directory.name}", "",
             "| 期間 | 判定 | 理由 |", "|---|---|---|"]
    for key, label in HORIZONS:
        h = (report.get("horizons") or {}).get(key) or {}
        verdict = h.get("verdict", "—") + ("（暫定）" if h.get("provisional") else "")
        lines.append(f"| {label} | **{verdict}** | {str(h.get('why', '')).replace('|', '／')} |")
    html, md = Path(report.get("html", "")).name, Path(report.get("md", "")).name
    lines += ["", f"- レポート: [{html}]({blob}/reports/{html})（ダウンロードしてブラウザで開く） / [文章（md）]({blob}/reports/{md})",
              f"- 実行ログ: {args.run_url}",
              "- 定期実行（お気に入り）に入れるときは `/favorites` で登録する", ""]
    return lines


def failure_lines(args: argparse.Namespace) -> list[str]:
    return ["## 企業分析レポートを作れなかった", "",
            f"- 実行ログと Summary: {args.run_url}",
            "- 途中まで進んだ収集・分析は main にコミット済み。Actions のこの実行で **Re-run failed jobs** を押すと続きから"
            "やり直し、成功したらこの Issue を閉じる",
            "- 入力（銘柄コード・URL など）が誤っていたときは、この Issue を閉じて新しく起票する", ""]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", choices=("success", "failure"), required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--result", nargs="*", default=[])
    args = parser.parse_args(argv)
    directory = company_dir(args.ticker)
    report = todays_report(directory) if directory else None
    ok = args.outcome == "success" and report is not None
    lines = success_lines(args, directory, report) if ok else failure_lines(args)
    for text in completion_reports(args.result):
        lines += ["<details><summary>Claude の完了報告</summary>", "", text, "", "</details>", ""]
    print("\n".join(lines))
    return 0 if ok else EXIT_FAILURE_COMMENT


if __name__ == "__main__":
    sys.exit(main())
