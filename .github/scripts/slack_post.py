"""Post today's company report (the single HTML) to Slack (.github/workflows/company-report.yml).

Usage: SLACK_BOT_TOKEN=xoxb-... SLACK_CHANNEL_ID=C0123 slack_post.py --company DIR --repo OWNER/REPO [--run-url URL]

Uploads companies/{dir}/reports/{today}_company-report.html with a comment holding the three horizon verdicts,
STEP 1-3 and the price, read from the report's JSON. Uses the Slack upload flow files.getUploadURLExternal ->
upload -> files.completeUploadExternal (files.upload is retired); the bot needs the files:write scope and must be
a member of the channel. Without SLACK_BOT_TOKEN / SLACK_CHANNEL_ID it does nothing (exit 0): the notification is
optional. Exit 1 when the report is missing or Slack refuses. Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
API = "https://slack.com/api"
HORIZONS = (("short", "短期"), ("mid", "中期"), ("long", "長期"))
TIMEOUT = 60

# (url, body, headers) -> parsed JSON (or {} for the raw upload); swapped out by the tests.
Sender = Callable[[str, bytes, dict], dict]


class SlackError(RuntimeError):
    pass


def todays_report(company: str, today: dt.date, root: Path = ROOT) -> tuple[dict, Path]:
    path = root / "companies" / company / "reports" / f"{today.isoformat()}_company-report.json"
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SlackError(f"今日のレポートの JSON が読めない: {path.name}（{e}）") from e
    html = root / report.get("html", "")
    if not report.get("html") or not html.is_file():
        raise SlackError(f"レポートの HTML が無い: {report.get('html') or '（JSON に html が無い）'}")
    return report, html


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
    links = []
    if report.get("md"):
        links.append(f"<https://github.com/{repo}/blob/main/{report['md']}|文章（md）>")
    if run_url:
        links.append(f"<{run_url}|実行ログ>")
    if links:
        lines.append(" / ".join(links))
    lines.append("添付の HTML はダウンロードしてブラウザで開く")
    return "\n".join(lines)


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


def upload(html: Path, text: str, token: str, channel: str, send: Sender = _send) -> str:
    data = html.read_bytes()
    form = urllib.parse.urlencode({"filename": html.name, "length": len(data)}).encode("ascii")
    ticket = _api(send, token, "files.getUploadURLExternal", form, "application/x-www-form-urlencoded")
    if not str(ticket.get("upload_url", "")).startswith("https://"):
        raise SlackError("files.getUploadURLExternal が https の upload_url を返さなかった")
    send(ticket["upload_url"], data, {"Content-Type": "application/octet-stream"})
    done = {"files": [{"id": ticket["file_id"], "title": html.name}], "channel_id": channel,
            "initial_comment": text}
    _api(send, token, "files.completeUploadExternal", json.dumps(done, ensure_ascii=False).encode("utf-8"),
         "application/json; charset=utf-8")
    return ticket["file_id"]


def main(argv: list[str] | None = None, send: Sender = _send, today: dt.date | None = None,
         root: Path = ROOT) -> int:
    p = argparse.ArgumentParser(description="Post today's company report HTML to Slack")
    p.add_argument("--company", required=True)
    p.add_argument("--repo", required=True)
    p.add_argument("--run-url")
    args = p.parse_args(argv)
    token, channel = os.environ.get("SLACK_BOT_TOKEN", ""), os.environ.get("SLACK_CHANNEL_ID", "")
    if not token or not channel:
        print("SLACK_BOT_TOKEN / SLACK_CHANNEL_ID が未設定。Slack には投稿しない")
        return 0
    try:
        report, html = todays_report(args.company, today or dt.date.today(), root)
        file_id = upload(html, comment(report, args.repo, args.run_url), token, channel, send)
    except (SlackError, OSError, ValueError, KeyError) as e:
        print(f"::warning::{args.company}: Slack に投稿できなかった: {e}")
        return 1
    print(f"Slack に投稿した: {html.name}（file {file_id}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
