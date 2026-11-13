import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / ".github" / "scripts")]

import slack_post as SP  # noqa: E402

TODAY = dt.date(2026, 11, 13)
REPORT = {
    "company": "1234_example", "name": "サンプル（1234）", "date": "2026-11-13",
    "horizons": {"short": {"verdict": "見送り", "provisional": None},
                 "mid": {"verdict": "ウォッチ", "provisional": "x"},
                 "long": {"verdict": "投資検討", "provisional": None}},
    "step1": {"grade": "B"}, "step2": {"grade": "A"}, "step3": {"verdict": "妥当"},
    "price": {"value": 3773.0, "date": "2026-11-10", "currency": "円"},
    "md": "companies/1234_example/reports/2026-11-13_company-report.md",
    "html": "companies/1234_example/reports/2026-11-13_company-report.html",
}


def _repo(tmp_path, report=REPORT, html=True):
    reports = tmp_path / "companies" / "1234_example" / "reports"
    reports.mkdir(parents=True)
    (reports / "2026-11-13_company-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    if html:
        (reports / "2026-11-13_company-report.html").write_text("<html>レポート</html>", encoding="utf-8")
    return tmp_path


class FakeSlack:
    def __init__(self, complete_ok=True):
        self.calls = []
        self.complete_ok = complete_ok

    def __call__(self, url, body, headers):
        self.calls.append((url, body, headers))
        if url.endswith("files.getUploadURLExternal"):
            return {"ok": True, "upload_url": "https://files.slack.com/upload/v1/abc", "file_id": "F1"}
        if url.endswith("files.completeUploadExternal"):
            return {"ok": True} if self.complete_ok else {"ok": False, "error": "not_in_channel"}
        return {}


def test_comment_has_verdicts_steps_price_and_links():
    text = SP.comment(REPORT, "owner/repo", "https://github.com/owner/repo/actions/runs/1")
    assert "*企業分析レポート — サンプル（1234）*（2026-11-13）" in text
    assert "短期 *見送り* / 中期 *ウォッチ*（暫定） / 長期 *投資検討*" in text
    assert "STEP 1 B・STEP 2 A・STEP 3 妥当" in text
    assert "株価 3,773円（2026-11-10）" in text
    assert "<https://github.com/owner/repo/blob/main/companies/1234_example/reports/2026-11-13_company-report.md|" in text
    assert "<https://github.com/owner/repo/actions/runs/1|実行ログ>" in text


def test_comment_tolerates_missing_fields():
    text = SP.comment({"company": "1234_example"}, "owner/repo", None)
    assert "短期 *—* / 中期 *—* / 長期 *—*" in text
    assert "株価" not in text and "実行ログ" not in text


def test_upload_runs_the_three_step_flow(tmp_path):
    root = _repo(tmp_path)
    fake = FakeSlack()
    _, html = SP.todays_report("1234_example", TODAY, root)

    file_id = SP.upload(html, "本文", "xoxb-t", "C1", fake)

    assert file_id == "F1"
    (u1, b1, h1), (u2, b2, h2), (u3, b3, h3) = fake.calls
    assert u1 == f"{SP.API}/files.getUploadURLExternal" and h1["Authorization"] == "Bearer xoxb-t"
    assert b"filename=2026-11-13_company-report.html" in b1 and f"length={html.stat().st_size}".encode() in b1
    assert u2 == "https://files.slack.com/upload/v1/abc" and b2 == html.read_bytes() and "Authorization" not in h2
    done = json.loads(b3.decode("utf-8"))
    assert done == {"files": [{"id": "F1", "title": "2026-11-13_company-report.html"}], "channel_id": "C1",
                    "initial_comment": "本文"}


def test_main_skips_without_credentials(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_CHANNEL_ID", raising=False)
    fake = FakeSlack()
    assert SP.main(["--company", "1234_example", "--repo", "o/r"], fake, TODAY, _repo(tmp_path)) == 0
    assert fake.calls == [] and "投稿しない" in capsys.readouterr().out


def test_main_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-t")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C1")
    fake = FakeSlack()
    assert SP.main(["--company", "1234_example", "--repo", "o/r"], fake, TODAY, _repo(tmp_path)) == 0
    assert len(fake.calls) == 3


def test_main_fails_when_slack_refuses(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-t")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C1")
    fake = FakeSlack(complete_ok=False)
    assert SP.main(["--company", "1234_example", "--repo", "o/r"], fake, TODAY, _repo(tmp_path)) == 1
    assert "not_in_channel" in capsys.readouterr().out


def test_main_fails_without_todays_report(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-t")
    monkeypatch.setenv("SLACK_CHANNEL_ID", "C1")
    fake = FakeSlack()
    root = _repo(tmp_path, html=False)
    assert SP.main(["--company", "1234_example", "--repo", "o/r"], fake, TODAY, root) == 1
    assert fake.calls == [] and "HTML が無い" in capsys.readouterr().out
