"""Provenance: every logged event carries its cause chain (Kernel.cause, kernel.py).

Scripted (offline) runs of two golden cases: every event has a non-empty chain rooted in its round; agents' actions, law hooks,
world effects (ageing) show the right frames; a resumed run equals an uninterrupted one, causes included.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, runner
from charter import spec as S
from charter.kernel import Kernel

SOCIETY_SMALL = ["rounds=4", "agents={worker: 4, scientist: 2, legislator: 2, media: 0, board: 2, fixer: 1}",
                 "life.full_scale_rounds=4", "life.lifespan=[3, 6]", "life.elapsed=[0, 2]", "outside_power.every=2",
                 "conflict.grace=0", "conflict.start.weapons=3"]                       # as tests/test_charter_golden.py
CASES = {"E4_fast_4": ("E4", 1, ["rounds=4", "turns=simultaneous"]), "society_small_4": ("society", 5, SOCIETY_SMALL)}


def _inst(name):
    preset, seed, sets = CASES[name]
    inst = generator.generate(S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"]), seed)
    inst["run_id"] = f"golden_{name}"
    return inst, seed


def _events(out: Path) -> list[dict]:
    return [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines()]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    base = tmp_path_factory.mktemp("cause")
    out = {}
    for name in CASES:
        inst, seed = _inst(name)
        out[name] = runner.run(inst, AG.ScriptedPolicy(seed), base / name, log=lambda *a: None)
    return out


def _kind(f):
    return Kernel.cause_kind(f)


@pytest.mark.parametrize("name", sorted(CASES))
def test_every_event_has_a_cause_rooted_in_its_round(runs, name):
    evs = _events(runs[name])
    assert evs
    for e in evs:
        ch = e.get("cause")
        assert ch, f"event without a cause: {e}"
        assert _kind(ch[0]) == "round", e
        assert len(ch) >= 2 and _kind(ch[1]) == "phase", e                      # every event happens in a named phase
        assert all(_kind(f) in Kernel.CAUSE_KINDS for f in ch), e
        phase = ch[1]["phase"]
        # end_round advances the round before the editorial turns (which prepare the next round's editions)
        assert ch[0]["round"] == e["round"] - (phase == "editorial"), e
        if e["type"] == "turn" and phase in ("turns",):
            assert any(f.get("turn") == e["agent"] for f in ch), e


@pytest.mark.parametrize("name", sorted(CASES))
def test_an_agents_transfer_shows_its_action_frame(runs, name):
    tr = [e for e in _events(runs[name]) if e["type"] == "transfer"]
    assert tr
    for e in tr:
        ch = e["cause"]
        turn = next((f["turn"] for f in reversed(ch) if "turn" in f), None)
        acts = [f for f in ch if "action" in f]
        assert acts, e
        assert (acts[-1].get("agent") or turn) == e["agent"], e                 # the agent: on the frame or its turn frame
    turns = [e for e in tr if any("turn" in f for f in e["cause"])]
    assert turns and all(next(f for f in e["cause"] if "turn" in f).get("call") for e in turns)   # linked to calls.jsonl


def test_a_death_from_ageing_shows_a_world_frame(runs):
    evs = _events(runs["society_small_4"])
    old = [e for e in evs if e["type"] == "disabled" and e["data"]["cause"] == "old_age"]
    assert old
    for e in old:
        assert {"world": "ageing", "agent": e["data"]["agent"]} in e["cause"], e
        assert e["cause"][1] == {"phase": "end_of_round"}
    estate = [e for e in evs if e["type"] == "move" and any(f.get("world") == "ageing" for f in e["cause"])]
    assert estate and all({"kernel": "death", "agent": next(f["agent"] for f in e["cause"] if f.get("world") == "ageing")}
                          in e["cause"] for e in estate)                       # the bequest follows the death it came from


def test_attacks_and_world_events_have_world_frames(runs):
    evs = _events(runs["society_small_4"])
    assert any(f.get("world") == "attack" for e in evs if e["type"] == "attack_truth" for f in e["cause"])
    assert all(any("world" in f for f in e["cause"]) for e in evs if e["type"] in ("world_event", "world_event_truth", "goal_change"))


def test_a_fine_levied_by_a_law_hook_shows_the_law_inside_the_action():
    inst, _ = _inst("E4_fast_4")
    k = Kernel(inst)
    assert k.current_cause() == ()                                             # set-up leaves the stack empty
    a, b = [x["id"] for x in inst["agents"] if x["cls"] == "worker"][:2]
    item = max(k.w["agents"][a]["holdings"], key=lambda i: k.w["agents"][a]["holdings"][i])
    lid = k.new_law(f'title = "Toll"\nintent = "Every sender is fined."\n\ndef on_transfer(src, dst, item, qty):\n'
                    f'    fine(src, "{item}", 1)\n    return 0\n', "constitution")
    k.enact(lid)
    seen = {}

    k.begin_round_cause(phase="turns")
    with k.cause("turn", a, call="r0:test:0"):
        A.act(k, a, "transfer", {"to": b, "item": item, "qty": 2})
        seen["after"] = k.current_cause()
    k.end_round_cause()
    fines = [e for e in k.events if e["type"] == "move" and e["data"]["why"] == "fine"]
    assert len(fines) == 1
    assert fines[0]["cause"] == [{"round": 0}, {"phase": "turns"}, {"turn": a, "call": "r0:test:0"}, {"action": "transfer"},
                                 {"law": lid, "hook": "on_transfer"}]
    tr = next(e for e in k.events if e["type"] == "transfer")
    assert tr["cause"][-1] == {"action": "transfer"}                          # the law frame is gone once the hook returns
    assert seen["after"] == ({"round": 0}, {"phase": "turns"}, {"turn": a, "call": "r0:test:0"})
    assert k.current_cause() == ()
    # read-only: the accessor hands out copies
    k.begin_round_cause(phase="turns")
    k.current_cause()[0]["round"] = 99
    assert k.current_cause()[0] == {"round": 0}
    with pytest.raises(AssertionError):
        k.checkpoint_state()                                                   # never inside a round's frames
    k.end_round_cause()
    st = k.checkpoint_state()
    assert set(st) == {"w", "events", "snapshots", "eff", "fn_n", "turn_log", "rng", "law_rng", "ns_data", "fns"}   # unchanged


def test_an_action_outside_a_turn_names_its_agent():
    inst, _ = _inst("E4_fast_4")
    k = Kernel(inst)
    a, b = [x["id"] for x in inst["agents"] if x["cls"] == "worker"][:2]
    item = max(k.w["agents"][a]["holdings"], key=lambda i: k.w["agents"][a]["holdings"][i])
    A.act(k, a, "transfer", {"to": b, "item": item, "qty": 1})
    tr = next(e for e in k.events if e["type"] == "transfer")
    assert tr["cause"] == [{"action": "transfer", "agent": a}]


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


@pytest.mark.slow
def test_resume_equals_an_uninterrupted_run_including_causes(runs, tmp_path):
    inst, seed = _inst("E4_fast_4")
    with pytest.raises(runner.RunStopped):
        runner.run(inst, _Stopper(seed, 2), tmp_path / "part", log=lambda *a: None)
    inst, seed = _inst("E4_fast_4")
    part = runner.run(inst, _Stopper(seed, -1), tmp_path / "part", log=lambda *a: None, resume=True)
    full = _events(runs["E4_fast_4"])
    got = _events(part)
    assert got == full
    assert all(e["cause"] for e in got)


def test_concealed_actors_are_not_named_in_visible_cause_chains():
    """Anonymous posts, forged DMs and unnamed disables hide their actor: no non-monitor event's chain names it (truth events do)."""
    import json as _json
    from charter import actions as A, generator, spec as S
    from charter.kernel import Kernel
    k = Kernel(generator.generate(S.apply_overrides(S.load("E3"), ["shared_archive.enabled=false"]), 2))
    a, b, c = list(k.w["agents"])[:3]
    k.w["agents"][a]["rights"].append("anon")
    with k.cause("turn", a, call=f"r0:{a}:0"):
        pid = A.act(k, a, "anon_post", {"text": "the Chair is bought"}).split("(")[1].rstrip(").")
    e = next(x for x in k.events if x["id"] == pid)
    assert a not in _json.dumps(e) and e["cause"]                       # the chain is kept, the author removed
    with k.cause("turn", a, call=f"r0:{a}:1"):
        eid = A.forge_message(k, a, c, b, "meet me", cost={})
    e = next(x for x in k.events if x["id"] == eid)
    assert a not in _json.dumps(e["cause"])                             # (the entry's agent field is the true sender by design: the
    truth = next(x for x in k.events if x["type"] == "forged_dm")
    assert truth["vis"] == "monitor" and any(f.get("turn") == a for f in truth["cause"])
    with k.concealing(a):
        k.log("note", None, {"x": 1}, vis="monitor")
    assert k.events[-1]["cause"] == list(k._causes)                    # monitor events keep the full chain
