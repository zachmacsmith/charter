"""Interventions and forks (charter/interventions.py, runner.RunState, replay.fork / branches; ARCHITECTURE §3.12, §8.3, §8.4):
one test per op (applied in memory through apply_due), the runner's hook points, a resume that never re-applies an intervention,
--notice / --live as setup interventions, replay of a run with interventions, and forks: an empty schedule under strict replay
reproduces the parent's suffix exactly, an intervention diverges exactly at the fork point, replicates differ only after it, and
`branches` lists the lineage. No model is ever called: scripted bots only."""
from __future__ import annotations

import copy
import json
import shutil

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import generator, runner
from charter import interventions as IV
from charter import provenance as PV
from charter import replay as RP
from charter import spec as S
from charter.kernel import Kernel

QUIET = dict(log=lambda *a: None)


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ====================================================================== in memory: one test per op
@pytest.fixture(scope="module")
def _inst():
    sp = S.apply_overrides(S.load("E4"), ["rounds=3", "shared_archive.enabled=false"])
    return generator.generate(sp, 1)


@pytest.fixture
def world(_inst, tmp_path):
    inst = copy.deepcopy(_inst)
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.end_round_cause()
    agents = {a["id"]: a for a in inst["agents"]}
    rs = runner.RunState(agents=agents, out=tmp_path, start_values={a: k.holdings_value(a) for a in agents},
                         sysp={aid: AG.system_prompt(inst, a) for aid, a in agents.items()})
    return k, inst, rs


def apply(world, op, args, phase="round_start", agent=None, **extra):
    """Schedule one entry at the kernel's round and phase, apply what is due; the record and the events it caused."""
    k, inst, rs = world
    iid = f"t{len(rs.schedule) + 1}"
    at = {"round": k.r, "phase": phase, **({"agent": agent} if agent else {})}
    rs.schedule = IV.merge(rs.schedule, IV.load_schedule([{"id": iid, "at": at, "op": op, "args": args, **extra}]))
    n = len(k.events)
    k.begin_round_cause(phase=phase)
    assert IV.apply_due(k, inst, rs, phase, agent) == [iid]
    assert IV.apply_due(k, inst, rs, phase, agent) == []                 # never twice
    k.end_round_cause()
    rec = k.w["interventions"][-1]
    evs = k.events[n:]
    assert evs[-1]["type"] == "intervention" and evs[-1]["data"]["id"] == iid and evs[-1]["vis"] == "monitor"
    assert all({"intervention": iid, "op": IV.get(op).name} in e["cause"] for e in evs)   # everything it caused carries it
    assert rec["id"] == iid and rec["round"] == k.r and rec["phase"] == phase and rec["op"] == IV.get(op).name
    return rec, evs[:-1]


def ok(rec):
    assert "error" not in rec, rec.get("error")
    return rec


def _worker(k):
    return next(a for a, v in k.w["agents"].items() if v["cls"] == "worker")


def test_op_move(world):
    k, inst, rs = world
    a = _worker(k)
    before = k.bal(a, "grain")
    rec, evs = apply(world, "move", {"src": "world", "dst": a, "item": "grain", "qty": 50})
    assert k.bal(a, "grain") == before + 50 and evs[0]["type"] == "move" and evs[0]["data"]["src"] == "world"
    assert ok(rec)["diff"]["n"] == 1 and f"agents.{a}.holdings.grain" in rec["diff"]["changes"][0]
    rec, _ = apply(world, "move", {"src": a, "dst": "reserve", "item": "grain", "qty": 20})
    assert ok(rec) and k.bal("reserve", "grain") == 20 and k.bal(a, "grain") == before + 30
    rec, evs = apply(world, "transfer", {"src": a, "dst": "reserve", "item": "grain", "qty": 10 ** 6})   # alias; too much
    assert "holds less" in rec["error"] and k.bal(a, "grain") == before + 30
    assert [c.split(":")[0] for c in rec["diff"]["changes"]] == ["effects.kernel_refusals"]   # the refusal only


def test_op_mint(world):
    k, inst, rs = world
    a = _worker(k)
    k.w["currencies"]["coin"] = {"backed": False, "supply": 0.0, "created_round": 0, "law": None, "reserve": "reserve"}
    ok(apply(world, "mint", {"item": "coin", "qty": 7, "to": a})[0])
    assert k.w["currencies"]["coin"]["supply"] == 7 and k.bal(a, "coin") == 7
    ok(apply(world, "mint", {"item": "stone", "qty": 3, "to": "reserve"})[0])   # not a currency: brought in from the world
    assert k.bal("reserve", "stone") == 3


def test_op_burn(world):
    k, inst, rs = world
    a = _worker(k)
    k.w["currencies"]["coin"] = {"backed": False, "supply": 10.0, "created_round": 0, "law": None, "reserve": "reserve"}
    k._add(a, "coin", 10)
    ok(apply(world, "burn", {"item": "coin", "qty": 4, "frm": a})[0])
    assert k.w["currencies"]["coin"]["supply"] == 6 and k.bal(a, "coin") == 6
    assert "holds less" in apply(world, "burn", {"item": "coin", "qty": 99, "frm": a})[0]["error"]


def test_op_gazette(world):
    rec, evs = apply(world, "gazette", {"text": "The world speaks."})
    assert ok(rec) and [e["type"] for e in evs] == ["gazette"] and evs[0]["data"]["text"] == "The world speaks."


def test_op_notify_and_message(world):
    k, inst, rs = world
    a = _worker(k)
    rec, evs = apply(world, "notify", {"to": a, "text": "psst"})
    assert ok(rec) and evs[0]["type"] == "notify" and evs[0]["vis"] == [a]
    rec, evs = apply(world, "message", {"to": "all", "text": "hello all"}, announce="and a notice", announce_to=[a])
    assert ok(rec)["op"] == "notify" and len([e for e in evs if e["data"].get("text") == "hello all"]) == len(k.players())
    assert evs[-1]["type"] == "notify" and evs[-1]["data"] == {"to": a, "text": "and a notice"}   # announce_to: private
    assert "no such agent" in apply(world, "notify", {"to": "nobody", "text": "x"})[0]["error"]


def test_op_grant(world):
    k, inst, rs = world
    a = _worker(k)
    from charter import rights as RT
    right = next(r for r in k.w["rights"] if r not in k.agent(a)["rights"] and not r.startswith("harvest:")
                 and r not in RT.ENTRENCHED and not RT.role_bound(r))
    rec, evs = apply(world, "grant", {"agent": a, "right": right})
    assert ok(rec) and right in k.agent(a)["rights"] and evs[0]["type"] == "rights" and evs[0]["data"]["change"] == "grant"
    assert "entrenched" in apply(world, "grant", {"agent": a, "right": "veto"})[0]["error"]
    assert "no such right" in apply(world, "grant", {"agent": a, "right": "fly"})[0]["error"]
    ok(apply(world, "grant", {"agent": a, "right": "fly", "create": True})[0])
    assert "fly" in k.w["rights"] and "fly" in k.agent(a)["rights"]


def test_op_revoke(world):
    k, inst, rs = world
    a = _worker(k)
    right = k.agent(a)["rights"][0]
    rec, evs = apply(world, "revoke", {"agent": a, "right": right})
    assert ok(rec) and right not in k.agent(a)["rights"] and evs[0]["data"]["change"] == "revoke"


def test_op_suspend(world):
    k, inst, rs = world
    a = _worker(k)
    right = k.agent(a)["rights"][0]
    rec, evs = apply(world, "suspend", {"agent": a, "right": right, "rounds": 2})
    assert ok(rec) and k.agent(a)["suspended"][right] == k.r + 2 and evs[0]["type"] == "sanction"


def test_op_add_agent(world):
    k, inst, rs = world
    n = len(inst["agents"])
    rec, evs = apply(world, "add_agent", {"cls": "worker"})
    new = ok(rec)["result"]["agent"]
    assert len(inst["agents"]) == n + 1 and new in k.w["agents"] and new in rs.agents and new in rs.sysp and new in rs.cursors
    assert any(e["type"] == "arrival" and e["agent"] == new for e in evs)
    with pytest.raises(IV.InterventionError, match="cannot run at setup"):
        IV.load_schedule([{"id": "x", "at": {"round": 0, "phase": "setup"}, "op": "begin_life", "args": {}}])


def test_op_remove_agent(world):
    k, inst, rs = world
    a = _worker(k)
    rec, evs = apply(world, "end_life", {"agent": a, "holdings": "reserve"})
    assert ok(rec)["op"] == "remove_agent" and k.w["agents"][a]["departed"] == k.r and a not in rs.agents
    assert k.agent(a)["holdings"] == {} and any(e["type"] == "departure" for e in evs)
    assert "already left" in apply(world, "remove_agent", {"agent": a})[0]["error"]


def test_op_set_goal(world):
    k, inst, rs = world
    a = _worker(k)
    old = next(x for x in inst["agents"] if x["id"] == a)["goal"]["primary"]
    goal = next(g for g in ("Wealth", "Influence", "Knowledge") if g != old)
    rec, evs = apply(world, "set_goal", {"agent": a, "primary": goal})
    g = next(x for x in inst["agents"] if x["id"] == a)["goal"]
    assert ok(rec)["result"] == {"goal": goal} and g["primary"] == goal and g["text"]
    b = k.w["world_events"]["boundaries"][-1]
    assert b["agent"] == a and b["old"]["primary"] == old and b["new"]["primary"] == goal   # scoring splits here (events.segments)
    assert {e["type"] for e in evs} == {"notify", "goal_change"}
    inst2 = copy.deepcopy(inst)
    next(x for x in inst2["agents"] if x["id"] == a)["goal"] = {"primary": old}
    __import__("charter.events", fromlist=["restore"]).restore(k, inst2, {})   # a resume puts the new goal back
    assert next(x for x in inst2["agents"] if x["id"] == a)["goal"]["primary"] == goal
    assert "unknown goal" in apply(world, "set_goal", {"agent": a, "primary": "Nonsense"})[0]["error"]


def test_op_set_model(world):
    k, inst, rs = world
    a = _worker(k)
    rec, _ = apply(world, "set_model", {"agent": a, "model": "claude-test-model"})
    assert ok(rec)["inst_edits"] == [[a, "model", "claude-test-model"]] and k.w["agents"][a]["model"] == "claude-test-model"
    inst2 = copy.deepcopy(inst)
    next(x for x in inst2["agents"] if x["id"] == a)["model"] = "old"
    IV.restore(k, inst2)                                                 # a resume regenerates the instance: put back
    assert next(x for x in inst2["agents"] if x["id"] == a)["model"] == "claude-test-model"


class _Capture:
    def __init__(self):
        self.calls = []

    def act(self, k, a, system, user, n, final, key=None):
        self.calls.append((a["id"], system, key))
        return {"actions": [], "notes": "sampled"}, "", {}


def test_op_set_prompt_extra(world):
    k, inst, rs = world
    a = _worker(k)
    ok(apply(world, "set_prompt_extra", {"agent": a, "text": "Remember the flood."})[0])
    cap = _Capture()
    pol = IV.PromptExtra(cap)
    pol.act(k, rs.agents[a], "SYSTEM", "u", 2, False)
    other = next(x for x in rs.agents if x != a)
    pol.act(k, rs.agents[other], "SYSTEM", "u", 2, False)
    assert cap.calls[0][1] == "SYSTEM\n\nRemember the flood." and cap.calls[1][1] == "SYSTEM"


def test_op_set_prompt_profile(world):
    k, inst, rs = world
    a = _worker(k)
    rec, _ = apply(world, "set_prompt_profile", {"agent": a, "profiles": ["p1"], "add": "p2"})
    assert ok(rec)["inst_edits"] == [[a, "profiles", ["p1", "p2"]]] and rs.agents[a]["profiles"] == ["p1", "p2"]
    ok(apply(world, "set_prompt_profile", {"agent": a, "remove": "p1"})[0])
    assert rs.agents[a]["profiles"] == ["p2"]
    assert (rs.out / "prompts" / f"{a}.system.md").exists()             # the rebuilt system prompt is kept


def test_op_set_notes(world):
    k, inst, rs = world
    a = _worker(k)
    ok(apply(world, "set_notes", {"agent": a, "text": "you owe Bo 5 grain"})[0])
    assert rs.notes[a] == "you owe Bo 5 grain"


def test_op_enact_law(world):
    k, inst, rs = world
    rec, evs = apply(world, "enact_law", {"library": inst["library"][0]})
    lid = ok(rec)["result"]["law"]
    assert k.w["laws"][lid]["status"] in ("active", "enacted_repeal") and k.w["laws"][lid]["author"] == "intervention"
    assert any(e["type"] == "enact" and e["data"]["law"] == lid for e in evs) or k.w["laws"][lid]["status"] != "active"


def test_op_repeal_law(world):
    k, inst, rs = world
    lid = ok(apply(world, "enact_law", {"code": 'title = "Quiet"\nintent = "nothing"\n\ndef on_round_start(r):\n    pass\n'})[0])["result"]["law"]
    rec, evs = apply(world, "repeal_law", {"law": lid})
    assert ok(rec) and k.w["laws"][lid]["status"] == "repealed" and evs[-1]["type"] == "repeal"
    assert "no law in force" in apply(world, "repeal_law", {"law": lid})[0]["error"]


def test_op_amend_law(world, tmp_path):
    k, inst, rs = world
    lid = ok(apply(world, "enact_law", {"code": 'title = "Quiet"\nintent = "nothing"\n\ndef on_round_start(r):\n    pass\n'})[0])["result"]["law"]
    new = 'title = "Loud"\nintent = "say loud"\n\ndef on_round_start(r):\n    gazette("loud")\n'
    (tmp_path / "l.py").write_text(new)
    p = tmp_path / "iv.yaml"
    p.write_text(f"- id: p1\n  at: {k.r}\n  op: patch_law\n  args: {{law: {lid}, code_file: l.py, reason: test}}\n")
    sched = IV.load_schedule(p)                                          # code_file read relative to the schedule
    assert sched[0]["op"] == "amend_law" and sched[0]["args"]["code"] == new
    rs.schedule = IV.merge(rs.schedule, sched)
    k.begin_round_cause(phase="round_start")
    IV.apply_due(k, inst, rs, "round_start")
    k.end_round_cause()
    assert "error" not in k.w["interventions"][-1] and k.w["laws"][lid]["code"] == new
    assert k.w["laws"][lid]["patches"][-1]["by"] == "intervention"
    assert any(e["type"] == "patched" and e["data"]["law"] == lid for e in k.events)


def test_op_set_spec(world):
    k, inst, rs = world
    rec, evs = apply(world, "set_spec", {"path": "context.explore_nudge", "value": False})
    assert ok(rec) and k.w["live"]["context.explore_nudge"] is False and inst["spec"]["context"]["explore_nudge"] is False
    assert evs[0]["type"] == "rules_changed"
    assert "not runtime-safe" in apply(world, "set_spec", {"path": "rounds", "value": 9})[0]["error"]
    rec, _ = apply(world, "set_spec", {"path": "conditions.drift", "value": False, "force": True})
    assert ok(rec)["inst_edits"] == [[None, "spec.conditions.drift", False]] and k.spec["conditions"]["drift"] is False
    inst2 = copy.deepcopy(inst)
    inst2["spec"]["conditions"]["drift"] = True
    IV.restore(k, inst2)
    assert inst2["spec"]["conditions"]["drift"] is False


def test_op_inject_action(world):
    k, inst, rs = world
    a = _worker(k)
    rec, evs = apply(world, "inject_action", {"agent": a, "action": "post", "args": {"text": "I was made to say this"}},
                     phase="before_turn", agent=a)
    assert ok(rec)["result"]["result"] and any(e["type"] in ("post", "submission") and e["agent"] == a for e in evs)
    assert any({"action": "post", "agent": a} in e["cause"] for e in evs)
    assert "unknown action" in apply(world, "inject_action", {"agent": a, "action": "fly"}, phase="after_turn")[0]["error"]


def test_op_replace_reply(world):
    k, inst, rs = world
    a = _worker(k)
    ok(apply(world, "replace_reply", {"agent": a, "reply": {"actions": [], "notes": "forced"}}, phase="before_turn")[0])
    cap = _Capture()
    pol = IV.Forced(cap, rs)
    out, _, usage, _ = pol.act_recorded(k, rs.agents[a], "S", "u", 2, False, key={"phase": "decide"})
    assert out["notes"] == "forced" and usage == {"forced": True} and cap.calls == []
    out, _, _ = pol.act(k, rs.agents[a], "S", "u", 2, False, key={"phase": "decide"})   # only once
    assert out["notes"] == "sampled" and len(cap.calls) == 1 and cap.calls[0][2] is None   # key not passed to a keyless policy


def test_op_python(world):
    k, inst, rs = world
    code = "def apply(k, inst, rs):\n    k.w['reserve']['gold'] = 3\n    return {'n': len(rs.agents)}\n"
    rec, _ = apply(world, "python", {"code": code})
    assert ok(rec)["result"] == {"result": {"n": len(rs.agents)}} and k.w["reserve"]["gold"] == 3
    assert rec["diff"]["changes"] == ["reserve.gold: + 3"]
    assert "ZeroDivisionError" in apply(world, "python", {"code": "def apply(k, inst, rs):\n    1/0\n"})[0]["error"]


def test_every_op_has_a_test():
    names = {n[len("test_op_"):] for n in globals() if n.startswith("test_op_")} | {"notify"}   # test_op_notify_and_message
    assert set(IV.OPS) <= names, set(IV.OPS) - names


def test_schedule_validation():
    with pytest.raises(IV.InterventionError, match="unknown intervention op"):
        IV.load_schedule([{"id": "a", "op": "teleport"}])
    with pytest.raises(IV.InterventionError, match="needs argument qty"):
        IV.load_schedule([{"id": "a", "op": "move", "args": {"src": "world", "dst": "reserve", "item": "x"}}])
    with pytest.raises(IV.InterventionError, match="takes no argument"):
        IV.load_schedule([{"id": "a", "op": "gazette", "args": {"text": "x", "loud": True}}])
    with pytest.raises(IV.InterventionError, match="duplicate"):
        IV.load_schedule("- {id: a, op: gazette, args: {text: x}}\n- {id: a, op: gazette, args: {text: y}}\n")
    with pytest.raises(IV.InterventionError, match="expected float"):
        IV.load_schedule([{"id": "a", "op": "move", "args": {"src": "w", "dst": "r", "item": "x", "qty": "lots"}}])
    s = IV.load_schedule(json.dumps({"interventions": [{"id": "a", "at": 4, "op": "gazette", "args": {"text": "x"}}]}))
    assert s[0]["at"] == {"round": 4, "phase": "round_start"}


def test_runstate_round_trips():
    rs = runner.RunState(notes={"a": "n"}, schedule=[{"id": "x"}], policy_state=(3, (1, 2), None))
    d = rs.to_dict()
    assert d["policy_rng"] == (3, (1, 2), None) and "sysp" not in d and "agents" not in d
    back = runner.RunState.from_dict(d)
    assert back.notes == {"a": "n"} and back.schedule == [{"id": "x"}] and back.policy_state == (3, (1, 2), None)
    old = {x: v for x, v in d.items() if x != "schedule"}               # a checkpoint from before RunState
    assert runner.RunState.from_dict(old).schedule == [] and back["notes"] is back.notes


# ====================================================================== the runner: hook points, resume, wrappers, replay
E0 = ("E0", 1, ["rounds=3"])


def _spec(preset, sets):
    return S.apply_overrides(S.load(preset), list(sets) + ["shared_archive.enabled=false"])


def _play(d, case=E0, policy=None, **kw):
    preset, seed, sets = case
    inst = generator.generate(_spec(preset, sets), seed)
    inst["run_id"] = "iv_run"
    return runner.run(inst, policy or AG.ScriptedPolicy(seed), d, **QUIET, **kw)


def _sched(inst_agents):
    a, b = inst_agents[0], inst_agents[1]
    return IV.load_schedule([
        {"id": "gift", "at": 1, "op": "move", "args": {"src": "world", "dst": a, "item": "grain", "qty": 40}, "announce": "A gift."},
        {"id": "nudge", "at": {"round": 1, "phase": "before_turn", "agent": b}, "op": "notify", "args": {"to": b, "text": "hi"}},
        {"id": "after", "at": {"round": 1, "phase": "after_turn", "agent": a}, "op": "set_notes", "args": {"agent": a, "text": "x"}},
        {"id": "news", "at": {"round": 2, "phase": "round_start"}, "op": "gazette", "args": {"text": "Round three."}},
        {"id": "late", "at": {"round": 2, "phase": "round_end"}, "op": "gazette", "args": {"text": "The end is near."}},
    ])


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


@pytest.fixture(scope="module")
def iv_run(tmp_path_factory):
    """An E0 run with interventions at every phase, --notice and --live, uninterrupted."""
    preset, seed, sets = E0
    ids = [a["id"] for a in generator.generate(_spec(preset, sets), seed)["agents"]]
    d = tmp_path_factory.mktemp("iv") / "run"
    _play(d, schedule=_sched(ids), notices=["Welcome."], live={"context.explore_nudge": False})
    return d, ids


def test_interventions_apply_at_their_round_and_phase(iv_run):
    d, ids = iv_run
    ev = _jsonl(d / "events.jsonl")
    iv = [e for e in ev if e["type"] == "intervention"]
    got = [(e["data"]["id"], e["round"], e["cause"][1]["phase"]) for e in iv]
    assert [g[0] for g in got[:2]] == ["live:context.explore_nudge=" + IV._sha(False) + "@r0", "notice:" + IV._sha("Welcome.")]
    assert all(g[1:] == (0, "setup") for g in got[:2])
    assert got[2:] == [("gift", 1, "round_start"), ("nudge", 1, "turns"), ("after", 1, "turns"), ("news", 2, "round_start"),
                       ("late", 2, "end_of_round")]
    pos = {e["id"]: i for i, e in enumerate(ev)}
    turn = {(e["round"], e["agent"]): pos[e["id"]] for e in ev if e["type"] == "turn"}
    nudge, after = (next(pos[e["id"]] for e in iv if e["data"]["id"] == x) for x in ("nudge", "after"))
    assert nudge < turn[(1, ids[1])] and after > turn[(1, ids[0])]     # before b's turn, after a's
    assert [r["id"] for r in _jsonl(d / "interventions.jsonl")][2:] == ["gift", "nudge", "after", "news", "late"]
    assert [e["id"] for e in IV.load_schedule(d / "interventions.yaml")][-2:] == ["live:context.explore_nudge=" + IV._sha(False) + "@r0",
                                                                                  "notice:" + IV._sha("Welcome.")]
    assert any(e["type"] == "gazette" and e["data"]["text"] == "Welcome." for e in ev)
    assert any(e["type"] == "rules_changed" and e["data"]["setting"] == "context.explore_nudge" for e in ev)


def test_resume_after_an_intervention_does_not_reapply_it(iv_run, tmp_path):
    d, ids = iv_run
    preset, seed, sets = E0
    out = tmp_path / "stopped"
    inst = generator.generate(_spec(preset, sets), seed) | {"run_id": "iv_run"}
    with pytest.raises(runner.RunStopped):                              # round 3 abandoned after "news" was applied in it
        runner.run(inst, _Stopper(seed, 2), out, **QUIET, schedule=_sched(ids), notices=["Welcome."],
                   live={"context.explore_nudge": False})
    inst = generator.generate(_spec(preset, sets), seed) | {"run_id": "iv_run"}
    runner.run(inst, AG.ScriptedPolicy(seed), out, resume=True, **QUIET, schedule=_sched(ids), notices=["Welcome."],
               live={"context.explore_nudge": False})                    # the same schedule, notice and setting given again
    ev = _jsonl(out / "events.jsonl")
    applied = [e["data"]["id"] for e in ev if e["type"] == "intervention"]
    assert len(applied) == len(set(applied)) == 7
    assert sum(e["type"] == "gazette" and e["data"]["text"] == "Welcome." for e in ev) == 1
    for f in ("events.jsonl", "snapshots.json", "reasoning.jsonl"):
        assert (out / f).read_bytes() == (d / f).read_bytes(), f
    assert len(_jsonl(out / "interventions.jsonl")) == 7


def test_replay_of_a_run_with_interventions_is_identical(iv_run, tmp_path):
    d, _ = iv_run
    res = RP.replay(d, tmp_path / "rep", **QUIET)
    assert res["identical"], res.get("first_difference")


def test_simultaneous_turns_forced_reply_and_its_replay(tmp_path):
    """Simultaneous mode: every before_turn runs before anyone decides; replace_reply's reply is what the agent does (recorded as
    a forced call), and a replay of the run, which applies the same schedule, reproduces it."""
    case = ("E0", 2, ["rounds=2", "turns=simultaneous"])
    a = generator.generate(_spec(case[0], case[2]), case[1])["agents"][0]["id"]
    sched = IV.load_schedule([
        {"id": "say", "at": {"round": 1, "phase": "before_turn", "agent": a}, "op": "replace_reply",
         "args": {"agent": a, "reply": {"actions": [], "notes": "forced notes", "reasoning": "told to"}}},
        {"id": "tick", "at": {"round": 1, "phase": "after_turn", "agent": a}, "op": "gazette", "args": {"text": "tick"}},
    ])
    run = _play(tmp_path / "sim", case=case, schedule=sched)
    rows = [r for r in _jsonl(run / "reasoning.jsonl") if r["round"] == 1 and r["agent"] == a and r["phase"] == "decide"]
    assert rows[0]["notes"] == "forced notes"
    call = next(c for c in _jsonl(run / "calls.jsonl") if c["key"] == f"r1:decide:0:{a}:0")
    assert call["usage"]["forced"] is True and call["parsed"]["notes"] == "forced notes"
    ev = _jsonl(run / "events.jsonl")
    pos = {e["data"]["id"]: i for i, e in enumerate(ev) if e["type"] == "intervention"}
    turns = [i for i, e in enumerate(ev) if e["type"] == "turn" and e["round"] == 1]
    assert pos["say"] < turns[0] and pos["tick"] > next(i for i in turns if ev[i]["agent"] == a)
    res = RP.replay(run, tmp_path / "rep", **QUIET)
    assert res["identical"], res.get("first_difference")


# ====================================================================== forks
@pytest.fixture(scope="module")
def base(tmp_path_factory):
    """A plain E0 run (no interventions), the parent of the forks."""
    return _play(tmp_path_factory.mktemp("base") / "E0_run")


def _scripted(spec, dry, seed):
    return AG.ScriptedPolicy(seed)


def _offset(run, n):
    return json.loads((run / "checkpoints" / "index.json").read_text())[str(n)]["files"]["events.jsonl"]


def test_fork_with_an_empty_schedule_reproduces_the_parent(base, tmp_path):
    [d] = RP.fork(base, 1, [], tmp_path / "f", policy_factory=_scripted, **QUIET)
    for f in ("events.jsonl", "snapshots.json", "reasoning.jsonl", "turns.jsonl"):
        assert (d / f).read_bytes() == (base / f).read_bytes(), f
    meta = PV.read(d)
    assert [s["kind"] for s in meta["segments"]] == ["start", "fork", "resume"]
    assert meta["parent"]["run"] == str(base.resolve()) and meta["parent"]["round"] == 1 and meta["parent"]["replay"] == "strict"
    assert meta["replicate"] is None and meta["segments"][1]["first_round"] == 1 and meta["fork"]["calls"]["replayed"] == 0
    assert (base / "events.jsonl").read_bytes() == (d / "events.jsonl").read_bytes()


def test_fork_with_an_intervention_diverges_exactly_at_the_fork_point(base, tmp_path, monkeypatch):
    monkeypatch.setattr(M, "load_env", lambda: None)
    monkeypatch.setattr(M, "policy_for", _scripted)
    a = json.loads((base / "instance.json").read_text())["agents"][0]["id"]
    (tmp_path / "iv.yaml").write_text(f"- id: windfall\n  at: {{round: 1, phase: round_start}}\n  op: move\n"
                                      f"  args: {{src: world, dst: {a}, item: grain, qty: 500}}\n  announce: A windfall.\n")
    M.main(["fork", str(base), "--at", "1", "--apply", str(tmp_path / "iv.yaml"), "--out", str(tmp_path / "f")])
    d = tmp_path / "f"
    new, old = (d / "events.jsonl").read_bytes(), (base / "events.jsonl").read_bytes()
    cut = _offset(base, 1)
    assert new[:cut] == old[:cut] and new != old                        # identical up to the fork point
    ev_new, ev_old = _jsonl(d / "events.jsonl"), _jsonl(base / "events.jsonl")
    i = next(i for i, (x, y) in enumerate(zip(ev_new, ev_old)) if x != y)
    assert i == len(old[:cut].splitlines())                             # ... and different from its first event on
    first = ev_new[i:]
    assert all(e["round"] >= 1 for e in first)
    assert any(e["type"] == "intervention" and e["data"]["id"] == "windfall" for e in first)
    assert any(e["type"] == "move" and {"intervention": "windfall", "op": "move"} in e["cause"] for e in first)
    assert json.loads((d / "snapshots.json").read_text())[0] == json.loads((base / "snapshots.json").read_text())[0]
    assert PV.read(d)["parent"]["schedule"] == ["windfall"] and (d / "score.json").exists()
    assert [r["id"] for r in _jsonl(d / "interventions.jsonl")] == ["windfall"]


def test_fork_replicates_differ_only_after_the_fork_point(base, tmp_path):
    dirs = RP.fork(base, 2, [], tmp_path / "reps", replicates=2, policy_factory=_scripted, **QUIET)
    assert [d.name for d in dirs] == ["rep1", "rep2"]
    cut = _offset(base, 2)
    evs = [(d / "events.jsonl").read_bytes() for d in dirs]
    assert all(e[:cut] == (base / "events.jsonl").read_bytes()[:cut] for e in evs) and evs[0] != evs[1]
    metas = [PV.read(d) for d in dirs]
    assert [m["replicate"] for m in metas] == [1, 2] and [m["segments"][1]["kind"] for m in metas] == ["fork", "fork"]
    seeds = [m["parent"]["live_seed"] for m in metas]
    assert len(set(seeds)) == 2 and seeds == [RP.replicate_seed(1, 2, i) for i in (1, 2)]


def test_fork_from_an_earlier_checkpoint_replays_up_to_the_fork_point(base, tmp_path):
    run = shutil.copytree(base, tmp_path / "thin")
    idx = json.loads((run / "checkpoints" / "index.json").read_text())
    (run / "checkpoints" / idx.pop("2")["file"]).unlink()               # retention dropped the checkpoint after round 2
    (run / "checkpoints" / "index.json").write_text(json.dumps(idx))

    class Live(AG.ScriptedPolicy):
        asked = []

        def act(self, k, a, system, user, n, final):
            Live.asked.append(k.r)
            return super().act(k, a, system, user, n, final)
    [d] = RP.fork(run, 2, [], tmp_path / "f", policy_factory=lambda sp, dry, seed: Live(seed), **QUIET)
    cut = _offset(base, 2)
    assert (d / "events.jsonl").read_bytes()[:cut] == (base / "events.jsonl").read_bytes()[:cut]   # round 2 replayed exactly
    assert Live.asked and min(Live.asked) >= 2                          # the live policy only from the fork point
    assert PV.read(d)["parent"]["checkpoint_round"] == 1 and PV.read(d)["fork"]["calls"]["replayed"] > 0
    calls = _jsonl(d / "calls.jsonl")
    assert all(c.get("replayed") for c in calls if c["round"] == 1 and c["key_fields"]["phase"] == "decide")


def test_fork_prompt_match_serves_the_parents_replies_while_prompts_match(base, tmp_path):
    class Never:
        rng = __import__("random").Random(0)

        def act(self, *a, **kw):
            raise AssertionError("the live policy was asked although every prompt matched")
    [d] = RP.fork(base, 1, [], tmp_path / "f", replay_mode="prompt-match", policy_factory=lambda *a: Never(), **QUIET)
    assert (d / "events.jsonl").read_bytes() == (base / "events.jsonl").read_bytes()
    assert PV.read(d)["fork"]["calls"]["live"] == 0


def test_fork_inherits_the_parents_pending_interventions_unless_fresh(iv_run, tmp_path):
    d, _ = iv_run
    [same] = RP.fork(d, 2, [], tmp_path / "same", policy_factory=_scripted, **QUIET)
    assert (same / "events.jsonl").read_bytes() == (d / "events.jsonl").read_bytes()   # "news" and "late" applied again
    [fresh] = RP.fork(d, 2, [], tmp_path / "fresh", policy_factory=_scripted, fresh_schedule=True, **QUIET)
    got = [r["id"] for r in _jsonl(fresh / "interventions.jsonl")]
    assert "gift" in got and "news" not in got and "late" not in got   # applied before the fork point: kept; pending: dropped


def test_fork_refuses_interventions_before_the_fork_point(base, tmp_path):
    with pytest.raises(SystemExit, match="before the fork point"):
        RP.fork(base, 2, [{"id": "x", "at": 1, "op": "gazette", "args": {"text": "t"}}], tmp_path / "f", policy_factory=_scripted)


def test_branches_lists_the_lineage(base, tmp_path, monkeypatch, capsys):
    run = shutil.copytree(base, tmp_path / "parent")
    [f1] = RP.fork(run, 1, [], tmp_path / "f1", policy_factory=_scripted, **QUIET)
    reps = RP.fork(run, 2, [{"id": "g", "at": 2, "op": "gazette", "args": {"text": "t"}}], tmp_path / "reps", replicates=2,
                   policy_factory=_scripted, **QUIET)
    [ff] = RP.fork(f1, 2, [], tmp_path / "f1f", policy_factory=_scripted, **QUIET)   # a fork of a fork
    b = RP.branches(ff)
    assert b["ancestors"] == [str(run.resolve()), str(f1.resolve()), str(ff.resolve())]
    t = b["tree"]
    assert t["name"] == "parent" and t["kind"] == "start"
    kids = {c["name"]: c for c in t["children"]}
    assert set(kids) == {"f1", "rep1", "rep2"} and kids["rep1"]["replicate"] == 1 and kids["rep2"]["schedule"] == ["g"]
    assert [c["name"] for c in kids["f1"]["children"]] == ["f1f"] and kids["f1"]["children"][0]["round"] == 2
    monkeypatch.setattr(M, "load_env", lambda: None)
    M.main(["branches", str(f1)])
    out = capsys.readouterr().out
    assert "parent" in out and "f1  <-" in out and "replicate 2" in out and "interventions g" in out
