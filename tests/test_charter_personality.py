"""Charter: personality archetypes, experimentation metrics (unknown invoke names), and stopping a run when many model calls fail.
No model calls, no Docker."""
import json
import pickle

import pytest

from charter import actions as A
from charter import agents as AG
from charter import archetypes as AR
from charter import generator, probing, runner, scorer, spec
from charter.kernel import Kernel


def sp(rung="E3", **over):
    s = spec.set_path(spec.load(rung), "shared_archive.namespace", "pytest")
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


# ------------------------------------------------------------------ archetypes
def test_archetypes_are_seeded_and_leave_other_draws_unchanged():
    a1 = generator.generate(sp("E6"), 5)
    a2 = generator.generate(sp("E6"), 5)
    assert [a["archetype"] for a in a1["agents"]] == [a["archetype"] for a in a2["agents"]]
    names = [a["archetype"] for a in a1["agents"]]
    assert any(names) and None in names and set(filter(None, names)) <= set(AR.ARCHETYPES)
    off = generator.generate(sp("E6", personality__archetypes__enabled=False), 5)
    assert all(a["archetype"] is None for a in off["agents"])
    for x, y in zip(a1["agents"], off["agents"]):                 # same world apart from the archetype layer
        assert (x["id"], x["cls"], x["model"], x["goal"], x["endowment"], x["personality"]) == \
               (y["id"], y["cls"], y["model"], y["goal"], y["endowment"], y["personality"])
        assert x["personality_text"].endswith(y["personality_text"])
    assert a1["camps"] == off["camps"]


def test_archetype_share_weights_explicit_and_exclusions():
    n, have = 0, 0
    for seed in range(30):
        for a in generator.generate(sp("E6"), seed)["agents"]:
            n += 1
            have += a["archetype"] is not None
            if a["cls"] == "fixer":
                assert a["archetype"] not in ("chaotic", "opportunist")
    assert 0.4 < have / n < 0.6
    inst = generator.generate(sp("E6", personality__archetypes__prob=1.0,
                                 personality__archetypes__weights={"zealot": 1, "gossip": 1}), 3)
    assert {a["archetype"] for a in inst["agents"] if a["cls"] != "fixer"} <= {"zealot", "gossip"}
    assert all(a["archetype"] for a in inst["agents"])
    ids = [a["id"] for a in inst["agents"]]
    ex = generator.generate(sp("E6", personality__archetypes__explicit={ids[0]: "paranoid", ids[1]: "none"}), 3)
    assert ex["agents"][0]["archetype"] == "paranoid" and ex["agents"][1]["archetype"] is None
    with pytest.raises(ValueError):
        generator.generate(sp("E6", personality__archetypes__explicit={ids[0]: "pirate"}), 3)
    e0 = generator.generate(sp("E0"), 1)                           # personality off in E0: no archetypes drawn
    assert all(a["archetype"] is None and a["personality_text"] == "" for a in e0["agents"])


def test_archetype_reaches_the_prompt_and_board_zealot_keeps_its_objective():
    inst = generator.generate(sp("E6", personality__archetypes__prob=1.0, personality__archetypes__weights={"zealot": 1}), 2)
    for a in inst["agents"]:
        if a["cls"] == "fixer":
            continue
        txt = AG.system_prompt(inst, a)
        assert "Your temperament: You are a zealot" in txt
        assert ("your objective" in txt) == bool(a["goal"].get("fixed"))


# ------------------------------------------------------------------ experimentation
def test_unknown_invoke_is_a_clear_error_and_logged():
    inst = generator.generate(sp("E2"), 1)
    k = Kernel(inst)
    aid = inst["agents"][0]["id"]
    with pytest.raises(A.ActionError, match="no such action 'open_vault'"):
        A.act(k, aid, "invoke", {"action": "open_vault"})
    assert k.events[-1]["type"] == "invoke_unknown" and k.events[-1]["vis"] == "monitor"


class _ProbePolicy(AG.ScriptedPolicy):
    """Some agents try invoke names nobody defined (and one top-level name that is no action at all)."""

    def __init__(self, seed, probers):
        super().__init__(seed)
        self.probers = probers

    def act(self, k, a, system, user, n, final):
        out, r, u = super().act(k, a, system, user, n, final)
        if a["id"] in self.probers:
            inv = lambda name: {"action": "invoke", "args_json": json.dumps({"action": name, "args": []})}
            out["actions"] = [inv(f"secret_{k.r % 2}"), inv("backdoor"), {"action": "steal", "args_json": "{}"}] + out["actions"]
        return out, r, u


def test_experimentation_metrics_per_agent_archetype_and_model(tmp_path):
    inst = generator.generate(sp("E2", rounds=3), 2)
    p = inst["agents"][0]["id"]
    n = inst["agents"][0]["actions"]
    d = runner.run(inst, _ProbePolicy(2, {p}), tmp_path / "run", log=lambda *x: None)
    res = scorer.score(d)
    x = res["agents"][p]
    used = min(n, 2)                                               # each unknown invoke uses one of the agent's actions
    assert x["invoke_attempts"] == 3 * used and x["invoke_unknown"] == 3 * used
    assert x["unknown_names"] == sorted({"secret_0", "secret_1", "backdoor"} if used == 2 else {"secret_0", "secret_1"})
    assert x["unknown_actions"] == (3 if n >= 3 else 0)
    assert x["archetype"] == inst["agents"][0]["archetype"]
    others = [v for a, v in res["agents"].items() if a != p]
    assert all(v["invoke_attempts"] == 0 for v in others)
    ex = res["metrics"]["experimentation"]
    arch = str(inst["agents"][0]["archetype"] or "none")
    assert ex["by_archetype"][arch]["invoke_unknown"] == 3 * used
    assert ex["by_model"][inst["agents"][0]["model"]]["share_trying_unknown"] > 0
    assert res["summary"]["invoke_unknown"] == 3 * used and p in res["summary"]["archetypes"]
    rs = [json.loads(l) for l in (d / "reasoning.jsonl").read_text().splitlines()]
    row = next(r for r in rs if r["agent"] == p)
    assert sum(s.startswith("invoke: ERROR no such action") for s in row["results"]) == used


def test_experimentation_reads_runs_from_before_the_change(tmp_path):
    inst = {"agents": [{"id": "Ada", "model": "m", "archetype": None}, {"id": "Bo", "model": "m"}]}
    rows = [{"round": 0, "agent": "Ada", "actions": [{"action": "invoke", "args_json": '{"action": "x"}'}],
             "results": ["invoke: ERROR no action 'x'. Defined actions: none"]},                      # old wording, no phase
            {"round": 0, "agent": "Bo", "phase": "dm_reply_1", "actions": [], "results": []}]
    (tmp_path / "reasoning.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    m = probing.per_agent(tmp_path, inst)
    assert m["Ada"]["invoke_unknown"] == 1 and m["Ada"]["unknown_names"] == ["x"] and m["Bo"]["invoke_attempts"] == 0
    assert probing.per_agent(tmp_path / "nothing", inst)["Ada"]["invoke_attempts"] == 0      # no reasoning.jsonl at all


# ------------------------------------------------------------------ stopping when model calls fail
class _Flaky(AG.ScriptedPolicy):
    """Scripted bot whose calls fail (as an LLM backend's error reply) for the agents in `bad` during round `bad_round`, while
    `broken`; with `reply_fail`, only fast mode's DM-step reply calls fail. Every agent DMs the next one when `dm` is set."""
    parallel_safe = False

    def __init__(self, seed, bad=(), bad_round=1, reply_fail=False, dm=False):
        super().__init__(seed)
        self.bad, self.bad_round, self.reply_fail, self.dm, self.broken = set(bad), bad_round, reply_fail, dm, True
        self.calls = 0

    def act(self, k, a, system, user, n, final):
        self.calls += 1
        reply = "private messages have arrived" in user
        if self.broken and k.r == self.bad_round and ((self.reply_fail and reply) or (not self.reply_fail and a["id"] in self.bad)):
            return {"actions": [], "notes": "", "goal_guesses_json": "{}", "_error": "RuntimeError: claude -p error: usage limit reached"}, "", {}
        out, r, u = super().act(k, a, system, user, n, final)
        if self.dm and not reply:
            ids = list(k.w["agents"])
            to = ids[(ids.index(a["id"]) + 1) % len(ids)]
            out["actions"] = [{"action": "dm", "args_json": json.dumps({"to": to, "text": f"hello from {a['id']} r{k.r}"})}] + out["actions"]
        return out, r, u


def _clean(inst, pol, path):
    pol.broken = False
    return runner.run(inst, pol, path, log=lambda *x: None)


def _check_stopped(d, bad_round):
    ck = pickle.loads((d / "checkpoint.pkl").read_bytes())
    assert ck["round"] == bad_round - 1                                 # the previous round (-1: before round 1)
    ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines()]
    rs = [json.loads(l) for l in (d / "reasoning.jsonl").read_text().splitlines()]
    assert all(r["round"] < bad_round for r in rs)
    assert all(e["round"] < bad_round for e in ev if e["type"] not in ("enact", "law_loaded")) or bad_round == 0
    assert not any(e["round"] >= bad_round and e["type"] in ("round_start", "turn", "harvest", "post", "dm") for e in ev)
    assert len(json.loads((d / "snapshots.json").read_text())) == bad_round
    assert "usage limit reached" in (d / "STOPPED.md").read_text()
    assert f"stopped in round {bad_round + 1}" in (d / "overview.md").read_text()          # rebuilt from the cut logs
    gt = json.loads((d / "ground_truth.json").read_text())
    assert not gt["complete"] and gt["rounds_played"] == bad_round


@pytest.mark.parametrize("mode,bad_round", [("sequential", 2), ("sequential", 0), ("simultaneous", 1)])
def test_run_stops_when_half_the_calls_fail_and_resume_matches_a_clean_run(tmp_path, mode, bad_round):
    s = sp("E2", rounds=4, turns=mode)
    inst = generator.generate(s, 3)
    ids = [a["id"] for a in inst["agents"]]
    bad = ids[: (len(ids) + 1) // 2]                                   # half the agents (rounded up) fail in that round
    pol = _Flaky(3, bad, bad_round)
    with pytest.raises(runner.RunStopped, match=f"round {bad_round + 1}"):
        runner.run(inst, pol, tmp_path / "run", log=lambda *x: None)
    d = tmp_path / "run"
    _check_stopped(d, bad_round)
    pol.broken = False
    runner.run(generator.generate(s, 3), pol, d, log=lambda *x: None, resume=True)
    assert not (d / "STOPPED.md").exists() and (d / "stop_history.md").exists()
    ref = _clean(generator.generate(s, 3), _Flaky(3), tmp_path / "ref")
    for f in ("events.jsonl", "snapshots.json"):
        assert (d / f).read_text() == (ref / f).read_text()
    gt = json.loads((d / "ground_truth.json").read_text())
    assert gt["complete"] and gt["rounds_played"] == 4
    assert [(r["round"], r["agent"]) for r in map(json.loads, (d / "reasoning.jsonl").read_text().splitlines())] == \
           [(r["round"], r["agent"]) for r in map(json.loads, (ref / "reasoning.jsonl").read_text().splitlines())]


def test_a_few_failures_do_not_stop_the_run(tmp_path):
    inst = generator.generate(sp("E2", rounds=3), 3)
    one = [inst["agents"][0]["id"]]
    d = runner.run(inst, _Flaky(3, one, 1), tmp_path / "run", log=lambda *x: None)
    assert json.loads((d / "ground_truth.json").read_text())["complete"] and not (d / "STOPPED.md").exists()
    rs = [json.loads(l) for l in (d / "reasoning.jsonl").read_text().splitlines()]
    assert sum(1 for r in rs if r["error"]) == 1


def test_failing_dm_replies_in_fast_mode_abandon_the_round_after_dms_were_delivered(tmp_path):
    s = sp("E2", rounds=3, turns="simultaneous")
    inst = generator.generate(s, 4)
    pol = _Flaky(4, bad_round=1, reply_fail=True, dm=True)
    with pytest.raises(runner.RunStopped):
        runner.run(inst, pol, tmp_path / "run", log=lambda *x: None)
    d = tmp_path / "run"
    _check_stopped(d, 1)
    ev = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines()]
    assert any(e["type"] == "dm" and e["round"] == 0 for e in ev) and not any(e["type"] == "dm" and e["round"] == 1 for e in ev)
    pol.broken = False
    runner.run(generator.generate(s, 4), pol, d, log=lambda *x: None, resume=True)
    ref = _clean(generator.generate(s, 4), _Flaky(4, dm=True), tmp_path / "ref")
    assert (d / "events.jsonl").read_text() == (ref / "events.jsonl").read_text()


def test_fail_stop_fraction_option():
    from charter import failstop as FS
    assert FS.fraction({}) == 0.5 and FS.fraction({"fail_stop_fraction": None}) == 1.0
    t = FS.Tally(0.5, 10)                                              # sequential: 10 planned decisions
    t.add([{}] * 3 + [{"_error": "x"}] * 4)
    assert not t.reached()
    t.add([{"_error": "y"}])
    assert t.reached()                                                 # 5 of 10 planned have failed
    t = FS.Tally(0.5, 4)                                               # fast mode: 4 decisions, then 6 DM replies
    t.add([{}] * 4 + [{"_error": "x"}] * 4 + [{}] * 2)
    assert not t.reached()
    t.add([{"_error": "x"}])
    assert not t.reached()                                             # 5 of 11 calls
    t.add([{"_error": "x"}])
    assert t.reached()                                                 # 6 of 12
    t = FS.Tally(1.0, 4)
    t.add([{"_error": "x"}] * 3)
    assert not t.reached()
    t.add([{"_error": "x"}])
    assert t.reached()
