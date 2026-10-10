"""llm.cache_ttl: the prompt-cache lifetime reaches both backends, and a run flags (never stops) rounds averaging longer."""
import pytest

from charter import llm as LLM


@pytest.fixture(autouse=True)
def _reset():
    yield
    LLM.set_cache_ttl(None)


def test_cli_env_and_api_marker_follow_the_setting():
    LLM.set_cache_ttl("5m")
    _, env = LLM.cli_command("m", "sys", "hi", {"type": "object"})
    assert env["CLAUDE_CODE_PROMPT_CACHE_TTL"] == "5m"
    assert LLM.cache_marker() == {"type": "ephemeral"}
    LLM.set_cache_ttl("1h")
    _, env = LLM.cli_command("m", "sys", "hi", {"type": "object"})
    assert env["CLAUDE_CODE_PROMPT_CACHE_TTL"] == "1h"
    assert LLM.cache_marker() == {"type": "ephemeral", "ttl": "1h"}


def test_auto_leaves_the_backend_choice():
    for v in (None, "auto"):
        LLM.set_cache_ttl(v)
        _, env = LLM.cli_command("m", "sys", "hi", {"type": "object"})
        assert "CLAUDE_CODE_PROMPT_CACHE_TTL" not in env or env["CLAUDE_CODE_PROMPT_CACHE_TTL"] == __import__("os").environ.get("CLAUDE_CODE_PROMPT_CACHE_TTL")
        assert LLM.cache_marker() == {"type": "ephemeral"}


def test_flag_only_when_rounds_average_longer_than_the_ttl():
    LLM.set_cache_ttl("5m")
    assert LLM.cache_ttl_flag([400]) is None                    # one round is not an average
    assert LLM.cache_ttl_flag([200, 350]) is None               # mean 275s < 300s
    msg = LLM.cache_ttl_flag([300, 400])
    assert msg and "350s" in msg and "1h" in msg
    LLM.set_cache_ttl("1h")
    assert LLM.cache_ttl_flag([400, 500]) is None
    LLM.set_cache_ttl(None)
    assert LLM.cache_ttl_flag([4000, 5000]) is None


def test_runner_flags_slow_rounds_without_stopping(tmp_path, monkeypatch):
    from charter import agents as AG, generator, provenance as PV, runner
    from charter import spec as S
    inst = generator.generate(S.apply_overrides(S.load("society"), ["rounds=3", "shared_archive.enabled=false"]), 1)
    assert inst["spec"]["llm"]["cache_ttl"] == "5m"
    clock = iter(range(0, 10_000, 400))                         # every time.time() call advances 400s
    monkeypatch.setattr(runner.time, "time", lambda: next(clock))
    logs = []
    runner.run(inst, AG.ScriptedPolicy(1), tmp_path, log=logs.append)
    rj = PV.read(tmp_path)
    assert rj["cache_ttl"] == "5m"
    assert [f["kind"] for f in rj["flags"]] == ["cache_ttl"]    # flagged once, and the run completed
    assert any("FLAG:" in x for x in logs)
