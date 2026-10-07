"""Provenance (charter/provenance.py): run.json and its segments, calls.jsonl with content-addressed system prompts, every attempt of a
model call, and the append-only files covered by checkpoint offsets (a member Spy's observer.jsonl after a stop and resume).
No model is ever called: scripted bots, and a patched llm._api for the attempt records."""
from __future__ import annotations

import argparse
import hashlib
import json

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import generator, llm, runner
from charter import provenance as PV
from charter import spec as S


def _spec(preset, *sets):
    return S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets])


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class _Stopper:
    """Scripted bot that fails every call in one round, to stop and resume a run."""
    parallel_safe = False

    def __init__(self, seed, stop_round):
        self.inner, self.stop = AG.ScriptedPolicy(seed), stop_round

    @property
    def rng(self):
        return self.inner.rng

    def act(self, k, a, system, user, n, final):
        if k.r == self.stop:
            return {"_error": "quota", "actions": []}, "", {}
        return self.inner.act(k, a, system, user, n, final)


# ------------------------------------------------------------------ run.json
def test_run_json_records_code_versions_and_no_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-NOT-A-REAL-KEY-123")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "oauth-NOT-A-REAL-TOKEN-456")
    sp = _spec("E2", "rounds=2")
    sp["llm"]["api_key"] = "sk-test-in-spec-789"                       # a key wrongly put in the spec is redacted too
    inst = generator.generate(sp, 3)
    out = runner.run(inst, AG.ScriptedPolicy(3), tmp_path / "r", log=lambda *a: None)
    text = (out / "run.json").read_text()
    for secret in ("sk-test-NOT-A-REAL-KEY-123", "oauth-NOT-A-REAL-TOKEN-456", "sk-test-in-spec-789"):
        assert secret not in text
    m = json.loads(text)
    assert m["dry"] is True and m["backend"] == "scripted" and m["seed"] == 3 and m["llm"]["api_key"] == "<redacted>"
    assert m["spec_sha"] == PV.sha(json.dumps(inst["spec"], sort_keys=True, default=str))
    assert m["python"] and "sha" in m["git"] and "dirty" in m["git"]
    code = m["code"]
    assert {"runner", "kernel", "llm", "provenance", "camptypes/"} <= set(code["modules"])
    assert code["modules"]["runner"] == hashlib.sha256((PV.PKG / "runner.py").read_bytes()).hexdigest()[:16]
    assert code["state_schema"] == 1 and code["law_api"] == 1 and code["scoring"] == 1
    (seg,) = m["segments"]
    assert seg["kind"] == "start" and seg["first_round"] == 0 and seg["status"] == "complete" and seg["last_round"] == 1
    assert seg["changed_modules"] == [] and seg["code"] == code


def test_resume_appends_a_segment_and_records_changed_code(tmp_path, monkeypatch):
    sp = _spec("E2", "rounds=4")
    with pytest.raises(runner.RunStopped):
        runner.run(generator.generate(sp, 3), _Stopper(3, 2), tmp_path / "r", log=lambda *a: None)
    m = PV.read(tmp_path / "r")
    assert m["segments"][-1]["status"] == "stopped" and m["segments"][-1]["last_round"] == 1
    real = PV.module_hashes
    monkeypatch.setattr(PV, "module_hashes", lambda: {**real(), "kernel": "0" * 16, "brand_new": "1" * 16})
    monkeypatch.setattr("charter.scorer.SCORING_VERSION", 2)
    runner.run(generator.generate(sp, 3), _Stopper(3, -1), tmp_path / "r", log=lambda *a: None, resume=True)
    m = PV.read(tmp_path / "r")
    a, b = m["segments"]
    assert a["kind"] == "start" and b["kind"] == "resume" and b["first_round"] == 2 and b["checkpoint_version"] == 1
    assert b["changed_modules"] == ["brand_new", "kernel"] and b["changed_versions"] == {"scoring": [1, 2]}
    assert b["status"] == "complete" and m["code"]["scoring"] == 1             # the top-level block stays the start's


def test_cmd_resume_reads_dry_from_run_json_not_the_directory_name(tmp_path, monkeypatch):
    sp = _spec("E2", "rounds=3")
    inst = generator.generate(sp, 3)
    d = tmp_path / "plain_name"                                         # no "_dry" in the name
    inst["run_id"] = d.name
    pristine = json.dumps(inst, default=str)
    # cmd_resume regenerates the world from instance.json's spec; a JSON round trip of the spec does not regenerate the same
    # world today (a separate generator issue), so serve the original instance here
    monkeypatch.setattr(M.generator, "generate", lambda spec, seed: json.loads(pristine))
    with pytest.raises(runner.RunStopped):
        runner.run(inst, _Stopper(3, 1), d, log=lambda *a: None)
    asked = []

    def policy_for(spec, dry, seed):
        asked.append(dry)
        assert dry, "would have built an LLM policy"
        return AG.ScriptedPolicy(seed)
    monkeypatch.setattr(M, "policy_for", policy_for)
    M.cmd_resume(argparse.Namespace(run=str(d), sandbox="off"))
    assert asked == [True] and json.loads((d / "ground_truth.json").read_text())["complete"]
    assert [s["dry"] for s in PV.read(d)["segments"]] == [True, True]


# ------------------------------------------------------------------ calls.jsonl and system prompts
def test_calls_link_to_reasoning_rows_and_store_each_system_prompt_once(tmp_path):
    sp = _spec("context_pilot", "rounds=3", "context.lookups_in_dm_step=false")
    inst = generator.generate(sp, 1)
    out = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "r", log=lambda *a: None)
    calls, rows = _jsonl(out / "calls.jsonl"), _jsonl(out / "reasoning.jsonl")
    by_id = {c["call"]: c for c in calls}
    assert len(by_id) == len(calls)                                     # ids are unique
    assert sorted(r["usage"]["call"] for r in rows) == sorted(by_id)  # one reasoning row per call, linked by id
    for r in rows:
        c = by_id[r["usage"]["call"]]
        assert c["agent"] == r["agent"] and c["round"] == r["round"] and c["parsed"] is not None and c["backend"] == "scripted"
    shas = {c["system_sha"] for c in calls}
    files = {p.stem: p.read_text() for p in (out / "prompts" / "system").glob("*.txt")}
    assert set(files) == shas                                           # each distinct prompt once, nothing else
    assert all(PV.sha(t) == h for h, t in files.items())
    per_agent = {}
    for c in calls:
        per_agent.setdefault(c["agent"], set()).add(c["system_sha"])
    assert len(shas) > len({c["agent"] for c in calls})                 # context on: the core prompt changes between turns...
    assert len(shas) < len(calls)                                       # ...and repeats are stored once


def test_llm_attempts_keep_raw_text_and_failed_attempts(tmp_path, monkeypatch):
    replies = iter([RuntimeError("overloaded"), '{"actions": [], "notes": "n", "goal_guesses_json": "{}"}'])

    def fake_api(model, system, user, schema, thinking_budget, max_tokens):
        x = next(replies)
        if isinstance(x, Exception):
            raise x
        return x, None, "thought", {"input": 1, "output": 2}
    monkeypatch.setattr(llm, "_api", fake_api)
    pol = PV.Recorder(AG.LLMPolicy("api", {}), tmp_path, append=False)

    class K:
        r, w = 4, {}
    out, reasoning, usage = pol.act(K(), {"id": "a1", "cls": "observer", "model": "m"}, "SYSTEM", "USER", 3, False)
    pol.close()
    assert out["notes"] == "n" and reasoning == "thought" and usage["call"] == "r4:a1:0"
    (row,) = _jsonl(tmp_path / "calls.jsonl")
    a0, a1 = row["attempts"]
    assert not a0["ok"] and "overloaded" in a0["error"] and a0["raw"] is None
    assert a1["ok"] and json.loads(a1["raw"])["notes"] == "n" and a1["backend"] == "api" and "latency_s" in a1
    assert row["n_attempts"] == 2 and row["backend"] == "api" and "parsed" not in row and row["error"] is None
    assert (tmp_path / "prompts" / "system" / f"{row['system_sha']}.txt").read_text() == "SYSTEM"
    replies = iter([ValueError("bad json"), ValueError("bad json")])   # every attempt fails: an empty turn, both errors kept
    out, _, _ = PV.Recorder(AG.LLMPolicy("api", {}), tmp_path, append=True).act(K(), {"id": "a1", "cls": "observer", "model": "m"},
                                                                                "SYSTEM", "USER", 3, False)
    row = _jsonl(tmp_path / "calls.jsonl")[-1]
    assert out["_error"] and row["error"] == out["_error"] and [x["ok"] for x in row["attempts"]] == [False, False]
    assert row["call"] == "r4:a1:0"                                     # a new Recorder (a new segment) counts from 0 again


# ------------------------------------------------------------------ checkpoint offsets: the member Spy's observer.jsonl
class _FailAfterSpy:
    """Scripted bot that, in round `r`, fails the first call made after the Spy's turn (so the Spy's observer.jsonl row of the
    abandoned round is already written when the round is abandoned)."""
    parallel_safe = False

    def __init__(self, seed, spy, r):
        self.inner, self.spy, self.r, self.seen = AG.ScriptedPolicy(seed), spy, r, False

    @property
    def rng(self):
        return self.inner.rng

    def act(self, k, a, system, user, n, final):
        if k.r == self.r and self.seen:
            return {"_error": "quota", "actions": []}, "", {}
        if k.r == self.r and a["id"] == self.spy:
            self.seen = True
        return self.inner.act(k, a, system, user, n, final)


def test_member_spy_resume_does_not_duplicate_observer_rows(tmp_path):
    sp = _spec("roles_pilot", "rounds=4", "turns=sequential", "roles.enabled=true", "observer.reads_per_round=2",
               "llm.fail_stop_fraction=0.01")                           # the first failed call stops the round
    inst = generator.generate(sp, 5)
    spy = inst["roles"]["holders"]["spy"][0]
    full = runner.run(inst, AG.ScriptedPolicy(5), tmp_path / "full", log=lambda *a: None)
    assert _jsonl(full / "observer.jsonl")                               # member mode: the Spy writes observer.jsonl
    orders = {e["round"]: e["data"]["order"] for e in _jsonl(full / "events.jsonl") if e["type"] == "round_start"}
    r = next(r for r in range(1, 4) if orders[r].index(spy) < len(orders[r]) - 1)   # a round where someone plays after the Spy
    with pytest.raises(runner.RunStopped):
        runner.run(generator.generate(sp, 5), _FailAfterSpy(5, spy, r), tmp_path / "cut", log=lambda *a: None)
    assert PV.read(tmp_path / "cut")["segments"][-1]["status"] == "stopped"
    cut = runner.run(generator.generate(sp, 5), AG.ScriptedPolicy(5), tmp_path / "cut", log=lambda *a: None, resume=True)
    recs = _jsonl(cut / "observer.jsonl")
    assert len({(x["round"], x["observer"]) for x in recs}) == len(recs)   # no duplicated Spy rows
    for f in ("observer.jsonl", "events.jsonl"):
        assert (cut / f).read_text() == (full / f).read_text(), f
    ab = _jsonl(cut / "abandoned_calls.jsonl")                          # the abandoned round's calls are kept, marked
    assert ab and all(x["round"] == r and x["abandoned"] for x in ab) and any(x["agent"] == spy for x in ab)
    assert [c["call"] for c in _jsonl(cut / "calls.jsonl")] == [c["call"] for c in _jsonl(full / "calls.jsonl")]
