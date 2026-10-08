"""P3.7 (compel visibility, D-5) and P3.8 (gas billed to treasuries, D-12): charter/dispatch/notify.py and billing.py. Under law.v2 a
law-caused change of every primitive whose row has compel_vis "parties" reaches its agent parties (a `compelled` event, or the row's
own event); law.gas_price bills each account's gas at round end. Offline: no model calls."""
from __future__ import annotations

import json
import re

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import agents as AG
from charter import dispatch as D
from charter import generator
from charter import primitives as PR
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel


def world(v2=True, preset="E4", sets=(), law=None, seed=1):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets])
    if v2:
        sp["law"] = {"v2": True, **(law or {})}
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def enact(k, code, jid=None):
    lid = k.new_law(code, "constitution")
    if jid:
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def agents(k, n=3, cls=None):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer", "observer") and (cls is None or k.cls_of(a) == cls)][:n]


def compelled(k, prim=None):
    return [e for e in k.events if e["type"] == "compelled" and (prim is None or e["data"]["primitive"] == prim)]


def run(k, lid, fn, *args):
    """Call a law's function as its hook would be: inside a root frame (a cascade), in the law's own frame (Kernel.call)."""
    with k.cause("kernel", "test", root=True):
        return k.call(lid, k.ns[lid][fn], *args)


def seen_by(k, e):
    return sorted(a for a in k.w["agents"] if k.can_see(a, e))


@pytest.fixture
def k():
    return world()


# ------------------------------------------------------------------ the registry side
def test_notify_is_every_live_parties_row_with_a_compel_face():
    rows = {p.name for p in PR.PRIMITIVES.values() if p.status == "live" and p.compel and p.compel_vis == "parties"}
    assert set(D.NOTIFY) == rows
    assert {"move", "mint", "burn", "set_title", "guard_bind", "guard_release", "subscribe"} <= rows
    assert all(PR.PRIMITIVES[n].legacy_vis in (None, "monitor") for n in rows)


def test_notify_parties_is_a_spec_key_following_law_v2():
    assert SC.validate(S.apply_overrides(S.load("E4"), ["law.v2=true", "law.notify_parties=false"])) == []
    assert D.notify_on(world()) and not D.notify_on(world(v2=False))
    assert not D.notify_on(world(law={"notify_parties": False}))
    assert not D.notify_on(world(v2=False, sets=["law.notify_parties=true"]))     # never without law.v2


# ------------------------------------------------------------------ one test per compel_vis="parties" primitive
def test_move_by_law_notifies_both_parties(k):
    a, b, _ = agents(k)
    k.w["reserve"]["timber"] = 10.0
    lid = enact(k, law("Fines", f"def fine_now(a):\n    fine(a, 'timber', 2)\ndef pay(b):\n    move('reserve', b, 'timber', 3)\n"))
    run(k, lid, "fine_now", a)
    e = compelled(k, "move")[-1]
    assert e["vis"] == [a] and e["agent"] is None                    # the reserve is no agent: only a is told
    assert e["data"] == {"primitive": "move", "law": lid, "hook": "fine_now", "why": "fine", "parties": [a],
                         "change": {"src": a, "dst": "reserve", "item": "timber", "qty": 2.0, "why": "fine"}}
    assert AG.render_event(k, e, a).endswith(f"compelled by law {lid} (fine_now): moved 2 timber from you to reserve (why: fine)")
    run(k, lid, "pay", b)
    e = compelled(k, "move")[-1]
    assert e["vis"] == [b] and e["data"]["change"]["dst"] == b and e["data"]["why"] == f"law:{lid}"
    n = len(compelled(k))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # an agent's own move: no law, no notice
    k.apply("move", src=a, dst=b, item="timber", qty=1.0, why="bookkeeping")      # the kernel's: none either
    assert len(compelled(k)) == n


def test_move_between_two_agents_reaches_both(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Levy", f"def levy(a, b):\n    move(a, b, 'timber', 1)\n"))
    run(k, lid, "levy", a, b)
    e = compelled(k, "move")[-1]
    assert e["vis"] == [a, b] and seen_by(k, e) == sorted([a, b])


def test_a_move_that_moves_nothing_notifies_nobody(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Levy", f"def levy(a, b):\n    move(a, b, 'timber', 1)\n"))
    k.w["agents"][a]["holdings"]["timber"] = 0.0
    n = len(compelled(k))
    run(k, lid, "levy", a, b)
    assert len(compelled(k)) == n


def test_a_laws_own_charge_is_told_once_by_law_charged(k):
    a, b, _ = agents(k)
    enact(k, law("Toll", "def before_move(p, chain):\n    if p['why'] == 'transfer':\n        return 2\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 5})
    assert [e["data"]["payer"] for e in k.events if e["type"] == "law_charged"] == [a] and not compelled(k)


def test_mint_by_law_notifies_the_recipient(k):
    a, _, _ = agents(k)
    lid = enact(k, law("Shells", "def on_enact():\n    create_currency('shell', False)\ndef pay(a):\n    mint('shell', 5, a)\n"))
    assert not compelled(k)                                          # create_currency: no agent party
    run(k, lid, "pay", a)
    e = compelled(k, "mint")[-1]
    assert e["vis"] == [a] and e["data"]["change"] == {"currency": "shell", "qty": 5.0, "to": a} and e["data"]["law"] == lid
    assert "minted 5 shell to you" in AG.render_event(k, e, a)


def test_burn_by_law_notifies_the_holder(k):
    a, _, _ = agents(k)
    lid = enact(k, law("Shells", "def on_enact():\n    create_currency('shell', False)\ndef pay(a):\n    mint('shell', 5, a)\n"
                                 "def take(a):\n    burn('shell', 2, a)\n"))
    run(k, lid, "pay", a)
    run(k, lid, "take", a)
    e = compelled(k, "burn")[-1]
    assert e["vis"] == [a] and e["data"]["change"] == {"currency": "shell", "qty": 2.0, "frm": a}
    assert "burned 2 shell held by you" in AG.render_event(k, e, a)


def test_set_title_by_law_notifies_the_agent(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Honours", "def honour(a):\n    title(a, 'Hero of the Commons')\n"))
    run(k, lid, "honour", a)
    e = compelled(k, "set_title")[-1]
    assert e["vis"] == [a] and e["data"]["change"] == {"agent": a, "text": "Hero of the Commons"}
    assert k.w["agents"][a]["title"] == "Hero of the Commons"
    assert "set your title to 'Hero of the Commons'" in AG.render_event(k, e, a)
    assert not k.can_see(b, e)


def _conflict():
    return world(preset="conflict_pilot", sets=["conflict.assassin.present_prob=0", "conflict.start={}", "conflict.grace=0"])


def test_guard_bind_by_law_notifies_guard_and_guarded():
    k = _conflict()
    g, a = agents(k, 2, cls="worker")
    lid = enact(k, law("Levy of guards", f"def on_enact():\n    oblige_guard('{g}', '{a}')\n"))
    e = compelled(k, "guard_bind")[-1]
    assert e["vis"] == [g, a] and e["data"]["change"] == {"guard": g, "agent": a, "fee": None}
    assert e["data"]["law"] == lid and e["data"]["hook"] == "on_enact"
    assert "obliged you to guard " + a in AG.render_event(k, e, g)


def test_guard_release_by_law_notifies_every_released_pair():
    k = _conflict()
    g, a, b = agents(k, 3, cls="worker")
    lid = enact(k, law("Levy of guards", f"def on_enact():\n    oblige_guard('{g}', '{a}')\n    oblige_guard('{a}', '{b}')\n"
                                         "def stop():\n    clear_obligations()\n"))
    run(k, lid, "stop")
    e = compelled(k, "guard_release")[-1]
    assert e["vis"] == [g, a, b] and e["data"]["change"] == {"released": [[g, a], [a, b]]} and e["data"]["why"] == "law"
    assert k.w["conflict"]["obligations"].get(lid) is None
    assert f"released the guard obligations {g} guarding you, you guarding {b}" in AG.render_event(k, e, a)
    run(k, lid, "stop")                                              # nothing left to release: nobody to tell
    assert len(compelled(k, "guard_release")) == 1


def test_subscribe_by_law_notifies_the_subscriber():
    k = world(preset="media2_pilot")
    m = k.w["media"]
    o = next(x for x in m["outlets"].values() if not x.get("official") and x["status"] == "open")
    a = next(x for x in agents(k, 20) if x != o["editor"])
    m["subs"][a] = []
    lid = enact(k, law("Compulsory", f"def force(a):\n    compel_subscription(a, '{o['id']}')\n"))
    run(k, lid, "force", a)
    e = compelled(k, "subscribe")[-1]
    assert e["vis"] == [a] and e["data"]["change"] == {"agent": a, "outlet": o["id"], "on": True} and e["data"]["law"] == lid
    assert f"subscribed you to outlet {o['id']}" in AG.render_event(k, e, a)
    assert any(x["type"] == "compelled_subscription" and x["vis"] == "monitor" for x in k.events)   # the monitor record stays


def test_destroy_caused_by_a_law_notifies_the_owner(k):
    a, _, _ = agents(k)
    lid = enact(k, law("Burner", "def noop():\n    return None\n"))
    with k.cause("kernel", "test", root=True), k.cause("law", lid, hook="raze"):
        k.apply("destroy", owner=a, item="timber", qty=1.0, cause="law")
    e = compelled(k, "destroy")[-1]
    assert e["vis"] == [a] and "destroyed 1 timber held by you" in AG.render_event(k, e, a)


def test_offer_loan_by_law_reaches_the_borrower_by_its_own_event(k):
    a, _, _ = agents(k)
    k.w["reserve"]["timber"] = 50.0
    lid = enact(k, law("Bank", "def on_enact():\n    enable_loans()\ndef lend(a):\n    lend_from_reserve(a, 'timber', 3)\n"))
    run(k, lid, "lend", a)
    e = [x for x in k.events if x["type"] == "loan_offer"][-1]
    assert e["vis"] == [a] and k.can_see(a, e) and not compelled(k)


def test_partyless_rows_tell_nobody(k):
    lid = enact(k, law("Makers", "def on_enact():\n    create_currency('shell', False)\n    create_right('fishing')\n"
                                 "    clause('c', 'no theft', pen)\ndef pen(accused, accuser):\n    return None\n"))
    assert k.w["laws"][lid]["status"] == "active" and not compelled(k)


# ------------------------------------------------------------------ off: law.v2 off, or notify_parties false
@pytest.mark.parametrize("w", [dict(v2=False), dict(law={"notify_parties": False})])
def test_nothing_is_logged_when_notification_is_off(w):
    k = world(**w)
    a, b, _ = agents(k)
    lid = enact(k, law("Fines", "def fine_now(a):\n    fine(a, 'timber', 2)\n    title(a, 'x')\n"))
    run(k, lid, "fine_now", a)
    assert not compelled(k) and k.w["agents"][a]["title"] == "x"


# ------------------------------------------------------------------ redaction (D-18)
def test_a_concealed_party_is_never_named_to_the_other(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Levy", "def levy(a, b):\n    move(a, b, 'timber', 1)\n"))
    with k.concealing(b):
        run(k, lid, "levy", a, b)
    es = compelled(k, "move")
    to_a = next(e for e in es if a in e["vis"])
    to_b = next(e for e in es if b in e["vis"])
    assert to_a["vis"] == [a] and b not in json.dumps(to_a["data"]) and to_a["data"]["change"]["dst"] is None
    assert to_b["vis"] == [b] and to_b["data"]["change"]["dst"] == b       # a party always sees itself
    assert "to someone unnamed" in AG.render_event(k, to_a, a)
    assert all(b not in json.dumps(f) for f in to_a["cause"])         # the chain hides it too (Kernel.log)


def test_the_observer_is_never_named(k):
    k = world(sets=["observer.enabled=true"])
    obs = k.inst["observer"]["id"]
    a, _, _ = agents(k)
    lid = enact(k, law("Levy", "def levy(a, b):\n    move(a, b, 'timber', 1)\n"))
    k.w["agents"][obs]["holdings"]["timber"] = 5.0
    run(k, lid, "levy", obs, a)
    e = next(e for e in compelled(k, "move") if a in e["vis"])
    assert obs not in json.dumps(e["data"])


def _hidden_world():
    sp = ["rounds=6", "hidden.enabled=false", "turns=sequential", "jurisdictions.start=j0"]
    k = world(preset="jurisdictions_pilot", sets=sp)
    k.start_round()
    return k


def test_a_hidden_jurisdictions_law_is_hidden_from_outsiders():
    k = _hidden_world()
    a, x = agents(k, 2)
    jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Shadow"})).group()
    assert k.w["jurisdictions"][jid]["status"] == "hidden" and a in k.w["jurisdictions"][jid]["hidden_members"]
    lid = enact(k, law("Shadow Levy", "def noop():\n    return None\n"))
    k.w["laws"][lid]["jurisdiction"] = jid                           # a law of the hidden jurisdiction (its acts reach only by
    with k.cause("kernel", "test", root=True), k.cause("law", lid, hook="levy"):     # force here: scope_api would refuse them)
        k.apply("move", src=x, dst=a, item="timber", qty=1.0, why=f"law:{lid}")
    es = compelled(k, "move")
    inside = next(e for e in es if a in e["vis"])
    outside = next(e for e in es if x in e["vis"])
    assert inside["vis"] == [a] and inside["data"]["law"] == lid and inside["data"]["hook"] == "levy"
    assert outside["vis"] == [x] and outside["data"]["law"] == "hidden" and "hook" not in outside["data"]
    assert lid not in json.dumps(outside["data"]) and outside["data"]["why"] == "law:hidden"
    assert "compelled by a law of a hidden jurisdiction: moved 1 timber from you to " + a in AG.render_event(k, outside, x)


# ------------------------------------------------------------------ P3.8: gas billing
def _burner(k, jid=None):
    return enact(k, law("Burn", "def after_move(p, chain):\n    n = 0\n    while n < 50:\n        n += 1\n"), jid)


def test_gas_price_is_a_spec_key_needing_law_v2():
    ok = S.apply_overrides(S.load("E4"), ["law.v2=true", 'law.gas_price={"item": "grain", "rate": 0.001}'])
    assert SC.validate(ok) == []
    assert SC.validate(S.apply_overrides(S.load("E4"), ["law.v2=true", 'law.gas_price={"item": "grain", "qty": 0.1, "per": 10000}'])) == []
    bad = SC.validate(S.apply_overrides(S.load("E4"), ['law.gas_price={"item": "grain", "rate": 0.001}']))
    assert any("needs law.v2" in x for x in bad)
    assert SC.validate(S.apply_overrides(S.load("E4"), ["law.v2=true", 'law.gas_price={"item": "grain"}']))
    assert D.gas_price(world()) is None                              # off by default
    assert D.gas_price(world(law={"gas_price": {"item": "grain", "qty": 0.1, "per": 10000}})) == {"item": "grain", "rate": 1e-05}


def test_without_a_gas_price_nothing_is_billed(k):
    a, b, _ = agents(k)
    _burner(k)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert D.bill_gas(k) == [] and "unpaid" not in k.w["law_v2"]
    assert not [e for e in k.events if e["type"] == "gas_billed"]


def test_billing_accounting_for_a_polity_treasury():
    k = world(preset="jurisdictions_pilot", sets=["rounds=6", "hidden.enabled=false", "turns=sequential", "jurisdictions.start=j0"],
              law={"gas_price": {"item": "timber", "rate": 0.001}})
    k.start_round()
    a, b = agents(k, 2)
    jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Port"})).group()
    A.act(k, a, "invite", {"jurisdiction": jid, "agent": b})
    A.act(k, b, "join", {"jurisdiction": jid})
    A.act(k, a, "declare", {"jurisdiction": jid})
    k.end_round()
    k.start_round()
    assert k.w["jur"]["member"][a] == jid == k.w["jur"]["member"][b]
    lid = _burner(k, jid)
    tre = AC.treasury_of(k, jid)
    k._add(tre, "timber", 100.0)
    totals0 = AC.totals(k, held=True)
    for _ in range(3):
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    used = k.w["law_v2"]["account_used"][jid]
    assert used > 0 and k.w["law_v2"]["law_gas"][lid] == used
    t0, r0 = k.bal(tre, "timber"), k.bal("reserve", "timber")
    bills = D.bill_gas(k)
    owed = round(used * 0.001, 6)
    assert [b_ for b_ in bills if b_["account"] == jid] == [{"account": jid, "gas": used, "item": "timber", "owed": owed, "paid": owed}]
    assert k.bal(tre, "timber") == pytest.approx(t0 - owed) and k.bal("reserve", "timber") == pytest.approx(r0 + owed)
    mv = [e for e in k.events if e["type"] == "move" and e["data"]["why"] == "gas"]
    assert mv[-1]["data"] == {"src": tre, "dst": "reserve", "item": "timber", "qty": owed, "why": "gas"}
    assert {"kernel": "gas"} in mv[-1]["cause"]
    assert AC.totals(k, held=True) == pytest.approx(totals0)          # a move: nothing created or destroyed
    assert "unpaid" not in k.w["law_v2"] and not [e for e in k.events if e["type"] == "account_out_of_gas"]


def test_an_account_that_cannot_pay_is_out_of_gas_next_round():
    k = world(law={"gas_price": {"item": "timber", "rate": 1.0}})
    a, b, _ = agents(k)
    burn = _burner(k)
    k.w["reserve"]["timber"] = 3.0                                   # J0's treasury: far less than the bill
    k.begin_round_cause(phase="turns")
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    k.end_round_cause()
    used = k.w["law_v2"]["account_used"]["J0"]
    r = k.r
    k.end_round()                                                    # the bill at the advance step
    bill = [e for e in k.events if e["type"] == "gas_billed"][-1]["data"]
    assert bill == {"account": "J0", "gas": used, "item": "timber", "owed": float(used), "paid": 3.0}
    assert k.bal("reserve", "timber") == 3.0                         # J0's laws pay into J0's own treasury: nothing moves
    oog = [e for e in k.events if e["type"] == "account_out_of_gas"][-1]
    assert oog["data"] == {"account": "J0", "round": r + 1, "unpaid": float(used) - 3.0, "item": "timber"} and oog["vis"] == "public"
    assert k.r == r + 1
    st0 = k.w["laws"][burn].get("state")
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})   # next round: J0's hooks are skipped
    assert D._state(k)["out_of_gas"] == {"J0": r + 1} and D._state(k)["account_used"].get("J0", 0) == 0
    assert k.w["laws"][burn].get("state") == st0
    k.w["reserve"]["timber"] = 0.0
    assert D.bill_gas(k) == []                                       # no gas used: no bill, so the round after runs again
    k.w["round"] += 1
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert D._state(k)["out_of_gas"] == {} and D._state(k)["account_used"]["J0"] > 0
