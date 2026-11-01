import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPORT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(REPORT)]

import cr_batch as B  # noqa: E402
import cr_status as S  # noqa: E402

DAY = "2026-11-02"
STEP1 = ("five-forces", "three-c", "moat", "swot")


class FakeCompany:
    def __init__(self, root: Path, path: Path):
        self.root, self.path = root, path
        self.dirname = path.name

    def rel(self, p: Path) -> str:
        return p.relative_to(self.root).as_posix()


class FakeAnalysis:
    """check / prepare / build of one analysis on files: md with one FILL per key, json once built."""

    def __init__(self, root: Path, skill: str, keys: tuple[str, ...], collect: dict | None = None):
        self.root, self.skill, self.keys, self.collect = root, skill, keys, collect
        self.dir = root / "companies" / "1111_x" / "analysis" / skill
        self.calls: list[str] = []

    def md(self, date: str = DAY) -> Path:
        return self.dir / f"{date}_{self.skill}.md"

    def built(self) -> bool:
        return self.md().with_suffix(".json").exists()

    def main(self, argv: list[str], root: Path) -> int:
        cmd = argv[0]
        self.calls.append(cmd)
        if cmd == "check":
            out = {"ok": True, "next": "collect", **self.collect} if self.collect else {"ok": True, "next": "prepare"}
        elif cmd == "prepare":
            md = self.md()
            if not md.exists():
                self.dir.mkdir(parents=True, exist_ok=True)
                md.write_text("# x\n\n> rule one\n\n" + "\n".join(f"| {k} | <!-- FILL:{k} {k} を書く --> |" for k in self.keys)
                              + "\n", encoding="utf-8")
            out = {"ok": True, "md": md.relative_to(root).as_posix(), "brief": "b.md", "date": DAY}
        elif "FILL:" in self.md().read_text(encoding="utf-8"):  # build
            out = {"ok": False, "issues": ["FILL が残っている"]}
        else:
            self.md().with_suffix(".json").write_text("{}", encoding="utf-8")
            out = {"ok": True, "verdict": "普通", "json": "j"}
        print(json.dumps(out, ensure_ascii=False))
        return 0


def _paths_for(skill: str):
    class Company(FakeCompany):
        @property
        def analysis_dir(self) -> Path:
            return self.path / "analysis" / skill

        def file(self, date: str, suffix: str) -> Path:
            return self.analysis_dir / f"{date}{suffix}"
    return SimpleNamespace(Company=Company, MD_SUFFIX=f"_{skill}.md", JSON_SUFFIX=f"_{skill}.json")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / "companies" / "1111_x"
    path.mkdir(parents=True)
    fakes = {k: FakeAnalysis(tmp_path, k, ("a", "b")) for k in B.BATCH}
    fakes["valuation"].keys = ()
    step1 = {k: "fresh" for k in STEP1}
    monkeypatch.setattr(S, "STEPS", tuple(SimpleNamespace(skill=k, script=fakes[k], paths=_paths_for(k))
                                          for k in B.BATCH))

    def check(root, company, today, redo=False, use_existing=False):
        rows = [{"skill": k, "result": step1[k], "date": None, "verdict": None} for k in STEP1]
        rows += [{"skill": k, "result": "fresh" if fakes[k].built() else "none", "date": None, "verdict": None}
                 for k in B.BATCH]
        return {"steps": rows, "next": next((r["skill"] for r in rows if r["result"] != "fresh"), "prepare")}
    monkeypatch.setattr(S, "check", check)
    return SimpleNamespace(root=tmp_path, company=FakeCompany(tmp_path, path), fakes=fakes, step1=step1)


def _fills(fake: FakeAnalysis, values: dict) -> None:
    (fake.dir / f"{DAY}_fills.json").write_text(json.dumps(values), encoding="utf-8")


def test_first_run_prepares_the_three_independent_analyses(setup):
    out = B.run(setup.root, setup.company, DAY)
    assert out["next"] == "write" and [w["skill"] for w in out["write"]] == ["profitability", "growth", "safety"]
    packet = out["write"][0]
    assert packet["fill_keys"] == ["a", "b"] and packet["rules"] == ["rule one"]
    assert packet["fills_json"].endswith(f"analysis/profitability/{DAY}_fills.json")
    assert setup.fakes["cash-flow"].calls == [] and setup.fakes["valuation"].calls == []  # upstream not ready


def test_json_is_poured_and_removed_then_the_next_analyses_follow(setup):
    B.run(setup.root, setup.company, DAY)
    for k in ("profitability", "growth", "safety"):
        _fills(setup.fakes[k], {"a": "x", "b": "y"})
    out = B.run(setup.root, setup.company, DAY)
    assert [b["skill"] for b in out["built"]] == ["profitability", "growth", "safety"]
    assert [w["skill"] for w in out["write"]] == ["cash-flow"] and setup.fakes["valuation"].calls == []
    assert not (setup.fakes["growth"].dir / f"{DAY}_fills.json").exists()
    setup.fakes["cash-flow"].md().write_text("| a | x |\n| b | y |\n", encoding="utf-8")  # written in the md itself
    out = B.run(setup.root, setup.company, DAY)
    assert [b["skill"] for b in out["built"]] == ["cash-flow", "valuation"]  # valuation has nothing to write
    assert out["next"] == "prepare" and out["ok"]


def test_a_partial_json_leaves_the_rest_to_write(setup):
    B.run(setup.root, setup.company, DAY)
    _fills(setup.fakes["safety"], {"a": "x"})
    out = B.run(setup.root, setup.company, DAY)
    safety = next(w for w in out["write"] if w["skill"] == "safety")
    assert safety["fill_keys"] == ["b"] and out["built"] == []


def test_bad_json_is_an_error_and_nothing_is_built(setup):
    B.run(setup.root, setup.company, DAY)
    _fills(setup.fakes["safety"], {"zzz": "x"})
    out = B.run(setup.root, setup.company, DAY)
    assert out["next"] == "fix" and not out["ok"] and out["errors"][0]["skill"] == "safety"
    assert "zzz" in out["errors"][0]["error"][0]


def test_step1_comes_first(setup):
    setup.step1["moat"] = "expired"
    out = B.run(setup.root, setup.company, DAY)
    assert out["next"] == "moat" and setup.fakes["profitability"].calls == []


def _built(fake: FakeAnalysis) -> None:
    fake.dir.mkdir(parents=True, exist_ok=True)
    fake.md().write_text("x\n", encoding="utf-8")
    fake.md().with_suffix(".json").write_text("{}", encoding="utf-8")


def test_price_only_gap_is_refreshed_by_the_script(setup, monkeypatch):
    for k in ("profitability", "growth", "safety", "cash-flow"):
        _built(setup.fakes[k])
    val = setup.fakes["valuation"]
    val.collect = {"price_refresh": "tools/collect/refresh_valuation.py --company 1111_x", "missing_inputs": []}
    calls = []

    def refresh(root, company, today):
        calls.append(company)
        val.collect = None  # the price is new now
        return {"ok": True, "base_date": "2026-10-30"}
    monkeypatch.setattr(B.RV, "run", refresh)
    out = B.run(setup.root, setup.company, DAY)
    assert calls == ["1111_x"] and out["price_refreshed"][0]["skill"] == "valuation"
    assert [b["skill"] for b in out["built"]] == ["valuation"] and out["next"] == "prepare"


def test_a_failed_refresh_goes_to_collect_once(setup, monkeypatch):
    for k in ("profitability", "growth", "safety", "cash-flow"):
        _built(setup.fakes[k])
    setup.fakes["valuation"].collect = {"price_refresh": "x", "missing_inputs": [{"agent": "a", "items": ["株価"]}]}
    monkeypatch.setattr(B.RV, "run", lambda root, company, today: {"ok": False, "error": "e", "fallback": "f"})
    out = B.run(setup.root, setup.company, DAY)
    assert out["next"] == "collect" and out["collect"][0]["fallback"] == "f"


def test_another_gap_is_returned_to_collect(setup):
    setup.fakes["profitability"].collect = {"missing_inputs": [{"agent": "collect-filings", "items": ["x"]}]}
    out = B.run(setup.root, setup.company, DAY)
    assert out["next"] == "write" and out["collect"][0]["skill"] == "profitability"
    assert [w["skill"] for w in out["write"]] == ["growth", "safety"]
