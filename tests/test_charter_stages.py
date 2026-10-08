"""Multi-stage procedures and ballot rule functions (charter/stages.py, W6c; review 10 §3.2, §6 item 6): bicameralism, readings,
a committee, executive assent with a veto override; rule functions (quorum, Borda, double majority, supermajority) under the gas
meter; the proposal's visible stage and per-stage events; checkpoint/restore, replay and rewind mid-procedure; law.v2 off unchanged."""
from __future__ import annotations

import json
import pickle

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import generator
from charter import lawdocs as LD
from charter import spec as S
from charter.kernel import Kernel


def code(title, body, intent="test"):
    return f'title = "{title}"\nintent = "{intent}"\n{body}\n'


def _world(procedure, v2=True, preset="E4"):
    """A world whose constitution sets `procedure` (the body of `def proc(p):`, which sees PEOPLE) for every class."""
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=8", "shared_archive.enabled=false",
                                                                 *(["law.v2=true"] if v2 else [])]), 1)
    k = Kernel(inst)
    const = code("Staged Constitution", 'rank = "constitution"\n' + procedure + '''
def on_enact():
    set_procedure("ordinary", proc)
    set_procedure("structural", proc)
    set_procedure("procedural", proc)''')
    k.enact(k.new_law(const, "constitution"))
    k.start_round()
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def propose(k, title="Small Notice"):
    lid = k.new_law(code(title, "def on_round_end(r):\n    state['n'] = state.get('n', 0) + 1"), people(k)[0])
    k.decide(lid)
    return lid


def ballot_of(k, lid):
    return next(b for b in k.w["ballots"].values() if b["proposal"] == lid and b["status"] == "open")


def vote(k, lid, choices):
    """Votes on the proposal's open ballot (choices: {agent: choice}, or one choice for the whole electorate), then closes it."""
    b = ballot_of(k, lid)
    for a in b["electorate"]:
        c = choices.get(a) if isinstance(choices, dict) else choices
        if c is not None:
            A.act(k, a, "vote", {"ballot": b["id"], "choice": c})
    k.w["round"] = max(k.r, b["closes"])
    k.close_ballots()
    return b


def stage_events(k, lid):
    return [(e["type"], e["data"]["kind"], e["data"].get("result")) for e in k.events
            if e["type"].startswith("proposal_stage") and e["data"]["law"] == lid]


HALVES = '''
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    half = len(ppl) // 2
    return {"stages": [{"name": "House", "electorate": ppl[:half], "rule": "majority"},
                       {"name": "Senate", "electorate": ppl[half:], "rule": "majority"}]}'''


# ---------------------------------------------------------------------- the four structures
def test_bicameralism_needs_both_chambers():
    k = _world(HALVES)
    ppl = people(k)
    house, senate = ppl[:len(ppl) // 2], ppl[len(ppl) // 2:]
    lid = propose(k)
    law = k.w["laws"][lid]
    assert law["status"] == "stage" and law["procedure"]["kind"] == "stage" and law["procedure"]["at"] == 0
    b1 = vote(k, lid, "yes")
    assert b1["electorate"] == house and "stage 1 of 2: House" in b1["question"]
    b2 = ballot_of(k, lid)
    assert b2["electorate"] == senate and law["procedure"]["at"] == 1 and law["procedure"]["ballot"] == b2["id"]
    vote(k, lid, "yes")
    assert law["status"] == "active"
    assert stage_events(k, lid) == [("proposal_stage_open", "stage", None), ("proposal_stage_close", "stage", "yes"),
                                    ("proposal_stage_open", "stage", None), ("proposal_stage_close", "stage", "yes")]
    # the second chamber can kill it
    lid = propose(k, "Other Notice")
    vote(k, lid, "yes")
    vote(k, lid, "no")
    assert k.w["laws"][lid]["status"] == "failed"
    why = [e["data"]["why"] for e in k.events if e["type"] == "proposal_failed" and e["data"]["law"] == lid]
    assert why and "voted down at Senate" in why[0]


def test_three_readings_of_the_same_chamber():
    k = _world('''
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    return {"stages": [{"name": n, "electorate": ppl, "rule": "majority_voting"} for n in ("first reading", "second reading",
                                                                                            "third reading")]}''')
    lid = propose(k)
    names = []
    for _ in range(3):
        names.append(ballot_of(k, lid)["question"].split(": ")[-1].rstrip(")"))
        vote(k, lid, "yes")
    assert names == ["first reading", "second reading", "third reading"] and k.w["laws"][lid]["status"] == "active"
    assert [h["stage"] for h in k.w["laws"][lid]["procedure"]["history"]] == [1, 2, 3]


def test_a_committee_stage_filters_before_the_floor():
    k = _world('''
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    return {"stages": [{"name": "committee", "electorate": ppl[:1], "rule": "majority"},
                       {"name": "floor", "electorate": ppl, "rule": "majority"}]}''')
    chair = people(k)[0]
    lid = propose(k)
    assert ballot_of(k, lid)["electorate"] == [chair]
    vote(k, lid, "no")
    assert k.w["laws"][lid]["status"] == "failed"
    assert not [b for b in k.w["ballots"].values() if b["proposal"] == lid and "floor" in b["question"]]
    lid = propose(k, "Second")
    vote(k, lid, "yes")
    assert len(ballot_of(k, lid)["electorate"]) == len(people(k))
    vote(k, lid, "yes")
    assert k.w["laws"][lid]["status"] == "active"


EXEC = '''
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    return {"stages": [{"name": "Congress", "electorate": ppl[1:], "rule": "majority"}], "assent": [ppl[0]],
            "override": {"rule": "two_thirds"}}'''


def test_executive_assent_veto_and_override():
    k = _world(EXEC)
    pres, rest = people(k)[0], people(k)[1:]
    lid = propose(k)
    vote(k, lid, "yes")
    b = ballot_of(k, lid)
    assert b["electorate"] == [pres] and b["rule"] == {"assent": True, "silence": "veto"}
    assert k.w["laws"][lid]["procedure"]["kind"] == "assent"
    vote(k, lid, "no")                                                 # vetoed: the override ballot opens
    ov = ballot_of(k, lid)
    assert ov["rule"] == "two_thirds" and ov["electorate"] == rest and "Override the veto" in ov["question"]
    vote(k, lid, "yes")
    assert k.w["laws"][lid]["status"] == "active"
    kinds = [x[1] for x in stage_events(k, lid) if x[0] == "proposal_stage_close"]
    assert kinds == ["stage", "assent", "override"]
    # signed: passes without an override
    lid = propose(k, "Signed")
    vote(k, lid, "yes")
    vote(k, lid, "yes")
    assert k.w["laws"][lid]["status"] == "active"
    # vetoed and the override falls short
    lid = propose(k, "Vetoed")
    vote(k, lid, "yes")
    vote(k, lid, "no")
    vote(k, lid, {a: "yes" for a in rest[:len(rest) // 2]})
    assert k.w["laws"][lid]["status"] == "failed"
    # silence is a veto (no override in this plan)
    k2 = _world(EXEC.replace(',\n            "override": {"rule": "two_thirds"}', ""))
    lid = propose(k2)
    vote(k2, lid, "yes")
    vote(k2, lid, {})
    assert k2.w["laws"][lid]["status"] == "failed"
    assert any("vetoed by" in e["data"].get("why", "") for e in k2.events if e["type"] == "proposal_failed")


def test_silence_may_assent():
    k = _world(EXEC.replace('"override": {"rule": "two_thirds"}', '"silence": "assent"'))
    lid = propose(k)
    vote(k, lid, "yes")
    vote(k, lid, {})
    assert k.w["laws"][lid]["status"] == "active"


# ---------------------------------------------------------------------- rule functions
def test_rule_functions_quorum_borda_and_supermajority_in_open_ballot():
    k = _world("def proc(p):\n    return True")
    lid = k.new_law(code("Polls", '''
def quorum(votes, electorate):
    if len(votes) * 2 < len(electorate):
        return None
    yes = len([a for a in votes if votes[a] == "yes"])
    return "yes" if yes * 2 > len(votes) else "no"
def supermajority(votes, electorate):
    yes = len([a for a in votes if votes[a] == "yes"])
    return "yes" if yes * 5 >= len(electorate) * 3 else "no"
def borda(votes, electorate):
    score = {}
    for a in votes:
        ranking = votes[a]
        for i in range(len(ranking)):
            score[ranking[i]] = score.get(ranking[i], 0) + len(ranking) - i
    best = None
    for o in sorted(score):
        if best is None or score[o] > score[best]:
            best = o
    return best
def got(winners):
    state.setdefault("results", []).append(winners)
def on_enact():
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    state["q"] = open_ballot("Quorum?", ppl, ["yes", "no"], quorum, 0, got)
    state["s"] = open_ballot("Super?", ppl, ["yes", "no"], supermajority, 0, got)
    state["b"] = open_ballot("Borda?", ppl, ["x", "y", "z"], borda, 0, got)'''), "constitution")
    k.enact(lid)
    st = k.w["laws"][lid]["state"]
    q, s, b = (k.w["ballots"][st[x]] for x in ("q", "s", "b"))
    assert q["rule"]["name"] == "quorum" and q["rule"]["law"] == lid and q["rule"]["fn"] in k.fnreg
    ev = next(e for e in k.events if e["type"] == "ballot_open" and e["data"]["ballot"] == q["id"])
    assert ev["data"]["rule"] == f"function quorum of {lid}"
    ppl = people(k)
    A.act(k, ppl[0], "vote", {"ballot": q["id"], "choice": "yes"})          # below quorum: no result
    for i, a in enumerate(ppl):
        A.act(k, a, "vote", {"ballot": s["id"], "choice": "yes" if i < len(ppl) * 3 // 5 + 1 else "no"})
    for i, a in enumerate(ppl):                                          # y beats x and z by Borda count
        A.act(k, a, "vote", {"ballot": b["id"], "choice": ["y", "x", "z"] if i % 2 else ["x", "y", "z"] if i % 3 else ["y", "z", "x"]})
    k.close_ballots()
    assert q["result"] is None and s["result"] == "yes" and b["result"] == "y"
    assert st["results"] == [[None], ["yes"], ["y"]]


def test_double_majority_stage_rule_and_procedure_ballot_rule():
    k = _world('''
def double_majority(votes, electorate):
    big = [a for a in electorate if class_of(a) == electorate_class()]
    yes = [a for a in votes if votes[a] == "yes"]
    ok_people = len(yes) * 2 > len(electorate)
    ok_big = len([a for a in yes if a in big]) * 2 > len(big)
    return "yes" if ok_people and ok_big else "no"
def electorate_class():
    return class_of([a for a in agents() if class_of(a) not in ("board", "fixer")][0])
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    return {"stages": [{"name": "people", "electorate": ppl, "rule": double_majority}]}''')
    ppl = people(k)
    big = [a for a in ppl if k.w["agents"][a]["cls"] == k.w["agents"][ppl[0]]["cls"]]
    other = [a for a in ppl if a not in big]
    assert other, "the test needs two classes"
    lid = propose(k)
    assert ballot_of(k, lid)["rule"]["name"] == "double_majority"
    vote(k, lid, {a: "yes" for a in ppl if a not in big[: len(big) // 2 + 1]})   # a majority of people, not of the big class
    assert k.w["laws"][lid]["status"] == "failed"
    lid = propose(k, "Both")
    vote(k, lid, "yes")
    assert k.w["laws"][lid]["status"] == "active"


def test_one_ballot_procedure_accepts_a_rule_function():
    k = _world('''
def need_all(votes, electorate):
    return "yes" if len([a for a in electorate if votes.get(a) == "yes"]) == len(electorate) else "no"
def proc(p):
    return {"electorate": [a for a in agents() if class_of(a) not in ("board", "fixer")], "rule": need_all}''')
    lid = propose(k)
    b = ballot_of(k, lid)
    assert k.w["laws"][lid]["status"] == "ballot" and b["rule"]["name"] == "need_all" and "stage" not in b
    vote(k, lid, {a: "yes" for a in people(k)[1:]})
    assert k.w["laws"][lid]["status"] == "failed"


def test_a_rule_function_runs_under_gas_and_its_error_gives_no_result():
    k = _world('''
def spin(votes, electorate):
    while True:
        pass
def proc(p):
    return {"stages": [{"electorate": [a for a in agents() if class_of(a) not in ("board", "fixer")], "rule": spin}]}''')
    const = k.w["law_order"][-1]
    lid = propose(k)
    vote(k, lid, "yes")
    b = next(b for b in k.w["ballots"].values() if b["proposal"] == lid)
    assert b["result"] is None and k.w["laws"][lid]["status"] == "failed"
    assert any(e["type"] == "law_error" and e["data"].get("law") == const for e in k.events)


def test_invalid_plans_fail_the_proposal():
    k = _world('def proc(p):\n    return {"stages": [{"electorate": agents(), "rule": "no_such_rule"}]}')
    lid = propose(k)
    assert k.w["laws"][lid]["status"] == "failed" and "procedure" not in k.w["laws"][lid]
    why = next(e["data"]["why"] for e in k.events if e["type"] == "proposal_failed" and e["data"]["law"] == lid)
    assert "stage plan is invalid" in why and "unknown rule" in why


# ---------------------------------------------------------------------- what agents see
def test_the_pending_proposal_shows_its_stage_and_events_render():
    k = _world(EXEC)
    lid = propose(k)
    vote(k, lid, "yes")
    text = CX.read_law(k, people(k)[1], lid)
    assert f"Procedure (" in text and "Congress -> assent of " in text and "now awaiting assent" in text and "stage 1 B" in text
    for e in k.events:
        if e["type"].startswith("proposal_stage"):
            s = AG.render_event(k, e, people(k)[1])
            assert s and lid in s
    mapping = LD.resolve(k.spec)["mapping"]
    assert mapping["procedure_stages"] == "prompt" and mapping["ballot_rule_function"] == "common"
    assert "procedure_stages" not in LD.resolve(S.load("E4"))["mapping"]          # law.v2 off: not documented


def test_decisive_set_and_vote_weights_read_a_stage_plan():
    k = _world(EXEC)
    ppl = people(k)
    ds = k.decisive_set("ordinary")
    assert ppl[0] in ds and len(ds) == len(ppl[1:]) // 2 + 2
    assert set(k.vote_weights()) == set(ppl[1:])


# ---------------------------------------------------------------------- law.v2 off, checkpoints, replay
def test_law_v2_off_treats_a_stage_plan_as_before():
    k = _world(HALVES, v2=False)
    lid = propose(k)
    law = k.w["laws"][lid]
    assert law["status"] == "ballot" and "procedure" not in law and ballot_of(k, lid)["electorate"] == []
    assert not [e for e in k.events if e["type"].startswith("proposal_stage")]


def test_checkpoint_and_restore_mid_procedure_with_a_rule_function():
    k = _world('''
def two_fifths(votes, electorate):
    return "yes" if len([a for a in votes if votes[a] == "yes"]) * 5 >= len(electorate) * 2 else "no"
def proc(p):
    ppl = [a for a in agents() if class_of(a) not in ("board", "fixer")]
    return {"stages": [{"name": "A", "electorate": ppl, "rule": "majority"},
                       {"name": "B", "electorate": ppl, "rule": two_fifths}], "assent": [ppl[0]]}''')
    lid = propose(k)
    vote(k, lid, "yes")
    k.end_round()
    st = pickle.loads(pickle.dumps(k.checkpoint_state()))
    k2 = Kernel(k.inst)
    k2.restore_state(st)
    law = k2.w["laws"][lid]
    assert law["status"] == "stage" and law["procedure"]["at"] == 1
    k2.start_round()
    ppl = people(k2)
    vote(k2, lid, {a: "yes" for a in ppl[: (2 * len(ppl) + 4) // 5]})
    assert law["procedure"]["kind"] == "assent" and law["procedure"]["history"][-1]["result"] == "yes"
    vote(k2, lid, "yes")
    assert law["status"] == "active"


@pytest.fixture
def staged_start_law():
    from charter import library as LB
    LB.LIB["Staged Procedure"] = {"name": "Staged Procedure", "category": "law_v2_test", "code": code("Staged Procedure", '''
def no_objection(votes, electorate):
    return "no" if len([a for a in votes if votes[a] == "no"]) * 2 > len(electorate) else "yes"
def quorum(votes, electorate):
    yes = len([a for a in votes if votes[a] == "yes"])
    return "yes" if yes * 2 > len(electorate) else "no"
def proc(p):
    ppl = holders("vote") or agents()
    return {"stages": [{"name": "first", "electorate": ppl, "rule": no_objection, "closes_in": 1},
                       {"name": "second", "electorate": ppl, "rule": quorum, "closes_in": 1}]}
def on_enact():
    set_procedure("ordinary", proc)
    set_procedure("structural", proc)''')}
    yield
    LB.LIB.pop("Staged Procedure", None)


def test_replay_and_rewind_mid_procedure(tmp_path, monkeypatch, staged_start_law):
    import argparse
    from charter import __main__ as M
    from charter import runner
    sp = S.apply_overrides(S.load("E4"), ["rounds=3", "turns=simultaneous", "shared_archive.enabled=false", "law.v2=true",
                                          "start_laws=" + json.dumps(["Staged Procedure"])])
    inst = generator.generate(sp, 1)
    inst["run_id"] = "staged"
    run = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "staged", log=lambda *a: None)
    evs = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines()]
    opened = [e for e in evs if e["type"] == "proposal_stage_open"]
    assert opened, "the scripted run proposed nothing"
    closed = {e["data"]["ballot"]: e["round"] for e in evs if e["type"] == "proposal_stage_close"}
    assert any(e["round"] <= 1 and closed.get(e["data"]["ballot"], 99) >= 2 for e in opened), "no stage open across the rewind"
    assert any(e["data"]["kind"] == "stage" and e["data"]["stage"] == 2 for e in opened)
    monkeypatch.setattr(M, "load_env", lambda: None)
    M.main(["replay", str(run), "--out", str(tmp_path / "rep")])
    for f in ("events.jsonl", "snapshots.json"):
        assert (tmp_path / "rep" / f).read_bytes() == (run / f).read_bytes(), f
    new = tmp_path / "rewound"
    M.main(["rewind", str(run), "--to", "1", "--out", str(new)])
    monkeypatch.setattr(M, "policy_for", lambda spec, dry, seed: AG.ScriptedPolicy(seed))
    M.cmd_resume(argparse.Namespace(run=str(new), sandbox="off"))
    for f in ("events.jsonl", "snapshots.json"):
        assert (new / f).read_bytes() == (run / f).read_bytes(), f


def test_an_association_s_procedure_may_use_a_rule_function():
    """P4.3 contracts reuse the rule functions (stage plans too since W7e: tests/test_charter_w7e.py)."""
    import re
    from charter import contracts as CT
    inst = generator.generate(S.apply_overrides(S.load("E2"), ["rounds=8", "shared_archive.enabled=false", "turns=sequential",
                                                               "law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    a, b, c = people(k)[:3]
    out = A.act(k, a, "create_contract", {"name": "Firm", "code": code("Rules", '''
def founder_decides(votes, electorate):
    return votes.get(electorate[0])
def proc(p):
    return {"rule": founder_decides}
def on_enact():
    set_procedure("ordinary", proc)''')})
    cid = re.search(r"A\d+", out).group()
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    out = A.act(k, b, "propose_contract_change", {"contract": cid, "code": code("More", "def on_round_end(r):\n    state['n'] = 1")})
    bid = re.search(r"B\d+", out).group()
    assert k.w["ballots"][bid]["rule"]["name"] == "founder_decides"
    A.act(k, a, "vote", {"ballot": bid, "choice": "yes"})
    for x in (b, c):
        A.act(k, x, "vote", {"ballot": bid, "choice": "no"})
    k.end_round()
    assert k.w["ballots"][bid]["result"] == "yes"
    assert list(CT.recs(k)[cid]["proposals"].values())[-1]["status"] == "adopted"
