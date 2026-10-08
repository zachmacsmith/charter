"""P4.3 contracts (charter/contracts.py; ARCHITECTURE §7.1-§7.2, review 06 §3-§4): associations are accounts no one can be forced
into. Their power set (allowed and denied per law function), exit (a member loses at most its escrow), errors that never reach the
Fixer, the templates end to end, binding only members, conservation with association and escrow accounts, and nothing when off."""
from __future__ import annotations

import re

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import contracts as CT
from charter import generator
from charter import lawapi as LA
from charter import lawlang as L
from charter import powers as PW
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


# ------------------------------------------------------------------ the record and its accounts
def test_a_contract_is_an_association_account_with_a_treasury_and_escrows():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code("def on_enact():\n    state['ok'] = True"))
    r = rec(k, cid)
    assert r["kind"] == "association" and r["treasury"] == f"assoc:{cid}" and r["members"] == [a] and r["founder"] == a
    assert AC.kind(k, cid) == "association" and AC.treasury_of(k, cid) == f"assoc:{cid}"
    lid = r["laws"][0]
    assert k.w["laws"][lid]["status"] == "active" and k.w["laws"][lid]["rank"] == "bylaw" and AC.account_of(k, lid) == cid
    assert k.w["laws"][lid]["state"] == {"ok": True}                    # in force at once: on_enact ran
    give(k, b, "timber", 5)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 2})
    esc = AC.escrow_key(cid, b)
    assert AC.resolve(k, esc).kind == "escrow" and k.bal(esc, "timber") == 2 and k.bal(b, "timber") == 3
    assert AC.resolve(k, f"assoc:{cid}").kind == "association"
    assert f"assoc:{cid}" in AC.keys(k) and esc in AC.keys(k)
    assert AC.binds(k, cid, b) and not AC.binds(k, cid, people(k)[2])
    for bad in ("assoc:A99", f"escrow:A99:{b}", f"escrow:{cid}:nobody"):
        with pytest.raises(L.LawError, match="no such"):
            k.bal(bad, "timber")
    with pytest.raises(A.ActionError, match="already a member"):
        A.act(k, b, "join_contract", {"contract": cid})


# ------------------------------------------------------------------ the power set
def test_power_table_association_column():
    k = make()
    cid = found(k, people(k)[0], code("x = 1"))
    ps = PW.power_set(k, cid)
    held = {n for n, v in ps.items() if v}
    assert held == {"take_deposits", "hook_members"}                   # no Board, Fixer, levels, dry run, compulsion, force, ...
    assert not PW.has_power(k, cid, "fixer_patch") and not PW.has_power(k, cid, "kernel_rights")
    assert PW.has_power(k, "J0", "fixer_patch") and PW.has_power(k, "J0", "hook_legal_acts")   # polities unchanged


def test_every_law_function_is_allowed_escrowed_or_denied_for_a_contract():
    k = make()
    cid = found(k, people(k)[0], code("x = 1"))
    lid = rec(k, cid)["laws"][0]
    api = k.api_for(lid)
    polity = k.api_for(k.active_laws()[0]["id"])
    seen = set()
    for name, f in LA.LAWFNS.items():
        if name not in api:
            continue
        seen.add(name)
        denied = api[name].__qualname__.startswith("_denied")
        if f.contract == "deny":
            assert denied, name
            with pytest.raises(L.LawError, match="a contract's law cannot call it"):
                api[name]()
        else:
            assert not denied, name
            assert not polity[name].__qualname__.startswith("_denied"), name
        if f.contract == "escrow":
            assert "scope_api" in api[name].__qualname__ or "law_api" in api[name].__qualname__, name
    assert {"grant", "revoke", "fine", "move", "lawful_attack", "set_quota", "mint", "create_currency", "suspend", "limit_actions",
            "define_action", "enable_loans", "pull", "breach", "members", "open_ballot"} <= seen
    deny = {n for n, f in LA.LAWFNS.items() if f.contract == "deny"}
    assert {"grant", "revoke", "suspend", "limit_actions", "censure", "set_dm_limit", "lawful_attack", "set_quota", "set_fee",
            "mint", "burn", "create_currency", "define_action", "create_right", "enable_loans", "start_project", "oblige_guard",
            "hide_post", "set_lease_rules", "title", "rename"} <= deny
    assert {f.name for f in LA.LAWFNS.values() if f.contract == "escrow"} == {"move", "fine", "pull", "forfeit", "refund", "swap"}   # P4.4


def test_contract_code_calling_a_denied_function_is_refused_when_founded():
    k = make()
    a = people(k)[0]
    for body in ("def on_enact():\n    grant(members()[0], 'vote')", "def on_round_end(r):\n    set_quota('c1', 1)",
                 "def on_enact():\n    lawful_attack('a', 'b', 1)"):
        with pytest.raises(A.ActionError, match="may not call"):
            A.act(k, a, "create_contract", {"name": "Bad", "code": code(body)})
    assert not k.w["contracts"]["assoc"]


def test_what_a_contract_may_move_fine_and_pull():
    k = make()
    a, b, out = people(k)[:3]
    cid = found(k, a, code('''
def on_round_end(r):
    if r != 0:
        return
    public["taken_from_member"] = move(members()[1], treasury(), "timber", 1)
    public["paid_outsider"] = move(treasury(), OUTSIDER, "timber", 1)
    public["fined"] = fine(members()[1], "timber", 100)
    public["pulled_over"] = pull(members()[1], "timber", 5)
    public["pulled"] = pull(members()[1], "timber", 2)
    public["pulled_again"] = pull(members()[1], "timber", 1)
'''.replace("OUTSIDER", repr(out))))
    give(k, b, "timber", 10)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 3})
    A.act(k, b, "set_allowance", {"contract": cid, "item": "timber", "qty": 2})
    k._add(f"assoc:{cid}", "timber", 4)
    t_out = k.bal(out, "timber")
    k.end_round()
    pub = k.w["laws"][rec(k, cid)["laws"][0]]["public"]
    assert pub == {"taken_from_member": False, "paid_outsider": True, "fined": 3.0, "pulled_over": False, "pulled": True,
                   "pulled_again": False}
    assert k.bal(out, "timber") == t_out + 1                            # pays outsiders from its treasury
    assert k.bal(b, "timber") == 10 - 3 - 2                             # escrow (fined in full, never more) and the allowance
    assert k.bal(f"assoc:{cid}", "timber") == 4 - 1 + 3 + 2
    assert [e["data"]["qty"] for e in events(k, "contract_pull")] == [2.0]
    assert events(k, "contract_out_of_scope")                           # the move from a member was refused, for the monitor


def test_allowances_reset_each_round_and_end_on_withdrawal():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code('def on_round_start(r):\n    public[str(r)] = pull(members()[-1], "grain", 1)'))
    give(k, b, "grain", 10)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, b, "set_allowance", {"contract": cid, "item": "grain", "qty": 1})
    next_round(k)
    next_round(k)
    A.act(k, b, "set_allowance", {"contract": cid, "item": "grain", "qty": 0})
    next_round(k)
    assert k.w["laws"][rec(k, cid)["laws"][0]]["public"] == {"1": True, "2": True, "3": False}
    assert k.bal(b, "grain") == 8


# ------------------------------------------------------------------ binding and hooks
def test_hooks_reach_members_only_and_charges_go_to_the_treasury():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, code("def on_transfer(src, dst, item, qty):\n    return qty * 0.5"))
    A.act(k, b, "join_contract", {"contract": cid})
    give(k, b, "stone", 4)
    give(k, c, "stone", 4)
    d0 = k.bal(a, "stone")
    A.act(k, b, "transfer", {"to": a, "item": "stone", "qty": 2})      # a member: taxed half, to the contract's treasury
    A.act(k, c, "transfer", {"to": a, "item": "stone", "qty": 2})      # not a member: untouched
    assert k.bal(f"assoc:{cid}", "stone") == 1 and k.bal(a, "stone") == d0 + 1 + 2


def test_v2_hooks_see_members_changes_and_own_legal_acts_but_no_polity_legal_act():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code('''
def before_move(p, chain):
    public.setdefault("moves", []).append(p["src"])

def before_propose(p, chain):
    public.setdefault("proposals", []).append(p["jurisdiction"])
'''))
    lid = rec(k, cid)["laws"][0]
    give(k, a, "stone", 3)
    give(k, b, "stone", 3)
    A.act(k, a, "transfer", {"to": b, "item": "stone", "qty": 1})
    A.act(k, b, "transfer", {"to": a, "item": "stone", "qty": 1})
    leg = next((x for x in people(k) if k.has(x, "propose")), None)
    if leg:
        A.act(k, leg, "propose", {"code": code("x = 1", "Polity Law")})
    A.act(k, a, "propose_contract_change", {"contract": cid, "code": code("y = 2", "Second")})
    pub = k.w["laws"][lid]["public"]
    assert pub["moves"] == [a]                                         # b is not a member
    assert pub["proposals"] == [cid]                                   # its own proposal only (D-24)


# ------------------------------------------------------------------ exit
def test_exit_forfeits_at_most_the_escrow_and_is_always_possible():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code('''
def on_exit(agent):
    public["forfeited"] = forfeit(agent, "timber", 1)
    public["seized"] = move(agent, treasury(), "timber", 50)

def before_leave(p, chain):
    return False
'''))
    give(k, b, "timber", 10)
    give(k, b, "grain", 7)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 4})
    A.act(k, b, "set_allowance", {"contract": cid, "item": "grain", "qty": 3})
    A.act(k, b, "leave_contract", {"contract": cid})
    assert b in rec(k, cid)["members"]                                  # leaving takes effect at the end of the round
    next_round(k)
    r = rec(k, cid)
    assert b not in r["members"] and b not in r["escrow"] and b not in r["allowances"]
    assert k.w["laws"][r["laws"][0]]["public"] == {"forfeited": 1.0, "seized": False}
    assert k.bal(b, "timber") == 9 and k.bal(b, "grain") == 7           # lost exactly what its escrow forfeited
    assert events(k, "contract_left")[-1]["data"]["refunded"] == {"timber": 3.0}
    with pytest.raises(A.ActionError, match="not a member"):
        A.act(k, b, "leave_contract", {"contract": cid})


def test_expel_and_dissolution():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, code("def on_round_start(r):\n    for m in members():\n        if m != FOUNDER:\n            expel(m)".replace(
        "FOUNDER", repr(a))))
    give(k, b, "timber", 2)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, b, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 2})
    next_round(k)                                                       # expelled at round 1's start, out at its end
    next_round(k)
    assert rec(k, cid)["members"] == [a] and k.bal(b, "timber") == 2
    A.act(k, a, "leave_contract", {"contract": cid})
    next_round(k)
    r = rec(k, cid)
    assert r["status"] == "dissolved" and not r["laws"] and events(k, "contract_dissolved")
    with pytest.raises(A.ActionError, match="no contract"):
        A.act(k, b, "join_contract", {"contract": cid})


# ------------------------------------------------------------------ errors never reach the Fixer
def test_a_contract_error_suspends_the_law_and_tells_members_not_the_fixer():
    k = make("E4")
    a, b = people(k)[:2]
    cid = found(k, a, code("def on_round_start(r):\n    state['x'] = members()[99]"))
    A.act(k, b, "join_contract", {"contract": cid})
    lid = rec(k, cid)["laws"][0]
    q0 = list(k.w["fixer_queue"])
    next_round(k)
    assert k.w["laws"][lid]["status"] == "suspended" and rec(k, cid)["status"] == "suspended"
    assert k.w["fixer_queue"] == q0 and not events(k, "law_error")
    e = events(k, "contract_law_error")[-1]
    assert e["data"]["law"] == lid and set(e["vis"]) == {a, b}
    assert rec(k, cid)["errors"][0]["law"] == lid
    out = A.act(k, a, "propose_contract_change", {"contract": cid, "code": code("x = 1", "Fixed"), "replaces": lid})
    bid = re.search(r"B\d+", out).group()                               # the members repair it (by default they vote)
    for x in (a, b):
        A.act(k, x, "vote", {"ballot": bid, "choice": "yes"})
    next_round(k)
    pr = list(rec(k, cid)["proposals"].values())[0]
    assert pr["status"] == "adopted" and rec(k, cid)["status"] == "active" and lid not in rec(k, cid)["laws"]
    assert k.w["fixer_queue"] == q0


def test_a_contract_error_in_a_dry_run_does_not_fail_a_polity_proposal():
    k = make("E4")
    a = people(k)[0]
    found(k, a, code("def on_round_start(r):\n    state['x'] = members()[99]"))
    leg = next(x for x in people(k) if k.has(x, "propose"))
    out = A.act(k, leg, "propose", {"code": code("def on_round_end(r):\n    gazette('hi')", "Polity Law")})
    assert "Proposed" in out


def test_a_polity_cannot_repeal_or_list_a_contracts_law():
    k = make()
    a = people(k)[0]
    cid = found(k, a, code("x = 1", "Club Rules"))
    lid = rec(k, cid)["laws"][0]
    assert not k.repeal("Club Rules") and k.w["laws"][lid]["status"] == "active"
    polity = k.api_for(k.active_laws()[0]["id"])
    assert lid not in [x["id"] for x in polity["laws"]()]
    with pytest.raises(L.LawError, match="works only in a contract's own law"):
        polity["pull"](a, "grain", 1)


# ------------------------------------------------------------------ changes through the contract's procedure
def test_changes_are_voted_by_members_by_default_and_by_the_founder_alone_when_set():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, code("x = 1", "Old"))
    old = rec(k, cid)["laws"][0]
    A.act(k, b, "join_contract", {"contract": cid})
    with pytest.raises(A.ActionError, match="only members"):
        A.act(k, c, "propose_contract_change", {"contract": cid, "code": code("x = 2", "New")})
    out = A.act(k, b, "propose_contract_change", {"contract": cid, "code": code("x = 2", "New"), "replaces": old})
    bid = re.search(r"B\d+", out).group()
    assert set(k.w["ballots"][bid]["electorate"]) == {a, b} and k.w["ballots"][bid]["jurisdiction"] == cid
    A.act(k, a, "vote", {"ballot": bid, "choice": "yes"})
    A.act(k, b, "vote", {"ballot": bid, "choice": "yes"})
    next_round(k)
    r = rec(k, cid)
    assert old not in r["laws"] and k.w["laws"][old]["status"] == "repealed" and len(r["laws"]) == 1
    assert k.w["laws"][r["laws"][0]]["title"] == "New" and events(k, "contract_changed")
    cf = found(k, c, template="crowdfund")                              # the crowdfund template: its founder decides
    A.act(k, a, "join_contract", {"contract": cf})
    A.act(k, a, "propose_contract_change", {"contract": cf, "template": "crowdfund", "params": {"TARGET": 1},
                                            "replaces": rec(k, cf)["laws"][0]})
    assert events(k, "contract_change_failed")[-1]["data"]["why"].startswith(f"only {c}")
    A.act(k, c, "propose_contract_change", {"contract": cf, "template": "crowdfund", "params": {"TARGET": 1},
                                            "replaces": rec(k, cf)["laws"][0]})
    assert rec(k, cf)["params"] == {} and "TARGET = 1" in k.w["laws"][rec(k, cf)["laws"][0]]["code"]


# ------------------------------------------------------------------ the templates, end to end
@pytest.mark.parametrize("funded", [False, True])
def test_crowdfund_refunds_below_the_target_and_pays_above_it(funded):
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, template="crowdfund", params={"ITEM": "timber", "TARGET": 5, "DEADLINE": 2})
    for x, q in ((b, 2), (c, 2 + funded)):
        give(k, x, "timber", 10)
        A.act(k, x, "join_contract", {"contract": cid})
        A.act(k, x, "deposit_escrow", {"contract": cid, "item": "timber", "qty": q})
    t_a = k.bal(a, "timber")
    next_round(k)                                                       # round 1 ends: before the deadline
    assert k.bal(b, "timber") == 8
    next_round(k)                                                       # round 2 ends: the deadline
    if funded:
        assert k.bal(a, "timber") == t_a + 5 and k.bal(b, "timber") == 8 and k.bal(c, "timber") == 7
    else:
        assert k.bal(a, "timber") == t_a and k.bal(b, "timber") == 10 and k.bal(c, "timber") == 10
    assert all(not v for v in rec(k, cid)["escrow"].values())


def test_cartel_quota_pool_and_penalty_from_escrow():
    k = make()
    a, b, out = people(k)[:3]
    cid = found(k, a, template="cartel", params={"ITEM": "grain", "QUOTA": 2, "BOND_ITEM": "timber", "BOND": 2, "PENALTY": 2})
    for x in (a, b):
        give(k, x, "timber", 5)
        if x != a:
            A.act(k, x, "join_contract", {"contract": cid})
        A.act(k, x, "deposit_escrow", {"contract": cid, "item": "timber", "qty": 3})
    give(k, b, "grain", 5)
    A.act(k, b, "transfer", {"to": out, "item": "grain", "qty": 1})     # sold outside the cartel: penalty from the bond
    assert k.bal(AC.escrow_key(cid, b), "timber") == 1 and k.bal(f"assoc:{cid}", "timber") == 2
    br = rec(k, cid)["breaches"][-1]
    assert br["member"] == b and "outside" in br["clause"]
    A.act(k, b, "transfer", {"to": a, "item": "grain", "qty": 1})       # inside the cartel: nothing
    assert k.bal(AC.escrow_key(cid, b), "timber") == 1
    ta, tb = k.bal(a, "timber"), k.bal(b, "timber")
    next_round(k)                                                       # the pool is shared equally at the round's end
    assert k.bal(a, "timber") == ta + 1 and k.bal(b, "timber") == tb + 1
    next_round(k)                                                       # b's bond (1 < 2) is short: expelled, its escrow back
    assert b not in rec(k, cid)["members"] and k.bal(AC.escrow_key(cid, b), "timber") == 0
    assert any(x["clause"] == "bond" and x["member"] == b for x in rec(k, cid)["breaches"])


def test_cartel_deducts_harvest_above_the_quota():
    k = make()
    a = people(k)[0]
    cid = found(k, a, template="cartel", params={"ITEM": "grain", "QUOTA": 0, "BOND": 0})
    lid = rec(k, cid)["laws"][0]
    got = CT.run_hook(k, k.w["laws"][lid], "on_harvest", a, "c1", [0], 3.0)
    assert got == [(lid, 3.0)]


def test_club_dues_from_allowances_breaches_and_payout():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, template="club", params={"ITEM": "grain", "DUES": 1, "PAYOUT_EVERY": 2, "MISSES": 2})
    give(k, a, "grain", 10)
    give(k, b, "grain", 10)
    A.act(k, a, "set_allowance", {"contract": cid, "item": "grain", "qty": 1})
    A.act(k, b, "join_contract", {"contract": cid})
    next_round(k)                                                       # round 1: a pays, b has no allowance (a breach)
    assert k.bal(f"assoc:{cid}", "grain") == 1 and [x["member"] for x in rec(k, cid)["breaches"]] == [b]
    next_round(k)                                                       # round 1's end: the payout (to a alone); round 2: b misses
    assert rec(k, cid)["leaving"] == {b: "expelled"}                    # again: expelled, out at the end of the round
    assert k.bal(a, "grain") == 9 and k.bal(f"assoc:{cid}", "grain") == 1
    next_round(k)
    assert b not in rec(k, cid)["members"] and k.bal(b, "grain") == 10


def test_company_cut_shares_and_dividends():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, template="company", params={"CUT": 0.5, "DIVIDEND_EVERY": 1, "PAYOUT": 1.0})
    A.act(k, b, "join_contract", {"contract": cid})
    lid = rec(k, cid)["laws"][0]
    law = k.w["laws"][lid]
    for who, y in ((a, 4.0), (b, 2.0)):
        assert CT.run_hook(k, law, "on_harvest", who, "c1", [0], y) == [(lid, y * 0.5)]
    assert law["public"]["shares"] == {a: 2.0, b: 1.0} and len(law["public"]["register"][a]) == 1
    k._add(f"assoc:{cid}", "grain", 3)
    ga, gb = k.bal(a, "grain"), k.bal(b, "grain")
    next_round(k)
    assert k.bal(a, "grain") == pytest.approx(ga + 2) and k.bal(b, "grain") == pytest.approx(gb + 1)
    assert rec(k, cid)["procedure"] not in CT.PROCEDURES                  # decided by shares (set_procedure in its code)


def test_templates_are_listed_in_the_manual_and_take_known_params_only():
    k = make()
    with pytest.raises(A.ActionError, match="no parameter NOPE"):
        A.act(k, people(k)[0], "create_contract", {"template": "club", "params": {"NOPE": 1}})
    with pytest.raises(A.ActionError, match="no template"):
        A.act(k, people(k)[0], "create_contract", {"template": "bank"})
    text = CT.rules_text(k.inst)
    assert all(t in text for t in CT.TEMPLATES) and "DUES=1" in text


def test_checkpoint_and_restore_keep_contracts_and_their_procedures():
    import pickle
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, template="company", params={"CUT": 0.5, "DIVIDEND_EVERY": 1, "PAYOUT": 1.0})
    A.act(k, b, "join_contract", {"contract": cid})
    next_round(k)
    st = pickle.loads(pickle.dumps(k.checkpoint_state()))
    k2 = Kernel(k.inst)
    k2.restore_state(st)
    assert k2.w["contracts"] == k.w["contracts"] and rec(k2, cid)["procedure"] in k2.fnreg
    lid = rec(k2, cid)["laws"][0]
    assert CT.run_hook(k2, k2.w["laws"][lid], "on_harvest", b, "c1", [0], 2.0) == [(lid, 1.0)]
    out = A.act(k2, a, "propose_contract_change", {"contract": cid, "template": "company", "params": {"CUT": 0.1}, "replaces": lid})
    assert re.search(r"B\d+", out) and k2.w["ballots"][re.search(r"B\d+", out).group()]["weights"] == {a: 1, b: 2.0}


# ------------------------------------------------------------------ off, and conservation
def test_off_nothing_exists():
    k = make(on=False)
    assert "contracts" not in k.w and CT.law_api(k, "L1") == {} and CT.state_lines(k, people(k)[0]) == []
    with pytest.raises(A.ActionError, match="unknown action 'create_contract'"):
        A.act(k, people(k)[0], "create_contract", {"template": "club"})
    msg = ""
    try:
        A.act(k, people(k)[0], "no_such_action", {})
    except A.ActionError as e:
        msg = str(e)
    assert "create_contract" not in msg and "harvest" in msg


def test_needs_law_v2():
    with pytest.raises(ValueError, match="needs law.v2"):
        make(extra=["law.v2=false"])


def test_conservation_with_association_and_escrow_accounts():
    import test_charter_accounts as TA
    t0, t1, flows = TA.ledger_run("E2", sets=("law.v2=true", "contracts.enabled=true", "rounds=5"))
    explicit = TA.SS | {"events.arrival", "escrow.destroyed", "projects.spent"}
    for item in sorted(set(t0) | set(t1)):
        change = t1.get(item, 0.0) - t0.get(item, 0.0)
        accounted = sum(f.get(item, 0.0) for site, f in flows.items() if site in explicit)
        assert change == pytest.approx(accounted, abs=1e-6), item


def test_scripted_bots_use_contracts():
    import json
    import tempfile
    from pathlib import Path
    from charter import agents as AG, runner
    inst = generator.generate(S.apply_overrides(S.load("E2"), ["rounds=5", "shared_archive.enabled=false", "law.v2=true",
                                                               "contracts.enabled=true"]), 3)
    inst["run_id"] = "t"
    with tempfile.TemporaryDirectory() as d:
        out = runner.run(inst, AG.ScriptedPolicy(3), Path(d) / "out", log=lambda *a: None)
        ev = [json.loads(x) for x in (out / "events.jsonl").read_text().splitlines()]
    kinds = {e["type"] for e in ev}
    assert {"contract_created", "contract_joined", "contract_allowance", "contract_pull", "contract_changed"} <= kinds
    assert not [e for e in ev if e["type"] == "law_error" and str(e["data"].get("law")) in
                {lid for x in ev if x["type"] == "contract_created" for lid in x["data"]["laws"]}]
