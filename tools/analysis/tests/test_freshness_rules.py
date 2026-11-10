from pathlib import Path
from types import SimpleNamespace

import freshness as T


def test_rule_triggers_by_analysis_kind_and_day(monkeypatch):
    monkeypatch.setattr(T, "RULE_CHANGES", {"safety": [("2026-11-10", "借入目的の区分")]})
    safety = SimpleNamespace(analysis_dir=Path("companies/x/analysis/safety"))
    swot = SimpleNamespace(analysis_dir=Path("companies/x/analysis/swot"))
    assert T.rule_triggers(safety, "2026-11-01") == ["判定ルールが変わった（2026-11-10: 借入目的の区分）"]
    assert T.rule_triggers(safety, "2026-11-10") == []  # built on or after the change
    assert T.rule_triggers(swot, "2026-11-01") == []    # its rules did not change
    assert T.rule_triggers(SimpleNamespace(), "2026-11-01") == []
