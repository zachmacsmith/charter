"""Review 14 WP-D (P4.6 done properly; charter/institutions.py): one institution store behind `institutions.unified`.

The same scenarios run with the flag off and on give the same agent-visible outcomes (action replies, events, holdings, rights,
snapshots) for founding, joining, leaving (exit as law, D-26), offices, companies (incorporation) and dissolution, and the views
over the unified store equal the old stores. Whole scripted runs (the jurisdictions and contracts golden cases) are compared file by
file: identical, except the routed contract dissolution's cause chains. Off, nothing is written (the goldens prove the bytes)."""
from __future__ import annotations

import copy
import json
import pickle
import re
import types

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import agents as AG
from charter import generator, runner
from charter import institutions as I
from charter import jurisdictions as J
from charter import spec as S
from charter.kernel import Kernel

import charter_golden_cases as GC

ON = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]
FLAG = "institutions.unified=true"


# ------------------------------------------------------------------ helpers
def world(unified, preset="jurisdictions_pilot", extra=()):
    """Jurisdictions and contracts both on (law.v2), J0 seeded."""
    sets = ["rounds=8", "shared_archive.enabled=false", "hidden.enabled=false", "turns=sequential", *ON, *extra]
    if unified:
        sets.append(FLAG)
    inst = generator.generate(S.apply_overrides(S.load(preset), sets), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    for a in people(k):
        k._add(a, "grain", 5)                                           # something to fund, deposit and be levied on leaving
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def code(body, title="Rules"):
    return f'title = "{title}"\nintent = "test"\n\n{body.strip()}\n'


def enact(k, src, jid=None):
    lid = k.new_law(src, "a_test")
    if jid is not None and jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid


def next_round(k):
    k.end_round()
    k.start_round()


class Log:
    """Every action's reply (or its refusal), as the agent saw it."""

    def __init__(self, k):
        self.k, self.out = k, []

    def __call__(self, aid, _action, **args):
        try:
            r = A.act(self.k, aid, _action, args)
        except A.ActionError as e:
            r = f"ERROR {e}"
        self.out.append((aid, _action, r))
        return r


def _nocause(x):
    if isinstance(x, dict):
        return {a: _nocause(v) for a, v in x.items() if a != "cause"}
    if isinstance(x, list):
        return [_nocause(v) for v in x]
    return x


def outcome(k, log):
    """What agents can see or hold: replies, events (cause chains aside: routing adds a frame), holdings, rights, every agent's
    feed, the old stores (the unified one projected back)."""
    ag = k.w["agents"]
    if I.unified(k):
        stores = I.legacy_stores(k)
        assert "jurisdictions" not in k.w and "assoc" not in k.w["contracts"]
    else:
        stores = {"jurisdictions": copy.deepcopy(k.w["jurisdictions"]), "assoc": copy.deepcopy(k.w["contracts"]["assoc"])}
    return {"replies": log.out, "events": _nocause(json.loads(json.dumps(k.events, default=str))),
            "holdings": {a: dict(v["holdings"]) for a, v in ag.items()}, "rights": {a: sorted(v["rights"]) for a, v in ag.items()},
            "reserves": {i: dict(J.jurs(k)[i]["reserve"]) for i in J.jurs(k)}, "member_of": dict(k.w["jur"]["member"]),
            "feeds": {a: [e["id"] for e in k.events if k.can_see(a, e)] for a in k.roster()},
            "stores": json.loads(json.dumps(stores, default=list))}


def both(scenario):
    """The scenario's outcome with the flag off and on (it must be the same)."""
    res = []
    for unified in (False, True):
        k = world(unified)
        log = Log(k)
        scenario(k, log)
        res.append(outcome(k, log))
    return res


# ------------------------------------------------------------------ scenarios
def s_polity(k, act):
    """Secret founding, invitations, a pledge and an unpledge, declaration; joining from J0 (ballot), exit as law (D-26: J0's
    on_exit seizes), expel by law, a hidden one dissolved by its last unpledge (refund)."""
    a, b, c, d, e = people(k)[:5]
    enact(k, code('''
def on_exit(agent):
    move(agent, "reserve", "timber", 1)
''', "Exit Levy"))
    jid = re.search(r"J\d+", act(a, "found", name="Free Camp")).group()
    act(a, "invite", jurisdiction=jid, agent=b)
    act(a, "invite", jurisdiction=jid, agent=c)
    act(b, "join", jurisdiction=jid)
    act(c, "join", jurisdiction=jid)
    act(c, "leave", jurisdiction=jid)                                   # unpledge from a hidden one
    act(a, "fund", jurisdiction=jid, item="timber", qty=6)
    act(a, "declare", jurisdiction=jid)
    next_round(k)
    act(d, "join", jurisdiction=jid)                                    # the members vote (ballot)
    for v in (a, b):
        bid = next((x for x, bb in k.w["ballots"].items() if bb.get("jurisdiction") == jid and bb["status"] == "open"), None)
        if bid:
            act(v, "vote", ballot=bid, choice="yes")
    next_round(k)
    act(b, "leave")                                                    # J1 has no exit law: free
    act(e, "leave")                                                    # J0's Exit Levy takes a grain on the way out
    next_round(k)
    lid = enact(k, code('''
def on_round_start(r):
    for m in members():
        if m == "%s":
            expel(m)
''' % d, "Expulsion"), jid)
    next_round(k)
    next_round(k)
    x = re.search(r"J\d+", act(c, "found", name="Cell")).group()
    act(c, "fund", jurisdiction=x, item="timber", qty=2)
    act(c, "leave", jurisdiction=x)                                    # its last member: dissolved, treasury refunded
    act(d, "found", name="Bad", laws=["this is not code"])             # a failed founding leaves no record
    assert lid


OFFICE = code('''
def on_enact():
    create_right("treasurer")
    public["act"] = define_action("treasurer", "pay", pay)

def appoint(m):
    return grant(m, "treasurer")

def pay(agent, to, qty):
    move(treasury(), to, "grain", qty)
    return "paid " + str(qty)
''', "Offices")


def s_association(k, act):
    """Founding (code and template), joining (open and closed), escrow, offices (rights and a defined action), leaving (exit kept:
    escrow back), expel, the last member's exit dissolving it (wound up among the last members), a failed founding."""
    a, b, c, d = people(k)[:4]
    r = act(a, "create_contract", name="Office", code=OFFICE)
    cid = re.search(r"A\d+", r).group()
    club = re.search(r"A\d+", act(b, "create_contract", name="Club", template="club", params={"DUES": 1})).group()
    act(b, "join_contract", contract=cid)
    act(c, "join_contract", contract=club)
    act(b, "deposit_escrow", contract=cid, item="grain", qty=2)
    lid = AC.assocs(k)[cid]["laws"][0]
    k.api_for(lid)["grant"](b, "treasurer")
    k._add(f"assoc:{cid}", "grain", 5)
    act(b, "invoke", action=f"{cid}.pay", args=[c, 2])
    act(a, "invoke", action=f"{cid}.pay", args=[c, 1])                 # holds no treasurer right
    act(d, "create_contract", name="Broken", code="not code at all")
    next_round(k)
    act(b, "leave_contract", contract=cid)
    next_round(k)
    act(a, "leave_contract", contract=cid)                             # the last member: dissolved, wound up
    act(b, "leave_contract", contract=club)
    act(c, "leave_contract", contract=club)
    next_round(k)
    next_round(k)


def s_company(k, act):
    """A company incorporated under a declared polity: registration fee, parent hooks, wind-up escheat to the parent."""
    a, b, f, m = people(k)[:4]
    jid = re.search(r"J\d+", act(f, "found", name="Delaware")).group()
    act(f, "invite", jurisdiction=jid, agent=m)
    act(m, "join", jurisdiction=jid)
    act(f, "declare", jurisdiction=jid)
    next_round(k)
    enact(k, code('''
def on_enact():
    company_rule("registration_fee", {"grain": 1})
    company_rule("wind_up", ["parent"])

def before_create_contract(p, chain):
    if p["under"] == jurisdiction() and p["template"] == "club":
        return {"block": True, "reason": "only companies may register here"}
''', "Companies Act"), jid)
    k._add(a, "grain", 3 - k.bal(a, "grain"))
    act(a, "create_contract", name="X", template="club", under=jid)   # refused by the parent's law
    cid = re.search(r"A\d+", act(a, "create_contract", name="Co", template="company", under=jid)).group()
    act(b, "join_contract", contract=cid)
    k._add(f"assoc:{cid}", "grain", 3)
    next_round(k)
    act(a, "leave_contract", contract=cid)
    act(b, "leave_contract", contract=cid)
    next_round(k)                                                      # dissolved; the treasury escheats to the parent


@pytest.mark.parametrize("scenario", [s_polity, s_association, s_company], ids=lambda f: f.__name__)
def test_the_same_scenario_gives_the_same_outcomes_with_the_flag_off_and_on(scenario):
    off, on = both(scenario)
    for key in off:
        assert off[key] == on[key], key


def test_scenarios_exercise_what_they_claim():
    off, _ = both(s_association)
    types_ = {e["type"] for e in off["events"]}
    assert {"contract_created", "contract_joined", "contract_left", "contract_dissolved", "contract_wound_up"} <= types_
    off, _ = both(s_polity)
    types_ = {e["type"] for e in off["events"]}
    assert {"jur_founded", "jur_pledged", "jur_left_hidden", "jur_declared", "jur_left", "jur_joined"} <= types_
    off, _ = both(s_company)
    assert any(e["type"] == "contract_wound_up" and e["data"].get("escheat") for e in off["events"])


# ------------------------------------------------------------------ the store and its views
def test_one_store_holds_both_kinds_and_the_old_stores_are_views():
    k = world(True)
    a, b = people(k)[:2]
    jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Free Camp"})).group()
    cid = re.search(r"A\d+", A.act(k, b, "create_contract", {"name": "Club", "template": "club"})).group()
    st = k.w["institutions"]
    assert list(st) == ["J0", jid, cid] and "jurisdictions" not in k.w and "assoc" not in k.w["contracts"]
    for rec in st.values():
        assert {"id", "kind", "name", "founder", "founded_round", "status", "published", "members", "parent", "treasury",
                "reserve"} <= set(rec)
    assert st[jid]["status"] == "forming" and st[jid]["published"] == "members" and st[jid]["members"] == [a]
    assert st[cid]["status"] == "active" and st[cid]["published"] == "public" and st[cid]["parent"] is None
    assert dict(J.jurs(k)) == {"J0": st["J0"], jid: st[jid]} and dict(AC.assocs(k)) == {cid: st[cid]}
    assert J.jurs(k)[jid] is st[jid]                                   # a view: the records themselves
    with pytest.raises(TypeError):
        J.jurs(k)["J9"] = {}                                           # read-only: writes go through institutions.add
    assert J.st(st[jid]) == "hidden" and J.secret(st[jid])
    A.act(k, a, "declare", {"jurisdiction": jid})
    next_round(k)
    assert st[jid]["status"] == "active" and st[jid]["published"] == "public" and J.st(st[jid]) == "declared"
    assert st[jid]["members"] == [a] == J.members(k, jid)


def test_views_equal_the_old_stores_after_a_scenario():
    off, on = both(s_polity)
    assert off["stores"] == on["stores"]
    off, on = both(s_association)
    assert off["stores"] == on["stores"] and off["stores"]["assoc"]


def test_helpers_answer_the_same_in_both_representations():
    for unified in (False, True):
        k = world(unified)
        a, b, c = people(k)[:3]
        jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Free Camp"})).group()
        cid = re.search(r"A\d+", A.act(k, b, "create_contract", {"name": "Club", "template": "club"})).group()
        assert I.kind_of(k, "J0") == "polity" and I.kind_of(k, jid) == "polity" and I.kind_of(k, cid) == "association"
        assert I.kind_of(k, "A99") is None and I.get(k, "A99") is None and I.get(k, None) is None
        assert I.get(k, cid)["name"] == "Club" and I.get(k, jid)["founder"] == a
        assert I.is_member(k, cid, b) and not I.is_member(k, cid, c)
        assert I.is_member(k, jid, a) and not I.is_member(k, jid, b)    # a forming polity: its pledged members
        assert I.is_member(k, "J0", c) and I.is_member(k, "J0", a)       # still J0's declared member while J1 forms
        assert I.status(k, jid) == "forming" and I.published(k, jid) == "members"
        assert I.status(k, cid) == "active" and I.published(k, cid) == "public" and I.status(k, "J0") == "active"
        assert set(I.all_(k)) == {"J0", jid, cid}
        assert I.laws(k, cid) == AC.assocs(k)[cid]["laws"]


def test_helpers_with_jurisdictions_off():
    k = world(False, preset="E2")
    a = people(k)[0]
    assert I.kind_of(k, "J0") == "polity" and I.is_member(k, "J0", a) and I.status(k, "J0") == "active"
    assert I.get(k, "J0") is None and I.members(k, "J1") == []


# ------------------------------------------------------------------ one path
def test_found_founds_an_association_given_code_or_a_template_under_the_flag():
    k = world(True)
    a = people(k)[0]
    r = A.act(k, a, "found", {"name": "Club", "template": "club"})
    cid = re.search(r"A\d+", r).group()
    assert I.kind_of(k, cid) == "association" and AC.assocs(k)[cid]["template"] == "club"
    r2 = A.act(k, a, "found", {"name": "Own", "laws": [code("def on_round_end(r):\n    return None")], "admission": "closed"})
    assert I.kind_of(k, re.search(r"A\d+", r2).group()) == "association"     # laws are its code once it is an association
    k2 = world(False)
    with pytest.raises(A.ActionError, match="unexpected keyword argument 'template'"):
        A.act(k2, people(k2)[0], "found", {"name": "Club", "template": "club"})   # off: today's refusal


def test_found_primitive_takes_kind_none_under_the_flag():
    k = world(True)
    a = people(k)[0]
    out = k.apply("found", agent=a, polity="J1", kind=None, members=[a], name="Plain")
    assert out.ok and I.kind_of(k, "J1") == "polity" and I.published(k, "J1") == "members"
    k2 = world(False)
    with pytest.raises(ValueError, match="no kind None"):
        k2.apply("found", agent=a, polity="J1", kind=None, members=[a], name="Plain")


def test_contract_dissolution_is_routed_and_hooks_see_it():
    for unified in (False, True):
        k = world(unified)
        a, b = people(k)[:2]
        enact(k, code('''
def after_dissolve(p, chain):
    public.setdefault("seen", []).append([p["polity"], p["kind"]])
''', "Watcher"))
        cid = re.search(r"A\d+", A.act(k, a, "create_contract", {"name": "Club", "template": "club"})).group()
        A.act(k, a, "leave_contract", {"contract": cid})
        next_round(k)
        assert AC.assocs(k)[cid]["status"] == "dissolved"
        seen = next(l for l in k.w["laws"].values() if l["title"] == "Watcher")
        assert k.ns[seen["id"]]["public"].get("seen", []) == ([[cid, "association"]] if unified else [])


def test_a_block_cannot_keep_a_memberless_contract_alive():
    k = world(True)
    a = people(k)[0]
    cid = re.search(r"A\d+", A.act(k, a, "create_contract", {"name": "Sticky", "code": code('''
def before_dissolve(p, chain):
    return {"block": True, "reason": "never"}
''')})).group()
    A.act(k, a, "leave_contract", {"contract": cid})
    next_round(k)
    assert AC.assocs(k)[cid]["status"] == "dissolved" and any(e["type"] == "contract_dissolved" for e in k.events)


def test_membership_takes_one_path_and_keeps_polity_members():
    k = world(True)
    a, b = people(k)[:2]
    calls = []
    real = I.change

    def spy(k_, op, *args, **kw):
        calls.append((op, kw.get("iid")))
        return real(k_, op, *args, **kw)

    I.change = spy
    try:
        jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Free Camp"})).group()
        A.act(k, a, "invite", {"jurisdiction": jid, "agent": b})
        A.act(k, b, "join", {"jurisdiction": jid})
        cid = re.search(r"A\d+", A.act(k, a, "create_contract", {"name": "Club", "template": "club"})).group()
        A.act(k, b, "join_contract", {"contract": cid})
        A.act(k, a, "declare", {"jurisdiction": jid})
        next_round(k)
    finally:
        I.change = real
    assert ("join", jid) in calls and ("join", cid) in calls and ("leave", "J0") in calls
    assert k.w["institutions"][jid]["members"] == J.members(k, jid) == [x for x in k.roster() if x in (a, b)]
    assert k.w["institutions"]["J0"]["members"] == J.members(k, "J0") and a not in J.members(k, "J0")


# ------------------------------------------------------------------ state: dry runs, checkpoints
def test_dry_runs_and_checkpoints_keep_one_store():
    k = world(True)
    a, b = people(k)[:2]
    cid = re.search(r"A\d+", A.act(k, b, "create_contract", {"name": "Club", "template": "club"})).group()
    diff = k.dry_run(k.new_law(code("def on_round_end(r):\n    return None", "Quiet"), a))   # rolled back: a copy of the store
    assert isinstance(diff, list)
    assert AC.assocs(k)[cid] is k.w["institutions"][cid]
    st = pickle.loads(pickle.dumps(k.checkpoint_state()))
    w = st["w"]
    assert w["institutions"][cid]["members"] == [b] and "assoc" not in w["contracts"]
    k2 = Kernel(k.inst)
    k2.restore_state(st)
    assert AC.assocs(k2)[cid] is k2.w["institutions"][cid] and I.legacy_stores(k2) == I.legacy_stores(k)


# ------------------------------------------------------------------ whole runs: the golden cases with the flag on
def _files(run_dir):
    d = run_dir
    out = {"events": [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()],
           "snapshots": json.loads((d / "snapshots.json").read_text()),
           "ground_truth": json.loads((d / "ground_truth.json").read_text())}
    return out


def _run_case(name, tmp, unified):
    preset, seed, sets = GC.CASES[name]
    sets = list(sets) + ["shared_archive.enabled=false"] + ([FLAG] if unified else [])
    inst = generator.generate(S.apply_overrides(S.load(preset), sets), seed)
    inst["run_id"] = f"golden_{name}"
    return runner.run(inst, AG.ScriptedPolicy(seed), tmp / ("on" if unified else "off") / name, log=lambda *a: None)


@pytest.mark.parametrize("name", ["society_small_4", "contracts_small"])
def test_golden_cases_run_the_same_with_the_flag_on(name, tmp_path):
    off = _files(_run_case(name, tmp_path, False))
    on = _files(_run_case(name, tmp_path, True))
    assert off["snapshots"] == on["snapshots"]
    assert off["ground_truth"] == on["ground_truth"]
    if name == "contracts_small":                                       # the routed dissolution adds its primitive's cause frame
        assert any(e["type"] == "contract_dissolved" for e in off["events"])
        assert _nocause(off["events"]) == _nocause(on["events"])
        assert off["events"] != on["events"]
    else:
        assert off["events"] == on["events"]


def test_jurisdictions_scripted_dry_run_runs_the_same_with_the_flag_on(tmp_path):
    res = []
    for unified in (False, True):
        sets = ["rounds=5", "shared_archive.enabled=false", "hidden.enabled=false", "jurisdictions.start=nature"] + \
               ([FLAG] if unified else [])
        inst = generator.generate(S.apply_overrides(S.load("jurisdictions_pilot"), sets), 2)
        inst["run_id"] = "unified"
        res.append(_files(runner.run(inst, AG.ScriptedPolicy(2), tmp_path / str(unified), log=lambda *a: None)))
    assert res[0] == res[1]
    assert any(e["type"] == "jur_declared" for e in res[0]["events"])


def test_the_flag_is_in_the_schema():
    from charter import schema as SC
    sp = S.apply_overrides(S.load("E2"), [FLAG])
    assert SC.validate(sp) == [] and I.unified_spec(sp) and not I.unified_spec(S.load("E2"))
    assert isinstance(I.view(types.SimpleNamespace(w={}), "polity"), type(I._EMPTY))
