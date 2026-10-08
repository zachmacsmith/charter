"""P4.5 contracts (charter/contracts.py; ARCHITECTURE §7.2, review 10 §3.6, §3.9, §3.11, §6 #11 and #13): shares (an association's
own currency, backed by its treasury, transferable, paid out pro rata at wind-up), contract-owned rights and offices, agency
(authorize / act_for / revoke_authorization, logged to the grantor, hookable under law.v2), standing orders (a one-member contract
template plus an action) and associations holding another's shares."""
from __future__ import annotations

import re

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import contracts as CT
from charter import generator
from charter import lawapi as LA
from charter import lawlang as L
from charter import primitives as PR
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


def same_totals(t0, t1):
    for item in set(t0) | set(t1):
        if item in t0 and item in t1:
            assert t0[item] == pytest.approx(t1[item], abs=1e-6), item


SHARES = code('''
def on_enact():
    public["cur"] = create_currency("shares")

def issue(agent, to, qty):
    return mint("shares", qty, to)
''')


# ------------------------------------------------------------------ the power set
def test_own_currency_rights_and_offices_are_escrow_column_and_no_longer_refused():
    for n in ("create_currency", "mint", "burn", "create_right", "grant", "revoke", "define_action"):
        assert LA.LAWFNS[n].contract == "escrow" and n not in LA.CONTRACT_DENIED, n
    assert "set_convertible" in LA.CONTRACT_DENIED and "suspend" in LA.CONTRACT_DENIED
    CT.check_code(SHARES)                                               # founded without complaint
    with pytest.raises(L.LawError, match="may not call suspend"):
        CT.check_code(code("def on_enact():\n    suspend(members()[0], 'vote', 2)"))


def test_shares_are_namespaced_backed_by_the_treasury_and_valued_at_nav():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, SHARES)
    lid = rec(k, cid)["laws"][0]
    cur = k.w["laws"][lid]["public"]["cur"]
    assert cur == f"{cid}.shares" and k.w["currencies"][cur]["reserve"] == f"assoc:{cid}"
    api = k.api_for(lid)
    assert api["create_currency"]("shares") == cur                     # the same one again (idempotent)
    assert api["mint"]("shares", 4, a) is True and api["mint"](cur, 4, f"assoc:{cid}") is True
    assert api["mint"]("shares", 1, "estate:" + a) is False             # not an estate (refused, logged); "reserve" is its own
    k._add(f"assoc:{cid}", "stone", 8)
    assert k.price(cur) == pytest.approx(8 * 2 / 8)                     # net asset value per unit (treasury stock counts in supply)
    assert k.holdings_value(a) >= 4 * 2                                 # D-15: shares count in wealth at NAV
    with pytest.raises(L.LawError, match="not a currency of"):
        api["mint"]("coin", 1, a)
    with pytest.raises(L.LawError):
        api["mint"]("A9.shares", 1, a)                                  # another's currency: not its own
    # transferable like any good; the register follows
    t0 = AC.totals(k, held=True)
    A.act(k, a, "transfer", {"to": b, "item": cur, "qty": 1})
    assert CT.shareholders(k, cur) == {a: 3.0, b: 1.0}
    same_totals(t0, AC.totals(k, held=True))
    # burn only what it holds (its treasury), never an agent's holdings
    assert api["burn"]("shares", 2, "treasury") is True and k.bal(f"assoc:{cid}", cur) == 2
    assert api["burn"]("shares", 1, a) is False and k.bal(a, cur) == 3
    assert any(e["data"]["fn"] == "burn" for e in events(k, "contract_out_of_scope"))


def test_a_polity_law_cannot_mint_an_association_currency_through_the_contract_rules_and_is_unchanged():
    k = make()
    a = people(k)[0]
    lid = enact(k, code('def on_enact():\n    public["c"] = create_currency("coin")\n    mint("coin", 2, "reserve")', "Mint"))
    assert k.w["laws"][lid]["public"]["c"] == "coin" and k.w["currencies"]["coin"]["reserve"] == "reserve"
    assert k.bal("reserve", "coin") == 2 and CT.shareholders(k, "coin") == {}
    assert a


def test_wind_up_pays_shareholders_pro_rata_including_outsiders_and_other_associations():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, SHARES)
    other = found(k, c, code("def on_round_end(r):\n    return None"))
    lid = rec(k, cid)["laws"][0]
    api = k.api_for(lid)
    api["mint"]("shares", 2, a)
    api["mint"]("shares", 1, b)                                         # b is not a member: an outside investor
    api["mint"]("shares", 1, f"assoc:{other}")                          # review 10 #13: an association holds shares
    api["mint"]("shares", 5, "treasury")                                # treasury stock: no claim
    k._add(f"assoc:{cid}", "grain", 8)
    g = {x: k.bal(x, "grain") for x in (a, b)}
    t0 = AC.totals(k, held=True)
    A.act(k, a, "leave_contract", {"contract": cid})
    next_round(k)
    assert rec(k, cid)["status"] == "dissolved"
    assert k.bal(a, "grain") == pytest.approx(g[a] + 4) and k.bal(b, "grain") == pytest.approx(g[b] + 2)
    assert k.bal(f"assoc:{other}", "grain") == pytest.approx(2) and k.bal(f"assoc:{cid}", "grain") == pytest.approx(0)
    w = events(k, "contract_wound_up")[-1]["data"]
    assert w["shareholders"] == {a: {"grain": 4.0}, b: {"grain": 2.0}, f"assoc:{other}": {"grain": 2.0}}
    assert k.price(f"{cid}.shares") == 0.0                              # nothing left behind them
    same_totals(t0, AC.totals(k, held=True))


def test_company_template_issues_real_shares_and_pays_dividends_to_holders():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, a, template="company", params={"CUT": 0.5, "DIVIDEND_EVERY": 1, "PAYOUT": 1.0})
    A.act(k, b, "join_contract", {"contract": cid})
    lid = rec(k, cid)["laws"][0]
    law = k.w["laws"][lid]
    for who, y in ((a, 4.0), (b, 2.0)):
        CT.run_hook(k, law, "on_harvest", who, "c1", [0], y)
    sh = f"{cid}.shares"
    A.act(k, b, "transfer", {"to": c, "item": sh, "qty": 1})            # b sells its share to an outsider
    k._add(f"assoc:{cid}", "grain", 3)
    gc = k.bal(c, "grain")
    next_round(k)
    assert k.bal(c, "grain") == pytest.approx(gc + 1)                   # dividends follow the shares, members or not
    assert "create_currency(SHARES)" in CT.TEMPLATES["company"]["code"] and "public[\"shares\"]" not in CT.TEMPLATES["company"]["code"]


# ------------------------------------------------------------------ rights and offices
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


def test_contract_rights_go_to_members_only_and_offices_are_its_own():
    k = make(extra=["law_level=L1"])
    a, b, c = people(k)[:3]
    cid = found(k, a, OFFICE)
    lid = rec(k, cid)["laws"][0]
    assert k.w["laws"][lid]["public"]["act"] == f"{cid}.pay" and f"{cid}.treasurer" in k.w["rights"]
    api = k.api_for(lid)
    assert api["grant"](c, "treasurer") is False and not k.has(c, f"{cid}.treasurer")    # not a member
    A.act(k, b, "join_contract", {"contract": cid})
    assert api["grant"](b, "treasurer") is True and k.has(b, f"{cid}.treasurer")
    with pytest.raises(L.LawError):
        api["grant"](b, "vote")                                         # a kernel right is not its own ("A1.vote" does not exist)
    k._add(f"assoc:{cid}", "grain", 5)
    gc = k.bal(c, "grain")
    out = A.act(k, b, "invoke", {"action": f"{cid}.pay", "args": [c, 2]})   # the office: any law level (L1 here)
    assert "paid 2" in out and k.bal(c, "grain") == gc + 2
    with pytest.raises(A.ActionError):
        A.act(k, a, "invoke", {"action": f"{cid}.pay", "args": [c, 1]})    # a holds no treasurer right
    A.act(k, b, "leave_contract", {"contract": cid})
    next_round(k)
    assert not k.has(b, f"{cid}.treasurer")                             # leaving ends its offices
    A.act(k, a, "propose_contract_change", {"contract": cid, "code": code("def on_round_end(r):\n    return None"),
                                             "replaces": lid})
    assert f"{cid}.pay" not in k.w["actions"]                           # the retired law's office went with it


# ------------------------------------------------------------------ agency
def test_authorize_bounds_logs_and_revocation():
    k = make()
    a, b, c = people(k)[:3]
    give(k, a, "grain", 10)
    out = A.act(k, a, "authorize", {"agent": b, "action": "transfer", "item": "grain", "qty": 3, "to": [c]})
    gid = re.search(r"G\d+", out).group()
    g = k.w["contracts"]["agency"]["auth"][gid]
    assert g["grantor"] == a and g["grantee"] == b and g["qty"] == 3 and g["to"] == [c]
    assert events(k, "agency_granted")[-1]["vis"] == [a, b]
    t0 = AC.totals(k, held=True)
    gb, gc = k.bal(b, "grain"), k.bal(c, "grain")
    A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 2})
    assert k.bal(a, "grain") == 8 and k.bal(c, "grain") == gc + 2 and k.bal(b, "grain") == gb
    used = events(k, "agency_used")[-1]
    assert used["agent"] == b and used["vis"] == [a, b] and used["data"]["grantor"] == a and used["data"]["done"]
    assert any(e["type"] == "transfer" and e["agent"] == a and e["data"].get("by") == b for e in k.events)
    with pytest.raises(A.ActionError, match="per round"):
        A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 2})        # 1 left this round
    with pytest.raises(A.ActionError, match="allows only"):
        A.act(k, b, "act_for", {"auth": gid, "to": b, "qty": 1})        # embezzling to itself: not in the scope
    with pytest.raises(A.ActionError, match="no authorization"):
        A.act(k, c, "act_for", {"auth": gid, "to": c, "qty": 1})        # only the grantee acts
    next_round(k)
    A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 3})            # a new round, a new budget
    assert k.bal(a, "grain") == 5
    same_totals(t0, AC.totals(k, held=True))
    lines = CT.state_lines(k, a)
    assert any(gid in x and "You authorized" in x for x in lines)
    with pytest.raises(A.ActionError):
        A.act(k, b, "revoke_authorization", {"auth": gid})              # only the grantor revokes
    A.act(k, a, "revoke_authorization", {"auth": gid})
    with pytest.raises(A.ActionError, match="revoked"):
        A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 1})
    assert events(k, "agency_revoked")[-1]["vis"] == [a, b]


def test_vote_is_not_authorizable_and_agency_expires():
    k = make()
    a, b = people(k)[:2]
    with pytest.raises(A.ActionError, match="cannot be authorized"):
        A.act(k, a, "authorize", {"agent": b, "action": "vote", "item": "grain", "qty": 1})
    give(k, a, "grain", 10)
    gid = re.search(r"G\d+", A.act(k, a, "authorize", {"agent": b, "item": "grain", "qty": 1, "rounds": 1})).group()
    next_round(k)
    with pytest.raises(A.ActionError, match="expired"):
        A.act(k, b, "act_for", {"auth": gid, "to": b, "qty": 1})


def test_agency_to_a_contract_office_and_escrow_deposit():
    k = make()
    a, b, c = people(k)[:3]
    cid = found(k, c, OFFICE)
    A.act(k, b, "join_contract", {"contract": cid})
    A.act(k, a, "join_contract", {"contract": cid})
    k.api_for(rec(k, cid)["laws"][0])["grant"](b, "treasurer")
    give(k, a, "grain", 10)
    gid = re.search(r"G\d+", A.act(k, a, "authorize", {"office": f"{cid}.treasurer", "action": "deposit_escrow",
                                                         "item": "grain", "qty": 4})).group()
    A.act(k, b, "act_for", {"auth": gid, "contract": cid, "qty": 4})     # the office holder deposits a's grain in a's escrow
    assert CT.escrow_of(k, cid, a) == {"grain": 4.0} and k.bal(a, "grain") == 6
    with pytest.raises(A.ActionError):
        A.act(k, c, "act_for", {"auth": gid, "contract": cid, "qty": 1})  # c holds no treasurer right


def test_a_polity_law_may_regulate_agency_under_law_v2():
    k = make()
    a, b, c = people(k)[:3]
    enact(k, code('''
def before_authorize(p, chain):
    if p["scope"]["qty"] > 5:
        return {"block": True, "reason": "agency is capped at 5 per round"}
    return None

def after_act_for(p, chain):
    public.setdefault("seen", []).append([p["grantor"], p["grantee"], p["auth"]])
''', "Agency Act"))
    give(k, a, "grain", 10)
    with pytest.raises(A.ActionError, match="capped"):
        A.act(k, a, "authorize", {"agent": b, "item": "grain", "qty": 6})
    gid = re.search(r"G\d+", A.act(k, a, "authorize", {"agent": b, "item": "grain", "qty": 5})).group()
    A.act(k, b, "act_for", {"auth": gid, "to": c, "qty": 1})
    law = next(x for x in k.w["laws"].values() if x["title"] == "Agency Act")
    assert law["public"]["seen"] == [[a, b, gid]]
    assert not PR.get("deauthorize").blockable                         # revocation cannot be blocked


def test_laws_never_act_for_an_agent():
    """No law function causes an agency primitive; an authorization gives a law nothing."""
    for n in ("authorize", "deauthorize", "act_for"):
        assert PR.get(n).compel == () and PR.get(n).causes == ("agent",)
    assert not any(f.primitive in ("authorize", "deauthorize", "act_for") for f in LA.LAWFNS.values())


# ------------------------------------------------------------------ standing orders
def test_standing_order_pays_every_round_and_ends_after_times():
    k = make()
    a, b = people(k)[:2]
    give(k, a, "grain", 10)
    gb = k.bal(b, "grain")
    out = A.act(k, a, "standing_order", {"to": b, "item": "grain", "qty": 2, "times": 2})
    cid = re.search(r"A\d+", out).group()
    assert rec(k, cid)["template"] == "standing_order" and rec(k, cid)["admission"] == "closed"
    assert rec(k, cid)["allowances"][a] == {"grain": 2.0}
    t0 = AC.totals(k, held=True)
    next_round(k)
    assert k.bal(b, "grain") == gb + 2
    next_round(k)
    assert k.bal(b, "grain") == gb + 4 and k.bal(a, "grain") == 6
    next_round(k)
    assert rec(k, cid)["status"] == "dissolved" and k.bal(b, "grain") == gb + 4
    same_totals(t0, AC.totals(k, held=True))


def test_standing_order_keeps_a_floor_and_pays_a_contract_treasury():
    k = make()
    a, b = people(k)[:2]
    club = found(k, b, code("def on_round_end(r):\n    return None"))
    give(k, a, "grain", 3)
    A.act(k, a, "standing_order", {"to": f"assoc:{club}", "item": "grain", "qty": 1, "keep": 2})
    next_round(k)
    next_round(k)
    assert k.bal(a, "grain") == 2 and k.bal(f"assoc:{club}", "grain") == 1    # stops at the floor


def test_standing_order_is_refused_under_word():
    k = make(extra=["contracts.enforcement=word"])
    a, b = people(k)[:2]
    with pytest.raises(A.ActionError, match="no escrow"):
        A.act(k, a, "standing_order", {"to": b, "item": "grain", "qty": 1})


# ------------------------------------------------------------------ off: unknown
def test_off_the_new_actions_are_unknown():
    k = make(on=False)
    a, b = people(k)[:2]
    for name in ("authorize", "act_for", "revoke_authorization", "standing_order"):
        with pytest.raises(A.ActionError, match="unknown action"):
            A.act(k, a, name, {"agent": b})
    assert "agency" not in (k.w.get("contracts") or {})


def test_scripted_bots_use_standing_orders_and_agency():
    import json
    k = make(extra=["contracts.scripted=true"])
    for _ in range(4):
        for aid in people(k):
            for x in CT.scripted_actions(k, k.w["agents"][aid], 6):
                try:
                    A.act(k, aid, x["action"], json.loads(x["args_json"]))
                except A.ActionError:
                    pass
        next_round(k)
    assert any(r["template"] == "standing_order" for r in k.w["contracts"]["assoc"].values())
    assert events(k, "agency_granted") and events(k, "agency_used")
