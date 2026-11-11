import json
import sys
from pathlib import Path

import pytest

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect")]

import issue_request as IR  # noqa: E402

TEMPLATE = REPO / ".github" / "ISSUE_TEMPLATE" / "company-analysis.yml"


def _blocks(ticker="1234", name="example", url="https://www.example.co.jp/ir/", market="japan") -> list[str]:
    values = {"ticker": ticker, "name": name, "url": url, "market": market}
    return [f"### {IR.LABELS[k]}\n\n{v}" for k, v in values.items()]


def _body(**kwargs) -> str:
    return "\n\n".join(_blocks(**kwargs)) + "\n"


def test_valid_japan_request(tmp_path):
    out = IR.parse(_body(), tmp_path)
    assert out == {"ok": True, "ticker": "1234", "name": "example", "url": "https://www.example.co.jp/ir/",
                   "market": "japan", "existing": None}


def test_us_ticker_is_upper_cased_and_crlf_is_accepted(tmp_path):
    out = IR.parse(_body(ticker="brk.b", market="us").replace("\n", "\r\n"), tmp_path)
    assert out["ok"] and out["ticker"] == "BRK.B" and out["market"] == "us"


def test_order_of_headings_does_not_matter(tmp_path):
    assert IR.parse("\n\n".join(reversed(_blocks())), tmp_path)["ok"]


def test_missing_field(tmp_path):
    out = IR.parse(_body(url=IR.NO_RESPONSE), tmp_path)
    assert not out["ok"] and any("ホームページ URL" in e and "未記入" in e for e in out["errors"])


@pytest.mark.parametrize("kwargs, word", [
    ({"ticker": "AAPL"}, "銘柄コード"),                       # a US ticker for a Japanese stock
    ({"ticker": "7203", "market": "us"}, "銘柄コード"),
    ({"market": "china"}, "市場"),
    ({"name": "Toyota Motor"}, "企業名"),
    ({"name": "../evil"}, "企業名"),
    ({"url": "http://example.com/"}, "URL"),
    ({"url": "https://example.com/$(curl x)"}, "URL"),
    ({"url": "https://example.com/ \"; rm"}, "URL"),
])
def test_invalid_values_are_rejected(tmp_path, kwargs, word):
    out = IR.parse(_body(**kwargs), tmp_path)
    assert not out["ok"] and any(word in e for e in out["errors"])


def test_existing_company_is_found(tmp_path):
    (tmp_path / "companies" / "1234_example").mkdir(parents=True)
    assert IR.parse(_body(), tmp_path)["existing"] == "1234_example"


def test_cli_reads_body_file(tmp_path, capsys):
    body = tmp_path / "body.md"
    body.write_text(_body(), encoding="utf-8")
    assert IR.main(["parse", "--body-file", str(body)], tmp_path) == 0
    assert json.loads(capsys.readouterr().out)["ticker"] == "1234"


def test_labels_match_the_issue_template():
    text = TEMPLATE.read_text(encoding="utf-8")
    for label in IR.LABELS.values():
        assert f"label: {label}" in text, label
