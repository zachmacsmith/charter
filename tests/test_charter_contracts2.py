"""P4.4 contracts (charter/contracts.py; ARCHITECTURE §7.2, review 10 §3.6 and §6 #7-#8): the enforcement dial (escrow |
escrow_court | word), the Contract Enforcement Act (a polity law over breaches()), atomic exchange (the swap primitive and the
exchange template), per-law funds (fund:<lid>:<name>), the wind-up of a dissolved contract's treasury, and a dead member's escrow
going to its heirs instead of its record."""
from __future__ import annotations

import re

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import contracts as CT
from charter import dispatch as D
from charter import generator
from charter import lawapi as LA
from charter import lawlang as L
from charter import library as LB
from charter import mortality as MO
from charter import primitives as PR
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel

ON = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]


def make(preset="E2", extra=(), on=True):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=8", "shared_archive.enabled=false", "turns=sequential",
                                                                 *(ON if on else ()), *extra]), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def give(k, aid, item, qty):
    k._add(aid, item, qty - k.bal(aid, item))


def found(k, aid, code=None, template=None, params=None, **kw):
    args = {"name": "Test", **({"code": code} if code else {}), **({"template": template} if template else {}),
            **({"params": params} if params else {}), **kw}
    out = A.act(k, aid, "create_contract", args)
    return re.search(r"A\d+", out).group()


def next_round(k):
    k.end_round()
    k.start_round()


def code(body, title="Rules"):
    return f'title = "{title}"\nintent = "test"\n\n{body.strip()}\n'


def rec(k, cid):
    return k.w["contracts"]["assoc"][cid]


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def enact(k, src):
    lid = k.new_law(src, "a_test")
    k.enact(lid)
    return lid


def totals(k):
    return AC.totals(k, held=True)


def same_totals(t0, t1):
    for item in set(t0) | set(t1):
        assert t0.get(item, 0.0) == pytest.approx(t1.get(item, 0.0), abs=1e-6), item


# ------------------------------------------------------------------ the dial
def test_dial_defaults_to_escrow_and_the_schema_suggests_a_value():
    k = make()
    assert CT.enforcement(k) == "escrow" and CT.cfg(k)["enforcement"] == "escrow"
    errs = SC.validate(S.apply_overrides(S.load("E2"), [*ON, "contracts.enforcement=escrowcourt"]))
    assert any("contracts.enforcement" in e and "escrow_court" in e for e in errs), errs
    assert not SC.validate(S.apply_overrides(S.load("E2"), [*ON, "contracts.enforcement=word"]))
    with pytest.raises(ValueError, match="did you mean 'word'"):
        make(extra=["contracts.enforcement=wordd"])


def test_word_refuses_every_escrow_function_and_keeps_public_breach_records():
    k = make(extra=["contracts.enforcement=word"])
    a, b, c = people(k)[:3]
    cid = found(k, a, code('''
def on_round_end(r):
    public["pulled"] = pull(BOB, "grain", 1)
    public["forfeit"] = forfeit(BOB, "grain", 1)
    public["fined"] = fine(BOB, "grain", 1)
    public["refund"] = refund(BOB)
    public["swap"] = swap(BOB, ALICE, {"grain": 1}, {"grain": 1})
    public["move_escrow"] = move("escrow:" + jurisdiction() + ":" + BOB, ALICE, "grain", 1)
    public["paid"] = move(treasury(), ALICE, "grain", 1)
    breach(BOB, "dues", "none: enforcement by word")
'''.replace("BOB", repr(b)).replace("ALICE", repr(a))))
    give(k, b, "grain", 5)
    A.act(k, b, "join_contract", {"contract": cid})
    for act in ("deposit_escrow", "set_allowance"):
        with pytest.raises(A.ActionError, match="no escrow"):
            A.act(k, b, act, {"contract": cid, "item": "grain", "qty": 1})
    k._add(f"assoc:{cid}", "grain", 2)                                  # the treasury still pays out (a charge could fill it)
    ga = k.bal(a, "grain")
    next_round(k)
    pub = k.w["laws"][rec(k, cid)["laws"][0]]["public"]
    assert pub == {"pulled": False, "forfeit": 0.0, "fined": 0.0, "refund": {}, "swap": False, "move_escrow": False, "paid": True}
    assert k.bal(b, "grain") == 5 and k.bal(a, "grain") == ga + 1
    assert k.w["laws"][rec(k, cid)["laws"][0]]["status"] == "active"   # refusals, not errors
    br = events(k, "contract_breach")[-1]
    assert br["vis"] == "public" and br["agent"] == b                   # a reputation: everyone sees it
    api = k.api_for(rec(k, cid)["laws"][0])
    assert api["reputation"](b) == {"breaches": 1, "contracts": [cid]} and api["reputation"](c)["breaches"] == 0
    assert api["enforcement"]() == "word"
    assert {e["data"]["fn"] for e in events(k, "contract_out_of_scope")} >= {"pull", "forfeit", "refund", "swap", "move"}
    assert "enforcement by word" in CT.rules_text(k.inst)


def test_escrow_keeps_breaches_with_members_and_not_actionable():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code(f"def on_round_start(r):\n    breach({b!r}, 'x', 'y')"))
    A.act(k, b, "join_contract", {"contract": cid})
    next_round(k)
    assert events(k, "contract_breach")[-1]["vis"] != "public"
    br = k.api_for(rec(k, cid)["laws"][0])["breaches"]()
    assert br and all(x["actionable"] is False and x["id"].startswith(f"{cid}:") for x in br)
    assert CT.court_breaches(k, b) == []


# ------------------------------------------------------------------ the Contract Enforcement Act (escrow_court)
CEA = LB.LIB["Contract Enforcement Act"]


def _breaching_world(dial, params=None):
    k = make(extra=[f"contracts.enforcement={dial}"])
    a, b, judge = people(k)[:3]
    cid = found(k, a, code(f"def on_round_start(r):\n    if r == 1:\n        breach({b!r}, 'dues', 'none')"))
    A.act(k, b, "join_contract", {"contract": cid})
    lid = enact(k, LB.instantiate("Contract Enforcement Act", params or {}) if params else CEA["code"])
    next_round(k)                                                       # round 1: the breach is recorded
    return k, a, b, judge, cid, lid


def test_the_act_is_a_gated_polity_library_law():
    assert LB.GATED_CATEGORIES["contracts"] == "contracts" and CEA["category"] == "contracts"
    assert L.classify(L.check(CEA["code"])) == "structural"
    from charter import media as MD
    on = S.apply_overrides(S.load("society"), ON)                     # library: all
    off = S.load("society")
    lib = [{"name": n, **LB.LIB[n]} for n in LB.LIB]
    assert any(x["name"] == "Contract Enforcement Act" for x in MD.filter_library(on, lib))
    assert not any(x["name"] == "Contract Enforcement Act" for x in MD.filter_library(off, lib))


def test_escrow_court_a_judge_rules_on_a_breach_and_the_act_fines_once():
    k, a, b, judge, cid, lid = _breaching_world("escrow_court")
    assert [x["id"] for x in CT.court_breaches(k, b)] == [f"{cid}:1"]
    give(k, b, "grain", 10)
    k.w["agents"][judge]["rights"].append("judge")
    A._accuse(k, a, b, lid, "breach_of_contract", [events(k, "contract_breach")[-1]["id"]])
    case = sorted(k.w["cases"])[-1]
    A._rule(k, judge, case, "guilty", "the contract's record")
    assert k.bal(b, "grain") == 8                                       # FINE 2 per breach, to the reserve
    assert k.w["laws"][lid]["state"]["done"] == [f"{cid}:1"]
    A._accuse(k, a, b, lid, "breach_of_contract", [])                   # the same breach is not sanctioned twice
    A._rule(k, judge, sorted(k.w["cases"], key=lambda c: int(c[1:]))[-1], "guilty", "again")
    assert k.bal(b, "grain") == 8


def test_plain_escrow_courts_do_not_hear_contract_breaches():
    k, a, b, judge, cid, lid = _breaching_world("escrow")
    give(k, b, "grain", 10)
    k.w["agents"][judge]["rights"].append("judge")
    A._accuse(k, a, b, lid, "breach_of_contract", [])
    A._rule(k, judge, sorted(k.w["cases"])[-1], "guilty", "x")
    assert k.bal(b, "grain") == 10
    assert any("no breach of contract on record" in str(e["data"].get("text", "")) for e in events(k, "gazette"))


def test_the_act_in_auto_mode_suspends_breaching_members():
    k, a, b, judge, cid, lid = _breaching_world("escrow_court", {"MODE": "auto", "SANCTION": "suspend", "RIGHT": "propose",
                                                                 "ROUNDS": 2})
    next_round(k)                                                       # the end of round 1: sanctioned
    assert k.w["laws"][lid]["state"]["done"] == [f"{cid}:1"]
    assert "propose" in k.w["agents"][b]["suspended"]
    next_round(k)
    assert k.w["laws"][lid]["state"]["done"] == [f"{cid}:1"]           # each breach once


# ------------------------------------------------------------------ atomic exchange
def test_swap_is_both_legs_or_neither_and_conserves():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code("def trade(a, b, g, t):\n    return swap(a, b, g, t)"))
    A.act(k, b, "join_contract", {"contract": cid})
    for x, it, q in ((a, "timber", 5), (a, "grain", 0), (b, "grain", 5), (b, "timber", 0)):
        give(k, x, it, q)
    A.act(k, a, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 2})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "grain", "qty": 1})
    lid = rec(k, cid)["laws"][0]
    swap = lambda *x: k.call(lid, k.ns[lid]["trade"], *x)              # inside the law's own call, as its code calls it
    t0 = totals(k)
    assert swap(a, b, {"timber": 2}, {"grain": 3}) is False             # b's leg is short: nothing moves
    assert k.bal(AC.escrow_key(cid, a), "timber") == 2 and k.bal(b, "timber") == 0
    assert swap(a, b, {"timber": 2}, {"grain": 1}) is True
    assert k.bal(b, "timber") == 2 and k.bal(a, "grain") == 1 and not rec(k, cid)["escrow"].get(a)
    same_totals(t0, totals(k))
    e = events(k, "contract_swap")[-1]
    assert e["data"]["give"] == {"timber": 2.0} and set(e["vis"]) >= {a, b}
    p = PR.get("swap")
    assert p.fn == "dispatch:do_swap" and "swap" in p.compel and p.hooks == ("before_swap", "after_swap")
    assert LA.LAWFNS["swap"].contract == "escrow" and LA.LAWFNS["open_fund"].contract == "allow"
    with pytest.raises(L.LawError, match="a contract's law only|only in a contract"):
        k.api_for(k.active_laws()[0]["id"])["swap"](a, b, {"timber": 1}, {"grain": 1})


def test_a_polity_hook_blocking_swap_blocks_both_legs():
    k = make()
    a, b = people(k)[:2]
    enact(k, code("def before_swap(p, chain):\n    return False", "No Swaps"))
    cid = found(k, a, code("def trade(a, b, g, t):\n    return swap(a, b, g, t)"))
    A.act(k, b, "join_contract", {"contract": cid})
    give(k, a, "timber", 1)
    give(k, b, "grain", 1)
    A.act(k, a, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 1})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "grain", "qty": 1})
    lid = rec(k, cid)["laws"][0]
    assert k.call(lid, k.ns[lid]["trade"], a, b, {"timber": 1}, {"grain": 1}) is False
    assert events(k, "primitive_blocked")[-1]["data"]["primitive"] == "swap"
    assert k.bal(AC.escrow_key(cid, a), "timber") == 1 and k.bal(AC.escrow_key(cid, b), "grain") == 1


@pytest.mark.parametrize("complete", [True, False])
def test_exchange_template_releases_both_or_refunds_both(complete):
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, template="exchange", params={"GIVE_ITEM": "timber", "GIVE_QTY": 2, "GET_ITEM": "grain", "GET_QTY": 3,
                                                   "DEADLINE": 2})
    for x, it, q in ((a, "timber", 5), (a, "grain", 0), (b, "grain", 5), (b, "timber", 0)):
        give(k, x, it, q)
    A.act(k, b, "join_contract", {"contract": cid})
    assert "refused" in A.act(k, c, "join_contract", {"contract": cid})   # one counterparty only
    A.act(k, a, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 2})
    if complete:
        A.act(k, b, "deposit_escrow", {"contract": cid, "item": "grain", "qty": 3})
    t0 = totals(k)
    next_round(k)
    if complete:
        assert k.bal(a, "grain") == 3 and k.bal(b, "timber") == 2 and k.bal(a, "timber") == 3 and k.bal(b, "grain") == 2
        assert rec(k, cid)["status"] == "dissolved"
    else:
        assert rec(k, cid)["status"] == "active" and k.bal(AC.escrow_key(cid, a), "timber") == 2
        next_round(k)                                                   # the deadline: both refunded, closed
        assert k.bal(a, "timber") == 5 and k.bal(b, "grain") == 5 and k.bal(a, "grain") == 0
        assert rec(k, cid)["status"] == "dissolved"
    same_totals(t0, totals(k))


# ------------------------------------------------------------------ per-law funds
FUND_LAW = code('''
def on_enact():
    state["fund"] = open_fund("works")
    move("reserve", state["fund"], "timber", 3)

def pay(to, q):
    return move(state["fund"], to, "timber", q)
''', "Works Fund")


def test_a_law_opens_a_fund_only_it_can_move_out_of():
    k = make()
    a = people(k)[0]
    k._add("reserve", "timber", 10)
    t0 = totals(k)
    lid = enact(k, FUND_LAW)
    key = f"fund:{lid}:works"
    assert k.w["laws"][lid]["state"]["fund"] == key and k.bal(key, "timber") == 3
    acc = AC.resolve(k, key)
    assert acc.kind == "fund" and acc.account == "J0" and key in AC.keys(k)
    assert AC.funds_of(k, "J0") == {key: {"timber": 3.0}}
    assert k.api_for(lid)["funds"]() == {key: {"timber": 3.0}}
    assert k.api_for(lid)["open_fund"]("works") == key                  # the same fund again
    same_totals(t0, totals(k))
    assert k.call(lid, k.ns[lid]["pay"], a, 1) is True and k.bal(key, "timber") == 2
    other = enact(k, code("x = 1", "Other"))
    with pytest.raises(L.LawError, match=f"only law {lid}"):
        k.api_for(other)["move"](key, a, "timber", 1)
    with pytest.raises(L.LawError, match=f"only law {lid}"):
        k.move(key, a, "timber", 1, why="transfer", by=a)
    assert k.api_for(other)["move"]("reserve", key, "timber", 1)        # anyone's law may pay into it
    assert k.bal(key, "timber") == 3 and events(k, "fund_opened")[-1]["data"]["fund"] == key
    assert CT.snapshot_fields(k)["funds"][key]["holdings"] == {"timber": 3.0}
    with pytest.raises(L.LawError, match="1-24"):
        k.api_for(lid)["open_fund"]("bad name!")


def test_an_amended_law_keeps_its_fund_and_a_repealed_one_closes_it_into_the_treasury():
    k = make()
    a = people(k)[0]
    k._add("reserve", "timber", 10)
    lid = enact(k, FUND_LAW)
    key = f"fund:{lid}:works"
    new = FUND_LAW.replace('return move(state["fund"], to, "timber", q)', 'return move(state["fund"], to, "timber", q * 2)')
    D.do_amend(k, "J0", lid, "x", "y", "", "patch", "fixer", patch={"code": new, "by": "fixer", "reason": "double", "diff": ""})
    assert k.call(lid, k.ns[lid]["pay"], a, 1) is True and k.bal(key, "timber") == 1
    r0 = k.bal("reserve", "timber")
    assert k.repeal(lid)
    next_round(k)
    f = AC.funds(k)[key]
    assert f["status"] == "closed" and not f["holdings"] and k.bal("reserve", "timber") == r0 + 1
    assert events(k, "fund_closed")[-1]["data"]["to"] == "reserve"
    assert key not in AC.funds_of(k, "J0") and key in AC.keys(k)


def test_a_contract_law_has_funds_in_its_own_account():
    k = make()
    a = people(k)[0]
    cid = found(k, a, code('''
def on_enact():
    state["f"] = open_fund("pot")

def on_round_end(r):
    move(treasury(), state["f"], "grain", 1)
'''))
    k._add(f"assoc:{cid}", "grain", 2)
    next_round(k)
    lid = rec(k, cid)["laws"][0]
    key = f"fund:{lid}:pot"
    assert AC.resolve(k, key).account == cid and k.bal(key, "grain") == 1
    assert CT.public_record(k, cid)["funds"] == {key: {"grain": 1.0}}
    assert k.api_for(lid)["move"](key, a, "grain", 1) is True           # its own fund: allowed by the contract column


# ------------------------------------------------------------------ dissolution: the treasury goes to the last members
def test_dissolution_shares_the_treasury_among_the_last_members():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, code("x = 1"))
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    k._add(f"assoc:{cid}", "grain", 9)
    A.act(k, c, "leave_contract", {"contract": cid})
    next_round(k)                                                       # c left alone: nothing
    assert k.bal(f"assoc:{cid}", "grain") == 9
    g = {x: k.bal(x, "grain") for x in (a, b, c)}
    t0 = totals(k)
    for x in (a, b):
        A.act(k, x, "leave_contract", {"contract": cid})
    next_round(k)
    assert rec(k, cid)["status"] == "dissolved" and k.bal(f"assoc:{cid}", "grain") == 0
    assert k.bal(a, "grain") == g[a] + 4.5 and k.bal(b, "grain") == g[b] + 4.5 and k.bal(c, "grain") == g[c]
    assert events(k, "contract_wound_up")[-1]["data"]["paid"] == {a: {"grain": 4.5}, b: {"grain": 4.5}}
    same_totals(t0, totals(k))


def test_company_on_dissolve_pays_pro_rata_to_shares():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, template="company", params={"CUT": 0.5, "DIVIDEND_EVERY": 99})
    A.act(k, b, "join_contract", {"contract": cid})
    law = k.w["laws"][rec(k, cid)["laws"][0]]
    law["public"]["shares"] = {a: 3.0, b: 1.0}
    k._add(f"assoc:{cid}", "grain", 8)
    ga, gb = k.bal(a, "grain"), k.bal(b, "grain")
    for x in (a, b):
        A.act(k, x, "leave_contract", {"contract": cid})
    next_round(k)
    assert k.bal(a, "grain") == pytest.approx(ga + 6) and k.bal(b, "grain") == pytest.approx(gb + 2)
    assert not events(k, "contract_wound_up")                          # on_dissolve paid it all


# ------------------------------------------------------------------ a dead member's escrow goes to its heirs
@pytest.mark.parametrize("bequest", [True, False])
def test_a_dead_members_escrow_follows_its_bequest(bequest):
    k = make(extra=["conflict.enabled=true"])
    a, b, c = people(k)[:3]
    cid = found(k, a, code("x = 1"))
    A.act(k, b, "join_contract", {"contract": cid})
    give(k, b, "stone", 4)
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "stone", "qty": 4})
    if bequest:
        MO.set_bequest(k, b, {"holdings": {c: 1.0}})
    sc, sr = k.bal(c, "stone"), k.bal("reserve", "stone")
    t0 = totals(k)
    MO.disable(k, b, "accident")
    next_round(k)
    assert b not in rec(k, cid)["members"] and k.bal(b, "stone") == 0   # never left on the dead agent's record
    if bequest:
        assert k.bal(c, "stone") == sc + 4
    else:
        assert k.bal("reserve", "stone") == sr + 4
    same_totals(t0, totals(k))


# ------------------------------------------------------------------ off
def test_off_nothing_new_exists():
    k = make(on=False, extra=["law.v2=true"])
    assert "contracts" not in k.w and AC.funds(k) == {} and CT.law_api(k, "L1") == {}
    assert "fund" in AC.KINDS and "open_fund" not in k.api_for(k.active_laws()[0]["id"])
