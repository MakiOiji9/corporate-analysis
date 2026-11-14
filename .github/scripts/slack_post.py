"""Post a report file to Slack (.github/workflows/company-report.yml and slack-post.yml).

Usage: SLACK_BOT_TOKEN=xoxb-... SLACK_CHANNEL_ID=C0123 slack_post.py <command> --repo OWNER/REPO [--run-url URL]
  company --company DIR             today's companies/{dir}/reports/{today}_company-report.html (company-report.yml)
  file --path PATH [--message TEXT] any file under companies/ or market/ (slack-post.yml)

A company report HTML is posted with a comment holding the three horizon verdicts, STEP 1-3 and the price, read
from the JSON next to it; any other file with its name and a link to it on main. Uses the Slack upload flow
files.getUploadURLExternal -> upload -> files.completeUploadExternal (files.upload is retired); the bot needs the
files:write scope and must be a member of the channel. company does nothing without SLACK_BOT_TOKEN /
SLACK_CHANNEL_ID (exit 0: the notification of a scheduled run is optional); file fails without them. Exit 1 when the
file is missing or refused, or Slack refuses. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
API = "https://slack.com/api"
HORIZONS = (("short", "短期"), ("mid", "中期"), ("long", "長期"))
TIMEOUT = 60
ALLOWED_TOPS = ("companies", "market")  # the outputs of the reports; nothing else of the repository is posted
MAX_BYTES = 50 * 1024 * 1024
MAX_MESSAGE = 2000
REPORT_SUFFIX = "_company-report.html"

# (url, body, headers) -> parsed JSON (or {} for the raw upload); swapped out by the tests.
Sender = Callable[[str, bytes, dict], dict]


class SlackError(RuntimeError):
    pass


def _read_report(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SlackError(f"レポートの JSON が読めない: {path.name}（{e}）") from e


def todays_report(company: str, today: dt.date, root: Path = ROOT) -> tuple[dict, Path]:
    report = _read_report(root / "companies" / company / "reports" / f"{today.isoformat()}_company-report.json")
    html = root / report.get("html", "")
    if not report.get("html") or not html.is_file():
        raise SlackError(f"レポートの HTML が無い: {report.get('html') or '（JSON に html が無い）'}")
    return report, html


def resolve_target(path: str, root: Path = ROOT) -> Path:
    """A file of the repository under companies/ or market/ (no absolute path, .., or link leading outside)."""
    rel = PurePosixPath(path.strip().replace("\\", "/"))
    if not rel.parts or rel.is_absolute() or ".." in rel.parts or rel.parts[0] not in ALLOWED_TOPS:
        raise SlackError(f"投稿できるのは {'/・'.join(ALLOWED_TOPS)}/ 配下のファイルだけ: {path}")
    target = (root / rel).resolve()
    if not target.is_relative_to(root.resolve()) or not target.is_file():
        raise SlackError(f"ファイルが無い: {rel}")
    if target.stat().st_size > MAX_BYTES:
        raise SlackError(f"ファイルが大きすぎる（{MAX_BYTES // 1024 // 1024}MB まで）: {rel}")
    return target


def _links(repo: str, md: str | None, run_url: str | None, md_label: str = "文章（md）") -> str | None:
    links = []
    if md:
        links.append(f"<https://github.com/{repo}/blob/main/{md}|{md_label}>")
    if run_url:
        links.append(f"<{run_url}|実行ログ>")
    return " / ".join(links) or None


def comment(report: dict, repo: str, run_url: str | None) -> str:
    horizons = report.get("horizons") or {}
    verdicts = []
    for key, label in HORIZONS:
        h = horizons.get(key) or {}
        verdicts.append(f"{label} *{h.get('verdict', '—')}*" + ("（暫定）" if h.get("provisional") else ""))
    s1, s2, s3 = (report.get(k) or {} for k in ("step1", "step2", "step3"))
    lines = [f"*企業分析レポート — {report.get('name') or report.get('company', '')}*（{report.get('date', '')}）",
             " / ".join(verdicts),
             f"STEP 1 {s1.get('grade', '—')}・STEP 2 {s2.get('grade', '—')}・STEP 3 {s3.get('verdict', '—')}"]
    price = report.get("price") or {}
    if price.get("value") is not None:
        lines.append(f"株価 {price['value']:,.0f}{price.get('currency', '')}（{price.get('date', '')}）")
    lines.append(_links(repo, report.get("md"), run_url))
    lines.append("添付の HTML はダウンロードしてブラウザで開く")
    return "\n".join(line for line in lines if line)


def file_comment(target: Path, repo: str, run_url: str | None, message: str | None, root: Path = ROOT) -> str:
    """The company report comment when target is one (its JSON is next to it), otherwise the file name and link."""
    rel = target.relative_to(root.resolve()).as_posix()
    head = [message.strip()[:MAX_MESSAGE]] if message and message.strip() else []
    if target.name.endswith(REPORT_SUFFIX):
        json_path = target.with_name(target.name[: -len(".html")] + ".json")
        if json_path.is_file():
            return "\n".join(head + [comment(_read_report(json_path), repo, run_url)])
    lines = head + [f"*{target.name}*", _links(repo, rel, run_url, "GitHub で見る")]
    if target.suffix.lower() == ".html":
        lines.append("添付の HTML はダウンロードしてブラウザで開く")
    return "\n".join(line for line in lines if line)


def _send(url: str, body: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=TIMEOUT) as res:  # noqa: S310 (Slack's https URLs only)
        raw = res.read()
    if not url.startswith(API):
        return {}  # the upload URL answers with plain text
    return json.loads(raw.decode("utf-8"))


def _api(send: Sender, token: str, method: str, body: bytes, content_type: str) -> dict:
    out = send(f"{API}/{method}", body, {"Authorization": f"Bearer {token}", "Content-Type": content_type})
    if not out.get("ok"):
        raise SlackError(f"{method} が失敗: {out.get('error', 'unknown')}")
    return out


def upload(path: Path, text: str, token: str, channel: str, send: Sender = _send) -> str:
    data = path.read_bytes()
    form = urllib.parse.urlencode({"filename": path.name, "length": len(data)}).encode("ascii")
    ticket = _api(send, token, "files.getUploadURLExternal", form, "application/x-www-form-urlencoded")
    if not str(ticket.get("upload_url", "")).startswith("https://"):
        raise SlackError("files.getUploadURLExternal が https の upload_url を返さなかった")
    send(ticket["upload_url"], data, {"Content-Type": "application/octet-stream"})
    done = {"files": [{"id": ticket["file_id"], "title": path.name}], "channel_id": channel,
            "initial_comment": text}
    _api(send, token, "files.completeUploadExternal", json.dumps(done, ensure_ascii=False).encode("utf-8"),
         "application/json; charset=utf-8")
    return ticket["file_id"]


def _parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--repo", required=True)
    common.add_argument("--run-url")
    p = argparse.ArgumentParser(description="Post a report file to Slack")
    sub = p.add_subparsers(dest="command", required=True)
    company = sub.add_parser("company", parents=[common], help="today's company report")
    company.add_argument("--company", required=True)
    file = sub.add_parser("file", parents=[common], help="a file under companies/ or market/")
    file.add_argument("--path", required=True)
    file.add_argument("--message")
    return p


def main(argv: list[str] | None = None, send: Sender = _send, today: dt.date | None = None,
         root: Path = ROOT) -> int:
    args = _parser().parse_args(argv)
    label = args.company if args.command == "company" else args.path
    token, channel = os.environ.get("SLACK_BOT_TOKEN", ""), os.environ.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        if args.command == "company":
            print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が未設定。Slack には投稿しない")
            return 0
        print("::error::SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が未設定")
        return 1
    level = "warning" if args.command == "company" else "error"
    try:
        if args.command == "company":
            report, target = todays_report(args.company, today or dt.date.today(), root)
            text = comment(report, args.repo, args.run_url)
        else:
            target = resolve_target(args.path, root)
            text = file_comment(target, args.repo, args.run_url, args.message, root)
        file_id = upload(target, text, token, channel, send)
    except (SlackError, OSError, ValueError, KeyError) as e:
        print(f"::{level}::{label}: Slack に投稿できなかった: {e}")
        return 1
    print(f"Slack に投稿した: {target.name}（file {file_id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
