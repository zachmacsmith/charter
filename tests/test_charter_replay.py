"""Exact replay and rewind (charter/replay.py; docs/review/04 steps 4-6): explicit call keys in calls.jsonl, a replay from the
recorded replies that reproduces events and snapshots byte for byte and fails loudly on a missing, extra or diverging call,
per-round state-only checkpoints, rewind to round N + resume == the uninterrupted run, and old single-checkpoint runs still resume.
No model is ever called: scripted bots, and a patched llm._api for the model-run replay."""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import shutil
import threading

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import generator, llm, runner
from charter import provenance as PV
from charter import replay as RP
from charter import spec as S

QUIET = dict(log=lambda *a: None)
E4 = ("E4", 1, ["rounds=3", "turns=simultaneous"])


def _spec(preset, sets):
    return S.apply_overrides(S.load(preset), list(sets) + ["shared_archive.enabled=false"])


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def _play(d, case=E4, **kw):
    preset, seed, sets = case
    inst = generator.generate(_spec(preset, sets), seed)
    inst["run_id"] = d.name
    return runner.run(inst, AG.ScriptedPolicy(seed), d, **QUIET, **kw)


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """One scripted E4 run (3 rounds, simultaneous turns), shared by the tests that only read it."""
    return _play(tmp_path_factory.mktemp("base") / "E4_run")


def _copy(run, d):
    shutil.copytree(run, d)
    return d


# ------------------------------------------------------------------ call keys
def test_every_call_has_an_explicit_unique_key(base):
    calls = _jsonl(base / "calls.jsonl")
    keys = [c["key"] for c in calls]
    assert len(set(keys)) == len(keys) == len(calls)
    for c in calls:
        kf = c["key_fields"]
        assert c["key"] == PV.call_key(kf) == f"r{kf['round']}:{kf['phase']}:{kf['wave']}:{kf['agent']}:{kf['n']}"
        assert kf["round"] == c["round"] and kf["agent"] == c["agent"] and "parsed" in c and "reasoning" in c
    phases = {c["key_fields"]["phase"] for c in calls}
    assert "decide" in phases and phases <= {"decide", "lookup", "dm_reply", "observer", "observer_step", "editorial"}


# ------------------------------------------------------------------ replay
def test_replay_of_a_scripted_run_is_byte_identical(base, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "load_env", lambda: None)
    M.main(["replay", str(base), "--out", str(tmp_path / "rep")])     # identical: no SystemExit
    rep = tmp_path / "rep"
    for f in ("events.jsonl", "snapshots.json", "reasoning.jsonl", "turns.jsonl", "instance.json"):
        assert (rep / f).read_bytes() == (base / f).read_bytes(), f
    res = json.loads((rep / "replay.json").read_text())
    assert res["identical"] and res["events_identical"] and res["snapshots_identical"] and not res["approximate"]
    calls = _jsonl(rep / "calls.jsonl")
    assert res["calls_replayed"] == len(calls) == len(_jsonl(base / "calls.jsonl")) and all(c["replayed"] for c in calls)
    strip = lambda rows: [{x: v for x, v in r.items() if x not in ("latency_s", "replayed")} for r in rows]
    assert strip(calls) == strip(_jsonl(base / "calls.jsonl"))         # the same calls, keys, prompts and replies
    meta = PV.read(rep)
    assert meta["replay_of"]["run"] == str(base.resolve()) and meta["policy"] == "ReplayPolicy" and meta["dry"] is True


def test_replay_to_round_n_matches_the_run_after_round_n(base, tmp_path):
    res = RP.replay(base, tmp_path / "rep", to=2, **QUIET)
    assert res["identical"] and res["compared_to"] == "checkpoint after round 2" and res["snapshots"] == [2, 2]
    off = json.loads((base / "checkpoints" / "index.json").read_text())["2"]["files"]
    assert (tmp_path / "rep" / "events.jsonl").read_bytes() == (base / "events.jsonl").read_bytes()[:off["events.jsonl"]]
    assert not json.loads((tmp_path / "rep" / "ground_truth.json").read_text())["complete"]
    assert PV.read(tmp_path / "rep")["segments"][-1]["status"] == "paused"


def test_replay_with_a_tampered_call_fails_loudly(base, tmp_path, monkeypatch):
    calls = _jsonl(base / "calls.jsonl")

    def tampered(name, rows):
        d = _copy(base, tmp_path / name)
        (d / "calls.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return d
    # a reply changed: the next prompts differ from the recorded ones
    i = next(i for i, c in enumerate(calls) if c["round"] == 0 and c["key_fields"]["phase"] == "decide" and c["parsed"].get("actions"))
    rows = json.loads(json.dumps(calls))
    rows[i]["parsed"]["actions"] = [{"action": "post", "args_json": json.dumps({"text": "tampered"})}]
    with pytest.raises(RP.ReplayDivergence, match="prompt differs"):
        RP.replay(tampered("changed", rows), tmp_path / "o1", **QUIET)
    # a recorded call removed: the replay asks for a reply nobody recorded
    with pytest.raises(RP.ReplayMiss, match="no recorded reply"):
        RP.replay(tampered("missing", calls[:i] + calls[i + 1:]), tmp_path / "o2", **QUIET)
    # an extra recorded call: never asked for (checked within the replayed rounds; --to 1 keeps this test short)
    ghost = {**calls[0], "key": "r0:decide:0:ghost:0", "call": "r0:ghost:0", "agent": "ghost"}
    with pytest.raises(RP.ReplayMiss, match="never asked for"):
        RP.replay(tampered("extra", calls + [ghost]), tmp_path / "o3", to=1, **QUIET)
    monkeypatch.setattr(M, "load_env", lambda: None)                    # the command line: a message and exit status 1
    with pytest.raises(SystemExit) as e:
        M.main(["replay", str(tmp_path / "missing"), "--out", str(tmp_path / "o4")])
    assert e.value.code == 1


def test_replay_of_a_run_recorded_before_call_keys_uses_call_ids(base, tmp_path):
    d = _copy(base, tmp_path / "legacy")
    rows = [{x: v for x, v in r.items() if x not in ("key", "key_fields")} for r in _jsonl(d / "calls.jsonl")]
    (d / "calls.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    res = RP.replay(d, tmp_path / "rep", to=1, **QUIET)
    assert res["identical"] and res["legacy_keys"] and res["approximate"]


def test_replay_of_a_model_run_reparses_the_raw_text(tmp_path, monkeypatch):
    """Model replies (fake llm._api): raw text in code fences, some calls failing once with reply text, some failing on every
    attempt. The replay calls no model, parses the recorded raw text again and reproduces the run."""
    lock, seen = threading.Lock(), set()

    def fake_api(model, system, user, schema, thinking_budget, max_tokens):
        h = hashlib.sha256((system + user).encode()).hexdigest()
        with lock:
            first = h not in seen
            seen.add(h)
        if h[0] in "01":
            raise RuntimeError("overloaded")                             # every attempt fails: an empty turn
        if first and h[0] in "23":
            raise llm.CallError("bad reply", raw="not json at all")      # a failed attempt with reply text, then a retry
        reply = {"reasoning": f"why {h[:4]}", "notes": f"n{h[:4]}", "goal_guesses_json": "{}",
                 "actions": [{"action": "post", "args_json": json.dumps({"text": f"hello {h[:6]}"})}]}
        return f"Here it is:\n```json\n{json.dumps(reply)}\n```", None, f"thinking {h[:4]}", {"input": 3, "output": 4}
    monkeypatch.setattr(llm, "_api", fake_api)
    sp = _spec("E4", ["rounds=2", "turns=simultaneous", "llm.fail_stop_fraction=2"])
    inst = generator.generate(sp, 2)
    run = runner.run(inst, AG.LLMPolicy("api", sp["llm"]), tmp_path / "llm", **QUIET)
    calls = _jsonl(run / "calls.jsonl")
    assert any(c["error"] for c in calls) and any(c["n_attempts"] == 2 and not c["error"] for c in calls)
    assert all("parsed" not in c for c in calls)                        # the raw text gives every reply back
    monkeypatch.setattr(llm, "_api", lambda *a, **k: pytest.fail("a replay called the model"))
    res = RP.replay(run, tmp_path / "rep", **QUIET)
    assert res["identical"] and not res["approximate"]
    assert (tmp_path / "rep" / "reasoning.jsonl").read_bytes() == (run / "reasoning.jsonl").read_bytes()
    assert PV.read(tmp_path / "rep")["dry"] is False


# ------------------------------------------------------------------ per-round checkpoints and rewind
def test_every_round_has_a_small_state_only_checkpoint(base):
    idx = json.loads((base / "checkpoints" / "index.json").read_text())
    assert sorted(map(int, idx)) == [0, 1, 2, 3]
    sizes = {}
    for n, ent in idx.items():
        blob = (base / "checkpoints" / ent["file"]).read_bytes()
        ck = pickle.loads(blob)
        assert ent["file"] == f"r{int(n):04d}.pkl" and ck["round"] == int(n) - 1 and ck["format"] == 2
        assert not {"events", "snapshots", "turn_log"} & set(ck["kernel"])   # logs are counted, not copied
        assert ck["counts"]["snapshots"] == int(n) and ent["bytes"] == len(blob)
        sizes[int(n)] = len(blob)
    assert (base / "checkpoint.pkl").read_bytes() == (base / "checkpoints" / "r0003.pkl").read_bytes()
    print("per-round checkpoint bytes (E4, 3 rounds):", sizes)
    assert max(sizes.values()) < 150_000                                # tens of KB: keeping every round is affordable
    ev = (base / "events.jsonl").stat().st_size
    assert sizes[3] < ev                                                # smaller than the log a full checkpoint would copy


def test_checkpoint_retention_keeps_every_kth_and_the_latest(tmp_path):
    out = _play(tmp_path / "keep2", ("E4", 1, ["rounds=3", "turns=simultaneous"]), keep_checkpoints=2)
    idx = json.loads((out / "checkpoints" / "index.json").read_text())
    assert sorted(map(int, idx)) == [0, 2, 3]
    assert sorted(p.name for p in (out / "checkpoints").glob("r*.pkl")) == ["r0000.pkl", "r0002.pkl", "r0003.pkl"]


def test_rewind_then_resume_equals_the_uninterrupted_run(base, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "load_env", lambda: None)
    new = tmp_path / "rewound"
    M.main(["rewind", str(base), "--to", "1", "--out", str(new)])
    assert len(json.loads((new / "snapshots.json").read_text())) == 1
    assert sorted(p.name for p in (new / "checkpoints").glob("r*.pkl")) == ["r0000.pkl", "r0001.pkl"]
    assert not json.loads((new / "ground_truth.json").read_text())["complete"]
    meta = PV.read(new)
    assert meta["parent"]["round"] == 1 and meta["parent"]["run"] == str(base.resolve()) and meta["run_id"] == "rewound"
    assert [s["kind"] for s in meta["segments"]] == ["start", "rewind"]
    monkeypatch.setattr(M, "policy_for", lambda spec, dry, seed: AG.ScriptedPolicy(seed))
    M.cmd_resume(argparse.Namespace(run=str(new), sandbox="off"))
    for f in ("events.jsonl", "snapshots.json", "reasoning.jsonl", "turns.jsonl"):
        assert (new / f).read_bytes() == (base / f).read_bytes(), f
    assert [c["key"] for c in _jsonl(new / "calls.jsonl")] == [c["key"] for c in _jsonl(base / "calls.jsonl")]
    assert [s["kind"] for s in PV.read(new)["segments"]] == ["start", "rewind", "resume"]
    assert json.loads((new / "ground_truth.json").read_text())["complete"]
    with pytest.raises(SystemExit, match="no checkpoint after round 7"):
        RP.rewind(base, 7, tmp_path / "nope")
    assert (base / "events.jsonl").read_bytes() == (new / "events.jsonl").read_bytes()   # the parent is never changed


class _Stopper:
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


def test_a_run_with_an_old_single_checkpoint_still_resumes(base, tmp_path):
    """A run from before per-round checkpoints: checkpoint.pkl (format 1) holds the event log, snapshots and turn log itself,
    and there is no checkpoints/ directory or turns.jsonl. It resumes and equals the uninterrupted run."""
    preset, seed, sets = E4
    inst = generator.generate(_spec(preset, sets), seed)
    d = tmp_path / "old"
    inst["run_id"] = base.name                                          # the same world as the base run
    with pytest.raises(runner.RunStopped):
        runner.run(inst, _Stopper(seed, 2), d, **QUIET)
    ck = runner.load_checkpoint(d, d / "checkpoint.pkl")                # rebuild it as the old runner wrote it
    old = {"version": ck["version"], "round": ck["round"], "kernel": ck["kernel"], "runner": ck["runner"],
           "files": {x: v for x, v in ck["files"].items() if x != "turns.jsonl"}}
    (d / "checkpoint.pkl").write_bytes(pickle.dumps(old))
    shutil.rmtree(d / "checkpoints")
    (d / "turns.jsonl").unlink()
    runner.run(generator.generate(_spec(preset, sets), seed) | {"run_id": base.name}, AG.ScriptedPolicy(seed), d, resume=True, **QUIET)
    for f in ("events.jsonl", "snapshots.json", "reasoning.jsonl", "turns.jsonl"):
        assert (d / f).read_bytes() == (base / f).read_bytes(), f
    assert sorted(map(int, json.loads((d / "checkpoints" / "index.json").read_text()))) == [3]   # per-round from here on


# ------------------------------------------------------------------ the golden society case
def test_replay_of_the_golden_society_case_is_byte_identical(tmp_path):
    import test_charter_golden as G                                     # tests/ is on sys.path (pytest rootdir insertion)
    CASES, GOLDEN, _sha = G.CASES, G.GOLDEN, G._sha
    preset, seed, sets = CASES["society_small_4"]
    inst = generator.generate(_spec(preset, sets), seed)
    inst["run_id"] = "golden_society_small_4"
    run = runner.run(inst, AG.ScriptedPolicy(seed), tmp_path / "society_small_4", **QUIET)
    res = RP.replay(run, tmp_path / "rep", **QUIET)
    assert res["identical"], res.get("first_difference")
    want = json.loads(GOLDEN.read_text())["society_small_4"]
    for f in ("events.jsonl", "snapshots.json"):                         # the golden fingerprints themselves
        assert _sha((tmp_path / "rep" / f).read_bytes()) == want[f], f
    assert (tmp_path / "rep" / "instance.json").read_bytes() == (run / "instance.json").read_bytes()
