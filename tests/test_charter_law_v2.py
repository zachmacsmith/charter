"""P3.1: law.v2 -- new-style before_<p>/after_<p> hooks from any cause, cascades and limited death (charter/dispatch/: cascade,
hooks, routing; review 09 §4, §9, §13.2, §13.3; ARCHITECTURE §5, §6, D-6, D-12, D-18, D-21). Offline: scripted bots, no model calls."""
from __future__ import annotations

import json
import shutil

import pytest

from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import lawlang as L
from charter import spec as S
from charter.kernel import Kernel

import charter_law_v2_laws as V2


def world(v2=True, preset="E4", sets=(), gas=None, seed=1):
    sp = S.apply_overrides(S.load(preset), [*sets, "shared_archive.enabled=false"])
    if v2:
        sp["law"] = {"v2": True}
    inst = generator.generate(sp, seed)
    if gas:
        inst["spec"]["law"]["gas"] = dict(gas)                       # not a schema key yet: set after validation
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def agents(k, n=3):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")][:n]


@pytest.fixture
def k():
    return world()


# ------------------------------------------------------------------ static rules (R5) and classes
def test_r5_new_style_hooks_are_a_check_error_without_law_v2():
    old = world(v2=False)
    code = law("Spy", "def after_move(p, chain):\n    return None\n")
    with pytest.raises(L.LawError, match="need law.v2"):
        old.new_law(code, "a")
    new = world()
    new.new_law(code, "a")                                            # fine under law.v2
    with pytest.raises(L.LawError, match="cannot be hooked before"):
        new.new_law(law("X", "def before_regrow(p, chain):\n    return False\n"), "a")
    with pytest.raises(L.LawError, match="not routed"):
        new.new_law(law("X", "def after_use_power(p, chain):\n    return None\n"), "a")   # W8b routed commission
    with pytest.raises(L.LawError, match=r"\(p, chain\)"):
        new.new_law(law("X", "def after_move(p):\n    return None\n"), "a")
    # a helper named like no primitive is just a function, in either world
    old.new_law(law("X", "def after_death(a):\n    return None\n"), "a")


def test_hooks_give_their_class():
    cls = lambda body: L.classify(L.check(law("X", body)))
    assert cls("def after_move(p, chain):\n    gazette('x')\n") == "ordinary"
    assert cls("def before_move(p, chain):\n    return None\n") == "ordinary"
    assert cls("def before_move(p, chain):\n    return False\n") == "structural"
    assert cls("def before_harvest(p, chain):\n    return p['qty'] * 0.1\n") == "structural"
    assert cls("def after_propose(p, chain):\n    gazette('x')\n") == "procedural"
    assert cls("def before_propose(p, chain):\n    return None\n") == "procedural"


def test_without_law_v2_nothing_new_happens():
    k = world(v2=False)
    a, b, _ = agents(k)
    k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="test")
    assert "law_v2" not in k.w and not D.hooks_live(k)
    assert all("primitive" not in f for e in k.events for f in e["cause"])


# ------------------------------------------------------------------ hooks fire whatever the cause
COUNTER = law("Counter", '''
def after_move(p, chain):
    state["n"] = state.get("n", 0) + 1
    state["roots"] = state.get("roots", []) + [root_kind(chain)]
    state["whys"] = state.get("whys", []) + [p["why"]]
    state["moved"] = p["result"]["moved"]
''')


def test_after_hooks_see_law_world_and_agent_caused_changes(k):
    a, b, _ = agents(k)
    c = enact(k, COUNTER)
    f = enact(k, law("Fines", "def fine_now(a):\n    fine(a, 'timber', 2)\n"))
    with k.cause("action", "rule", agent=b, root=True):              # a law-caused change (fact 7 of review 09)
        k.call(f, k.ns[f]["fine_now"], a)
        assert k.w["laws"][c]["state"].get("n") is None               # queued, not yet run: after-hooks drain at the root's exit
    st = k.w["laws"][c]["state"]
    assert st["n"] == 1 and st["whys"] == ["fine"] and st["roots"] == ["action"] and st["moved"] == 2.0
    k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="bookkeeping")     # outside any root: an implicit kernel root
    assert st["n"] == 2 and st["roots"][-1] == "kernel"
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # an agent's action
    assert st["n"] == 3 and st["roots"][-1] == "action" and st["whys"][-1] == "transfer"


def test_before_hook_blocks_an_agents_transfer(k):
    a, b, _ = agents(k)
    enact(k, law("No Stone", "def before_move(p, chain):\n    if p['item'] == 'stone':\n        return {'block': True, 'reason': 'stone stays'}\n"))
    before = (k.bal(a, "stone"), k.bal(b, "stone"))
    with pytest.raises(A.ActionError, match="blocked"):
        A.act(k, a, "transfer", {"to": b, "item": "stone", "qty": 1})
    assert (k.bal(a, "stone"), k.bal(b, "stone")) == before
    e = events(k, "primitive_blocked")[-1]
    assert e["data"]["by"] == ["L2"] and e["data"]["reason"] == "stone stays" and set(e["vis"]) == {a, b}
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # other goods pass


def test_a_blocked_law_call_ends_quietly_without_suspending_the_law(k):
    a, _, _ = agents(k)
    enact(k, law("Guard", "def before_grant_right(p, chain):\n    return False\n"))
    g = enact(k, law("Granter", "def give(a):\n    state['r'] = grant(a, 'press')\n    state['after'] = 1\n"))
    with k.cause("kernel", "test", root=True):
        k.call(g, k.ns[g]["give"], a)
    st = k.w["laws"][g]["state"]
    assert st == {"r": False, "after": 1} and "press" not in k.w["agents"][a]["rights"]   # refused: grant returns False
    assert k.w["laws"][g]["status"] == "active"


def test_numeric_verdict_is_a_charge_to_the_laws_treasury(k):
    a, b, _ = agents(k)
    enact(k, law("Toll", "def before_move(p, chain):\n    if p['why'] == 'transfer':\n        return 2\n"))
    ta, tb, res = k.bal(a, "timber"), k.bal(b, "timber"), k.bal("reserve", "timber")
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 5})
    assert k.bal(b, "timber") == tb + 5 and k.bal(a, "timber") == ta - 7 and k.bal("reserve", "timber") == res + 2
    e = events(k, "law_charged")[-1]
    assert e["data"] == {"law": "L2", "primitive": "move", "payer": a, "item": "timber", "qty": 2.0} and e["vis"] == [a]


def test_a_malformed_verdict_is_the_laws_runtime_error(k):
    a, b, _ = agents(k)
    t = enact(k, law("Bad", "def before_move(p, chain):\n    return {'nonsense': 1}\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # the change goes ahead: the dead hook abstains
    assert k.w["laws"][t]["status"] == "suspended" and "unknown keys" in events(k, "law_error")[-1]["data"]["error"]


# ------------------------------------------------------------------ re-entrancy rules
def test_r1_a_law_never_gates_its_own_doings(k):
    a, b, _ = agents(k)
    gate = enact(k, law("Gate", '''
def before_move(p, chain):
    return False
def pay(a):
    state["own"] = move(a, "reserve", "timber", 1)
'''))
    other = enact(k, law("Other", "def pay(a):\n    state['other'] = move(a, 'reserve', 'timber', 1)\n"))
    with k.cause("kernel", "test", root=True):
        k.call(gate, k.ns[gate]["pay"], a)
        k.call(other, k.ns[other]["pay"], a)
    assert k.w["laws"][gate]["state"]["own"] is True and k.w["laws"][other]["state"]["other"] is False


def test_r1_covers_a_laws_own_charges(k):
    a, b, _ = agents(k)
    enact(k, law("Toll", '''
def before_move(p, chain):
    state["seen"] = state.get("seen", []) + [p["why"]]
    if p["why"] == "transfer":
        return 1
'''))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 3})
    assert k.w["laws"]["L2"]["state"]["seen"] == ["transfer"]        # its own charge move ("charge:L2") was not shown to it


def test_r2_no_direct_self_feedback(k):
    a, b, _ = agents(k)
    rebate = enact(k, law("Rebate", '''
def after_move(p, chain):
    state["n"] = state.get("n", 0) + 1
    if p["why"] == "transfer":
        move("reserve", p["src"], p["item"], 0.1)
'''))
    k.w["reserve"]["timber"] = 10.0
    c = enact(k, COUNTER)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][rebate]["state"]["n"] == 1                    # not called again for its own rebate
    assert k.w["laws"][c]["state"]["n"] == 2                         # but another law sees both moves


def test_cycles_are_legal_and_bounded_by_the_depth_cap(k):
    a, b, _ = agents(k)
    ping = law("Ping", "def after_move(p, chain):\n    if p['dst'] == '{b}':\n        move('{b}', '{a}', 'timber', 0.01)\n")
    pong = law("Pong", "def after_move(p, chain):\n    if p['dst'] == '{a}':\n        move('{a}', '{b}', 'timber', 0.01)\n")
    l1 = enact(k, ping.replace("{a}", a).replace("{b}", b))
    l2 = enact(k, pong.replace("{a}", a).replace("{b}", b))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    moves = [e for e in events(k, "move") if e["data"]["qty"] == 0.01]
    assert len(moves) == D.GAS["depth_cap"]                          # depths 1..8; the 9th was refused
    flags = events(k, "law_flagged")
    assert [f["data"] for f in flags] == [{"law": l1, "kind": "depth"}]   # Ping moves at odd depths: its 9th-depth move dies
    assert [l["status"] for l in (k.w["laws"][l1], k.w["laws"][l2])] == ["active", "active"]


def test_r4_no_new_style_hook_runs_while_quiet(k):
    c = enact(k, law("Watch", "def before_move(p, chain):\n    state['n'] = state.get('n', 0) + 1\n"))
    k.probe("transfer")
    k.procedure_spec("ordinary", agents(k)[0])
    assert k.w["laws"][c]["state"].get("n") is None


def test_legacy_hooks_keep_their_exact_semantics_under_v2(k):
    a, b, _ = agents(k)
    t = enact(k, law("Legacy Tax", "def on_transfer(src, dst, item, qty):\n    return 0.5\n"))
    f = enact(k, law("Fines", "def fine_now(a):\n    fine(a, 'timber', 1)\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 2})
    assert events(k, "transfer")[-1]["data"]["tax"] == 0.5
    with k.cause("kernel", "test", root=True):                        # law-caused: the legacy alias does not fire (today's rule)
        k.call(f, k.ns[f]["fine_now"], a)
    assert sum(1 for e in events(k, "move") if e["data"]["why"] == "transfer_tax") == 1


# ------------------------------------------------------------------ halting points (review 09 §9.4)
LOOP = "def after_move(p, chain):\n    n = 0\n    while True:\n        n += 1\n"


def test_per_call_limit_kills_only_the_invocation(k):
    a, b, _ = agents(k)
    bad = enact(k, law("Loop", LOOP))
    c = enact(k, COUNTER)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][c]["state"]["n"] == 1                         # the cascade went on
    assert k.w["laws"][bad]["status"] == "active" and k.w["laws"][bad]["flags"] == [
        {"round": 0, "kind": "gas_call", "cascade": "action:transfer"}]
    assert events(k, "law_flagged")[-1]["data"] == {"law": bad, "kind": "gas_call"} and events(k, "law_flagged")[-1]["vis"] == "public"


def test_flags_escalate_to_suspension():
    k = world(gas={"flag_limit": 2})
    a, b, _ = agents(k)
    bad = enact(k, law("Loop", LOOP))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][bad]["status"] == "active"
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][bad]["status"] == "suspended"
    assert "repeatedly exceeded its computation limits" in events(k, "law_error")[-1]["data"]["error"]
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # suspended: no third flag
    assert len(k.w["laws"][bad]["flags"]) == 2


def test_per_cascade_budget_halts_the_cascade():
    k = world(gas={"per_cascade": 3000})
    a, b, _ = agents(k)
    burn = "def after_move(p, chain):\n    n = 0\n    while n < 400:\n        n += 1\n    move('{a}', '{b}', 'timber', 0.01)\n"
    l1 = enact(k, law("Burn1", burn.replace("{a}", a).replace("{b}", b)))
    l2 = enact(k, law("Burn2", burn.replace("{a}", a).replace("{b}", b)))
    c = enact(k, COUNTER)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    flags = [e["data"] for e in events(k, "law_flagged")]
    assert len(flags) == 1 and flags[0]["kind"] == "gas_cascade"     # only the first offender
    halted = events(k, "cascade_halted")[-1]
    assert halted["vis"] == "monitor" and halted["data"]["by"] == flags[0]["law"] and halted["data"]["root"] == "action:transfer"
    assert halted["data"]["dropped"] > 0
    # the next root starts a fresh cascade
    n = k.w["laws"][c]["state"]["n"]
    k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="test")
    assert k.w["laws"][c]["state"]["n"] > n
    assert {l1, l2}


def test_a_halted_cascade_refuses_law_changes_and_runs_world_changes_unhooked():
    k = world(gas={"per_cascade": 500})
    a, b, _ = agents(k)
    enact(k, law("Burn", "def before_move(p, chain):\n    n = 0\n    while n < 1000:\n        n += 1\n"))
    c = enact(k, COUNTER)
    with k.cause("world", "test", root=True):
        k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="w1")   # the before-hook exhausts the cascade: halted
        cas = k.cascade()
        assert cas.halted == "L2"
        out = k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="w2")   # depth 0: applies, without hooks
        assert out.ok
    assert k.w["laws"][c]["state"].get("n") is None                  # queued after-items dropped
    w2 = [e for e in events(k, "move") if e["data"]["why"] == "w2"][-1]
    assert w2["data"]["unhooked"] is True
    with k.cause("world", "test2", root=True):                        # a law-caused change in a halted cascade is refused
        k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="w3")
        k.cascade().halted = "L2"
        k._invs.append(D.Invocation(law="L3", hook="after_move", depth=0))
        with pytest.raises(D.Halted):
            k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="w4")
        k._invs.pop()


def test_per_account_budget_closes_the_account_for_the_round():
    k = world(gas={"per_account_round": 2000})
    a, b, _ = agents(k)
    burn = enact(k, law("Burn", "def after_move(p, chain):\n    n = 0\n    while n < 300:\n        n += 1\n"))
    for _ in range(4):
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert [e["data"]["kind"] for e in events(k, "law_flagged")] == ["gas_round"]
    oog = events(k, "account_out_of_gas")
    assert len(oog) == 1 and oog[0]["data"] == {"account": "J0", "law": burn}
    used = k.w["law_v2"]["account_used"]["J0"]
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["law_v2"]["account_used"]["J0"] == used               # skipped for the rest of the round
    k.w["round"] += 1                                                # a new round: a fresh budget
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["law_v2"]["account_used"]["J0"] > 0 and "J0" not in k.w["law_v2"]["out_of_gas"]


def test_a_dead_before_hook_abstains_unless_a_constitution_fails_closed(k):
    a, b, _ = agents(k)
    enact(k, law("Loop Gate", "def before_move(p, chain):\n    while True:\n        pass\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # D-6: abstains, the transfer goes through
    assert events(k, "transfer")
    rv = enact(k, law("Review", "fail_closed = True\ndef before_propose(p, chain):\n    while True:\n        pass\n"))
    k.w["laws"][rv]["rank"] = "constitution"                         # ranks are P3.2: set by hand here
    leg = next(x for x in k.roster() if k.has(x, "propose"))
    with pytest.raises(A.ActionError, match="fail_closed"):
        A.act(k, leg, "propose", {"code": law("Note", "def on_round_end(r):\n    gazette('hi')\n")})
    assert events(k, "proposal_blocked")[-1]["data"]["reason"] == "fail_closed"


# ------------------------------------------------------------------ legal acts
def test_constitutional_review_blocks_a_draft_before_the_procedure(k):
    rv = enact(k, V2.V2_LAWS["Rights Review"])
    leg = next(x for x in k.roster() if k.has(x, "propose"))
    victim = agents(k)[0]
    with pytest.raises(A.ActionError, match="protected right: vote"):
        A.act(k, leg, "propose", {"code": law("Purge", f"def on_enact():\n    revoke('{victim}', 'vote')\n")})
    lid = events(k, "proposal_blocked")[-1]["data"]["law"]
    assert k.w["laws"][lid]["status"] == "blocked" and events(k, "proposal_blocked")[-1]["data"]["by"] == [rv]
    assert not [b for b in k.w["ballots"].values() if b.get("proposal") == lid]
    out = A.act(k, leg, "propose", {"code": law("Fine", "def on_round_end(r):\n    gazette('hi')\n")})
    assert "Proposed" in out


def test_a_duplicate_proposal_is_noted_not_blocked():
    """The haiku runs: two identical Harvest Quotas (different authors) were proposed and enacted in one round. law.v2 notes an
    active or pending law with the same normalised code (title, intent, comments and layout aside); law v1 says nothing."""
    body = "def on_round_end(r):\n    gazette('quota')\n"
    for v2 in (True, False):
        k = world(v2=v2)
        leg = [x for x in k.roster() if k.has(x, "propose")]
        first = A.act(k, leg[0], "propose", {"code": law("Harvest Quotas", body)})
        assert "Note:" not in first
        same = law("Harvest Quotas II", "# a copy\ndef on_round_end(r):\n    gazette( 'quota' )\n")
        out = A.act(k, leg[-1], "propose", {"code": same})
        prop = events(k, "proposal")[-1]["data"]
        if v2:
            assert "Note:" in out and "the same code" in out and "Proposed" in out                     # noted, not refused
            assert prop["similar_to"][0]["match"] == "identical" and prop["similar_to"][0]["title"] == "Harvest Quotas"
        else:
            assert "Note:" not in out and "similar_to" not in prop
    k = world()
    leg = next(x for x in k.roster() if k.has(x, "propose"))
    A.act(k, leg, "propose", {"code": law("A", body)})
    assert "Note:" not in A.act(k, leg, "propose", {"code": law("B", "def on_round_end(r):\n    gazette('a different law')\n    move('reserve', 'x', 'grain', 1)\n")})


def test_before_enact_strikes_down_an_enactment(k):
    enact(k, law("Strike", "def before_enact(p, chain):\n    if p['via'] == 'test':\n        return {'block': True, 'reason': 'no'}\n"))
    lid = k.new_law(law("T", "def on_round_end(r):\n    gazette('x')\n"), "a")
    out = k.apply("enact", jurisdiction=None, law=lid, via="test")
    assert not out.ok and out.blocked_by == ("L2",) and k.w["laws"][lid]["status"] == "struck_down" and lid not in k.w["law_order"]
    e = events(k, "primitive_blocked")[-1]
    assert e["vis"] == "public" and e["data"] == {"primitive": "enact", "by": ["L2"], "reason": "no", "law": lid}


# ------------------------------------------------------------------ chains (D-18)
def test_chain_is_redacted_for_laws(k):
    a, b, _ = agents(k)
    c = enact(k, law("Chains", "def after_move(p, chain):\n    state['c'] = chain\n    state['by'] = caused_by_agent(chain)\n"))
    k.begin_round_cause(phase="turns")
    with k.cause("turn", a, call="r0:x:0"):
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
        ch = k.w["laws"][c]["state"]["c"]
        assert ch[0] == {"kind": "action", "id": "action:transfer", "agent": a} and k.w["laws"][c]["state"]["by"] == a
        assert all("call" not in f for f in ch) and ch[1]["kind"] == "primitive"
        with k.concealing(a):                                       # a concealed actor is never named
            A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
        assert k.w["laws"][c]["state"]["c"][0]["agent"] is None and k.w["laws"][c]["state"]["by"] is None
    k.end_round_cause()
    with k.cause("intervention", "iv1", op="shock", root=True):       # an unannounced intervention reads as the world
        k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="shock")
    assert k.w["laws"][c]["state"]["c"][0] == {"kind": "world", "id": "world"}


def test_dry_run_previews_are_isolated(k):
    a, b, _ = agents(k)
    c = enact(k, COUNTER)
    leg = next(x for x in k.roster() if k.has(x, "propose"))
    A.act(k, leg, "propose", {"code": law("Pay", f"def on_round_end(r):\n    move('{a}', '{b}', 'timber', 1)\n")})
    assert k.w["laws"][c]["state"].get("n") is None                  # the preview's moves reached no law in force


# ------------------------------------------------------------------ review 09's worked examples
def test_worked_example_13_2_fine_relief(k):
    a, b, _ = agents(k)
    k.w["agents"][a]["holdings"]["timber"] = 6.0
    k.w["reserve"]["timber"] = 20.0
    pen = enact(k, law("Penalties", "def penalty(accused, accuser):\n    fine(accused, 'timber', 4)\n"))
    relief = enact(k, V2.V2_LAWS["Fine Relief"])
    tax = enact(k, law("Payment Tax", '''
def before_move(p, chain):
    if p["src"] == "reserve":
        state["chains"] = state.get("chains", []) + [chain_laws(chain)]
        return 0.5
'''))
    with k.cause("action", "rule", agent=b, root=True):              # a judge's ruling runs the clause penalty: a law-caused fine
        k.call(pen, k.ns[pen]["penalty"], a, b)
    st = k.w["laws"][relief]["state"]
    assert st["relief"] == 1                                         # R2: not again for its own relief payment
    assert st["chain"] == ["action", "law", "primitive"]             # the chain of the fine it reacted to
    assert k.bal(a, "timber") == pytest.approx(6 - 4 + 2)            # half the fine back
    assert k.w["laws"][tax]["state"]["chains"] == [[pen, relief]]    # the tax law saw the relief payment (R1 exempts only L9)
    charge = [e for e in events(k, "move") if e["data"]["why"] == f"charge:{tax}"]
    assert [c["data"]["qty"] for c in charge] == [0.5] and charge[0]["data"]["src"] == "reserve"   # charged to the payer (src)
    assert any(e["data"]["to"] == a and "Fine Relief" in e["data"]["text"] for e in events(k, "notify"))


def _life_world():
    sp = S.apply_overrides(S.load("opus20"), ["shared_archive.enabled=false"])
    sp["law"] = {"v2": True}
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def test_worked_example_13_3_equal_partition():
    k = _life_world()
    p = enact(k, V2.V2_LAWS["Equal Partition"])
    reg = enact(k, V2.V2_LAWS["Death Register"])
    pool = [x for x in k.roster() if k.cls_of(x) == "worker"]
    dead, kid1, kid2, heir = pool[:4]
    k.w["life"].setdefault("parent", {}).update({kid1: dead, kid2: dead})
    k.w["agents"][dead]["holdings"] = {"timber": 10.0, "stone": 4.0}
    from charter import mortality as MO
    MO.state(k)["bequests"][dead] = {"holdings": {heir: 1.0}, "files": None, "public": False}
    base = {x: dict(k.w["agents"][x]["holdings"]) for x in (kid1, kid2, heir)}
    with k.cause("world", "ageing", agent=dead, root=True):           # a death from old age: a world root frame
        assert MO.disable(k, dead, "old_age")
        assert MO.estate(k, dead) == {"timber": 10.0, "stone": 4.0}   # probate waits for the end of the cascade
    for kid in (kid1, kid2):
        assert k.bal(kid, "timber") == base[kid].get("timber", 0) + 5 and k.bal(kid, "stone") == base[kid].get("stone", 0) + 2
    assert k.bal(heir, "timber") == base[heir].get("timber", 0)      # nothing left for the bequest
    assert k.w["laws"][p]["state"] == {"deaths": 1, "partitions": 1}
    assert any("Death register: " + dead + " (old_age)" in e["data"].get("text", "") for e in k.events if e["type"] in ("gazette", "official_post", "post"))
    assert k.w["mortality"]["estates"][dead]["status"] == "probated"
    # whatever the cause: a law-caused death and a death outside any root frame reach it too
    victim = pool[4]
    MO.disable(k, victim, "law")
    assert k.w["laws"][p]["state"]["deaths"] == 2 and reg


# ------------------------------------------------------------------ determinism and replay with law.v2
def _v2_case(tmp, name):
    from charter import agents as AG, runner
    sp = S.apply_overrides(S.load("E4"), ["rounds=3", "turns=simultaneous", "shared_archive.enabled=false", "law.v2=true",
                                          "start_laws=" + json.dumps(["Harvest Tithe", "Fine Relief", "Speech Ledger"])])
    inst = generator.generate(sp, 1)
    inst["run_id"] = name
    return runner.run(inst, AG.ScriptedPolicy(1), tmp / name, log=lambda *a: None)


def test_determinism_and_replay_with_law_v2(tmp_path, monkeypatch):
    from charter import __main__ as M
    with V2.registered():
        a = _v2_case(tmp_path, "a")
        b = _v2_case(tmp_path, "b")
        for f in ("events.jsonl", "snapshots.json"):
            assert (a / f).read_bytes() == (b / f).read_bytes(), f
        evs = [json.loads(x) for x in (a / "events.jsonl").read_text().splitlines()]
        assert any(e["type"] == "law_charged" for e in evs)          # the v2 tithe ran
        monkeypatch.setattr(M, "load_env", lambda: None)
        M.main(["replay", str(a), "--out", str(tmp_path / "rep")])
        for f in ("events.jsonl", "snapshots.json"):
            assert (tmp_path / "rep" / f).read_bytes() == (a / f).read_bytes(), f
    shutil.rmtree(tmp_path, ignore_errors=True)


# ------------------------------------------------------------------ more halting points, R3, imports, redaction, typed harvests
def test_python_depth_is_a_per_call_limit(k):
    a, b, _ = agents(k)
    deep = enact(k, law("Deep", "def down(n):\n    return down(n + 1)\ndef after_move(p, chain):\n    down(0)\n"))
    c = enact(k, COUNTER)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][c]["state"]["n"] == 1 and k.w["laws"][deep]["status"] == "active"
    assert k.w["laws"][deep]["flags"][0]["kind"] == "gas_call"


def test_a_dead_invocations_queued_reactions_are_dropped(k):
    a, b, _ = agents(k)
    pay = enact(k, law("Pay Then Spin", f"def after_move(p, chain):\n    if p['why'] == 'transfer':\n"
                                       f"        move('{a}', '{b}', 'timber', 0.5)\n        while True:\n            pass\n"))
    c = enact(k, COUNTER)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][c]["state"]["whys"] == ["transfer"]           # its reaction to the 0.5 move died with the invocation
    assert events(k, "cascade_halted")[-1]["data"] == {"root": "action:transfer", "by": None, "dropped": 1}
    assert [f["kind"] for f in k.w["laws"][pay]["flags"]] == ["gas_call"]


def test_r3_on_enact_runs_inside_the_enact_change(k):
    a, b, _ = agents(k)
    c = enact(k, law("Chains", "def after_move(p, chain):\n    state['ids'] = [f['id'] for f in chain]\n"
                               "    state['law'] = chain_laws(chain)\n"))
    pay = enact(k, law("Pay On Enact", f"def on_enact():\n    move('{a}', '{b}', 'timber', 1)\n"))
    ids = k.w["laws"][c]["state"]["ids"]
    assert ids[0] == "kernel:enact" and ids[1] == "primitive:enact" and k.w["laws"][c]["state"]["law"] == [pay]


def test_imported_functions_run_under_the_importers_gas(k):
    a, b, _ = agents(k)
    lib = enact(k, law("Spinner", 'exports = ["spin"]\ndef spin():\n    n = 0\n    while True:\n        n += 1\n'))
    imp = enact(k, law("Importer", f'sp = use("{lib}")\ndef after_move(p, chain):\n    sp["spin"]()\n'))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert [f["kind"] for f in k.w["laws"][imp].get("flags", [])] == ["gas_call"]
    assert not k.w["laws"][lib].get("flags") and k.w["law_v2"]["law_gas"][imp] >= D.GAS["per_call"] - 1   # the importer paid


def test_typed_harvest_deductions_go_to_the_taxing_laws_treasury_only_under_v2():
    for v2 in (False, True):
        k = world(v2=v2)
        a, t, _ = agents(k)
        to = t if v2 else "reserve"                                   # charge_to stands for the taxing law's treasury
        before = k.bal(to, "grain")
        D.do_harvest(k, a, "c0", [0], "grain", 4.0, via="typed", charged=1.0, charge_to=t)
        assert k.bal(to, "grain") == before + 1.0, v2


def test_a_covert_killer_is_never_named_to_laws():
    k = _life_world()
    spy = enact(k, law("Spy", "def after_end_life(p, chain):\n    state['p'] = p\n    state['by'] = caused_by_agent(chain)\n"))
    pool = [x for x in k.roster() if k.cls_of(x) == "worker"]
    killer, victim = pool[:2]
    from charter import mortality as MO
    with k.cause("action", "attack", agent=killer, root=True):
        MO.disable(k, victim, "assassin", by=killer, named=False)
    st = k.w["laws"][spy]["state"]
    assert st["p"]["agent"] == victim and st["p"]["by"] is None and st["p"]["result"]["by"] is None
    assert killer not in json.dumps(st["p"])


def test_law_gas_is_a_spec_key():
    from charter import schema as SC
    assert SC.validate(S.apply_overrides(S.load("E4"), ["law.v2=true", "law.gas.per_cascade=3000"])) == []
    k = world(gas={"per_cascade": 3000})
    assert D.gas_cfg(k)["per_cascade"] == 3000 and D.gas_cfg(k)["per_call"] == 10_000


def test_the_observer_never_appears_to_laws():
    k = world(sets=["observer.enabled=true"])
    obs = k.inst["observer"]["id"]
    a, _, _ = agents(k)
    spy = enact(k, law("Spy", "def after_move(p, chain):\n    state['p'] = p\n    state['c'] = chain\n"))
    with k.cause("action", "transfer", agent=obs, root=True):
        k.apply("move", src=obs, dst=a, item="timber", qty=1.0, why="transfer")
    st = k.w["laws"][spy]["state"]
    assert st["c"][0] == {"kind": "world", "id": "world"} and st["p"]["src"] is None and obs not in json.dumps(st)


def test_a_blocked_repeal_leaves_the_law_in_force(k):
    keep = enact(k, law("Keep", "def on_round_end(r):\n    gazette('x')\n"))
    enact(k, law("Entrench", f"def before_repeal(p, chain):\n    if p['law'] == '{keep}':\n        return False\n"))
    assert k.repeal(keep) is False and k.w["laws"][keep]["status"] == "active"
    assert events(k, "primitive_blocked")[-1]["data"]["primitive"] == "repeal"
