import json
import subprocess
import sys
from pathlib import Path

GUARD = Path(__file__).resolve().parents[2] / "guard" / "write_guard.py"
REPO = GUARD.parents[2]
sys.path.insert(0, str(GUARD.parent))

from write_guard import decide  # noqa: E402

TODAY = "2026-10-11"


def _repo(tmp_path: Path) -> Path:
    session = tmp_path / "market" / "sessions" / "2026-10-11_weekly"
    (session / "raw").mkdir(parents=True)
    (session / "raw" / "calendar-japan.md").write_text("# x\n<!-- FILL:events -->\n", encoding="utf-8")
    (session / "raw" / "done.md").write_text("# finished\n> `<!-- FILL:... -->` の行だけを置き換える\n",
                                             encoding="utf-8")
    lib = tmp_path / "market" / "policy" / "japan" / "raw"
    lib.mkdir(parents=True)
    (lib / "2026-10-11_pm-speech.md").write_text("<!-- FILL:summary -->\n", encoding="utf-8")
    company = tmp_path / "companies" / "7203_toyota" / "raw" / "ir"
    company.mkdir(parents=True)
    (company / "2026-10-01_business-overview.md").write_text("old", encoding="utf-8")
    (company / "2026-10-11_business-overview.md").write_text("today", encoding="utf-8")
    return tmp_path


def _start_run(root: Path, allowed: list[str]) -> None:
    session = root / "market" / "sessions" / "2026-10-11_weekly"
    (session / ".running").write_text("{}", encoding="utf-8")
    (session / "tasks.json").write_text(json.dumps({"tasks": [{"allowed_files": allowed}]}), encoding="utf-8")


def test_script_only_files_are_blocked(tmp_path):
    root = _repo(tmp_path)
    for rel in ("market/data/japan_series.csv", "market/policy/japan/index.csv",
                "market/policy/japan/sources/2026-10-11/a.pdf", "market/sessions/2026-10-11_weekly/tasks.json",
                "market/sessions/2026-10-11_weekly/raw/indicators-japan.md", "companies/7203_toyota/data/financials.csv"):
        assert decide("Write", rel, root, TODAY), rel


def test_market_raw_only_editable_while_fill_remains(tmp_path):
    root = _repo(tmp_path)
    fill = "market/sessions/2026-10-11_weekly/raw/calendar-japan.md"
    assert decide("Edit", fill, root, TODAY) is None
    assert "上書き" in decide("Write", fill, root, TODAY)
    assert "完成済み" in decide("Edit", "market/sessions/2026-10-11_weekly/raw/done.md", root, TODAY)
    assert "新しいファイル" in decide("Write", "market/sessions/2026-10-11_weekly/raw/new.md", root, TODAY)


def test_running_session_may_correct_its_finished_files_with_edit_only(tmp_path):
    root = _repo(tmp_path)
    done = "market/sessions/2026-10-11_weekly/raw/done.md"
    _start_run(root, [done])
    assert decide("Edit", done, root, TODAY) is None
    assert "上書き" in decide("Write", done, root, TODAY)
    (root / "market" / "sessions" / "2026-10-11_weekly" / ".running").unlink()
    assert "reopen" in decide("Edit", done, root, TODAY)


def test_latest_is_script_only(tmp_path):
    assert decide("Edit", "market/LATEST.md", _repo(tmp_path), TODAY)


def test_company_raw_from_earlier_day_is_immutable(tmp_path):
    root = _repo(tmp_path)
    assert decide("Edit", "companies/7203_toyota/raw/ir/2026-10-01_business-overview.md", root, TODAY)
    assert decide("Edit", "companies/7203_toyota/raw/ir/2026-10-11_business-overview.md", root, TODAY) is None
    assert decide("Write", "companies/7203_toyota/summaries/business.md", root, TODAY) is None


def test_running_session_limits_writes_to_allowed_files(tmp_path):
    root = _repo(tmp_path)
    allowed = "market/policy/japan/raw/2026-10-11_pm-speech.md"
    _start_run(root, [allowed])
    assert decide("Edit", allowed, root, TODAY) is None
    assert "実行中" in decide("Edit", "market/sessions/2026-10-11_weekly/raw/calendar-japan.md", root, TODAY)
    assert "実行中" in decide("Write", ".ai/skills/collect-market-info.md", root, TODAY)
    assert decide("Write", None, root, TODAY) is None  # outside the repository
    assert decide("Read", ".ai/skills/x.md", root, TODAY) is None


def test_hook_process_exit_codes(tmp_path):
    def run(payload: bytes) -> int:
        return subprocess.run([sys.executable, "-I", str(GUARD)], input=payload,
                              capture_output=True, check=False).returncode

    blocked = {"tool_name": "Write", "tool_input": {"file_path": "market/data/x.csv"}, "cwd": str(REPO)}
    outside = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / "x.txt")}, "cwd": str(tmp_path)}
    assert run(json.dumps(blocked).encode()) == 2
    assert run(json.dumps(outside).encode()) == 0
    assert run(b"not json") == 0


def test_check_cli_for_agents_without_hooks():
    def check(path: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-I", str(GUARD), "--check", path], cwd=REPO,
                              capture_output=True, check=False)

    blocked = check("market/data/x.csv")
    assert blocked.returncode == 2 and b"BLOCKED" in blocked.stdout
    assert check("companies/0000_new/summaries/business.md").returncode in (0, 2)  # 2 only while a session runs
