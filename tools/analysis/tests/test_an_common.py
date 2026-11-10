import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ANALYSIS)]

import an_common as A  # noqa: E402

DAY = "2026-11-01"


def _files(directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = [directory / f"{DAY}_x.json", directory / f"{DAY}_x.md", directory / f"{DAY}_brief.md"]
    for p in paths:
        p.write_text(p.name, encoding="utf-8")
    (directory / "2026-10-01_x.json").write_text("old", encoding="utf-8")
    return paths


def test_supersede_moves_only_todays_files_and_numbers_the_folder(tmp_path):
    _files(tmp_path)
    first = A.supersede_today(tmp_path, DAY)
    assert first == tmp_path / A.SUPERSEDED_DIR / f"{DAY}-1"
    assert sorted(p.name for p in first.iterdir()) == [f"{DAY}_brief.md", f"{DAY}_x.json", f"{DAY}_x.md"]
    assert (tmp_path / "2026-10-01_x.json").exists()
    _files(tmp_path)
    assert A.supersede_today(tmp_path, DAY) == tmp_path / A.SUPERSEDED_DIR / f"{DAY}-2"


def test_supersede_returns_none_when_nothing_to_move(tmp_path):
    assert A.supersede_today(tmp_path / "missing", DAY) is None
    assert A.supersede_today(tmp_path, DAY) is None
    assert not (tmp_path / A.SUPERSEDED_DIR).exists()


def test_supersede_puts_files_back_when_a_move_fails(tmp_path, monkeypatch):
    paths = _files(tmp_path)
    real_rename = Path.rename
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise PermissionError("locked")
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(OSError):
        A.supersede_today(tmp_path, DAY)
    monkeypatch.setattr(Path, "rename", real_rename)
    assert all(p.exists() for p in paths)
    assert not (tmp_path / A.SUPERSEDED_DIR / f"{DAY}-1").exists()


def test_supersede_keeps_the_original_error_when_the_rollback_also_fails(tmp_path, monkeypatch):
    _files(tmp_path)
    real_rename = Path.rename
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] == 2:
            raise PermissionError("locked")
        if calls["n"] == 3:
            raise PermissionError("still locked")  # putting the first file back fails too
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", flaky)
    with pytest.raises(PermissionError, match="^locked") as caught:  # the original error, not the rollback's
        A.supersede_today(tmp_path, DAY)
    monkeypatch.setattr(Path, "rename", real_rename)
    notes = " ".join(getattr(caught.value, "__notes__", []))
    assert f"{DAY}_brief.md" in notes and "_superseded" in notes  # tells where the stranded file is


# ---------------------------------------------------------------- retention (latest + one before)

def _built(directory: Path, date: str, verdict: str = "中", draft: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{date}_x.md").write_text("<!-- FILL:a -->" if draft else "done", encoding="utf-8")
    (directory / f"{date}_x.json").write_text(f'{{"verdict": "{verdict}"}}', encoding="utf-8")
    (directory / f"{date}_x_brief.md").write_text("b", encoding="utf-8")


def test_prune_keeps_the_two_newest_finished_dates(tmp_path):
    for date, verdict in (("2026-01-01", "低"), ("2026-05-01", "中"), ("2026-08-01", "中"), ("2026-11-01", "高")):
        _built(tmp_path, date, verdict)
    (tmp_path / "_superseded" / "2026-11-01-1").mkdir(parents=True)
    (tmp_path / "_superseded" / "2026-11-01-1" / "2026-11-01_x.md").write_text("old", encoding="utf-8")
    removed = A.prune(tmp_path, "_x.md")
    left = sorted(p.name for p in tmp_path.iterdir())
    assert left == ["2026-08-01_x.json", "2026-08-01_x.md", "2026-08-01_x_brief.md", "2026-11-01_x.json",
                    "2026-11-01_x.md", "2026-11-01_x_brief.md", "_history.json"]
    assert len(removed) == 7  # 2 dates x 3 files + the _superseded folder
    assert A.history_verdict(tmp_path, "2026-06-30") == ("2026-05-01", "中")
    assert A.history_verdict(tmp_path, "2026-03-01") == ("2026-01-01", "低")
    assert A.history_verdict(tmp_path, "2025-12-31") is None


def test_prune_keeps_a_newer_draft_and_the_finished_ones_under_it(tmp_path):
    for date in ("2026-01-01", "2026-05-01", "2026-08-01"):
        _built(tmp_path, date)
    _built(tmp_path, "2026-11-01", draft=True)
    A.prune(tmp_path, "_x.md")
    dates = sorted({p.name[:10] for p in tmp_path.glob("2026-*")})
    assert dates == ["2026-05-01", "2026-08-01", "2026-11-01"]


def test_prune_with_two_or_fewer_results_removes_nothing_but_superseded(tmp_path):
    _built(tmp_path, "2026-08-01")
    _built(tmp_path, "2026-11-01")
    (tmp_path / "_superseded").mkdir()
    removed = A.prune(tmp_path, "_x.md")
    assert removed == [tmp_path / "_superseded"]
    assert not (tmp_path / "_history.json").exists()


def test_prune_on_a_missing_directory(tmp_path):
    assert A.prune(tmp_path / "none", "_x.md") == []
