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
