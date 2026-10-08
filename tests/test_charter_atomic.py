"""P3.6: atomic invocations under law.v2 (charter/dispatch.py, the P3.6 block; review 09 §9.5; ARCHITECTURE D-7). A law.v2 hook
invocation that dies (gas, depth cap, a LawError) is rolled back: its world changes, law state, public and module data, the events
it logged and the reactions it queued are undone, leaving one monitor-only hook_aborted record (and its flag). Offline."""
from __future__ import annotations

import copy
import json

import pytest

from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import lawapi as LA
from charter import spec as S
from charter.kernel import Kernel

ALL_ON = ["conflict.enabled=true", "media2.enabled=true", "life.enabled=true", "shared_archive.enabled=false", "law.v2=true"]
_INST = {}


def world(jur=False, atomic=None, preset="society", sets=()):
    key = (jur, preset, tuple(sets))
    if key not in _INST:
        sp = S.apply_overrides(S.load(preset), [*ALL_ON, f"jurisdictions.enabled={str(jur).lower()}", *sets])
        _INST[key] = generator.generate(sp, 1)
    inst = copy.deepcopy(_INST[key])
    if atomic is not None:
        inst["spec"]["law"]["atomic"] = atomic
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def workers(k, n=3):
    return [a for a in k.roster() if any(r.startswith("harvest:") for r in k.w["agents"][a]["rights"])][:n]


def image(k):
    """Everything a law's work can change, as comparable data: the world (minus gas bookkeeping), the events, every law module's
    data globals, the registered callbacks, the random streams."""
    w = {x: v for x, v in k.w.items() if x != "law_v2"}
    data = {lid: {n: v for n, v in ns.items() if n != "__builtins__" and not callable(v) and not hasattr(v, "_ns")}
            for lid, ns in k.ns.items()}
    return copy.deepcopy({"w": w, "events": k.events, "ns": data, "fnreg": sorted(k.fnreg), "fn_n": k._fn_n,
                          "rng": k.rng.getstate(), "law_rng": k._law_rng_state(), "links": {a: len(v) for a, v in k.links.items()}})


def run_hook(k, lid, hook="after_post", payload=None):
    """Invoke `hook` of law `lid` as the cascade machinery does (a root cause, then invoke): (its value, hook_aborted data or None)."""
    with k.cause("kernel", "test", root=True):
        cas = k.cascade()
        n = len(k.events)
        out = D.invoke(k, cas, lid, hook, payload or {}, ({"kind": "kernel", "id": "kernel:test"},), 0)
        ab = [e for e in k.events[n:] if e["type"] == "hook_aborted"]
    return out, (ab[0]["data"] if ab else None)


LOOP = "\n    while True:\n        pass\n"

# Every law-API function that writes (a LawFn row with a primitive): a hook body that calls it so that it changes the world. {a},
# {b}: workers; {camp}: a camp; {post}: a post's event id; {other}: an active law; {outlet}: an outlet. Module-level helpers go in
# CALL_MODULE. A body may set things up first (all inside the same invocation, so all of it is undone).
CALLS = {
    "hide_post": "hide_post('{post}')",
    "unhide_post": "hide_post('{post}')\n    unhide_post('{post}')",
    "create_right": "create_right('tinkering')",
    "grant": "create_right('tinkering')\n    grant('{a}', 'tinkering')",
    "revoke": "revoke('{a}', '{ra}')",
    "define_action": "create_right('tinkering')\n    define_action('tinkering', 'tinker', tinker)",
    "create_currency": "create_currency('bead')",
    "mint": "create_currency('bead')\n    mint('bead', 5, '{a}')",
    "burn": "create_currency('bead')\n    mint('bead', 5, '{a}')\n    burn('bead', 2, '{a}')",
    "move": "move('{a}', '{b}', 'timber', 1)",
    "set_convertible": "create_currency('bead')\n    set_convertible('bead')",
    "enable_loans": "enable_loans()",
    "forgive_loan": "enable_loans()\n    forgive_loan(lend_from_reserve('{a}', 'timber', 2))",
    "set_quota": "set_quota('{camp}', 2)",
    "set_harvest_limit": "set_harvest_limit('{camp}', 2)",
    "set_fee": "set_fee('{camp}', 'timber', 1)",
    "set_procedure": "set_procedure('ordinary', proc)",
    "open_ballot": "open_ballot('More bread?', ['{a}', '{b}'], ['yes', 'no'])",
    "rename": "rename('{a}', 'Bobbin')",
    "title": "title('{a}', 'Warden')",
    "set_dm_limit": "set_dm_limit(1, '{a}')",
    "fine": "fine('{a}', 'timber', 1)",
    "suspend": "suspend('{a}', '{ra}', 2)",
    "limit_actions": "limit_actions('{a}', 1, 2)",
    "clause": "clause('quiet', 'no shouting', penalty)",
    "repeal": "repeal('{other}')",
    "set_par": "create_currency('bead')\n    set_par('bead', 'timber', 2)",
    "suspend_redemption": "create_currency('bead')\n    suspend_redemption('bead', 2)",
    "set_interest_cap": "set_interest_cap(0.1)",
    "set_default_consequence": "set_default_consequence('sanction')",
    "restructure_loan": "enable_loans()\n    restructure_loan(lend_from_reserve('{a}', 'timber', 2), repay_qty=3)",
    "lend_from_reserve": "enable_loans()\n    lend_from_reserve('{a}', 'timber', 2)",
    "buy_loan": "enable_loans()\n    buy_loan(lend_from_reserve('{a}', 'timber', 2))",
    "disclose_capability_use": "disclose_capability_use(True)",
    "revoke_capability": "revoke_capability('{cap}')",
    "start_project": "start_project('road', 25, 3, params={{'tier': 2}})",
    "contribute_project": "contribute_project(start_project('road', 25, 3, params={{'tier': 2}}), 'timber', 1)",
    "set_refund": "set_refund(start_project('road', 25, 3, params={{'tier': 2}}), False)",
    "pay_tribute": "pay_tribute('timber', 1)",
    "set_lease_rules": "set_lease_rules(True, 0.1)",
    "set_succession_public": "set_succession_public(True)",
    "ban_forging": "ban_forging(True)",
    "oblige_guard": "oblige_guard('{a}', '{b}')",
    "clear_obligations": "clear_obligations()",
    "admit": "admit('{outsider}')",
    "expel": "expel('{a}')",
    "lawful_attack": "lawful_attack('{a}', '{b}', 1)",
    "publish_stat": "publish_stat('laws')",
    "official_stream": "official_stream(['{a}'])",
    "set_official_editor": "set_official_editor('{a}')",
    "set_open_board": "set_open_board(True)",
    "set_press_freedom": "set_press_freedom(False)",
    "require_sponsor_label": "require_sponsor_label(True)",
    "suspend_outlet": "suspend_outlet('{outlet}', 2)",
    "compel_subscription": "compel_subscription('{a}', '{outlet}')",
    "set_birth_rules": "set_birth_rules(max_children=1)",
    "publish_commissions": "publish_commissions(True)",
    "publish_births": "publish_births(True)",
}
CALL_MODULE = '''
def tinker(agent, *args):
    return "tinkered"

def proc(p):
    return True

def penalty(guilty, accuser):
    fine(guilty, "timber", 1)
'''
JUR_ONLY = {"admit", "expel", "lawful_attack"}
WRITERS = sorted(n for n, f in LA.LAWFNS.items() if f.primitive)


def test_every_writer_has_a_call():
    assert set(CALLS) == set(WRITERS)


def _setup(k, name):
    """A world where `name` can change something: a post, another law to repeal, reserve stock, an outlet, a capability holder, an
    open tribute demand, a guard obligation, an outsider."""
    from charter import outside as OUT
    a, b, c = workers(k)
    k.w["reserve"]["timber"] = k.w["reserve"].get("timber", 0) + 50.0
    for x in (a, b):
        k._add(x, "timber", 20.0)
    post = k.log("post", a, {"text": "hello"}, vis="public")
    other = enact(k, law("Other", "def noop():\n    return None\n"))
    ra = next(r for r in k.w["agents"][a]["rights"] if r.startswith("harvest:"))
    cap = next(x for hs in k.w["hidden_caps"]["holders"].values() for x in hs)
    outlet = next(o for o, v in k.w["media"]["outlets"].items() if v["editor"] != a and v["status"] == "open")
    if name == "pay_tribute":
        OUT.demand_tribute(k)
    return {"a": a, "b": b, "camp": next(iter(k.w["camps"])), "post": post, "other": other, "ra": ra, "cap": cap,
            "outlet": outlet, "outsider": c}


def _writer_law(k, name, dies):
    body = CALLS[name].format(**_setup(k, name))
    code = law(f"Writer {name}", CALL_MODULE + "\ndef after_post(p, chain):\n    state['ran'] = 1\n    " + body + "\n    state['done'] = 1\n"
               + "    public_note.append(1)\n" + (LOOP if dies else ""))
    code = code.replace('intent = "test"\n', 'intent = "test"\npublic_note = []\n')
    lid = enact(k, code)
    if name == "clear_obligations":                                  # an obligation of this law's to clear
        a, b, _ = workers(k)
        k.apply("guard_bind", guard=a, agent=b, fee=None, lid=lid)
    return lid


@pytest.mark.parametrize("name", WRITERS)
def test_a_killed_invocation_leaves_no_trace_whatever_it_wrote(name):
    """Generic: each writer, run inside a hook that then dies (per-call gas), leaves the world, the events, module data and side
    state exactly as before the invocation, except the hook_aborted record and the dying law's flag."""
    jur = name in JUR_ONLY
    # the same call, committed: it must change something, or this test proves nothing
    k = world(jur=jur)
    lid = _writer_law(k, name, dies=False)
    before = image(k)
    out, ab = run_hook(k, lid)
    assert ab is None and out is None
    after = image(k)
    assert k.w["laws"][lid]["state"].get("done") == 1, (name, k.w["laws"][lid]["status"], events(k, "law_error")[-1:])
    changed = {x for x in before["w"] if before["w"][x] != after["w"].get(x)} - {"laws"}
    assert changed or len(after["events"]) > len(before["events"]) or after["fnreg"] != before["fnreg"], name
    # killed
    k = world(jur=jur)
    lid = _writer_law(k, name, dies=True)
    before = image(k)
    out, ab = run_hook(k, lid)
    assert out is D.DEAD and ab is not None and ab["kind"] == "gas_call" and ab["law"] == lid
    after = image(k)
    flags = after["w"]["laws"][lid].pop("flags")
    assert flags == [{"round": k.r, "kind": "gas_call", "cascade": "kernel:test"}]
    new = after["events"][len(before["events"]):]
    assert [e["type"] for e in new] == ["hook_aborted", "law_flagged"]
    assert new[0]["vis"] == "monitor" and ab["events_dropped"] == sum(ab["dropped"].values())
    after["events"] = after["events"][:len(before["events"])]
    assert after == before, name


# ------------------------------------------------------------------ nested invocations roll back independently
def _nested(k, inner_dies, outer_dies):
    a, b, _ = workers(k)
    inner = enact(k, law("Inner", "seen = []\ndef before_move(p, chain):\n    state['saw'] = p['qty']\n    seen.append(p['qty'])\n"
                                  "    gazette('inner saw a move')\n" + (LOOP if inner_dies else "    return None\n")))
    outer = enact(k, law("Outer", f"def after_post(p, chain):\n    state['x'] = 1\n    move('{a}', '{b}', 'timber', 1)\n"
                                  "    state['moved'] = 1\n" + (LOOP if outer_dies else "")))
    return a, b, inner, outer


def test_an_inner_death_is_undone_and_the_outer_invocation_goes_on():
    k = world()
    a, b, inner, outer = _nested(k, inner_dies=True, outer_dies=False)
    ta, tb = k.bal(a, "timber"), k.bal(b, "timber")
    out, ab = run_hook(k, outer)
    assert out is None and ab["law"] == inner and ab["hook"] == "before_move" and ab["kind"] == "gas_call"
    assert ab["dropped"] == {"gazette": 1} and f"law:{inner}" in ab["undone"]
    assert k.w["laws"][inner]["state"] == {} and k.ns[inner]["seen"] == []          # state and module data undone
    assert [f["kind"] for f in k.w["laws"][inner]["flags"]] == ["gas_call"]         # its flag stands
    assert k.w["laws"][outer]["state"] == {"x": 1, "moved": 1}                     # the outer invocation's changes stand
    assert (k.bal(a, "timber"), k.bal(b, "timber")) == (ta - 1, tb + 1)              # the dead before-hook abstained
    assert not any(e["type"] == "gazette" and "inner saw" in json.dumps(e["data"]) for e in k.events)


def test_an_outer_death_undoes_its_committed_inner_invocations():
    k = world()
    a, b, inner, outer = _nested(k, inner_dies=False, outer_dies=True)
    before = image(k)
    out, ab = run_hook(k, outer)
    assert out is D.DEAD and ab["law"] == outer and ab["dropped"].get("move") == 1 and ab["dropped"].get("gazette") == 1
    after = image(k)
    after["w"]["laws"][outer].pop("flags")
    new = after["events"][len(before["events"]):]
    assert [e["type"] for e in new] == ["hook_aborted", "law_flagged"]
    after["events"] = after["events"][:len(before["events"])]
    assert after == before                                               # the inner law's committed state went with it


def test_a_penalty_inside_a_rolled_back_invocation_stands():
    """Both die: the outer rollback undoes the inner's changes but replays its flag (a law cannot shed its flags by dying inside
    another law's hook)."""
    k = world()
    a, b, inner, outer = _nested(k, inner_dies=True, outer_dies=True)
    n = len(k.events)
    run_hook(k, outer)
    assert [(e["type"], e["data"].get("law")) for e in k.events[n:]] == [("hook_aborted", outer), ("law_flagged", inner),
                                                                         ("law_flagged", outer)]
    assert [f["kind"] for f in k.w["laws"][inner]["flags"]] == ["gas_call"]
    assert [f["kind"] for f in k.w["laws"][outer]["flags"]] == ["gas_call"]
    assert k.w["laws"][inner]["state"] == {} and k.ns[inner]["seen"] == [] and k.w["laws"][outer]["state"] == {}


# ------------------------------------------------------------------ a LawError, public, references, law.atomic false
def test_a_runtime_error_rolls_back_in_place_and_suspends_the_law():
    k = world()
    a, b, _ = workers(k)
    ta = k.bal(a, "timber")
    lid = enact(k, law("Oops", f"def after_post(p, chain):\n    move('{a}', '{b}', 'timber', 1)\n    public['n'] = 1\n"
                               "    state['n'] = 1\n    x = 1 / 0\n"))
    pub = k.w["laws"][lid]["public"]
    agent = k.w["agents"][a]
    out, ab = run_hook(k, lid)
    assert out is D.DEAD and ab["kind"] == "error" and ab["dropped"] == {"move": 1}
    assert k.bal(a, "timber") == ta and k.w["laws"][lid]["state"] == {} and pub == {}
    assert k.w["laws"][lid]["public"] is pub and k.ns[lid]["public"] is pub and k.ns[lid]["state"] is k.w["laws"][lid]["state"]
    assert k.w["agents"][a] is agent                                     # restored in place: references stay valid
    assert k.w["laws"][lid]["status"] == "suspended" and "division by zero" in events(k, "law_error")[-1]["data"]["error"]


def test_law_atomic_false_keeps_p3_1_semantics():
    k = world(atomic=False)
    a, b, _ = workers(k)
    ta = k.bal(a, "timber")
    lid = enact(k, law("Spin", f"def after_post(p, chain):\n    move('{a}', '{b}', 'timber', 1)\n    state['n'] = 1\n" + LOOP))
    out, ab = run_hook(k, lid)
    assert out is D.DEAD and ab is None and not events(k, "hook_aborted")
    assert k.bal(a, "timber") == ta - 1 and k.w["laws"][lid]["state"] == {"n": 1}   # its earlier changes stand
    assert D.atomic(world()) and D.atomic(world(atomic=True))
    v1 = Kernel(generator.generate(S.apply_overrides(S.load("E4"), ["shared_archive.enabled=false"]), 1))
    assert not D.atomic(v1) and "_journal" not in v1.__dict__


def test_a_dying_after_hook_through_the_cascade():
    """End to end: an after_move hook that pays and then dies, from an agent's transfer: everything it caused is undone, its queued
    reactions are dropped, the transfer itself stands."""
    k = world()
    a, b, c = workers(k)
    ledger = enact(k, law("Ledger", "def after_move(p, chain):\n    state['n'] = state.get('n', 0) + 1\n"))
    spin = enact(k, law("Spin", f"def after_move(p, chain):\n    if p['why'] == 'transfer':\n"
                                f"        move('{a}', '{c}', 'timber', 0.5)\n        state['paid'] = 1\n"
                                "        while True:\n            pass\n"))
    ta, tb, tc = (k.bal(x, "timber") for x in (a, b, c))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert (k.bal(a, "timber"), k.bal(b, "timber"), k.bal(c, "timber")) == (ta - 1, tb + 1, tc)
    assert k.w["laws"][spin]["state"] == {} and k.w["laws"][ledger]["state"]["n"] == 1
    ab = events(k, "hook_aborted")[-1]
    assert ab["vis"] == "monitor" and ab["data"]["law"] == spin and ab["data"]["dropped"] == {"move": 1}
    assert events(k, "cascade_halted")[-1]["data"]["dropped"] == 1


# ------------------------------------------------------------------ determinism and replay with deaths
SPIN_LAW = '''title = "Spin Toll"
intent = "Takes a toll on every transfer, then spins forever (a test fixture: every invocation dies)."

def after_move(p, chain):
    if p["why"] == "transfer":
        move(p["src"], treasury(), p["item"], 0.1)
        state["n"] = state.get("n", 0) + 1
        while True:
            pass
'''


@pytest.fixture
def spin_law():
    from charter import library as LB
    LB.LIB["Spin Toll"] = {"name": "Spin Toll", "category": "law_v2_test", "code": SPIN_LAW}
    yield
    LB.LIB.pop("Spin Toll", None)


def _spin_case(tmp, name):
    from charter import agents as AG, runner
    sp = S.apply_overrides(S.load("E4"), ["rounds=3", "turns=simultaneous", "shared_archive.enabled=false", "law.v2=true",
                                          "law.gas.flag_limit=100", "start_laws=" + json.dumps(["Spin Toll"])])
    inst = generator.generate(sp, 1)
    inst["run_id"] = name
    return runner.run(inst, AG.ScriptedPolicy(1), tmp / name, log=lambda *a: None)


def test_determinism_and_replay_with_aborted_invocations(tmp_path, monkeypatch, spin_law):
    from charter import __main__ as M
    a = _spin_case(tmp_path, "a")
    b = _spin_case(tmp_path, "b")
    for f in ("events.jsonl", "snapshots.json"):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f
    evs = [json.loads(x) for x in (a / "events.jsonl").read_text().splitlines()]
    aborted = [e for e in evs if e["type"] == "hook_aborted"]
    assert aborted and all(e["data"]["dropped"] == {"move": 1} and e["vis"] == "monitor" for e in aborted)
    monkeypatch.setattr(M, "load_env", lambda: None)
    M.main(["replay", str(a), "--out", str(tmp_path / "rep")])
    for f in ("events.jsonl", "snapshots.json"):
        assert (tmp_path / "rep" / f).read_bytes() == (a / f).read_bytes(), f
