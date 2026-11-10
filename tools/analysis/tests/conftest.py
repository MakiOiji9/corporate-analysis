"""Shared fixtures of the analysis tests."""
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1]
REPO = ANALYSIS.parents[1]
sys.path[:0] = [str(ANALYSIS), str(REPO / "tools" / "report"), str(REPO / "tools" / "collect" / "market"),
                str(REPO / "tools" / "collect")]

import freshness  # noqa: E402


@pytest.fixture(autouse=True)
def no_rule_changes(monkeypatch):
    """The test fixtures are dated before the real rule changes: without this every analysis would read as
    triggered. test_freshness_rules sets RULE_CHANGES itself."""
    monkeypatch.setattr(freshness, "RULE_CHANGES", {})
