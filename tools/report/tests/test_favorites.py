import json
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1]
REPO = REPORT.parents[1]
sys.path[:0] = [str(REPORT), str(REPO / "tools" / "analysis"), str(REPO / "tools" / "collect"),
                str(REPO / "tools" / "guard")]

import favorites as FV  # noqa: E402
import write_guard as WG  # noqa: E402

TODAY = "2026-11-11"


def _company(root: Path, dirname: str, report: bool = True) -> None:
    reports = root / "companies" / dirname / "reports"
    reports.mkdir(parents=True)
    if report:
        (reports / f"2026-11-10{FV.REPORT_JSON}").write_text("{}", encoding="utf-8")


def _run(root: Path, *argv: str, capsys) -> tuple[int, dict]:
    code = FV.main(list(argv), root)
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def _ledger(root: Path) -> dict:
    return json.loads((root / FV.LEDGER).read_text(encoding="utf-8"))


def test_add_writes_ledger_with_digest(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    code, out = _run(tmp_path, "add", "--company", "1234", "--group", "A", "--date", TODAY, capsys=capsys)
    assert code == 0 and out["added"] == "1234_alpha"
    ledger = _ledger(tmp_path)
    assert ledger["groups"] == {"A": [{"company": "1234_alpha", "added": TODAY}], "B": []}
    assert ledger["digest"] == FV.digest(ledger["groups"])


def test_add_rejects_company_without_built_report(tmp_path, capsys):
    _company(tmp_path, "1234_alpha", report=False)
    code, out = _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    assert code == 1 and "一度も作っていない" in out["error"]
    assert not (tmp_path / FV.LEDGER).exists()


def test_add_rejects_sixth_company(tmp_path, capsys):
    for i in range(FV.MAX_PER_GROUP + 1):
        _company(tmp_path, f"100{i}_c{i}")
    for i in range(FV.MAX_PER_GROUP):
        assert _run(tmp_path, "add", "--company", f"100{i}", "--group", "B", capsys=capsys)[0] == 0
    code, out = _run(tmp_path, "add", "--company", f"100{FV.MAX_PER_GROUP}", "--group", "B", capsys=capsys)
    assert code == 1 and "上限" in out["error"]


def test_add_rejects_company_already_in_other_group(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    code, out = _run(tmp_path, "add", "--company", "1234", "--group", "B", capsys=capsys)
    assert code == 1 and "move" in out["error"]


def test_remove_and_move(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    _company(tmp_path, "5678_beta")
    _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    _run(tmp_path, "add", "--company", "5678", "--group", "A", capsys=capsys)
    code, out = _run(tmp_path, "move", "--company", "5678", "--group", "B", capsys=capsys)
    assert code == 0 and out["from"] == "A"
    code, out = _run(tmp_path, "remove", "--company", "1234", capsys=capsys)
    assert code == 0 and out["group"] == "A"
    assert [e["company"] for e in _ledger(tmp_path)["groups"]["B"]] == ["5678_beta"]
    assert _ledger(tmp_path)["groups"]["A"] == []


def test_remove_company_whose_directory_is_gone(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    for p in sorted((tmp_path / "companies" / "1234_alpha").rglob("*"), reverse=True):
        p.unlink() if p.is_file() else p.rmdir()
    (tmp_path / "companies" / "1234_alpha").rmdir()
    assert _run(tmp_path, "validate", capsys=capsys)[0] == 1
    code, out = _run(tmp_path, "remove", "--company", "1234_alpha", capsys=capsys)
    assert code == 0 and out["issues"] == []


def test_hand_edit_is_detected_and_blocks_targets(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    _company(tmp_path, "5678_beta")
    _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    ledger = _ledger(tmp_path)
    edited = {**ledger, "groups": {**ledger["groups"], "B": [{"company": "5678_beta", "added": TODAY}]}}
    (tmp_path / FV.LEDGER).write_text(json.dumps(edited), encoding="utf-8")
    code, out = _run(tmp_path, "targets", "--group", "B", capsys=capsys)
    assert code == 1 and any("digest" in i for i in out["issues"])
    assert _run(tmp_path, "add", "--company", "5678", "--group", "A", capsys=capsys)[0] == 1


def test_targets_returns_group_in_order(tmp_path, capsys):
    _company(tmp_path, "1234_alpha")
    _company(tmp_path, "5678_beta")
    _run(tmp_path, "add", "--company", "5678", "--group", "A", capsys=capsys)
    _run(tmp_path, "add", "--company", "1234", "--group", "A", capsys=capsys)
    code, out = _run(tmp_path, "targets", "--group", "A", capsys=capsys)
    assert code == 0 and out["companies"] == ["5678_beta", "1234_alpha"]
    assert _run(tmp_path, "targets", "--group", "B", capsys=capsys)[1]["companies"] == []


def test_missing_ledger_is_empty_and_valid(tmp_path, capsys):
    code, out = _run(tmp_path, "validate", capsys=capsys)
    assert code == 0 and out["counts"] == {"A": 0, "B": 0}


def test_write_guard_blocks_hand_edits_of_ledger(tmp_path):
    for tool in ("Write", "Edit"):
        assert WG.decide(tool, "companies/favorites.json", tmp_path, TODAY)
