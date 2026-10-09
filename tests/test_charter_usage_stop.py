"""Runs on the subscription (claude_code backend) stop before a round once a usage window is at llm.usage_stop (default 90%)."""
from __future__ import annotations

import pytest

from charter import agents as AG, generator, llm as LLM, runner, spec as S


def _event(five, seven, status="allowed"):
    return {"status": status, "unifiedWindows": {"five_hour": {"utilization": five}, "seven_day": {"utilization": seven}}}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("CHARTER_USAGE_STOP", raising=False)
    LLM.USAGE.clear()
    yield
    LLM.USAGE.clear()


def test_usage_stop_levels(monkeypatch):
    assert LLM.usage_stop({}) is None                                  # no usage seen (api backend, dry runs)
    LLM.note_usage(_event(0.5, 0.89))
    assert LLM.usage_stop({}) is None
    LLM.note_usage(_event(0.9, 0.45))
    assert "five_hour window 90% used" in LLM.usage_stop({})
    assert LLM.usage_stop({"usage_stop": 0.95}) is None
    assert LLM.usage_stop({"usage_stop": None}) is None
    monkeypatch.setenv("CHARTER_USAGE_STOP", "null")
    assert LLM.usage_stop({}) is None
    monkeypatch.setenv("CHARTER_USAGE_STOP", "0.5")
    assert LLM.usage_stop({"usage_stop": 0.99}) is not None
    monkeypatch.delenv("CHARTER_USAGE_STOP")
    LLM.note_usage(_event(0.2, 0.2, status="rejected"))
    assert "limit reached" in LLM.usage_stop({})


def test_run_stops_before_the_next_round(tmp_path):
    sp = S.apply_overrides(S.load("base"), ["rounds=4", "shared_archive.enabled=false"])
    LLM.note_usage(_event(0.93, 0.4))
    with pytest.raises(runner.RunStopped, match="subscription usage"):
        runner.run(generator.generate(sp, 2), AG.ScriptedPolicy(2), tmp_path / "r", log=lambda *a: None)
    text = (tmp_path / "r" / "STOPPED.md").read_text()
    assert "five_hour window 93% used" in text and "CHARTER_USAGE_STOP" in text
