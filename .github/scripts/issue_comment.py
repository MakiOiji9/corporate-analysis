"""Markdown of the result comment posted to a company-analysis Issue (.github/workflows/issue-company-report.yml).

Usage: issue_comment.py --outcome success|failure --ticker T --repo OWNER/REPO --run-url URL
                        [--pr-url URL] [--merged yes|no] [--result JSON ...]

success: the three horizon verdicts from today's companies/{dir}/reports/{date}_company-report.json, links to the
html/md on main, and Claude's completion reports. failure: where to look and how to retry (the work branch and its
draft PR keep what was done). A built report whose PR could not be merged (--merged no) is reported as such.
Exit 0 when the comment reports a finished report merged into main (the workflow then closes the Issue), 3 otherwise
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
    lines += ["", f"- レポート: [{html}]({blob}/reports/{html})（ダウンロードしてブラウザで開く） / [文章（md）]({blob}/reports/{md})"]
    if args.pr_url:
        lines.append(f"- PR: {args.pr_url}（main にスカッシュマージ済み）")
    lines += [f"- 実行ログ: {args.run_url}", "- 定期実行（お気に入り）に入れるときは `/favorites` で登録する", ""]
    return lines


def unmerged_lines(args: argparse.Namespace) -> list[str]:
    return ["## レポートはできたが、PR を main にマージできなかった", "",
            f"- PR: {args.pr_url or '—'}（main と競合している可能性がある。PR で競合を解消してマージすると、この Issue は閉じる）",
            f"- 実行ログと Summary: {args.run_url}", ""]


def failure_lines(args: argparse.Namespace) -> list[str]:
    return ["## 企業分析レポートを作れなかった", "",
            f"- 実行ログと Summary: {args.run_url}",
            f"- 途中までの収集・分析は作業ブランチにコミット済み（ドラフト PR: {args.pr_url or '—'}）。"
            "Actions のこの実行の **Re-run failed jobs**、またはこの Issue のラベル `company-analysis` を付け直すと、"
            "済んだ部分を飛ばして続きから進み、完了したら PR をマージしてこの Issue を閉じる",
            "- 利用枠の上限で止まったときは、枠のリセット後にやり直す",
            "- 入力（銘柄コード・URL など）が誤っていたときは、この Issue と PR を閉じて新しく起票する", ""]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--outcome", choices=("success", "failure"), required=True)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--pr-url", default="")
    parser.add_argument("--merged", choices=("yes", "no"), default="yes")
    parser.add_argument("--result", nargs="*", default=[])
    args = parser.parse_args(argv)
    directory = company_dir(args.ticker)
    report = todays_report(directory) if directory else None
    built = args.outcome == "success" and report is not None
    ok = built and args.merged == "yes"
    if ok:
        lines = success_lines(args, directory, report)
    else:
        lines = unmerged_lines(args) if built else failure_lines(args)
    for text in completion_reports(args.result):
        lines += ["<details><summary>Claude の完了報告</summary>", "", text, "", "</details>", ""]
    print("\n".join(lines))
    return 0 if ok else EXIT_FAILURE_COMMENT


if __name__ == "__main__":
    sys.exit(main())
